from __future__ import annotations

import pytest

from app.nemo.action_registry import action_name_for
from app.nemo.actions.contracts import ActionResult
from app.runtime.contracts import (
    EngineRequest,
    GuardrailPlanModule,
    GuardrailPlanSnapshot,
    GuardrailPlanStep,
    RiskFinding,
)
from tests.nemo_helpers import nemo_engine


class ResultAction:
    version = "1.0.0"
    rails = frozenset({"input"})

    def __init__(self, risk: str, result: ActionResult) -> None:
        self.name = action_name_for(risk, "deterministic")
        self.risks = frozenset({risk})
        self._result = result

    async def execute(self, request):
        del request
        return self._result


def _finding(risk: str, action: str, *, replacement: str | None = None):
    return RiskFinding(
        risk=risk,
        verdict="unsafe",
        confidence=0.99,
        evidence=f"{risk} triggered.",
        recommended_action=action,
        replacement=replacement,
    )


def _plan(
    *items: tuple[str, str, str],
    failure_modes: dict[str, str] | None = None,
) -> GuardrailPlanSnapshot:
    steps = tuple(
        GuardrailPlanStep(
            id=f"{risk}:deterministic",
            risk=risk,
            stage="deterministic",
            phases=("input",),
            on_unsafe=action,
        )
        for risk, action, _ in items
    )
    modules = tuple(
        GuardrailPlanModule(
            id=f"module:{risk}",
            module=module,
            phase="input",
            step_ids=(f"{risk}:deterministic",),
            failure_mode=(failure_modes or {}).get(risk, "fail_closed"),
        )
        for risk, _, module in items
    )
    return GuardrailPlanSnapshot(
        guardrail_id="guardrail-resolution",
        guardrail_version=1,
        compiler_version="test-plan-v1",
        safety_level="balanced",
        output_delivery="window_buffered",
        steps=steps,
        modules=modules,
    )


@pytest.mark.asyncio
async def test_nemo_resolve_action_preserves_multiple_interventions():
    plan = _plan(
        ("private_data", "redact", "data_protection"),
        ("business_policy", "rewrite", "business_assurance"),
    )
    engine = nemo_engine(
        plan,
        ResultAction(
            "private_data",
            ActionResult(
                "unsafe",
                "[SECRET]",
                (_finding("private_data", "redact"),),
            ),
        ),
        ResultAction(
            "business_policy",
            ActionResult(
                "unsafe",
                "secret",
                (_finding("business_policy", "rewrite", replacement="safe rewrite"),),
            ),
        ),
    )

    result = await engine.evaluate(EngineRequest("input", "secret", plan))

    assert result.decision == "transform"
    assert result.action == "rewrite"
    assert result.texts == ("safe rewrite",)
    assert {item.kind for item in result.interventions} == {"redact", "rewrite"}
    await engine.shutdown()


@pytest.mark.asyncio
async def test_nemo_resolve_action_fails_closed_on_conflicting_patches():
    plan = _plan(
        ("first_data", "redact", "data_protection"),
        ("second_data", "redact", "data_protection"),
    )
    engine = nemo_engine(
        plan,
        ResultAction(
            "first_data",
            ActionResult(
                "unsafe",
                "Adef",
                (_finding("first_data", "redact"),),
            ),
        ),
        ResultAction(
            "second_data",
            ActionResult(
                "unsafe",
                "abBf",
                (_finding("second_data", "redact"),),
            ),
        ),
    )

    result = await engine.evaluate(EngineRequest("input", "abcdef", plan))

    assert result.decision == "block"
    assert result.action == "reject"
    assert "conflicted" in (result.reason or "")
    await engine.shutdown()


@pytest.mark.asyncio
async def test_nemo_detect_mode_records_without_enforcing():
    plan = _plan(("attack", "reject", "interaction_safety"))
    engine = nemo_engine(
        plan,
        ResultAction(
            "attack",
            ActionResult(
                "unsafe",
                "attack",
                (_finding("attack", "reject"),),
            ),
        ),
    )

    result = await engine.evaluate(
        EngineRequest("input", "attack", plan, mode="detect")
    )

    assert result.decision == "allow"
    assert result.action == "pass"
    assert result.interventions[0].kind == "reject"
    await engine.shutdown()


@pytest.mark.asyncio
async def test_colang1_uses_the_strongest_finding_and_applies_fallback_content():
    block_plan = _plan(("mixed_policy", "redact", "interaction_safety"))
    block_engine = nemo_engine(
        block_plan,
        ResultAction(
            "mixed_policy",
            ActionResult(
                "unsafe",
                "[MASKED] and blocked",
                (
                    _finding("mixed_policy", "redact"),
                    _finding("mixed_policy", "reject"),
                ),
            ),
        ),
    )

    blocked = await block_engine.evaluate(
        EngineRequest("input", "masked and blocked", block_plan)
    )

    assert blocked.decision == "block"
    assert blocked.action == "reject"
    await block_engine.shutdown()

    clarify_plan = _plan(("uncertain_policy", "reject", "interaction_safety"))
    clarify_engine = nemo_engine(
        clarify_plan,
        ResultAction(
            "uncertain_policy",
            ActionResult("uncertain", "ambiguous", reason="More context is required."),
        ),
    )

    clarified = await clarify_engine.evaluate(
        EngineRequest("input", "ambiguous", clarify_plan)
    )

    assert clarified.decision == "transform"
    assert clarified.action == "clarify"
    assert clarified.texts == (
        "More information is required before the request can be evaluated safely.",
    )
    await clarify_engine.shutdown()


@pytest.mark.asyncio
async def test_required_action_errors_honor_module_failure_mode():
    open_plan = _plan(
        ("optional_policy", "reject", "business_assurance"),
        failure_modes={"optional_policy": "fail_open"},
    )
    stage = ResultAction(
        "optional_policy",
        ActionResult("error", "request", reason="Provider unavailable."),
    )
    open_engine = nemo_engine(open_plan, stage)
    allowed = await open_engine.evaluate(EngineRequest("input", "request", open_plan))
    assert allowed.decision == "allow"
    assert allowed.usage is not None
    assert allowed.usage.fail_closed is False
    assert allowed.usage.action_invocations == 1
    assert all(
        step.route != "fail_closed"
        for step in allowed.trace
        if step.kind in {"rail", "action"}
    )
    await open_engine.shutdown()

    closed_plan = _plan(("required_policy", "reject", "business_assurance"))
    closed_engine = nemo_engine(
        closed_plan,
        ResultAction(
            "required_policy",
            ActionResult("error", "request", reason="Provider unavailable."),
        ),
    )
    blocked = await closed_engine.evaluate(
        EngineRequest("input", "request", closed_plan)
    )
    assert blocked.decision == "block"
    assert blocked.action == "reject"
    await closed_engine.shutdown()
