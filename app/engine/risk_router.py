from __future__ import annotations

import re

from .contracts import (
    EngineRequest,
    EvaluationTraceStep,
    GuardrailPlanStep,
    GuardrailStage,
    RiskFinding,
    StageResult,
)


class RiskAwareStageRouter:
    """Dispatch one evaluation stage to risk-specific evaluators."""

    def __init__(self, stage: str, children: tuple[GuardrailStage, ...]) -> None:
        self.stage = stage
        self.name = stage.replace("_", " ").title()
        self._children = children
        self.supported_phases = frozenset(
            phase for child in children for phase in child.supported_phases
        )

    async def evaluate(
        self,
        request: EngineRequest,
        steps: tuple[GuardrailPlanStep, ...],
    ) -> StageResult:
        content = request.text
        findings: list[RiskFinding] = []
        trace: list[EvaluationTraceStep] = []
        uncertain = False
        handled: set[str] = set()

        for child in self._children:
            supported_risks = frozenset(getattr(child, "supported_risks", ()))
            selected = tuple(
                step for step in steps if not supported_risks or step.risk in supported_risks
            )
            if not selected or request.phase not in child.supported_phases:
                continue
            handled.update(step.id for step in selected)
            result = await child.evaluate(
                EngineRequest(
                    phase=request.phase,
                    text=content,
                    plan=request.plan,
                    context_messages=request.context_messages,
                    trusted_instruction=request.trusted_instruction,
                    target_source=request.target_source,
                ),
                selected,
            )
            findings.extend(result.findings)
            trace.append(
                EvaluationTraceStep(
                    id=f"evaluator:{self.stage}:{_slug(child.name)}",
                    kind="evaluator",
                    name=child.name,
                    status=result.verdict,
                    detail=result.reason or f"{child.name} returned {result.verdict}.",
                    stage=self.stage,
                    verdict=result.verdict,
                    risk=result.findings[0].risk if result.findings else selected[0].risk,
                    confidence=(
                        min(item.confidence for item in result.findings)
                        if result.findings
                        else None
                    ),
                )
            )
            trace.extend(result.trace)
            content = result.content
            if result.verdict in {"error", "unsafe"}:
                return StageResult(
                    verdict=result.verdict,
                    content=content,
                    findings=tuple(findings),
                    reason=result.reason,
                    trace=tuple(trace),
                )
            uncertain = uncertain or result.verdict == "uncertain"

        missing = [step.risk for step in steps if step.id not in handled]
        if missing:
            return StageResult(
                verdict="error",
                content=content,
                findings=tuple(findings),
                reason=f"No {self.stage.replace('_', ' ')} evaluator supports: {', '.join(sorted(set(missing)))}.",
                trace=tuple(trace),
            )
        return StageResult(
            verdict="uncertain" if uncertain else "safe",
            content=content,
            findings=tuple(findings),
            reason=(
                "A risk-specific evaluator requires deeper review."
                if uncertain
                else "All risk-specific evaluators returned a decisive safe classification."
            ),
            trace=tuple(trace),
        )


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
