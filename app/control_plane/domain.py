from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..engine.contracts import (
    AutomatedReasoningResult,
    EnforcementAction,
    EvaluationTraceStep,
    GuardrailPhase,
    GuardrailPlanSnapshot,
    OutputDeliveryMode,
    ControlModule,
    SafetyLevel,
)


GuardrailStatus = Literal["needs_testing", "ready", "protected"]
EvaluationRunStatus = Literal["passed", "failed", "incomplete"]
TestCaseOrigin = Literal["generated", "custom"]
TestTargetSource = Literal[
    "user_input",
    "retrieved_content",
    "tool_output",
    "model_output",
]


@dataclass(frozen=True, slots=True)
class ControlDefinition:
    id: str
    display_name: str
    description: str
    domain: str
    default_phases: tuple[GuardrailPhase, ...]
    default_action: EnforcementAction
    allowed_actions: tuple[EnforcementAction, ...]
    available_stages: tuple[str, ...]
    limitations: tuple[str, ...]
    module: ControlModule


@dataclass(frozen=True, slots=True)
class TemplateControl:
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
class GuardrailTemplate:
    id: str
    name: str
    description: str
    purpose: str
    allowed_topics: tuple[str, ...]
    restricted_topics: tuple[str, ...]
    default_controls: tuple[TemplateControl, ...]
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
class ControlTemplatePackReference:
    id: str
    name: str
    domain: str


@dataclass(frozen=True, slots=True)
class ControlTemplateRule:
    id: str
    name: str
    detector: Literal["regex", "keyword", "category"]
    action: str
    description: str = ""
    expression: str | None = None
    context_expression: str | None = None
    redaction: str | None = None
    severity_threshold: str | None = None
    identifiers: tuple[str, ...] = ()
    conditions: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    always_block: tuple[str, ...] = ()
    exceptions: tuple[str, ...] = ()
    phrase_patterns: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ControlTemplate:
    id: str
    name: str
    description: str
    source: str
    version: str
    status: Literal["built_in", "registered"]
    phases: tuple[GuardrailPhase, ...]
    default_action: str
    allowed_actions: tuple[str, ...]
    detector_types: tuple[Literal["regex", "keyword", "category"], ...]
    rules: tuple[ControlTemplateRule, ...]
    packs: tuple[ControlTemplatePackReference, ...]
    tags: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GuardrailControl:
    risk: str
    action: EnforcementAction
    reasoning_policy: AutomatedReasoningPolicyBinding | None = None


@dataclass(frozen=True, slots=True)
class GuardrailRuleConfig:
    """A reviewed Rule enabled inside one Guardrail Control instance."""

    id: str
    name: str
    detector: str
    action: str
    phases: tuple[GuardrailPhase, ...]
    enabled: bool = True
    description: str = ""
    expression: str | None = None
    keywords: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GuardrailControlConfig:
    """A version-pinned Control Template or custom Control in a Guardrail."""

    id: str
    name: str
    kind: Literal["template", "custom"]
    runtime_risk: str
    template_id: str | None
    template_version: str | None
    rules: tuple[GuardrailRuleConfig, ...]


@dataclass(frozen=True, slots=True)
class AutomatedReasoningPolicyBinding:
    """Draft-time binding to an externally deployed immutable policy version."""

    policy_id: str
    policy_version: str
    confidence_threshold: float = 0.8


@dataclass(frozen=True, slots=True)
class Guardrail:
    id: str
    name: str
    purpose: str
    allowed_topics: tuple[str, ...]
    restricted_topics: tuple[str, ...]
    controls: tuple[GuardrailControl, ...]
    safety_level: SafetyLevel
    output_delivery: OutputDeliveryMode
    source_template_id: str | None
    template_parameters: tuple[tuple[str, str], ...]
    draft_version: int
    active_version: int | None
    updated_at: str
    control_configurations: tuple[GuardrailControlConfig, ...] = ()

@dataclass(frozen=True, slots=True)
class GuardrailVersion:
    guardrail_id: str
    version: int
    source_draft_version: int
    compiler_version: str
    plan_checksum: str
    created_at: str
    active: bool


@dataclass(frozen=True, slots=True)
class TrafficScopeRule:
    field: str
    operator: str
    value: str
    key: str = ""


@dataclass(frozen=True, slots=True)
class TrafficScopeExpression:
    combinator: str
    rules: tuple[TrafficScopeRule | TrafficScopeExpression, ...]


@dataclass(frozen=True, slots=True)
class GuardrailAssignment:
    id: str
    name: str
    guardrail_id: str
    guardrail_version: int
    traffic_scope: TrafficScopeExpression
    enabled: bool
    updated_at: str


@dataclass(frozen=True, slots=True)
class Integration:
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
class IntegrationRegistration:
    integration: Integration
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
    query: str = ""
    grounding_sources: tuple[str, ...] = ()
    expected_reasoning_result: AutomatedReasoningResult | None = None


@dataclass(frozen=True, slots=True)
class GuardrailTestCase:
    id: str
    guardrail_id: str
    name: str
    risk: str
    phase: GuardrailPhase
    content: str
    expected_decision: str
    origin: TestCaseOrigin
    updated_at: str
    trusted_instruction: str = ""
    target_source: TestTargetSource = "user_input"
    query: str = ""
    grounding_sources: tuple[str, ...] = ()
    expected_reasoning_result: AutomatedReasoningResult | None = None


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
    query: str = ""
    grounding_sources: tuple[str, ...] = ()
    expected_reasoning_result: AutomatedReasoningResult | None = None
    actual_reasoning_result: AutomatedReasoningResult | None = None


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
    guardrail_id: str
    guardrail_version: int | None
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
    guardrail_id: str | None
    assignment_id: str | None
    risk: str | None
    detail: str


@dataclass(frozen=True, slots=True)
class RuntimeMetricEvent:
    """Privacy-safe dimensions for one Guardrail runtime evaluation."""

    id: str
    created_at: str
    guardrail_id: str | None
    guardrail_version: int | None
    assignment_id: str | None
    integration_id: str | None
    protocol: str
    phase: str
    outcome: str
    action: str
    risk: str | None
    latency_ms: int
    timed_out: bool
    module_invocations: int
    evaluator_invocations: int


@dataclass(frozen=True, slots=True)
class GuardrailEvaluation:
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


class IntegrationAuthenticationError(ControlPlaneError):
    pass


@dataclass(frozen=True, slots=True)
class TestedGuardrailVersion:
    guardrail: Guardrail
    version: GuardrailVersion
    plan: GuardrailPlanSnapshot
