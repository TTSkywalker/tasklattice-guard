from app.control_plane.compiler import GuardrailCompiler
from app.control_plane.domain import (
    Guardrail,
    GuardrailPolicyBinding,
    ResolvedPolicyCapability,
)
from app.runtime.contracts import (
    EngineRequest,
    GuardrailPlanSnapshot,
    GuardrailPlanStep,
)
from app.nemo.actions.topic import (
    _interaction_text,
    _response_payload,
    _topic_messages,
    topic_judge_prompt,
)
from tests.nemo_helpers import provider_request


def test_topic_judge_receives_guardrail_purpose_and_primary_intent_rule():
    guardrail = Guardrail(
        id="guardrail-finance",
        name="Finance",
        purpose="Finance employees analyze approved company and market data.",
        allowed_topics=("Financial analysis", "Accounting and reporting"),
        restricted_topics=("Biomedical advice", "Chemical refining instructions"),
        policy_bindings=(
            GuardrailPolicyBinding("builtin-topic-safety", "1", action="redirect"),
        ),
        safety_level="balanced",
        output_delivery="window_buffered",
        draft_version=1,
        active_version=None,
        updated_at="2026-08-10T00:00:00Z",
    )
    plan = GuardrailCompiler(
        specialized_evaluator_risks=frozenset({"topic_control"})
    ).compile(
        guardrail,
        1,
        resolved_policies=(ResolvedPolicyCapability("topic_control", "redirect"),),
    )
    prompt = topic_judge_prompt(
        plan.steps_for("input", "deep_judge")[0].parameters
    )

    assert guardrail.purpose in prompt
    assert "Financial analysis" in prompt
    assert "Chemical refining instructions" in prompt
    assert "primary requested task" in prompt
    assert "analysis of a chemical manufacturer's revenue" in prompt
    assert prompt.endswith('You must respond with "on-topic" or "off-topic".')


def test_topic_judge_keeps_input_turn_verbatim():
    step = GuardrailPlanStep(
        id="topic:deep",
        risk="topic_control",
        stage="deep_judge",
        phases=("input",),
        on_unsafe="redirect",
    )
    request = EngineRequest(
        phase="input",
        text="Analyze a chemical company's quarterly revenue.",
        plan=GuardrailPlanSnapshot(
            guardrail_id="guardrail-finance",
            guardrail_version=1,
            compiler_version="test",
            safety_level="balanced",
            output_delivery="window_buffered",
            steps=(step,),
        ),
    )

    assert _interaction_text(provider_request(request, step)) == request.text


def test_topic_judge_preserves_prior_conversation_for_input():
    guardrail = Guardrail(
        id="guardrail-finance",
        name="Finance",
        purpose="Support approved financial analysis.",
        allowed_topics=("Financial analysis",),
        restricted_topics=("Chemical process guidance",),
        policy_bindings=(
            GuardrailPolicyBinding("builtin-topic-safety", "1", action="redirect"),
        ),
        safety_level="balanced",
        output_delivery="window_buffered",
        draft_version=1,
        active_version=None,
        updated_at="2026-08-10T00:00:00Z",
    )
    plan = GuardrailCompiler(
        specialized_evaluator_risks=frozenset({"topic_control"})
    ).compile(
        guardrail,
        1,
        resolved_policies=(ResolvedPolicyCapability("topic_control", "redirect"),),
    )
    request = EngineRequest(
        phase="input",
        text="Now compare that with last quarter.",
        plan=plan,
        context_messages=(
            {"role": "user", "content": "Analyze this company's revenue."},
            {"role": "assistant", "content": "Revenue increased by 8%."},
        ),
    )

    messages = _topic_messages(
        provider_request(request, plan.steps_for("input", "deep_judge")[0])
    )

    assert [item["role"] for item in messages] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    assert messages[-1]["content"] == request.text


def test_topic_judge_parses_nvidia_topic_safety_labels():
    assert _response_payload(
        {"choices": [{"message": {"content": "on-topic "}}]}
    )["verdict"] == "safe"
    assert _response_payload(
        {"choices": [{"message": {"content": "off-topic"}}]}
    )["verdict"] == "unsafe"
