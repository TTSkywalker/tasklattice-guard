from __future__ import annotations

import asyncio
import time

import pytest

from app.control_plane.nemo_compiler import NeMoConfigCompiler
from app.nemo.action_registry import runtime_action_registry
from app.nemo.actions.contracts import ActionRequest, ActionResult
from app.nemo.actions.deterministic import FastPassEngine
from app.nemo.runtime import NeMoGuardrailsEngine
from app.nemo.registry import NeMoRailsRegistry
from app.runtime.contracts import (
    EngineRequest,
    GuardrailPlanModule,
    GuardrailPlanSnapshot,
    GuardrailPlanStep,
)
from tests.nemo_helpers import StaticNeMoStore


def _plan(risk: str = "secrets", stage: str = "deterministic"):
    step = GuardrailPlanStep(
        id=f"{risk}:{stage}",
        risk=risk,
        stage=stage,
        phases=("input",),
        on_unsafe="reject",
    )
    return GuardrailPlanSnapshot(
        guardrail_id="native-action-contract",
        guardrail_version=7,
        compiler_version="test",
        safety_level="balanced",
        output_delivery="window_buffered",
        steps=(step,),
        modules=(
            GuardrailPlanModule(
                id="native-actions",
                module="data_protection",
                phase="input",
                step_ids=(step.id,),
                timeout_ms=100,
            ),
        ),
    )


@pytest.mark.asyncio
async def test_direct_action_has_fixed_request_and_result_schema():
    plan = _plan()
    config = NeMoConfigCompiler().compile(plan)
    binding = config.action_bindings[0]
    registry = runtime_action_registry(FastPassEngine())
    provider = registry.get(binding.action_name or "", binding.action_version or "")

    result = await provider.execute(
        ActionRequest(
            content="api_key=abcdefghijklmnop",
            rail_type="input",
            guardrail_id=plan.guardrail_id,
            guardrail_version=plan.guardrail_version,
            control_id=None,
            control_version=None,
            trusted_context=(),
            content_blocks=(),
            deadline=time.monotonic() + 1,
            parameters=(),
            risk="secrets",
            proposed_action="reject",
            plan=plan,
            binding=binding,
        )
    )

    assert isinstance(result, ActionResult)
    assert result.verdict == "unsafe"
    assert result.proposed_action == "reject"
    assert result.findings[0].risk == "secrets"


class _CancellableEvaluator:
    name = "Cancellable"
    stage = "deterministic"
    supported_risks = frozenset({"secrets"})
    supported_phases = frozenset({"input"})

    async def evaluate(self, request, steps):
        del request, steps
        await asyncio.sleep(10)


@pytest.mark.asyncio
async def test_action_execution_propagates_cancellation():
    plan = _plan()
    config = NeMoConfigCompiler().compile(plan)
    engine = NeMoGuardrailsEngine(
        NeMoRailsRegistry(
            StaticNeMoStore((plan,), (config,)),
            runtime_action_registry(_CancellableEvaluator()),
        )
    )
    task = asyncio.create_task(
        engine.evaluate(EngineRequest("input", "safe", plan))
    )
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await engine.shutdown()


class _SensitiveFailureEvaluator:
    name = "Sensitive failure"
    stage = "deterministic"
    supported_risks = frozenset({"secrets"})
    supported_phases = frozenset({"input"})

    async def evaluate(self, request, steps):
        del request, steps
        raise RuntimeError(
            "credential=super-secret prompt=private provider_response=private"
        )


@pytest.mark.asyncio
async def test_action_errors_are_privacy_safe_and_fail_closed():
    plan = _plan()
    config = NeMoConfigCompiler().compile(plan)
    engine = NeMoGuardrailsEngine(
        NeMoRailsRegistry(
            StaticNeMoStore((plan,), (config,)),
            runtime_action_registry(_SensitiveFailureEvaluator()),
        )
    )

    decision = await engine.evaluate(EngineRequest("input", "sensitive content", plan))

    serialized = " ".join(item.detail for item in decision.trace)
    assert decision.decision == "block"
    assert decision.usage is not None and decision.usage.fail_closed is True
    assert "super-secret" not in serialized
    assert "provider_response" not in serialized
    assert "RuntimeError" in serialized
    failed_action = next(step for step in decision.trace if step.kind == "action")
    assert failed_action.outcome == "error"
    assert failed_action.timed_out is False
    assert failed_action.action_name == "TaskLatticeSecretsAction"
    assert failed_action.action_version == "1.0.0"
    assert failed_action.engine == "llmrails"
    assert failed_action.config_checksum
    await engine.shutdown()


def test_current_compiler_uses_direct_actions_without_stage_protocol():
    plan = _plan("prompt_injection", "fast_semantic")
    config = NeMoConfigCompiler().compile(plan)
    assert "TaskLatticePromptSecurityFastAction" in config.colang_content
    assert all(
        item.action_name and item.action_version for item in config.action_bindings
    )

    import app.runtime.contracts as contracts

    assert not hasattr(contracts, "GuardrailStage")
    assert not hasattr(contracts, "EvaluationStage")
