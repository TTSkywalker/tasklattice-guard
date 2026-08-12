from __future__ import annotations

import httpx
import pytest

from app.control_plane.chat_model import (
    OpenAICompatibleChatModel,
    PlaygroundChatError,
)


@pytest.mark.asyncio
async def test_openai_compatible_chat_model_returns_complete_text(monkeypatch):
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["authorization"]
        captured["payload"] = request.content.decode()
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "  Full answer.  "}}]},
        )

    monkeypatch.setenv("PLAYGROUND_TEST_KEY", "secret")
    model = OpenAICompatibleChatModel(
        model_id="deep-judge",
        provider="DeepSeek",
        base_url="https://api.deepseek.com",
        model="deepseek-test",
        api_key_env_var="PLAYGROUND_TEST_KEY",
        request_options={"thinking": {"type": "disabled"}},
        transport=httpx.MockTransport(handler),
    )

    result = await model.complete(
        ({"role": "user", "content": "Give me an answer."},)
    )

    assert result == "Full answer."
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["authorization"] == "Bearer secret"
    assert '"model":"deepseek-test"' in captured["payload"]
    assert '"thinking":{"type":"disabled"}' in captured["payload"]
    assert "Give me an answer." in captured["payload"]


@pytest.mark.asyncio
async def test_openai_compatible_chat_model_requires_configured_credential(
    monkeypatch,
):
    monkeypatch.delenv("PLAYGROUND_TEST_KEY", raising=False)
    model = OpenAICompatibleChatModel(
        model_id="deep-judge",
        provider="DeepSeek",
        base_url="https://api.deepseek.com",
        model="deepseek-test",
        api_key_env_var="PLAYGROUND_TEST_KEY",
    )

    with pytest.raises(PlaygroundChatError, match="not available"):
        await model.complete(
            ({"role": "user", "content": "Give me an answer."},)
        )
