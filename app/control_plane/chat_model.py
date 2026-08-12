from __future__ import annotations

import os
from typing import Any, Protocol

import httpx


class PlaygroundChatError(RuntimeError):
    pass


class PlaygroundChatModel(Protocol):
    id: str
    provider: str
    model: str

    async def complete(self, messages: tuple[dict[str, str], ...]) -> str: ...


class OpenAICompatibleChatModel:
    """A selectable Playground model backed by an OpenAI-compatible endpoint."""

    def __init__(
        self,
        *,
        model_id: str,
        provider: str,
        base_url: str,
        model: str,
        api_key_env_var: str,
        request_options: dict[str, object] | None = None,
        timeout_seconds: float = 90.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.id = model_id
        self.provider = provider
        self.model = model
        self._base_url = base_url.rstrip("/")
        self._api_key_env_var = api_key_env_var
        self._request_options = dict(request_options or {})
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def complete(self, messages: tuple[dict[str, str], ...]) -> str:
        credential = os.environ.get(self._api_key_env_var, "").strip()
        if not credential:
            raise PlaygroundChatError("The selected Playground model is not available.")

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers={"authorization": f"Bearer {credential}"},
                    json={
                        "model": self.model,
                        "temperature": 0.7,
                        "max_tokens": 2_000,
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    "You are a helpful AI assistant. Answer the user's "
                                    "request directly and respond in the user's language."
                                ),
                            },
                            *messages,
                        ],
                        **self._request_options,
                    },
                )
                response.raise_for_status()
                return _response_text(response.json())
        except PlaygroundChatError:
            raise
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise PlaygroundChatError(
                "The selected Playground model could not complete this turn."
            ) from error


def _response_text(payload: dict[str, Any]) -> str:
    content = payload["choices"][0]["message"]["content"]
    if not isinstance(content, str) or not content.strip():
        raise PlaygroundChatError("The selected Playground model returned no text.")
    return content.strip()
