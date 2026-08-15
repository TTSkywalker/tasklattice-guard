from __future__ import annotations

import asyncio
import re
import time

import pytest

from app.control_plane.nemo_compiler import NeMoConfigCompiler
from app.nemo.action_registry import (
    BUILTIN_ACTION_CATALOG,
    action_name_for,
    action_providers,
)
from app.nemo.actions import (
    ContentFilterActionProvider,
    IndirectPromptInjectionActionProvider,
    PiiActionProvider,
    PromptSecurityActionProvider,
    PromptLeakageActionProvider,
    SecretsActionProvider,
    TopicRulesActionProvider,
    local_action_providers,
)
from app.nemo.actions.contracts import ActionRequest, ActionResult
from app.nemo.actions.names import (
    ACTION_CONTENT_FILTER,
    ACTION_INDIRECT_PROMPT_INJECTION,
    ACTION_PII,
    ACTION_PROMPT_SECURITY,
    ACTION_PROMPT_LEAKAGE,
    ACTION_SECRETS,
    ACTION_TOPIC_RULES,
)
from app.nemo.runtime import NeMoRuntime
from app.nemo.registry import NeMoRuntimeRegistry
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


def test_owned_action_ids_use_one_compact_structured_namespace():
    names = {item.name for item in BUILTIN_ACTION_CATALOG.definitions()}

    assert names
    assert all(re.fullmatch(r"Guard[A-Z][A-Za-z0-9]*Action", name) for name in names)
    assert max(map(len, names)) <= 30
    assert action_name_for("custom compliance-risk", "deterministic") == (
        "GuardCustomComplianceRiskAction"
    )


def test_local_deterministic_actions_use_explicit_providers_without_an_engine_adapter():
    registry = action_providers(*local_action_providers())

    assert isinstance(
        registry[(ACTION_CONTENT_FILTER, "1.0.0")],
        ContentFilterActionProvider,
    )
    assert isinstance(registry[(ACTION_SECRETS, "1.0.0")], SecretsActionProvider)
    assert isinstance(registry[(ACTION_PII, "1.0.0")], PiiActionProvider)
    assert isinstance(
        registry[(ACTION_TOPIC_RULES, "1.0.0")],
        TopicRulesActionProvider,
    )
    assert isinstance(
        registry[(ACTION_PROMPT_SECURITY, "1.0.0")],
        PromptSecurityActionProvider,
    )
    assert isinstance(
        registry[(ACTION_INDIRECT_PROMPT_INJECTION, "1.0.0")],
        IndirectPromptInjectionActionProvider,
    )
    assert isinstance(
        registry[(ACTION_PROMPT_LEAKAGE, "1.0.0")],
        PromptLeakageActionProvider,
    )


@pytest.mark.asyncio
async def test_direct_action_has_fixed_request_and_result_schema():
    plan = _plan()
    config = NeMoConfigCompiler().compile(plan)
    binding = config.action_bindings[0]
    registry = action_providers(SecretsActionProvider())
    provider = registry[(binding.action_name or "", binding.action_version or "")]

    result = await provider.execute(
        ActionRequest(
            content="api_key=abcdefghijklmnop",
            rail_type="input",
            guardrail_id=plan.guardrail_id,
            guardrail_version=plan.guardrail_version,
            policy_id=None,
            policy_version=None,
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


class _CancellableProvider:
    name = ACTION_SECRETS
    version = "1.0.0"
    risks = frozenset({"secrets"})
    rails = frozenset({"input"})

    async def execute(self, request):
        del request
        await asyncio.sleep(10)


@pytest.mark.asyncio
async def test_action_execution_propagates_cancellation():
    plan = _plan()
    config = NeMoConfigCompiler().compile(plan)
    engine = NeMoRuntime(
        NeMoRuntimeRegistry(
            StaticNeMoStore((plan,), (config,)),
            action_providers(_CancellableProvider()),
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


class _SensitiveFailureProvider:
    name = ACTION_SECRETS
    version = "1.0.0"
    risks = frozenset({"secrets"})
    rails = frozenset({"input"})

    async def execute(self, request):
        del request
        raise RuntimeError(
            "credential=super-secret prompt=private provider_response=private"
        )


@pytest.mark.asyncio
async def test_action_errors_are_privacy_safe_and_fail_closed():
    plan = _plan()
    config = NeMoConfigCompiler().compile(plan)
    engine = NeMoRuntime(
        NeMoRuntimeRegistry(
            StaticNeMoStore((plan,), (config,)),
            action_providers(_SensitiveFailureProvider()),
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
    assert failed_action.action_name == "GuardSecretsAction"
    assert failed_action.action_version == "1.0.0"
    assert failed_action.engine == "llmrails"
    assert failed_action.config_checksum
    await engine.shutdown()


def test_current_compiler_uses_direct_actions_without_stage_protocol():
    plan = _plan("prompt_injection", "fast_semantic")
    config = NeMoConfigCompiler().compile(plan)
    assert "GuardPromptSecurityAction" in config.colang_content
    assert all(
        item.action_name and item.action_version for item in config.action_bindings
    )

    import app.runtime.contracts as contracts

    assert not hasattr(contracts, "GuardrailStage")
    assert not hasattr(contracts, "EvaluationStage")
