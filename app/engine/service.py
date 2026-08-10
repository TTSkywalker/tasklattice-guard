from __future__ import annotations

from .context import CallContextStore
from .contracts import (
    EngineRequest,
    EvaluationDecision,
    EvaluationRequest,
    GuardrailEngine,
    PlanResolver,
)


class ModelGuardrailsEngineService:
    """Pin a tested Guardrail Plan and evaluate model input or output."""

    def __init__(
        self,
        engine: GuardrailEngine,
        resolver: PlanResolver,
        contexts: CallContextStore | None = None,
    ) -> None:
        self._engine = engine
        self._resolver = resolver
        self._contexts = contexts or CallContextStore()

    async def evaluate(self, request: EvaluationRequest) -> EvaluationDecision:
        stored = self._contexts.get(request.call_id)
        resolution = (
            stored.resolution
            if request.phase == "output" and stored is not None
            else self._resolver.resolve(request.context)
        )
        if request.phase == "input":
            self._contexts.put(request.call_id, request.messages, resolution)

        if not request.texts:
            return EvaluationDecision(
                decision="allow",
                action="pass",
                reason="No model content required evaluation.",
                profile_id=resolution.plan.profile_id,
                profile_revision=resolution.plan.profile_revision,
                workload_id=resolution.workload_id,
                gateway_id=resolution.gateway_id,
                output_delivery=resolution.plan.output_delivery,
                trace=resolution.trace,
            )

        output: list[str] = []
        findings = []
        trace = list(resolution.trace)
        final_decision = "allow"
        final_action = "pass"
        reason = "All model content passed the active Safety Profile."
        context_messages = stored.messages if stored else request.messages
        trusted_instruction = _trusted_instruction(context_messages)
        target_source = request.context.value("field", "target_source") or "user_input"

        for text in request.texts:
            decision = await self._engine.evaluate(
                EngineRequest(
                    phase=request.phase,
                    text=text,
                    plan=resolution.plan,
                    context_messages=context_messages,
                    trusted_instruction=trusted_instruction,
                    target_source=target_source,
                )
            )
            findings.extend(decision.findings)
            trace.extend(decision.trace)
            if decision.decision == "block":
                return EvaluationDecision(
                    decision="block",
                    action="reject",
                    reason=decision.reason,
                    profile_id=resolution.plan.profile_id,
                    profile_revision=resolution.plan.profile_revision,
                    workload_id=resolution.workload_id,
                    gateway_id=resolution.gateway_id,
                    output_delivery=resolution.plan.output_delivery,
                    findings=tuple(findings),
                    trace=tuple(trace),
                )
            if decision.decision == "transform":
                final_decision = "transform"
                final_action = decision.action
                reason = decision.reason or "Safety Profile transformed model content."
                output.extend(decision.texts or (text,))
            else:
                output.append(text)

        return EvaluationDecision(
            decision=final_decision,
            action=final_action,
            reason=reason,
            texts=tuple(output) if final_decision == "transform" else (),
            profile_id=resolution.plan.profile_id,
            profile_revision=resolution.plan.profile_revision,
            workload_id=resolution.workload_id,
            gateway_id=resolution.gateway_id,
            output_delivery=resolution.plan.output_delivery,
            findings=tuple(findings),
            trace=tuple(trace),
        )


def _trusted_instruction(messages: tuple[dict, ...]) -> str:
    return "\n\n".join(
        str(message.get("content", "")).strip()
        for message in messages
        if message.get("role") in {"system", "developer"}
        and isinstance(message.get("content"), str)
        and str(message.get("content", "")).strip()
    )
