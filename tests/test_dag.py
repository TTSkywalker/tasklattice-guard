from __future__ import annotations

import asyncio

import pytest

from app.engine.contracts import (
    EngineRequest,
    GuardrailPlanModule,
    GuardrailPlanSnapshot,
    GuardrailPlanStep,
    RiskFinding,
    StageResult,
)
from app.engine.dag import ModularGuardrailsEngine


def _plan(
    steps: tuple[GuardrailPlanStep, ...],
    modules: tuple[GuardrailPlanModule, ...],
) -> GuardrailPlanSnapshot:
    return GuardrailPlanSnapshot(
        guardrail_id="guardrail-dag",
        guardrail_version=2,
        compiler_version="guardrail-plan-v3",
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
        risk="content_safety",
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
    engine = ModularGuardrailsEngine((stage,))
    evaluation = asyncio.create_task(
        engine.evaluate(EngineRequest("input", "request", _plan((first, second), modules)))
    )

    await asyncio.wait_for(stage.all_entered.wait(), timeout=1)
    stage.release.set()
    result = await asyncio.wait_for(evaluation, timeout=1)

    assert result.decision == "allow"
    assert tuple(item.module_id for item in result.assessments) == ("one", "two")


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
    engine = ModularGuardrailsEngine((mask, business))

    result = await engine.evaluate(
        EngineRequest(
            "input",
            "contact a@example.com",
            _plan((pii, policy), modules),
        )
    )

    assert business.received == "contact [EMAIL]"
    assert business.view.kind == "masked"
    assert business.view.active_block.text == "contact [EMAIL]"
    assert business.view.source_digest == mask.view.source_digest
    assert result.decision == "transform"
    assert result.texts == ("contact [EMAIL]",)


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

    result = await ModularGuardrailsEngine((NeverReturns(),)).evaluate(
        EngineRequest("input", "request", _plan((step,), (module,)))
    )

    assert result.decision == "block"
    assert result.assessments[0].status == "error"
    assert "timeout" in result.assessments[0].trace[0].detail


@pytest.mark.asyncio
async def test_flat_plan_without_modules_fails_closed():
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

    result = await ModularGuardrailsEngine((SafeStage(),)).evaluate(
        EngineRequest("input", "request", flat_plan)
    )

    assert result.decision == "block"
    assert result.assessments[0].status == "error"
    assert "no control modules" in result.reason.lower()
