from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol


GuardrailPhase = Literal["input", "output"]
EvaluationStage = Literal["deterministic", "fast_semantic", "deep_judge"]
EvaluatorVerdict = Literal["safe", "unsafe", "uncertain", "error"]
RouteDecision = Literal["complete", "enforce", "escalate", "fail_open", "fail_closed"]
PolicyDecision = Literal["allow", "transform", "block"]
EnforcementAction = Literal[
    "pass",
    "redact",
    "rewrite",
    "regenerate",
    "redirect",
    "reject",
    "fallback",
]
SafetyLevel = Literal["balanced", "strict"]
OutputDeliveryMode = Literal["interruptible", "window_buffered", "full_buffered"]
EscalationMode = Literal["never", "on_uncertain", "always"]
MatcherKind = Literal["header", "jwt_claim", "field"]


@dataclass(frozen=True, slots=True)
class EvaluationTraceStep:
    id: str
    kind: str
    name: str
    status: str
    detail: str
    duration_ms: int = 0
    parent_id: str | None = None
    evidence: str | None = None
    stage: EvaluationStage | None = None
    verdict: EvaluatorVerdict | None = None
    route: RouteDecision | None = None
    risk: str | None = None
    confidence: float | None = None


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Gateway-normalized, trusted attributes used for Workload resolution."""

    gateway: str
    gateway_id: str | None = None
    headers: tuple[tuple[str, str], ...] = ()
    jwt_claims: tuple[tuple[str, str], ...] = ()
    fields: tuple[tuple[str, str], ...] = ()

    def value(self, kind: MatcherKind, key: str) -> str | None:
        source = {
            "header": self.headers,
            "jwt_claim": self.jwt_claims,
            "field": self.fields,
        }[kind]
        lookup = key.lower() if kind == "header" else key
        return next(
            (
                value
                for candidate, value in source
                if (candidate.lower() if kind == "header" else candidate) == lookup
            ),
            None,
        )


@dataclass(frozen=True, slots=True)
class EvaluationRequest:
    phase: GuardrailPhase
    texts: tuple[str, ...]
    context: RequestContext
    call_id: str | None = None
    messages: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True, slots=True)
class GuardrailPlanStep:
    id: str
    risk: str
    stage: EvaluationStage
    phases: tuple[GuardrailPhase, ...]
    on_unsafe: EnforcementAction
    escalation: EscalationMode = "never"
    threshold: float | None = None
    parameters: tuple[tuple[str, str], ...] = ()

    def parameter(self, name: str) -> str | None:
        return next((value for key, value in self.parameters if key == name), None)


@dataclass(frozen=True, slots=True)
class GuardrailPlanSnapshot:
    profile_id: str
    profile_revision: int
    compiler_version: str
    safety_level: SafetyLevel
    output_delivery: OutputDeliveryMode
    steps: tuple[GuardrailPlanStep, ...]

    def steps_for(
        self,
        phase: GuardrailPhase,
        stage: EvaluationStage | None = None,
    ) -> tuple[GuardrailPlanStep, ...]:
        return tuple(
            step
            for step in self.steps
            if phase in step.phases and (stage is None or step.stage == stage)
        )


@dataclass(frozen=True, slots=True)
class RiskFinding:
    risk: str
    verdict: EvaluatorVerdict
    confidence: float
    evidence: str
    recommended_action: EnforcementAction
    replacement: str | None = None


@dataclass(frozen=True, slots=True)
class StageResult:
    verdict: EvaluatorVerdict
    content: str
    findings: tuple[RiskFinding, ...] = ()
    reason: str | None = None
    trace: tuple[EvaluationTraceStep, ...] = ()


@dataclass(frozen=True, slots=True)
class EvaluationDecision:
    decision: PolicyDecision
    action: EnforcementAction
    reason: str | None = None
    texts: tuple[str, ...] = ()
    profile_id: str | None = None
    profile_revision: int | None = None
    workload_id: str | None = None
    gateway_id: str | None = None
    output_delivery: OutputDeliveryMode | None = None
    findings: tuple[RiskFinding, ...] = ()
    trace: tuple[EvaluationTraceStep, ...] = ()


@dataclass(frozen=True, slots=True)
class PlanResolution:
    plan: GuardrailPlanSnapshot
    workload_id: str
    gateway_id: str | None = None
    trace: tuple[EvaluationTraceStep, ...] = ()


@dataclass(frozen=True, slots=True)
class EngineRequest:
    phase: GuardrailPhase
    text: str
    plan: GuardrailPlanSnapshot
    context_messages: tuple[dict[str, Any], ...] = ()
    trusted_instruction: str = ""
    target_source: str = "user_input"


class GuardrailStage(Protocol):
    name: str
    stage: EvaluationStage
    supported_phases: frozenset[GuardrailPhase]

    async def evaluate(
        self,
        request: EngineRequest,
        steps: tuple[GuardrailPlanStep, ...],
    ) -> StageResult: ...


class GuardrailEngine(Protocol):
    name: str
    supported_phases: frozenset[GuardrailPhase]

    async def evaluate(self, request: EngineRequest) -> EvaluationDecision: ...


class PlanResolver(Protocol):
    def resolve(self, context: RequestContext) -> PlanResolution: ...
