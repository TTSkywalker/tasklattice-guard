from __future__ import annotations

import json
import os
from typing import Any

import httpx

from ...runtime.contracts import EngineRequest, GuardrailPlanStep, RiskFinding, StageResult


class PurposeAwareTopicJudgeEngine:
    """Judge organization-specific topic intent with the compiled Guardrail context."""

    name = "Purpose-Aware Topic Judge"
    stage = "deep_judge"
    supported_phases = frozenset({"input", "output"})
    # Organization policies use the same dedicated NVIDIA Topic Control
    # evaluator because both capabilities classify an interaction against
    # explicit, compiled business boundaries. No general-purpose LLM fallback
    # is registered for either risk.
    supported_risks = frozenset({"topic_control", "company_policy"})

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key_env_var: str,
        timeout_seconds: float = 20.0,
        request_options: dict[str, object] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key_env_var = api_key_env_var
        self._timeout_seconds = timeout_seconds
        self._request_options = dict(request_options or {})

    async def evaluate(
        self,
        request: EngineRequest,
        steps: tuple[GuardrailPlanStep, ...],
    ) -> StageResult:
        configured = tuple(
            step for step in steps if step.risk in self.supported_risks
        )
        if not configured:
            return StageResult(verdict="safe", content=request.text)
        credential = os.environ.get(self._api_key_env_var, "").strip()
        if not credential:
            return StageResult(
                verdict="error",
                content=request.text,
                reason=f"{self.name} credential is not configured.",
            )

        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers={"authorization": f"Bearer {credential}"},
                    json={
                        "model": self._model,
                        "temperature": 0.01,
                        "max_tokens": 16,
                        "messages": _topic_messages(request, configured),
                        **self._request_options,
                    },
                )
                response.raise_for_status()
                payload = _response_payload(response.json())
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            return StageResult(
                verdict="error",
                content=request.text,
                reason=f"{self.name} evaluator failed: {type(error).__name__}.",
            )

        verdict = str(payload.get("verdict", "uncertain")).lower()
        reason = str(payload.get("reason", "Topic decision returned without a reason."))
        if verdict == "safe":
            return StageResult(verdict="safe", content=request.text, reason=reason)
        if verdict not in {"unsafe", "uncertain"}:
            verdict = "uncertain"
        step = configured[0]
        findings = () if verdict == "uncertain" else (
            RiskFinding(
                risk=step.risk,
                verdict="unsafe",
                confidence=_confidence(payload.get("confidence")),
                evidence=reason,
                recommended_action=step.on_unsafe,
            ),
        )
        return StageResult(
            verdict=verdict,
            content=request.text,
            findings=findings,
            reason=reason,
        )


def topic_judge_prompt(steps: tuple[GuardrailPlanStep, ...]) -> str:
    policies: list[str] = []
    for step in steps:
        parameters = dict(step.parameters)
        policies.append(
            "\n".join(
                (
                    "You are the topic policy for an enterprise assistant whose authorized role is: "
                    f"{parameters.get('purpose', '')}",
                    f"You may help with these allowed business tasks:\n{parameters.get('allowed_topics', '')}",
                    f"Do not help with requests whose primary task belongs to these restricted domains:\n{parameters.get('restricted_topics', '')}",
                    "Classify by the primary requested task, never by an industry, product, or entity merely mentioned as context. "
                    "Financial analysis of a company in any industry is financial analysis. For example, analysis of a chemical manufacturer's revenue, "
                    "profit margin, or cash flow is allowed when financial analysis is an allowed task; chemical process or refining guidance is restricted.",
                    "A request unrelated to the authorized business purpose is off-topic.",
                )
            )
        )
    return "\n\n".join(
        (
            *policies,
            'If any of the above conditions are violated, please respond with "off-topic". Otherwise, respond with "on-topic". '
            'You must respond with "on-topic" or "off-topic".',
        )
    )


def _interaction_text(request: EngineRequest) -> str:
    if request.phase == "input":
        # Topic Guard expects the conversation to end with the user message that
        # is being moderated. Keep the input turn verbatim instead of wrapping it
        # in evaluator-oriented instructions.
        return request.text
    context = "\n".join(
        f"{message.get('role', 'unknown')}: {message.get('content', '')}"
        for message in request.context_messages[-6:]
    )
    return f"Conversation context:\n{context}\n\nModel output to evaluate:\n{request.text}"


def _topic_messages(
    request: EngineRequest,
    steps: tuple[GuardrailPlanStep, ...],
) -> list[dict[str, str]]:
    messages = [{"role": "system", "content": topic_judge_prompt(steps)}]
    if request.phase == "output":
        messages.append({"role": "user", "content": _interaction_text(request)})
        return messages

    for message in request.context_messages[-12:]:
        role = str(message.get("role", ""))
        content = message.get("content")
        if role in {"user", "assistant"} and isinstance(content, str) and content.strip():
            messages.append({"role": role, "content": content})
    if not (
        len(messages) > 1
        and messages[-1]["role"] == "user"
        and messages[-1]["content"] == request.text
    ):
        messages.append({"role": "user", "content": request.text})
    return messages


def _response_payload(payload: dict[str, Any]) -> dict[str, Any]:
    content = payload["choices"][0]["message"]["content"]
    if not isinstance(content, str):
        raise TypeError("Judge response content must be text.")
    cleaned = content.strip()
    normalized = cleaned.casefold().replace("_", "-")
    if normalized == "on-topic":
        return {
            "verdict": "safe",
            "confidence": 0.95,
            "reason": "The request is within the Guardrail's allowed business purpose.",
        }
    if normalized == "off-topic":
        return {
            "verdict": "unsafe",
            "confidence": 0.95,
            "reason": "The request is outside the Guardrail's allowed business purpose or enters a restricted domain.",
        }
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```")
        cleaned = cleaned.removesuffix("```").strip()
    return json.loads(cleaned)


def _confidence(value: object) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.75
