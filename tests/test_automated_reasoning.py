from __future__ import annotations

import json

import pytest
import httpx

from app.control_plane.compiler import GuardrailCompiler
from app.control_plane.domain import (
    AutomatedReasoningPolicyBinding,
    Guardrail,
    GuardrailPolicyBinding,
    PlanCompilationError,
    ResolvedPolicyCapability,
)
from app.nemo.actions.automated_reasoning import (
    ReasoningActionProvider,
    HTTPAutomatedReasoningProvider,
    aggregate_reasoning_result,
    parse_reasoning_findings,
)
from app.runtime.content_views import content_view
from app.runtime.contracts import (
    AutomatedReasoningFinding,
    AutomatedReasoningPolicySnapshot,
    EngineRequest,
    GuardContentBlock,
    GuardrailPlanModule,
    GuardrailPlanSnapshot,
    GuardrailPlanStep,
)
from tests.nemo_helpers import nemo_engine


class FindingProvider:
    def __init__(self, *findings: AutomatedReasoningFinding) -> None:
        self.findings = findings
        self.calls = []

    async def evaluate(self, **request):
        self.calls.append(request)
        return self.findings


def _finding(result: str, *, identifier: str = "finding-1"):
    return AutomatedReasoningFinding(
        id=identifier,
        result=result,
        confidence=0.92,
        message=f"Provider returned {result.upper()}.",
    )


def _plan(action: str = "rewrite") -> GuardrailPlanSnapshot:
    step = GuardrailPlanStep(
        id="automated_reasoning:deep-judge",
        risk="automated_reasoning",
        stage="deep_judge",
        phases=("output",),
        on_unsafe=action,
        escalation="always",
        parameters=(("policy_snapshot_id", "automated-reasoning:leave-policy:7"),),
    )
    return GuardrailPlanSnapshot(
        guardrail_id="guardrail-reasoning",
        guardrail_version=3,
        compiler_version="guardrail-plan-v4",
        safety_level="balanced",
        output_delivery="full_buffered",
        steps=(step,),
        modules=(
            GuardrailPlanModule(
                id="business_assurance:automated_reasoning:output",
                module="business_assurance",
                phase="output",
                step_ids=(step.id,),
                input_view="complete_output",
            ),
        ),
        reasoning_policies=(
            AutomatedReasoningPolicySnapshot(
                id="automated-reasoning:leave-policy:7",
                policy_id="leave-policy",
                policy_version="7",
                confidence_threshold=0.8,
            ),
        ),
    )


def _request(plan: GuardrailPlanSnapshot, evidence_scope="full") -> EngineRequest:
    blocks = (
        GuardContentBlock(
            id="query",
            text="Can a part-time employee take parental leave?",
            role="query",
            trust="untrusted",
            source="query",
            qualifiers=("query",),
        ),
        GuardContentBlock(
            id="output",
            text="Yes, every part-time employee is eligible.",
            role="model_output",
            trust="untrusted",
            source="model_output",
        ),
    )
    return EngineRequest(
        phase="output",
        text=blocks[-1].text,
        plan=plan,
        content_view=content_view(blocks, "output"),
        active_block_id="output",
        evidence_scope=evidence_scope,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("result", "decision", "action"),
    (
        ("valid", "allow", "pass"),
        ("invalid", "transform", "rewrite"),
        ("satisfiable", "transform", "clarify"),
        ("impossible", "block", "reject"),
        ("translation_ambiguous", "transform", "clarify"),
        ("too_complex", "block", "reject"),
        ("no_translations", "transform", "clarify"),
    ),
)
async def test_resolver_maps_detection_only_results(result, decision, action):
    provider = FindingProvider(_finding(result))
    plan = _plan()
    engine = nemo_engine(plan, ReasoningActionProvider(provider))

    observed = await engine.evaluate(_request(plan))

    assert observed.decision == decision
    assert observed.action == action
    assert observed.findings[0].recommended_action == "pass"
    assert observed.findings[0].reasoning[0].result == result
    assert provider.calls[0]["policy"].policy_version == "7"
    assert provider.calls[0]["query_content"].startswith("Can a part-time")
    if action != "pass":
        assert observed.interventions[0].kind == action
    await engine.shutdown()


@pytest.mark.asyncio
async def test_valid_finding_is_omitted_from_compact_evidence():
    plan = _plan()
    engine = nemo_engine(
        plan,
        ReasoningActionProvider(FindingProvider(_finding("valid"))),
    )

    observed = await engine.evaluate(_request(plan, "interventions"))

    assert observed.decision == "allow"
    assert observed.findings == ()
    await engine.shutdown()


@pytest.mark.asyncio
async def test_detect_mode_records_resolver_action_without_enforcing_it():
    plan = _plan()
    engine = nemo_engine(
        plan,
        ReasoningActionProvider(FindingProvider(_finding("invalid"))),
    )
    request = _request(plan)
    request = EngineRequest(
        phase=request.phase,
        text=request.text,
        plan=request.plan,
        mode="detect",
        evidence_scope=request.evidence_scope,
        content_view=request.content_view,
        active_block_id=request.active_block_id,
    )

    observed = await engine.evaluate(request)

    assert observed.decision == "allow"
    assert observed.action == "pass"
    assert observed.interventions[0].kind == "rewrite"
    await engine.shutdown()


