from __future__ import annotations

from app.engine.contracts import (
    ContentPatch,
    DecisionFragment,
    EngineRequest,
    GuardrailPlanModule,
    GuardrailPlanSnapshot,
    ModuleAssessment,
    RuntimeCoverage,
)
from app.engine.resolver import DeterministicResolver


def _plan(*modules: GuardrailPlanModule) -> GuardrailPlanSnapshot:
    return GuardrailPlanSnapshot(
        guardrail_id="guardrail-test",
        guardrail_version=4,
        compiler_version="guardrail-plan-v3",
        safety_level="balanced",
        output_delivery="window_buffered",
        steps=(),
        modules=modules,
    )


def _module(
    module_id: str,
    module: str,
    fragment: DecisionFragment,
    *,
    status: str | None = None,
) -> ModuleAssessment:
    return ModuleAssessment(
        module_id=module_id,
        module=module,
        status=status or fragment.status,
        fragments=(fragment,),
        coverage=RuntimeCoverage(status="complete"),
    )


def test_resolver_is_independent_of_assessment_completion_order():
    data_plan = GuardrailPlanModule(
        id="data:input",
        module="data_protection",
        phase="input",
        step_ids=(),
    )
    business_plan = GuardrailPlanModule(
        id="business:input",
        module="business_assurance",
        phase="input",
        step_ids=(),
    )
    request = EngineRequest("input", "email a@example.com", _plan(data_plan, business_plan))
    data = _module(
        "data:input",
        "data_protection",
        DecisionFragment(
            id="pii",
            module_id="data:input",
            module="data_protection",
            status="intervene",
            action="redact",
            patches=(ContentPatch(6, 19, "[EMAIL]"),),
            reason="PII detected.",
        ),
    )
    business = _module(
        "business:input",
        "business_assurance",
        DecisionFragment(
            id="topic",
            module_id="business:input",
            module="business_assurance",
            status="pass",
        ),
    )
    resolver = DeterministicResolver()

    first = resolver.resolve(request, (data, business))
    second = resolver.resolve(request, (business, data))

    assert first == second
    assert first.decision == "transform"
    assert first.texts == ("email [EMAIL]",)


def test_resolver_preserves_multiple_interventions():
    data_plan = GuardrailPlanModule(
        id="data:input",
        module="data_protection",
        phase="input",
        step_ids=(),
    )
    business_plan = GuardrailPlanModule(
        id="business:input",
        module="business_assurance",
        phase="input",
        step_ids=(),
    )
    request = EngineRequest("input", "secret", _plan(data_plan, business_plan))
    data = _module(
        "data:input",
        "data_protection",
        DecisionFragment(
            id="mask",
            module_id="data:input",
            module="data_protection",
            status="intervene",
            action="redact",
            patches=(ContentPatch(0, 6, "[SECRET]"),),
        ),
    )
    business = _module(
        "business:input",
        "business_assurance",
        DecisionFragment(
            id="rewrite",
            module_id="business:input",
            module="business_assurance",
            status="intervene",
            action="rewrite",
        ),
    )

    result = DeterministicResolver().resolve(request, (business, data))

    assert result.decision == "transform"
    assert result.action == "rewrite"
    assert {item.kind for item in result.interventions} == {"redact", "rewrite"}


def test_resolver_fails_closed_on_conflicting_patches():
    data_plan = GuardrailPlanModule(
        id="data:input",
        module="data_protection",
        phase="input",
        step_ids=(),
    )
    request = EngineRequest("input", "abcdef", _plan(data_plan))
    assessment = ModuleAssessment(
        module_id="data:input",
        module="data_protection",
        status="intervene",
        fragments=(
            DecisionFragment(
                id="one",
                module_id="data:input",
                module="data_protection",
                status="intervene",
                action="redact",
                patches=(ContentPatch(0, 3, "A"),),
            ),
            DecisionFragment(
                id="two",
                module_id="data:input",
                module="data_protection",
                status="intervene",
                action="redact",
                patches=(ContentPatch(2, 5, "B"),),
            ),
        ),
        coverage=RuntimeCoverage(status="complete"),
    )

    result = DeterministicResolver().resolve(request, (assessment,))

    assert result.decision == "block"
    assert result.action == "reject"
    assert "conflicting" in (result.reason or "")


def test_detect_mode_records_but_does_not_apply_interventions():
    module_plan = GuardrailPlanModule(
        id="interaction:input",
        module="interaction_safety",
        phase="input",
        step_ids=(),
    )
    request = EngineRequest(
        "input",
        "attack",
        _plan(module_plan),
        mode="detect",
    )
    assessment = _module(
        "interaction:input",
        "interaction_safety",
        DecisionFragment(
            id="attack",
            module_id="interaction:input",
            module="interaction_safety",
            status="intervene",
            action="reject",
        ),
    )

    result = DeterministicResolver().resolve(request, (assessment,))

    assert result.decision == "allow"
    assert result.action == "pass"
    assert result.interventions[0].kind == "reject"


def test_required_module_error_uses_its_failure_mode():
    closed_plan = GuardrailPlanModule(
        id="closed:input",
        module="interaction_safety",
        phase="input",
        step_ids=(),
        failure_mode="fail_closed",
    )
    open_plan = GuardrailPlanModule(
        id="open:input",
        module="business_assurance",
        phase="input",
        step_ids=(),
        failure_mode="fail_open",
    )
    request = EngineRequest("input", "request", _plan(closed_plan, open_plan))
    closed = ModuleAssessment(
        module_id=closed_plan.id,
        module=closed_plan.module,
        status="error",
        fragments=(),
        coverage=RuntimeCoverage(status="none"),
    )
    opened = ModuleAssessment(
        module_id=open_plan.id,
        module=open_plan.module,
        status="error",
        fragments=(),
        coverage=RuntimeCoverage(status="none"),
    )

    result = DeterministicResolver().resolve(request, (opened, closed))

    assert result.decision == "block"
    assert tuple(item.module_id for item in result.interventions) == (closed_plan.id,)
