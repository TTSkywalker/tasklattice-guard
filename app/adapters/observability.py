from __future__ import annotations

import logging
import time
import uuid

from ..control_plane.service import ControlPlaneService
from ..runtime.contracts import ProtectionDecision, ProtectionRequest


logger = logging.getLogger(__name__)


def record_runtime_decision(
    control_plane: ControlPlaneService,
    *,
    decision: ProtectionDecision,
    integration_id: str | None,
    protocol: str,
    phase: str,
    started: float,
    detail: str,
    request: ProtectionRequest | None = None,
    call_id: str | None = None,
    content_before: tuple[dict[str, object], ...] = (),
) -> None:
    usage = decision.usage
    trace_id = f"trace-{uuid.uuid4().hex}"
    latency_ms = _latency_ms(started)
    timed_out = _timed_out(decision)
    fail_closed = usage.fail_closed if usage else False
    control_plane.record_decision(
        trace_id=trace_id,
        outcome=decision.decision,
        guardrail_id=decision.guardrail_id,
        guardrail_version=decision.guardrail_version,
        deployment_id=decision.deployment_id,
        integration_id=integration_id,
        protocol=protocol,
        phase=phase,
        action=decision.action,
        risk=decision.findings[0].risk if decision.findings else None,
        latency_ms=latency_ms,
        timed_out=timed_out,
        module_invocations=usage.module_invocations if usage else len(decision.assessments),
        evaluator_invocations=usage.evaluator_invocations if usage else 0,
        rail_invocations=usage.rail_invocations if usage else 0,
        action_invocations=usage.action_invocations if usage else 0,
        model_invocations=usage.model_invocations if usage else 0,
        queue_latency_ms=usage.queue_latency_ms if usage else 0,
        cache_hits=usage.cache_hits if usage else 0,
        cache_misses=usage.cache_misses if usage else 0,
        runtime_engine=usage.runtime_engine if usage else "",
        config_checksum=usage.config_checksum if usage else "",
        fail_closed=fail_closed,
        active_concurrency=usage.active_concurrency if usage else 0,
        provider_latency_ms=usage.provider_latency_ms if usage else 0,
        detail=detail,
        findings=decision.findings,
    )
    control_plane.record_runtime_steps(
        trace_id=trace_id,
        guardrail_id=decision.guardrail_id,
        guardrail_version=decision.guardrail_version,
        deployment_id=decision.deployment_id,
        integration_id=integration_id,
        protocol=protocol,
        phase=phase,
        trace=decision.trace,
        runtime_engine=usage.runtime_engine if usage else "",
        config_checksum=usage.config_checksum if usage else "",
    )
    before = _request_content(request) if request is not None else content_before
    try:
        control_plane.record_runtime_log(
            trace_id=trace_id,
            call_id=request.call_id if request is not None else call_id,
            guardrail_id=decision.guardrail_id,
            guardrail_version=decision.guardrail_version,
            deployment_id=decision.deployment_id,
            integration_id=integration_id,
            protocol=protocol,
            phase=phase,
            outcome=decision.decision,
            action=decision.action,
            risk=decision.findings[0].risk if decision.findings else None,
            latency_ms=latency_ms,
            timed_out=timed_out,
            fail_closed=fail_closed,
            detail=detail,
            content_before=before,
            content_after=_decision_content(decision, before),
        )
    except Exception:
        # Protection decisions must remain available even if optional content
        # logging is temporarily unavailable.
        logger.exception("Runtime Prompt History persistence failed.")


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
    trace_id = f"trace-{uuid.uuid4().hex}"
    control_plane.record_decision(
        trace_id=trace_id,
        outcome=outcome,
        guardrail_id=None,
        deployment_id=None,
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


def _timed_out(decision: ProtectionDecision) -> bool:
    return any(step.timed_out for step in decision.trace)


def _request_content(
    request: ProtectionRequest,
) -> tuple[dict[str, object], ...]:
    if request.content_blocks:
        return tuple(
            {
                "id": block.id,
                "role": block.role,
                "source": block.source,
                "text": block.text,
            }
            for block in request.content_blocks
            if block.guard_content and block.trust != "trusted"
        )
    role = "user_input" if request.phase == "input" else "model_output"
    return tuple(
        {
            "id": f"{request.phase}:{index}",
            "role": role,
            "source": role,
            "text": text,
        }
        for index, text in enumerate(request.texts)
    )


def _decision_content(
    decision: ProtectionDecision,
    before: tuple[dict[str, object], ...],
) -> tuple[dict[str, object], ...]:
    if decision.decision != "transform":
        return ()
    if decision.content_results:
        return tuple(
            {
                "id": item.id,
                "role": item.role,
                "source": item.source,
                "text": item.text,
            }
            for item in decision.content_results
            if item.evaluated and item.text is not None
        )
    return tuple(
        {**item, "text": decision.texts[index]}
        for index, item in enumerate(before)
        if index < len(decision.texts)
    )