@pytest.mark.asyncio
async def test_provider_failure_is_not_converted_into_a_logical_finding():
    class BrokenProvider:
        async def evaluate(self, **request):
            raise ValueError("invalid proof payload")

    plan = _plan()
    engine = nemo_engine(plan, ReasoningActionProvider(BrokenProvider()))

    observed = await engine.evaluate(_request(plan))

    assert observed.decision == "block"
    assert observed.findings == ()
    assert observed.assessments[0].status == "error"
    assert "ValueError" in observed.assessments[0].fragments[0].reason
    await engine.shutdown()


@pytest.mark.asyncio
async def test_http_provider_sends_only_policy_reference_and_content(monkeypatch):
    observed = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        observed.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "findings": [
                    {
                        "id": "valid-1",
                        "result": "VALID",
                        "confidence": 0.97,
                        "message": "Proved by rule 1.",
                    }
                ]
            },
        )

    monkeypatch.setenv("REASONING_TEST_KEY", "secret")
    provider = HTTPAutomatedReasoningProvider(
        endpoint_url="https://reasoning.example/v1/evaluate",
        api_key_env_var="REASONING_TEST_KEY",
        transport=httpx.MockTransport(handler),
    )

    findings = await provider.evaluate(
        policy=_plan().reasoning_policies[0],
        query_content="Who is eligible?",
        guard_content="Full-time employees are eligible.",
    )

    assert findings[0].result == "valid"
    assert observed == {
        "policy": {"id": "leave-policy", "version": "7"},
        "query_content": "Who is eligible?",
        "guard_content": "Full-time employees are eligible.",
        "confidence_threshold": 0.8,
    }


def test_aggregate_result_is_order_independent_and_uses_worst_severity():
    values = (
        _finding("valid", identifier="valid"),
        _finding("invalid", identifier="invalid"),
        _finding("satisfiable", identifier="satisfiable"),
    )

    assert aggregate_reasoning_result(values) == "invalid"
    assert aggregate_reasoning_result(tuple(reversed(values))) == "invalid"


def test_provider_payload_parser_retains_proof_evidence():
    findings = parse_reasoning_findings(
        {
            "findings": [
                {
                    "id": "proof-1",
                    "result": "INVALID",
                    "confidence": 0.94,
                    "translation": {
                        "premises": ["employmentType = part_time"],
                        "claims": ["leaveEligible = true"],
                        "untranslated": [],
                    },
                    "contradicting_rules": [
                        {
                            "id": "rule-17",
                            "expression": "part_time -> !leaveEligible",
                            "description": "Part-time employees are ineligible.",
                        }
                    ],
                    "claims_false_scenario": {
                        "variable_values": {
                            "employmentType": "part_time",
                            "leaveEligible": "false",
                        }
                    },
                    "message": "The eligibility claim contradicts rule 17.",
                }
            ]
        }
    )

    finding = findings[0]
    assert finding.result == "invalid"
    assert finding.translation.claims == ("leaveEligible = true",)
    assert finding.contradicting_rules[0].id == "rule-17"
    assert finding.claims_false_scenario.variable_values[0] == (
        "employmentType",
        "part_time",
    )


def _profile(*, output_delivery="full_buffered", binding=True) -> Guardrail:
    reasoning = (
        AutomatedReasoningPolicyBinding("leave-policy", "7", 0.85)
        if binding
        else None
    )
    return Guardrail(
        id="guardrail-ar",
        name="Leave policy",
        purpose="Answer employee leave eligibility questions.",
        allowed_topics=("leave eligibility",),
        restricted_topics=(),
        policy_bindings=(
            GuardrailPolicyBinding("builtin-pii", "1", action="redact"),
            GuardrailPolicyBinding(
                "builtin-automated-reasoning",
                "1",
                action="rewrite",
                reasoning_policy=reasoning,
            ),
        ),
        safety_level="balanced",
        output_delivery=output_delivery,
        draft_version=1,
        active_version=None,
        updated_at="2026-08-11T00:00:00+00:00",
    )


def _resolved(guardrail: Guardrail) -> tuple[ResolvedPolicyCapability, ...]:
    return (
        ResolvedPolicyCapability("pii", "redact"),
        ResolvedPolicyCapability(
            "automated_reasoning",
            "rewrite",
            guardrail.policy_bindings[1].reasoning_policy,
        ),
    )


def test_compiler_pins_policy_and_creates_masked_dependency():
    guardrail = _profile()
    plan = GuardrailCompiler().compile(
        guardrail, 4, resolved_policies=_resolved(guardrail)
    )

    reasoning = next(
        item for item in plan.modules if "automated_reasoning" in item.id
    )
    assert reasoning.depends_on == ("data_protection:output",)
    assert reasoning.input_view == "masked"
    assert reasoning.timeout_ms == 30_000
    assert plan.reasoning_policies[0].policy_version == "7"
    assert plan.reasoning_policies[0].confidence_threshold == 0.85


@pytest.mark.parametrize(
    ("guardrail", "message"),
    (
        (_profile(binding=False), "policy binding"),
        (_profile(output_delivery="window_buffered"), "full-buffered"),
    ),
)
def test_compiler_rejects_incomplete_reasoning_configuration(guardrail, message):
    with pytest.raises(PlanCompilationError, match=message):
        GuardrailCompiler().compile(
            guardrail, 1, resolved_policies=_resolved(guardrail)
        )
