from __future__ import annotations

import pytest

from app.engine.contracts import (
    EngineRequest,
    GuardrailPlanSnapshot,
    GuardrailPlanStep,
    RiskFinding,
    StageResult,
)
from app.engine.pipeline import ProgressiveGuardrailsEngine


def plan(*steps: GuardrailPlanStep) -> GuardrailPlanSnapshot:
    return GuardrailPlanSnapshot(
        profile_id="profile-test",
        profile_revision=3,
        compiler_version="test",
        safety_level="balanced",
        output_delivery="window_buffered",
        steps=steps,
    )


class Stage:
    supported_phases = frozenset({"input", "output"})

    def __init__(self, stage: str, result: StageResult):
        self.stage = stage
        self.name = stage
        self.result = result
        self.calls = 0

    async def evaluate(self, request, steps):
        self.calls += 1
        return self.result


def finding(verdict="uncertain"):
    return RiskFinding(
        risk="company_policy",
        verdict=verdict,
        confidence=0.61 if verdict == "uncertain" else 0.95,
        evidence="Boundary requires contextual policy judgment.",
        recommended_action="reject",
    )


FAST_STEP = GuardrailPlanStep(
    id="company:fast",
    risk="company_policy",
    stage="fast_semantic",
    phases=("input",),
    on_unsafe="reject",
    escalation="on_uncertain",
)
DEEP_STEP = GuardrailPlanStep(
    id="company:deep",
    risk="company_policy",
    stage="deep_judge",
    phases=("input",),
    on_unsafe="reject",
    escalation="on_uncertain",
)


@pytest.mark.asyncio
async def test_uncertain_fast_verdict_escalates_to_deep_judge():
    fast = Stage("fast_semantic", StageResult("uncertain", "request", (finding(),)))
    deep = Stage("deep_judge", StageResult("safe", "request"))
    engine = ProgressiveGuardrailsEngine((fast, deep))

    result = await engine.evaluate(
        EngineRequest("input", "request", plan(FAST_STEP, DEEP_STEP))
    )

    assert result.decision == "allow"
    assert fast.calls == deep.calls == 1
    assert next(step for step in result.trace if step.stage == "fast_semantic").route == "escalate"


@pytest.mark.asyncio
async def test_decisive_fast_verdict_skips_deep_judge():
    fast = Stage("fast_semantic", StageResult("safe", "request"))
    deep = Stage("deep_judge", StageResult("safe", "request"))
    engine = ProgressiveGuardrailsEngine((fast, deep))

    result = await engine.evaluate(
        EngineRequest("input", "request", plan(FAST_STEP, DEEP_STEP))
    )

    assert result.decision == "allow"
    assert fast.calls == 1
    assert deep.calls == 0
    assert next(step for step in result.trace if step.stage == "deep_judge").status == "skipped"


@pytest.mark.asyncio
async def test_unsafe_fast_verdict_enforces_and_stops():
    fast = Stage("fast_semantic", StageResult("unsafe", "request", (finding("unsafe"),)))
    deep = Stage("deep_judge", StageResult("safe", "request"))
    engine = ProgressiveGuardrailsEngine((fast, deep))

    result = await engine.evaluate(
        EngineRequest("input", "request", plan(FAST_STEP, DEEP_STEP))
    )

    assert result.decision == "block"
    assert result.action == "reject"
    assert deep.calls == 0


@pytest.mark.asyncio
async def test_mandatory_deep_step_runs_after_safe_fast_verdict():
    fast_step = GuardrailPlanStep(
        id="topic:fast",
        risk="topic_control",
        stage="fast_semantic",
        phases=("input",),
        on_unsafe="redirect",
        escalation="always",
    )
    deep_step = GuardrailPlanStep(
        id="topic:deep",
        risk="topic_control",
        stage="deep_judge",
        phases=("input",),
        on_unsafe="redirect",
        escalation="always",
    )
    fast = Stage("fast_semantic", StageResult("safe", "request"))
    deep = Stage("deep_judge", StageResult("safe", "request"))
    engine = ProgressiveGuardrailsEngine((fast, deep))

    result = await engine.evaluate(
        EngineRequest("input", "request", plan(fast_step, deep_step))
    )

    assert result.decision == "allow"
    assert fast.calls == deep.calls == 1
