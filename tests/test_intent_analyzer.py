from __future__ import annotations

import json

import httpx
import pytest

from app.control_plane.intent_analyzer import (
    DeepSeekIntentAnalyzer,
    IntentAnalysisError,
    intent_analysis_prompt,
)


@pytest.mark.asyncio
async def test_deepseek_intent_analyzer_requests_json_and_validates_rules(monkeypatch):
    request_payload: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        request_payload.update(json.loads(request.content))
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "summary": "Finance data analysis only.",
                                    "allowed_topics": [
                                        "Financial data analysis",
                                        "SQL and Python for finance",
                                    ],
                                    "restricted_topics": [
                                        "Biomedical research advice",
                                        "Chemical refining instructions",
                                    ],
                                    "review_notes": [
                                        "Confirm whether general statistics is allowed."
                                    ],
                                }
                            )
                        }
                    }
                ]
            },
        )

    monkeypatch.setenv("TEST_DEEPSEEK_KEY", "test-key")
    analyzer = DeepSeekIntentAnalyzer(
        base_url="https://api.deepseek.test",
        model="deepseek-test",
        api_key_env_var="TEST_DEEPSEEK_KEY",
        transport=httpx.MockTransport(handler),
    )
    result = await analyzer.analyze(
        purpose="Finance analysts use this model for approved data analysis only.",
        language="en",
    )

    assert request_payload["response_format"] == {"type": "json_object"}
    assert request_payload["temperature"] == 0
    assert result.allowed_topics[0] == "Financial data analysis"
    assert result.restricted_topics[-1] == "Chemical refining instructions"


@pytest.mark.asyncio
async def test_deepseek_intent_analyzer_rejects_overlapping_rules(monkeypatch):
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "summary": "Draft.",
                                    "allowed_topics": ["Finance", "SQL"],
                                    "restricted_topics": ["Finance", "Biomedicine"],
                                    "review_notes": [],
                                }
                            )
                        }
                    }
                ]
            },
        )

    monkeypatch.setenv("TEST_DEEPSEEK_KEY", "test-key")
    analyzer = DeepSeekIntentAnalyzer(
        base_url="https://api.deepseek.test",
        model="deepseek-test",
        api_key_env_var="TEST_DEEPSEEK_KEY",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(IntentAnalysisError, match="overlapping"):
        await analyzer.analyze(
            purpose="Finance analysts use this model for approved data analysis only.",
            language="en",
        )


def test_intent_analysis_prompt_preserves_primary_intent_and_output_language():
    prompt = intent_analysis_prompt("zh-CN")

    assert "primary business task" in prompt
    assert "financial analysis of a chemical company" in prompt
    assert "Simplified Chinese" in prompt
    assert "JSON" in prompt
