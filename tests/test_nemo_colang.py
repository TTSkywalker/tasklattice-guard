from __future__ import annotations

import asyncio

import pytest

from app.runtime.contracts import (
    EngineRequest,
    GuardrailPlanModule,
    GuardrailPlanSnapshot,
    GuardrailPlanStep,
    RiskFinding,
    StageResult,
)
from app.control_plane.domain import PlanCompilationError
from tests.nemo_helpers import nemo_engine


def _plan(
    steps: tuple[GuardrailPlanStep, ...],
    modules: tuple[GuardrailPlanModule, ...],
) -> GuardrailPlanSnapshot:
    return GuardrailPlanSnapshot(
        guardrail_id="guardrail-dag",
        guardrail_version=2,
        compiler_version="guardrail-plan-v4",
        safety_level="balanced",
        output_delivery="window_buffered",
        steps=steps,
        modules=modules,
    )


class ConcurrentStage:
    stage = "fast_semantic"
    name = "Concurrent"
    supported_phases = frozenset({"input"})

    def __init__(self) -> None:
        self.entered = 0
        self.all_entered = asyncio.Event()
        self.release = asyncio.Event()

    async def evaluate(self, request, steps):
        self.entered += 1
        if self.entered == 2:
            self.all_entered.set()
        await self.release.wait()
        return StageResult("safe", request.text)


@pytest.mark.asyncio
async def test_independent_modules_execute_concurrently():
    first = GuardrailPlanStep(
        id="prompt:fast",
        risk="prompt_injection",
        stage="fast_semantic",
        phases=("input",),
        on_unsafe="reject",
    )
    second = GuardrailPlanStep(
        id="content:fast",
        risk="company_policy",
        stage="fast_semantic",
        phases=("input",),
        on_unsafe="reject",
    )
    modules = (
        GuardrailPlanModule(
            id="one",
            module="interaction_safety",
            phase="input",
            step_ids=(first.id,),
        ),
        GuardrailPlanModule(
            id="two",
            module="business_assurance",
            phase="input",
            step_ids=(second.id,),
        ),
    )
    stage = ConcurrentStage()
    selected_plan = _plan((first, second), modules)
    engine = nemo_engine(selected_plan, stage)
    runtime_check = asyncio.create_task(
        engine.evaluate(EngineRequest("input", "request", selected_plan))
    )

    await asyncio.wait_for(stage.all_entered.wait(), timeout=1)
    stage.release.set()
    result = await asyncio.wait_for(runtime_check, timeout=1)

    assert result.decision == "allow"
    assert tuple(item.module_id for item in result.assessments) == ("one", "two")
    await engine.shutdown()


class DeterministicMask:
    stage = "deterministic"
    name = "Mask"
    supported_phases = frozenset({"input"})

    def __init__(self) -> None:
        self.view = None

    async def evaluate(self, request, steps):
        self.view = request.content_view
        return StageResult(
            "unsafe",
            request.text.replace("a@example.com", "[EMAIL]"),
            (
                RiskFinding(
                    risk="pii",
                    verdict="unsafe",
                    confidence=0.99,
                    evidence="PII detected.",
                    recommended_action="redact",
                ),
            ),
        )


class BusinessJudge:
    stage = "deep_judge"
    name = "Business"
    supported_phases = frozenset({"input"})

    def __init__(self) -> None:
        self.received = ""
        self.view = None

    async def evaluate(self, request, steps):
        self.received = request.text
        self.view = request.content_view
        return StageResult("safe", request.text)


@pytest.mark.asyncio
async def test_dependent_module_can_read_masked_immutable_view():
    pii = GuardrailPlanStep(
        id="pii:local",
        risk="pii",
        stage="deterministic",
        phases=("input",),
        on_unsafe="redact",
    )
    policy = GuardrailPlanStep(
        id="policy:deep",
        risk="company_policy",
        stage="deep_judge",
        phases=("input",),
        on_unsafe="reject",
        escalation="always",
    )
    modules = (
        GuardrailPlanModule(
            id="data",
            module="data_protection",
            phase="input",
            step_ids=(pii.id,),
        ),
        GuardrailPlanModule(
            id="business",
            module="business_assurance",
            phase="input",
            step_ids=(policy.id,),
            depends_on=("data",),
            input_view="masked",
        ),
    )
    business = BusinessJudge()
    mask = DeterministicMask()
    selected_plan = _plan((pii, policy), modules)
    engine = nemo_engine(selected_plan, mask, business)

    result = await engine.evaluate(
        EngineRequest(
            "input",
            "contact a@example.com",
            selected_plan,
        )
    )

    assert business.received == "contact [EMAIL]"
    assert business.view.kind == "masked"
    assert business.view.active_block.text == "contact [EMAIL]"
    assert business.view.source_digest == mask.view.source_digest
    assert result.decision == "transform"
    assert result.texts == ("contact [EMAIL]",)
    await engine.shutdown()


class NeverReturns:
    stage = "fast_semantic"
    name = "Never returns"
    supported_phases = frozenset({"input"})

    async def evaluate(self, request, steps):
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


@pytest.mark.asyncio
async def test_module_timeout_is_converted_to_fail_closed_assessment():
    step = GuardrailPlanStep(
        id="attack:fast",
        risk="prompt_injection",
        stage="fast_semantic",
        phases=("input",),
        on_unsafe="reject",
    )
    module = GuardrailPlanModule(
        id="interaction",
        module="interaction_safety",
        phase="input",
        step_ids=(step.id,),
        timeout_ms=10,
        failure_mode="fail_closed",
    )

    selected_plan = _plan((step,), (module,))
    engine = nemo_engine(selected_plan, NeverReturns())
    result = await engine.evaluate(EngineRequest("input", "request", selected_plan))

    assert result.decision == "block"
    assert result.assessments[0].status == "error"
    assert any("timeout" in item.detail for item in result.assessments[0].trace)
    await engine.shutdown()


@pytest.mark.asyncio
async def test_flat_plan_without_modules_is_rejected_before_runtime():
    step = GuardrailPlanStep(
        id="prompt:fast",
        risk="prompt_injection",
        stage="fast_semantic",
        phases=("input",),
        on_unsafe="reject",
    )
    flat_plan = _plan((step,), ())

    class SafeStage:
        stage = "fast_semantic"
        name = "Safe"
        supported_phases = frozenset({"input"})

        async def evaluate(self, request, steps):
            return StageResult("safe", request.text)

    with pytest.raises(PlanCompilationError, match="module"):
        nemo_engine(flat_plan, SafeStage())
