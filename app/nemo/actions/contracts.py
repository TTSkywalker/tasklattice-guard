from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ...runtime.contracts import (
    ContentPatch,
    ContentViewSnapshot,
    EngineRequest,
    EnforcementMode,
    EvidenceScope,
    GuardContentBlock,
    GuardrailPhase,
    GuardrailPlanSnapshot,
    NeMoActionBinding,
    RiskFinding,
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
    proposed_action: str
    plan: GuardrailPlanSnapshot
    binding: NeMoActionBinding
    context_messages: tuple[dict[str, object], ...] = ()
    target_source: str = "user_input"
    mode: EnforcementMode = "enforce"
    evidence_scope: EvidenceScope = "interventions"
    content_view: ContentViewSnapshot | None = None
    active_block_id: str | None = None


@dataclass(frozen=True, slots=True)
class ActionUsage:
    provider_latency_ms: int = 0
    model_invocations: int = 0
    input_characters: int = 0


@dataclass(frozen=True, slots=True)
class ActionResult:
    verdict: str
    content: str
    findings: tuple[RiskFinding, ...] = ()
    patches: tuple[ContentPatch, ...] = ()
    confidence: float | None = None
    proposed_action: str = "pass"
    evidence: str = ""
    reason: str | None = None
    usage: ActionUsage = ActionUsage()


class ActionProvider(Protocol):
    name: str
    version: str

    async def execute(self, request: ActionRequest) -> ActionResult: ...


def engine_request(request: ActionRequest) -> EngineRequest:
    return EngineRequest(
        phase=request.rail_type,
        text=request.content,
        plan=request.plan,
        context_messages=request.context_messages,
        trusted_instruction=dict(request.trusted_context).get(
            "trusted_instruction", ""
        ),
        target_source=request.target_source,
        mode=request.mode,
        evidence_scope=request.evidence_scope,
        content_view=request.content_view,
        active_block_id=request.active_block_id,
    )


def binding_step(binding: NeMoActionBinding):
    from ...runtime.contracts import GuardrailPlanStep

    return GuardrailPlanStep(
        id=binding.id,
        risk=binding.risk,
        stage=binding.stage,
        phases=binding.phases,
        on_unsafe=binding.on_unsafe,
        escalation=binding.escalation,
        parameters=binding.parameters,
    )
