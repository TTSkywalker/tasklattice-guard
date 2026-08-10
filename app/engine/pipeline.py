from __future__ import annotations

import time

from .contracts import (
    EnforcementAction,
    EngineRequest,
    EvaluationDecision,
    EvaluationStage,
    EvaluationTraceStep,
    GuardrailPlanStep,
    GuardrailStage,
    RiskFinding,
    StageResult,
)


STAGE_ORDER: tuple[EvaluationStage, ...] = (
    "deterministic",
    "fast_semantic",
    "deep_judge",
)


class ProgressiveGuardrailsEngine:
    """Apply the cheapest sufficient evaluation and escalate only by plan."""

    name = "progressive"
    supported_phases = frozenset({"input", "output"})

    def __init__(self, stages: tuple[GuardrailStage, ...]) -> None:
        self._stages = {stage.stage: stage for stage in stages}

    @property
    def stages(self) -> tuple[GuardrailStage, ...]:
        return tuple(self._stages[item] for item in STAGE_ORDER if item in self._stages)

    async def evaluate(self, request: EngineRequest) -> EvaluationDecision:
        content = request.text
        trace: list[EvaluationTraceStep] = []
        findings: list[RiskFinding] = []
        uncertain_risks: set[str] = set()
        transformed = False

        for stage_name in STAGE_ORDER:
            planned = request.plan.steps_for(request.phase, stage_name)
            if not planned:
                trace.append(self._skip(stage_name, "No plan steps require this stage."))
                continue

            if stage_name == "deep_judge":
                planned = self._required_deep_steps(planned, uncertain_risks)
                if not planned:
                    trace.append(
                        self._skip(
                            stage_name,
                            "Deep Judge was not required because earlier evaluation was decisive.",
                        )
                    )
                    continue

            stage = self._stages.get(stage_name)
            if stage is None or request.phase not in stage.supported_phases:
                reason = f"Configured {stage_name.replace('_', ' ')} evaluator is unavailable."
                trace.append(
                    EvaluationTraceStep(
                        id=f"stage:{stage_name}",
                        kind="stage",
                        name=self._label(stage_name),
                        status="error",
                        detail=reason,
                        stage=stage_name,
                        verdict="error",
                        route="fail_closed",
                    )
                )
                return self._block(request, content, reason, tuple(findings), tuple(trace))

            started = time.perf_counter()
            result = await stage.evaluate(
                EngineRequest(
                    phase=request.phase,
                    text=content,
                    plan=request.plan,
                    context_messages=request.context_messages,
                    trusted_instruction=request.trusted_instruction,
                    target_source=request.target_source,
                ),
                planned,
            )
            duration = max(0, round((time.perf_counter() - started) * 1000))
            result_findings = result.findings
            findings.extend(result_findings)
            route = self._route(stage_name, result, planned)
            trace.append(
                EvaluationTraceStep(
                    id=f"stage:{stage_name}",
                    kind="stage",
                    name=self._label(stage_name),
                    status=result.verdict,
                    detail=result.reason or self._detail(result.verdict, route),
                    duration_ms=duration,
                    evidence="; ".join(item.evidence for item in result_findings) or None,
                    stage=stage_name,
                    verdict=result.verdict,
                    route=route,
                    risk=result_findings[0].risk if result_findings else None,
                    confidence=(
                        min(item.confidence for item in result_findings)
                        if result_findings
                        else None
                    ),
                )
            )
            trace.extend(result.trace)

            if result.verdict == "error":
                return self._block(
                    request,
                    content,
                    result.reason or "Safety evaluation failed closed.",
                    tuple(findings),
                    tuple(trace),
                )
            if result.verdict == "uncertain":
                uncertain_risks.update(item.risk for item in result_findings)
                if stage_name == "deep_judge":
                    return self._block(
                        request,
                        content,
                        "Deep Judge could not reach a reliable policy decision.",
                        tuple(findings),
                        tuple(trace),
                    )
                continue
            if result.verdict == "unsafe":
                return self._enforce(request, result, tuple(findings), tuple(trace))

            if result.content != content:
                transformed = True
                content = result.content

        return EvaluationDecision(
            decision="transform" if transformed else "allow",
            action="redact" if transformed else "pass",
            reason="Content was safely transformed." if transformed else "All planned evaluations were decisive and safe.",
            texts=(content,) if transformed else (),
            profile_id=request.plan.profile_id,
            profile_revision=request.plan.profile_revision,
            output_delivery=request.plan.output_delivery,
            findings=tuple(findings),
            trace=tuple(trace),
        )

    @staticmethod
    def _required_deep_steps(
        planned: tuple[GuardrailPlanStep, ...],
        uncertain_risks: set[str],
    ) -> tuple[GuardrailPlanStep, ...]:
        return tuple(
            step
            for step in planned
            if (
            step.escalation == "always"
            or (step.escalation == "on_uncertain" and step.risk in uncertain_risks)
            )
        )

    @staticmethod
    def _route(
        stage: EvaluationStage,
        result: StageResult,
        steps: tuple[GuardrailPlanStep, ...],
    ) -> str:
        if result.verdict == "unsafe":
            return "enforce"
        if result.verdict == "error":
            return "fail_closed"
        if result.verdict == "uncertain":
            return "escalate"
        if stage != "deep_judge" and any(step.escalation == "always" for step in steps):
            return "escalate"
        return "complete"

    @staticmethod
    def _detail(verdict: str, route: str) -> str:
        if route == "escalate":
            return "Evaluation was uncertain or policy requires deeper judgment; escalating."
        if verdict == "unsafe":
            return "A configured risk was found; applying the profile enforcement action."
        return "Evaluation completed with a decisive safe result."

    def _enforce(
        self,
        request: EngineRequest,
        result: StageResult,
        findings: tuple[RiskFinding, ...],
        trace: tuple[EvaluationTraceStep, ...],
    ) -> EvaluationDecision:
        action = self._strongest_action(item.recommended_action for item in result.findings)
        reason = result.reason or next(
            (item.evidence for item in result.findings),
            "Profile protection was triggered.",
        )
        if action == "reject":
            return self._block(request, result.content, reason, findings, trace)
        transformed_content = self._transformed_content(action, result.content)
        return EvaluationDecision(
            decision="transform",
            action=action,
            reason=reason,
            texts=(transformed_content,),
            profile_id=request.plan.profile_id,
            profile_revision=request.plan.profile_revision,
            output_delivery=request.plan.output_delivery,
            findings=findings,
            trace=trace,
        )

    @staticmethod
    def _strongest_action(actions: object) -> EnforcementAction:
        priority: tuple[EnforcementAction, ...] = (
            "reject",
            "fallback",
            "regenerate",
            "rewrite",
            "redirect",
            "redact",
            "pass",
        )
        values = set(actions)
        return next(item for item in priority if item in values)

    @staticmethod
    def _transformed_content(action: EnforcementAction, content: str) -> str:
        if action == "redact":
            return content
        if action == "redirect":
            return "I can help with topics inside this assistant's approved purpose."
        if action == "regenerate":
            return "The response was withheld and should be regenerated under the active safety profile."
        if action == "rewrite":
            return "The response was rewritten to comply with the active safety profile."
        return "A safe fallback response was selected by the active safety profile."

    def _block(
        self,
        request: EngineRequest,
        content: str,
        reason: str,
        findings: tuple[RiskFinding, ...],
        trace: tuple[EvaluationTraceStep, ...],
    ) -> EvaluationDecision:
        del content
        return EvaluationDecision(
            decision="block",
            action="reject",
            reason=reason,
            profile_id=request.plan.profile_id,
            profile_revision=request.plan.profile_revision,
            output_delivery=request.plan.output_delivery,
            findings=findings,
            trace=trace,
        )

    @staticmethod
    def _label(stage: EvaluationStage) -> str:
        return {
            "deterministic": "Deterministic",
            "fast_semantic": "Fast Semantic",
            "deep_judge": "Deep Judge",
        }[stage]

    def _skip(self, stage: EvaluationStage, detail: str) -> EvaluationTraceStep:
        return EvaluationTraceStep(
            id=f"stage:{stage}",
            kind="stage",
            name=self._label(stage),
            status="skipped",
            detail=detail,
            stage=stage,
            route="complete",
        )
