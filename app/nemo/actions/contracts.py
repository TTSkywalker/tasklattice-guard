from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ...runtime.content_views import content_view
from ...runtime.contracts import (
    ContentPatch,
    ContentViewSnapshot,
    EnforcementMode,
    EnforcementAction,
    EvidenceScope,
    EvaluatorVerdict,
    GuardContentBlock,
    GuardrailPhase,
    GuardrailPlanSnapshot,
    NeMoActionBinding,
    RiskFinding,
    RequestContext,
    RuntimeTraceStep,
)


@dataclass(frozen=True, slots=True)
class ActionRequest:
    content: str
    rail_type: GuardrailPhase
    guardrail_id: str
    guardrail_version: int
    policy_id: str | None
    policy_version: int | None
    trusted_context: tuple[tuple[str, str], ...]
    content_blocks: tuple[GuardContentBlock, ...]
    deadline: float
    parameters: tuple[tuple[str, str], ...]
    risk: str
    proposed_action: EnforcementAction
    plan: GuardrailPlanSnapshot
    binding: NeMoActionBinding
    context_messages: tuple[dict[str, object], ...] = ()
    target_source: str = "user_input"
    mode: EnforcementMode = "enforce"
    evidence_scope: EvidenceScope = "interventions"
    content_view: ContentViewSnapshot | None = None
    active_block_id: str | None = None
    request_context: RequestContext | None = None


@dataclass(frozen=True, slots=True)
class ActionUsage:
    provider_latency_ms: int = 0
    model_invocations: int = 0
    input_characters: int = 0


@dataclass(frozen=True, slots=True)
class ActionResult:
    verdict: EvaluatorVerdict
    content: str
    findings: tuple[RiskFinding, ...] = ()
    patches: tuple[ContentPatch, ...] = ()
    confidence: float | None = None
    proposed_action: EnforcementAction = "pass"
    evidence: str = ""
    reason: str | None = None
    trace: tuple[RuntimeTraceStep, ...] = ()
    usage: ActionUsage = ActionUsage()


class ActionProvider(Protocol):
    name: str
    version: str
    risks: frozenset[str]
    rails: frozenset[GuardrailPhase]

    async def execute(self, request: ActionRequest) -> ActionResult: ...


def action_view(request: ActionRequest) -> ContentViewSnapshot:
    """Return the immutable content view supplied to a NeMo Action."""
    if request.content_view is not None:
        return request.content_view
    if not request.content_blocks:
        raise ValueError("A NeMo Action request must include a content view.")
    active_block_id = request.active_block_id or request.content_blocks[0].id
    return content_view(request.content_blocks, active_block_id)


def action_result(
    request: ActionRequest,
    verdict: EvaluatorVerdict,
    content: str,
    *,
    findings: tuple[RiskFinding, ...] = (),
    patches: tuple[ContentPatch, ...] = (),
    reason: str | None = None,
    trace: tuple[RuntimeTraceStep, ...] = (),
    usage: ActionUsage = ActionUsage(),
) -> ActionResult:
    """Build the single result contract returned by every NeMo Action provider."""
    confidence = next((item.confidence for item in findings), None)
    return ActionResult(
        verdict=verdict,
        content=content,
        findings=findings,
        patches=patches,
        confidence=confidence,
        proposed_action=request.proposed_action,
        evidence=reason or "",
        reason=reason,
        trace=trace,
        usage=usage,
    )
