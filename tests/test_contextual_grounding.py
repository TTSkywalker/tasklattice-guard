from __future__ import annotations

import json

import httpx
import pytest

from app.control_plane.compiler import GuardrailCompiler
from app.control_plane.catalog import builtin_policy_id, capability_id_for_policy
from app.control_plane.domain import (
    Guardrail,
    GuardrailPolicyBinding,
    PlanCompilationError,
    ResolvedPolicyCapability,
)
from app.runtime.content_views import content_view
from app.nemo.actions.grounding import GroundingActionProvider
from app.runtime.contracts import EngineRequest, GuardContentBlock
from tests.nemo_helpers import nemo_engine, provider_request


def _profile(*policies: ResolvedPolicyCapability, parameters=()) -> Guardrail:
    resolved = policies or (
        ResolvedPolicyCapability("contextual_grounding", "regenerate"),
    )
    return Guardrail(
        id="guardrail-grounding",
        name="Grounded answers",
        purpose="Answer questions from approved knowledge sources.",
        allowed_topics=(),
        restricted_topics=(),
        policy_bindings=tuple(
            GuardrailPolicyBinding(
                policy_id=builtin_policy_id(item.risk),
                policy_version="1",
                action=item.action,
                parameter_values=(parameters if item.risk == "contextual_grounding" else ()),
            )
            for item in resolved
        ),
        safety_level="balanced",
        output_delivery="full_buffered",
        draft_version=1,
        active_version=None,
        updated_at="2026-08-11T00:00:00Z",
    )


def _resolved(guardrail: Guardrail) -> tuple[ResolvedPolicyCapability, ...]:
    return tuple(
        ResolvedPolicyCapability(
            capability_id_for_policy(item.policy_id),
            item.action or "reject",
        )
        for item in guardrail.policy_bindings
    )


def _compile(guardrail: Guardrail, version: int):
    return GuardrailCompiler().compile(
        guardrail, version, resolved_policies=_resolved(guardrail)
    )


def _request(response: str, *, full: bool = True) -> EngineRequest:
    plan = _compile(_profile(), 1)
    blocks = (
        GuardContentBlock(
            id="query",
            text="What is the capital of France?",
            role="query",
            trust="untrusted",
            source="query",
            qualifiers=("query",),
        ),
        GuardContentBlock(
            id="source-france",
            text="Paris is the capital of France.",
            role="grounding_source",
            trust="untrusted",
            source="grounding_source",
            qualifiers=("grounding_source",),
        ),
        GuardContentBlock(
            id="answer",
            text=response,
            role="model_output",
            trust="untrusted",
            source="model_output",
        ),
    )
    return EngineRequest(
        phase="output",
        text=response,
        plan=plan,
        evidence_scope="full" if full else "interventions",
        content_view=content_view(blocks, "answer"),
        active_block_id="answer",
        target_source="model_output",
    )


def _transport(payload: dict) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "grounding-test"
        context = json.loads(body["messages"][1]["content"])
        assert context["queries"][0]["block_id"] == "query"
        assert context["grounding_sources"][0]["block_id"] == "source-france"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(payload)}}]},
        )

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_grounding_judge_returns_scores_and_claim_level_source_evidence(monkeypatch):
    monkeypatch.setenv("GROUNDING_TEST_KEY", "test-key")
    judge = GroundingActionProvider(
        base_url="https://grounding.test/v1",
        model="grounding-test",
        api_key_env_var="GROUNDING_TEST_KEY",
        transport=_transport(
            {
                "grounding_score": 0.25,
                "relevance_score": 0.98,
                "reason": "The city in the response is not supported by the source.",
                "claims": [
                    {
                        "id": "capital-claim",
                        "claim": "London is the capital of France.",
                        "support": "unsupported",
                        "confidence": 0.99,
                        "source_block_ids": ["source-france"],
                        "rationale": "The source names Paris instead.",
                    }
                ],
            }
        ),
    )
    request = _request("London is the capital of France.")

    result = await judge.execute(
        provider_request(
            request,
            request.plan.steps_for("output", "deep_judge")[0],
        )
    )

    assert result.verdict == "unsafe"
    finding = result.findings[0]
    assert tuple(item.type for item in finding.grounding) == (
        "grounding",
        "relevance",
    )
    assert finding.grounding[0].detected is True
    assert finding.grounding[1].detected is False
    assert finding.claims[0].support == "unsupported"
    assert finding.claims[0].source_block_ids == ("source-france",)
    assert finding.recommended_action == "regenerate"


