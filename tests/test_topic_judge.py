from app.control_plane.compiler import GuardrailCompiler
from app.control_plane.domain import ProfileRisk, SafetyProfile
from app.engine.contracts import EngineRequest, GuardrailPlanSnapshot
from app.engine.topic_judge import (
    _interaction_text,
    _response_payload,
    _topic_messages,
    topic_judge_prompt,
)


def test_topic_judge_receives_profile_purpose_and_primary_intent_rule():
    profile = SafetyProfile(
        id="profile-finance",
        name="Finance",
        purpose="Finance employees analyze approved company and market data.",
        allowed_topics=("Financial analysis", "Accounting and reporting"),
        restricted_topics=("Biomedical advice", "Chemical refining instructions"),
        risks=(ProfileRisk("topic_control", "redirect"),),
        safety_level="balanced",
        output_delivery="window_buffered",
        source_template_id=None,
        template_parameters=(),
        draft_version=1,
        active_revision=None,
        updated_at="2026-08-10T00:00:00Z",
    )
    plan = GuardrailCompiler().compile(profile, 1)
    prompt = topic_judge_prompt(plan.steps_for("input", "deep_judge"))

    assert profile.purpose in prompt
    assert "Financial analysis" in prompt
    assert "Chemical refining instructions" in prompt
    assert "primary requested task" in prompt
    assert "analysis of a chemical manufacturer's revenue" in prompt
    assert prompt.endswith('You must respond with "on-topic" or "off-topic".')


def test_topic_judge_keeps_input_turn_verbatim():
    request = EngineRequest(
        phase="input",
        text="Analyze a chemical company's quarterly revenue.",
        plan=GuardrailPlanSnapshot(
            profile_id="profile-finance",
            profile_revision=1,
            compiler_version="test",
            safety_level="balanced",
            output_delivery="window_buffered",
            steps=(),
        ),
    )

    assert _interaction_text(request) == request.text


def test_topic_judge_preserves_prior_conversation_for_input():
    profile = SafetyProfile(
        id="profile-finance",
        name="Finance",
        purpose="Support approved financial analysis.",
        allowed_topics=("Financial analysis",),
        restricted_topics=("Chemical process guidance",),
        risks=(ProfileRisk("topic_control", "redirect"),),
        safety_level="balanced",
        output_delivery="window_buffered",
        source_template_id=None,
        template_parameters=(),
        draft_version=1,
        active_revision=None,
        updated_at="2026-08-10T00:00:00Z",
    )
    plan = GuardrailCompiler().compile(profile, 1)
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
        request, plan.steps_for("input", "deep_judge")
    )

    assert [item["role"] for item in messages] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    assert messages[-1]["content"] == request.text


def test_topic_judge_parses_nvidia_topic_control_labels():
    assert _response_payload(
        {"choices": [{"message": {"content": "on-topic "}}]}
    )["verdict"] == "safe"
    assert _response_payload(
        {"choices": [{"message": {"content": "off-topic"}}]}
    )["verdict"] == "unsafe"
