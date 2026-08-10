from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..engine.contracts import (
    EnforcementAction,
    EvaluationTraceStep,
    GuardrailPhase,
    GuardrailPlanSnapshot,
    OutputDeliveryMode,
    SafetyLevel,
)


ProfileStatus = Literal["needs_testing", "ready", "protected"]
EvaluationRunStatus = Literal["passed", "failed", "incomplete"]
TestCaseOrigin = Literal["generated", "custom"]
TestTargetSource = Literal["user_input", "retrieved_content", "tool_output"]


@dataclass(frozen=True, slots=True)
class ProtectionDefinition:
    id: str
    display_name: str
    description: str
    domain: str
    default_phases: tuple[GuardrailPhase, ...]
    default_action: EnforcementAction
    allowed_actions: tuple[EnforcementAction, ...]
    available_stages: tuple[str, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TemplateRisk:
    risk: str
    action: EnforcementAction


@dataclass(frozen=True, slots=True)
class TemplateParameterDefinition:
    name: str
    label: str
    kind: str
    required: bool
    placeholder: str
    description: str = ""


@dataclass(frozen=True, slots=True)
class SafetyTemplate:
    id: str
    name: str
    description: str
    purpose: str
    allowed_topics: tuple[str, ...]
    restricted_topics: tuple[str, ...]
    risks: tuple[TemplateRisk, ...]
    safety_level: SafetyLevel
    output_delivery: OutputDeliveryMode
    source: str = "TaskLattice"
    version: str = "builtin"
    domain: str = "Enterprise Safety"
    collections: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    controls: tuple[str, ...] = ()
    parameters: tuple[TemplateParameterDefinition, ...] = ()


@dataclass(frozen=True, slots=True)
class ProfileRisk:
    risk: str
    action: EnforcementAction


@dataclass(frozen=True, slots=True)
class SafetyProfile:
    id: str
    name: str
    purpose: str
    allowed_topics: tuple[str, ...]
    restricted_topics: tuple[str, ...]
    risks: tuple[ProfileRisk, ...]
    safety_level: SafetyLevel
    output_delivery: OutputDeliveryMode
    source_template_id: str | None
    template_parameters: tuple[tuple[str, str], ...]
    draft_version: int
    active_revision: int | None
    updated_at: str

@dataclass(frozen=True, slots=True)
class ProfileRevision:
    profile_id: str
    revision: int
    source_draft_version: int
    compiler_version: str
    plan_checksum: str
    created_at: str
    active: bool


@dataclass(frozen=True, slots=True)
class WorkloadFilterRule:
    field: str
    operator: str
    value: str
    key: str = ""


@dataclass(frozen=True, slots=True)
class WorkloadFilterExpression:
    combinator: str
    rules: tuple[WorkloadFilterRule | WorkloadFilterExpression, ...]


@dataclass(frozen=True, slots=True)
class ProtectedWorkload:
    id: str
    name: str
    profile_id: str
    profile_revision: int
    filter: WorkloadFilterExpression
    enabled: bool
    updated_at: str


@dataclass(frozen=True, slots=True)
class Gateway:
    id: str
    protocol: str
    name: str
    description: str
    environment: str
    enabled: bool
    credential_prefix: str
    verification_status: str
    runtime_status: str
    last_seen_at: str | None
    request_count: int
    error_count: int
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class GatewayRegistration:
    gateway: Gateway
    credential: str


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    id: str
    name: str
    risk: str
    phase: GuardrailPhase
    content: str
    expected_decision: str
    trusted_instruction: str = ""
    target_source: TestTargetSource = "user_input"


@dataclass(frozen=True, slots=True)
class ProfileTestCase:
    id: str
    profile_id: str
    name: str
    risk: str
    phase: GuardrailPhase
    content: str
    expected_decision: str
    origin: TestCaseOrigin
    updated_at: str
    trusted_instruction: str = ""
    target_source: TestTargetSource = "user_input"


@dataclass(frozen=True, slots=True)
class EvaluationCaseResult:
    case_id: str
    name: str
    risk: str
    expected_decision: str
    actual_decision: str
    passed: bool
    stage_reached: str
    latency_ms: int
    reason: str
    phase: GuardrailPhase = "input"
    input_content: str = ""
    action: EnforcementAction = "pass"
    output_content: str = ""
    findings: tuple[dict[str, object], ...] = ()
    trace: tuple[dict[str, object], ...] = ()
    trusted_instruction: str = ""
    target_source: TestTargetSource = "user_input"


@dataclass(frozen=True, slots=True)
class EvaluationMetrics:
    total: int
    passed: int
    compliance_rate: float
    false_positive_rate: float
    false_negative_rate: float
    deep_escalation_rate: float
    p95_latency_ms: int


@dataclass(frozen=True, slots=True)
class EvaluationRun:
    id: str
    profile_id: str
    profile_revision: int | None
    source_draft_version: int
    status: EvaluationRunStatus
    metrics: EvaluationMetrics
    results: tuple[EvaluationCaseResult, ...]
    created_at: str


@dataclass(frozen=True, slots=True)
class DecisionEvent:
    id: str
    created_at: str
    kind: str
    outcome: str
    profile_id: str | None
    workload_id: str | None
    risk: str | None
    detail: str


@dataclass(frozen=True, slots=True)
class ProfileEvaluation:
    decision: str
    action: str
    content: str
    reason: str
    latency_ms: int
    findings: tuple[dict[str, object], ...]
    trace: tuple[EvaluationTraceStep, ...]


class ControlPlaneError(RuntimeError):
    pass


class NotFoundError(ControlPlaneError):
    pass


class ValidationError(ControlPlaneError):
    pass


class PlanCompilationError(ControlPlaneError):
    pass


class PlanResolutionError(ControlPlaneError):
    pass


class GatewayAuthenticationError(ControlPlaneError):
    pass


@dataclass(frozen=True, slots=True)
class TestedProfileVersion:
    profile: SafetyProfile
    revision: ProfileRevision
    plan: GuardrailPlanSnapshot