@pytest.mark.asyncio
async def test_grounding_judge_retains_safe_evidence_only_for_full_scope(monkeypatch):
    monkeypatch.setenv("GROUNDING_TEST_KEY", "test-key")
    response = {
        "grounding_score": 0.97,
        "relevance_score": 0.96,
        "reason": "The response directly answers the query from the source.",
        "claims": [
            {
                "claim": "Paris is the capital of France.",
                "support": "supported",
                "confidence": 0.99,
                "source_block_ids": ["source-france"],
            }
        ],
    }
    judge = GroundingActionProvider(
        base_url="https://grounding.test/v1",
        model="grounding-test",
        api_key_env_var="GROUNDING_TEST_KEY",
        transport=_transport(response),
    )
    full = _request("Paris is the capital of France.")
    interventions = _request("Paris is the capital of France.", full=False)

    full_result = await judge.execute(
        provider_request(full, full.plan.steps_for("output", "deep_judge")[0])
    )
    compact_result = await judge.execute(
        provider_request(
            interventions,
            interventions.plan.steps_for("output", "deep_judge")[0],
        )
    )

    assert full_result.verdict == compact_result.verdict == "safe"
    assert full_result.findings[0].claims[0].support == "supported"
    assert compact_result.findings == ()


@pytest.mark.asyncio
async def test_grounding_judge_detects_a_grounded_but_irrelevant_response(monkeypatch):
    monkeypatch.setenv("GROUNDING_TEST_KEY", "test-key")
    judge = GroundingActionProvider(
        base_url="https://grounding.test/v1",
        model="grounding-test",
        api_key_env_var="GROUNDING_TEST_KEY",
        transport=_transport(
            {
                "grounding_score": 0.95,
                "relevance_score": 0.2,
                "reason": "The response is sourced but does not answer the query.",
                "claims": [
                    {
                        "claim": "The source contains a supported but unrelated fact.",
                        "support": "supported",
                        "confidence": 0.9,
                        "source_block_ids": ["source-france"],
                    }
                ],
            }
        ),
    )
    request = _request("The source contains a supported but unrelated fact.")

    result = await judge.execute(
        provider_request(
            request,
            request.plan.steps_for("output", "deep_judge")[0],
        )
    )

    assert result.verdict == "unsafe"
    assert result.findings[0].grounding[0].detected is False
    assert result.findings[0].grounding[1].detected is True


@pytest.mark.asyncio
async def test_grounding_judge_requests_context_before_provider_access(monkeypatch):
    monkeypatch.delenv("GROUNDING_TEST_KEY", raising=False)
    plan = _compile(_profile(), 1)
    request = EngineRequest("output", "Paris is the capital.", plan)
    judge = GroundingActionProvider(
        base_url="https://grounding.test/v1",
        model="grounding-test",
        api_key_env_var="GROUNDING_TEST_KEY",
    )

    result = await judge.execute(
        provider_request(request, plan.steps_for("output", "deep_judge")[0])
    )

    assert result.verdict == "uncertain"
    assert "query and grounding source" in (result.reason or "")


@pytest.mark.asyncio
async def test_grounding_provider_failure_fails_closed_at_module_boundary(monkeypatch):
    monkeypatch.delenv("GROUNDING_TEST_KEY", raising=False)
    request = _request("Paris is the capital of France.")
    judge = GroundingActionProvider(
        base_url="https://grounding.test/v1",
        model="grounding-test",
        api_key_env_var="GROUNDING_TEST_KEY",
    )
    engine = nemo_engine(request.plan, judge)

    result = await engine.evaluate(request)

    assert result.decision == "block"
    assert result.action == "reject"
    assert result.assessments[0].status == "error"
    assert "credential" in (result.assessments[0].fragments[0].reason or "")
    await engine.shutdown()


def test_compiler_creates_grounding_module_after_output_data_protection():
    guardrail = _profile(
        ResolvedPolicyCapability("pii", "redact"),
        ResolvedPolicyCapability("contextual_grounding", "regenerate"),
    )
    plan = _compile(guardrail, 1)

    grounding = next(
        item
        for item in plan.modules_for("output")
        if "contextual_grounding" in item.id
    )
    assert grounding.depends_on == ("data_protection:output",)
    assert grounding.input_view == "masked"
    assert plan.steps_for("input") != ()
    assert {
        item.risk for item in plan.steps_for("output", "deep_judge")
    } == {"contextual_grounding"}


def test_compiler_rejects_invalid_grounding_thresholds():
    with pytest.raises(PlanCompilationError, match="between 0 and 0.99"):
        guardrail = _profile(parameters=(("grounding_threshold", "1"),))
        _compile(guardrail, 1)
