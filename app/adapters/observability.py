from __future__ import annotations

import time

from ..control_plane.service import ControlPlaneService
from ..engine.contracts import EvaluationDecision


def record_runtime_decision(
    control_plane: ControlPlaneService,
    *,
    decision: EvaluationDecision,
    integration_id: str,
    protocol: str,
    phase: str,
    started: float,
    detail: str,
) -> None:
    usage = decision.usage
    control_plane.record_decision(
        outcome=decision.decision,
        guardrail_id=decision.guardrail_id,
        guardrail_version=decision.guardrail_version,
        assignment_id=decision.assignment_id,
        integration_id=integration_id,
        protocol=protocol,
        phase=phase,
        action=decision.action,
        risk=decision.findings[0].risk if decision.findings else None,
        latency_ms=_latency_ms(started),
        timed_out=_timed_out(decision),
        module_invocations=usage.module_invocations if usage else len(decision.assessments),
        evaluator_invocations=usage.evaluator_invocations if usage else 0,
        detail=detail,
    )


def record_runtime_failure(
    control_plane: ControlPlaneService,
    *,
    integration_id: str,
    protocol: str,
    phase: str,
    started: float,
    outcome: str,
    detail: str,
) -> None:
    control_plane.record_decision(
        outcome=outcome,
        guardrail_id=None,
        assignment_id=None,
        integration_id=integration_id,
        protocol=protocol,
        phase=phase,
        action="reject" if outcome == "block" else "error",
        risk=None,
        latency_ms=_latency_ms(started),
        detail=detail,
    )


def _latency_ms(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1_000))


def _timed_out(decision: EvaluationDecision) -> bool:
    return any(
        "timeout" in step.detail.casefold()
        for assessment in decision.assessments
        for step in assessment.trace
    )
