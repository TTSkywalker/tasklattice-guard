from __future__ import annotations

from .context import CallContextStore
from .contracts import GenericGuardrailRequest, GenericGuardrailResponse
from .runtime import GuardrailsRuntime


class ModelGuardrailsService:
    def __init__(
        self,
        runtime: GuardrailsRuntime,
        contexts: CallContextStore | None = None,
    ) -> None:
        self._runtime = runtime
        self._contexts = contexts or CallContextStore()

    async def apply(self, request: GenericGuardrailRequest) -> GenericGuardrailResponse:
        context = self._contexts.get(request.litellm_call_id)
        if request.input_type == "request":
            self._contexts.put(
                request.litellm_call_id,
                request.structured_messages,
            )

        texts = request.texts or []
        if not texts:
            return GenericGuardrailResponse(action="NONE")

        context_messages = context.messages if context else request.structured_messages or []
        output: list[str] = []
        modified = False
        for text in texts:
            result = await self._runtime.check(
                request.input_type,
                text,
                context_messages,
            )
            if result.status == "BLOCKED":
                phase = "input" if request.input_type == "request" else "output"
                rail = f" by {result.rail}" if result.rail else ""
                return GenericGuardrailResponse(
                    action="BLOCKED",
                    blocked_reason=f"Model {phase} blocked{rail}.",
                )
            output.append(result.content)
            modified = modified or result.status == "MODIFIED" or result.content != text

        if modified:
            return GenericGuardrailResponse(
                action="GUARDRAIL_INTERVENED",
                texts=output,
            )
        return GenericGuardrailResponse(action="NONE")
