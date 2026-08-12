from __future__ import annotations

import json

import httpx
import pytest

from app.control_plane.compiler import GuardrailCompiler
from app.control_plane.domain import PlanCompilationError, GuardrailControl, Guardrail
from app.runtime.content_views import content_view
from app.nemo.actions.grounding import ContextualGroundingJudgeEngine
from app.runtime.contracts import EngineRequest, GuardContentBlock
from tests.nemo_helpers import nemo_engine


def _profile(*risks: GuardrailControl, parameters=()) -> Guardrail:
    return Guardrail(
        id="guardrail-grounding",
        name="Grounded answers",
        purpose="Answer questions from approved knowledge sources.",
        allowed_topics=(),
        restricted_topics=(),
        controls=risks or (GuardrailControl("contextual_grounding", "regenerate"),),
        safety_level="balanced",
        output_delivery="full_buffered",
        source_pack_id=None,
        parameters=parameters,
        draft_version=1,
        active_version=None,
        updated_at="2026-08-11T00:00:00Z",
    )


def _request(response: str, *, full: bool = True) -> EngineRequest:
    plan = GuardrailCompiler().compile(_profile(), 1)
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
    judge = ContextualGroundingJudgeEngine(
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

    result = await judge.evaluate(
        request,
        request.plan.steps_for("output", "deep_judge"),
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
    judge = ContextualGroundingJudgeEngine(
        base_url="https://grounding.test/v1",
        model="grounding-test",
        api_key_env_var="GROUNDING_TEST_KEY",
        transport=_transport(response),
    )
    full = _request("Paris is the capital of France.")
    interventions = _request("Paris is the capital of France.", full=False)

    full_result = await judge.evaluate(
        full,
        full.plan.steps_for("output", "deep_judge"),
    )
    compact_result = await judge.evaluate(
        interventions,
        interventions.plan.steps_for("output", "deep_judge"),
    )

    assert full_result.verdict == compact_result.verdict == "safe"
    assert full_result.findings[0].claims[0].support == "supported"
    assert compact_result.findings == ()


@pytest.mark.asyncio
async def test_grounding_judge_detects_a_grounded_but_irrelevant_response(monkeypatch):
    monkeypatch.setenv("GROUNDING_TEST_KEY", "test-key")
    judge = ContextualGroundingJudgeEngine(
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

    result = await judge.evaluate(
        request,
        request.plan.steps_for("output", "deep_judge"),
    )

    assert result.verdict == "unsafe"
    assert result.findings[0].grounding[0].detected is False
    assert result.findings[0].grounding[1].detected is True


@pytest.mark.asyncio
async def test_grounding_judge_requests_context_before_provider_access(monkeypatch):
    monkeypatch.delenv("GROUNDING_TEST_KEY", raising=False)
    plan = GuardrailCompiler().compile(_profile(), 1)
    request = EngineRequest("output", "Paris is the capital.", plan)
    judge = ContextualGroundingJudgeEngine(
        base_url="https://grounding.test/v1",
        model="grounding-test",
        api_key_env_var="GROUNDING_TEST_KEY",
    )

    result = await judge.evaluate(
        request,
        plan.steps_for("output", "deep_judge"),
    )

    assert result.verdict == "uncertain"
    assert "query and grounding source" in (result.reason or "")


@pytest.mark.asyncio
async def test_grounding_provider_failure_fails_closed_at_module_boundary(monkeypatch):
    monkeypatch.delenv("GROUNDING_TEST_KEY", raising=False)
    request = _request("Paris is the capital of France.")
    judge = ContextualGroundingJudgeEngine(
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
    plan = GuardrailCompiler().compile(
        _profile(
            GuardrailControl("pii", "redact"),
            GuardrailControl("contextual_grounding", "regenerate"),
        ),
        1,
    )

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
        GuardrailCompiler().compile(
            _profile(parameters=(("grounding_threshold", "1"),)),
            1,
        )
