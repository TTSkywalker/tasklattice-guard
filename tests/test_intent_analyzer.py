from __future__ import annotations

import json

import httpx
import pytest

from app.control_plane.intent_analyzer import (
    DeepSeekIntentAnalyzer,
    IntentAnalysisError,
    compliance_document_prompt,
    intent_analysis_prompt,
)
from app.control_plane.document_ingestion import extract_documents


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
    assert request_payload["thinking"] == {"type": "disabled"}
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


@pytest.mark.asyncio
async def test_document_analyzer_treats_content_as_untrusted_and_validates_citations(
    monkeypatch,
):
    request_payload: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        request_payload.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "summary": "Support customer service while protecting account data.",
                                    "allowed_topics": ["Customer support"],
                                    "restricted_topics": ["Credential disclosure"],
                                    "requirements": [
                                        {
                                            "title": "Protect credentials",
                                            "description": "Do not disclose account credentials.",
                                            "effect": "block",
                                            "source_refs": ["document-1:lines-1-1"],
                                        }
                                    ],
                                    "recommended_policy_ids": ["builtin-secrets"],
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
    documents = extract_documents(
        (("policy.txt", b"Customer support must never disclose account credentials."),)
    )
    result = await analyzer.analyze_documents(
        documents=documents,
        policies=(
            ("builtin-secrets", "Secrets", "Protect credentials."),
            ("builtin-pii", "Personal information", "Protect personal data."),
        ),
        language="en",
    )

    messages = request_payload["messages"]
    assert isinstance(messages, list)
    assert "untrusted evidence" in messages[0]["content"]
    assert "<compliance_documents>" in messages[1]["content"]
    assert request_payload["max_tokens"] == 4_000
    assert result.requirements[0].source_refs == ("document-1:lines-1-1",)
    assert result.recommended_policy_ids == ("builtin-secrets",)


def test_document_prompt_limits_recommendations_to_known_policy_ids():
    prompt = compliance_document_prompt(
        "zh-CN", "- builtin-pii: Personal information — Protect personal data."
    )

    assert "untrusted evidence" in prompt
    assert "Simplified Chinese" in prompt
    assert "builtin-pii" in prompt
