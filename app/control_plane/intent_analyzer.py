from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import httpx


class IntentAnalysisError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class IntentAnalysis:
    summary: str
    allowed_topics: tuple[str, ...]
    restricted_topics: tuple[str, ...]
    review_notes: tuple[str, ...]


class IntentAnalyzer(Protocol):
    provider: str
    model: str

    async def analyze(
        self, *, purpose: str, language: Literal["en", "zh-CN"]
    ) -> IntentAnalysis: ...


class DeepSeekIntentAnalyzer:
    """Translate business intent into a reviewable Topic Control rule draft."""

    provider = "DeepSeek"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key_env_var: str,
        timeout_seconds: float = 45.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self.model = model
        self._api_key_env_var = api_key_env_var
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def analyze(
        self, *, purpose: str, language: Literal["en", "zh-CN"]
    ) -> IntentAnalysis:
        credential = os.environ.get(self._api_key_env_var, "").strip()
        if not credential:
            raise IntentAnalysisError("The control-plane assistant is not configured.")

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds, transport=self._transport
            ) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers={"authorization": f"Bearer {credential}"},
                    json={
                        "model": self.model,
                        "temperature": 0,
                        "max_tokens": 1_200,
                        "response_format": {"type": "json_object"},
                        "messages": [
                            {
                                "role": "system",
                                "content": intent_analysis_prompt(language),
                            },
                            {"role": "user", "content": purpose},
                        ],
                    },
                )
                response.raise_for_status()
                payload = _response_payload(response.json())
                return _analysis(payload)
        except IntentAnalysisError:
            raise
        except (
            httpx.HTTPError,
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            raise IntentAnalysisError(
                "The control-plane assistant could not analyze this intent."
            ) from error


def intent_analysis_prompt(language: Literal["en", "zh-CN"]) -> str:
    output_language = "Simplified Chinese" if language == "zh-CN" else "English"
    return "\n".join(
        (
            "You are the policy analyst inside an enterprise AI safety control plane.",
            "Translate a business user's plain-language protection intent into a concise, editable Topic Control rule draft.",
            "Focus on the primary business task, not isolated keywords. For example, financial analysis of a chemical company remains financial analysis; chemical process instructions do not.",
            "Allowed topics must be clear business domains or task-and-domain combinations. Restricted topics must describe disallowed domains, advice, processes, or technologies with enough context to avoid accidental keyword blocking.",
            "Preserve every explicit allow or deny boundary in the user's text. Do not invent legal, regulatory, or company facts.",
            "Generate 2 to 10 distinct allowed topics and 2 to 10 distinct restricted topics. Keep each item under 160 characters.",
            f"Write every user-facing value in {output_language}.",
            "Return JSON only using this exact object shape:",
            '{"summary":"one-sentence normalized purpose","allowed_topics":["rule"],"restricted_topics":["rule"],"review_notes":["assumption or boundary the user should verify"]}',
        )
    )


def _response_payload(payload: dict[str, Any]) -> dict[str, Any]:
    content = payload["choices"][0]["message"]["content"]
    if not isinstance(content, str) or not content.strip():
        raise TypeError("Intent analysis response content must be text.")
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```")
        cleaned = cleaned.removesuffix("```").strip()
    parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        raise TypeError("Intent analysis response must be an object.")
    return parsed


def _analysis(payload: dict[str, Any]) -> IntentAnalysis:
    summary = _text(payload.get("summary"), "summary", maximum=500)
    allowed = _text_list(payload.get("allowed_topics"), "allowed_topics")
    restricted = _text_list(payload.get("restricted_topics"), "restricted_topics")
    notes = _text_list(
        payload.get("review_notes", []),
        "review_notes",
        minimum=0,
        maximum=6,
        item_maximum=300,
    )
    overlap = {item.casefold() for item in allowed} & {
        item.casefold() for item in restricted
    }
    if overlap:
        raise IntentAnalysisError(
            "The control-plane assistant returned overlapping topic rules."
        )
    return IntentAnalysis(summary, allowed, restricted, notes)


def _text(value: object, field: str, *, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise IntentAnalysisError(
            f"The control-plane assistant returned an invalid {field}."
        )
    return value.strip()


def _text_list(
    value: object,
    field: str,
    *,
    minimum: int = 2,
    maximum: int = 10,
    item_maximum: int = 160,
) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise IntentAnalysisError(
            f"The control-plane assistant returned an invalid {field}."
        )
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise IntentAnalysisError(
                f"The control-plane assistant returned an invalid {field}."
            )
        clean = item.strip()
        key = clean.casefold()
        if not clean or len(clean) > item_maximum:
            raise IntentAnalysisError(
                f"The control-plane assistant returned an invalid {field}."
            )
        if key not in seen:
            seen.add(key)
            result.append(clean)
    if not minimum <= len(result) <= maximum:
        raise IntentAnalysisError(
            f"The control-plane assistant returned an invalid {field}."
        )
    return tuple(result)
