from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..runtime.contracts import (
    AutomatedReasoningResult,
    EnforcementAction,
    EvaluationTraceStep,
    GuardrailPhase,
    GuardrailPlanSnapshot,
    NeMoConfigSnapshot,
    OutputDeliveryMode,
    ControlModule,
    SafetyLevel,
    RailType,
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
ControlSourceKind = Literal["built-in", "custom"]
ControlVersionStatus = Literal["draft", "published"]
IntegrationSetupStatus = Literal[
    "awaiting_input", "awaiting_output", "verified", "disabled"
]


@dataclass(frozen=True, slots=True)
class ControlSourceFile:
    path: str
    content: str


@dataclass(frozen=True, slots=True)
class ControlParameterDefinition:
    name: str
    kind: str
    required: bool = False
    default: str | None = None
    description: str = ""


@dataclass(frozen=True, slots=True)
class RailBinding:
    rail_type: RailType
    flow_name: str
    execution_mode: Literal["detect", "mutate"]
    on_unsafe: EnforcementAction
    parallel_group: str | None = None
    priority: int | None = None
    timeout_ms: int = 2_000
    failure_mode: Literal["fail_open", "fail_closed"] = "fail_closed"
    required: bool = True
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ActionReference:
    name: str
    version: str


@dataclass(frozen=True, slots=True)
class ControlTestDefinition:
    name: str
    rail_type: RailType
    content: str
    expected_decision: str
    case_type: str = "unit"
    required: bool = True
    expected_failure: str | None = None
    concurrency_group: str | None = None


@dataclass(frozen=True, slots=True)
class ControlDraft:
    colang_version: str
    sources: tuple[ControlSourceFile, ...]
    parameter_schema: tuple[ControlParameterDefinition, ...]
    rail_bindings: tuple[RailBinding, ...]
    action_references: tuple[ActionReference, ...]
    model_dependencies: tuple[str, ...] = ()
    prompt_dependencies: tuple[str, ...] = ()
    execution_contract: tuple[tuple[str, str], ...] = ()
    tests: tuple[ControlTestDefinition, ...] = ()


@dataclass(frozen=True, slots=True)
class ControlPackage:
    id: str
    name: str
    description: str
    source: ControlSourceKind
    owner: str
    draft: ControlDraft
    draft_revision: int
    updated_at: str


@dataclass(frozen=True, slots=True)
class ControlVersion:
    control_id: str
    version: int
    name: str
    description: str
    source: ControlSourceKind
    owner: str
    colang_version: str
    sources: tuple[ControlSourceFile, ...]
    parameter_schema: tuple[ControlParameterDefinition, ...]
    rail_bindings: tuple[RailBinding, ...]
    action_references: tuple[ActionReference, ...]
    model_dependencies: tuple[str, ...]
    prompt_dependencies: tuple[str, ...]
    execution_contract: tuple[tuple[str, str], ...]
    tests: tuple[ControlTestDefinition, ...]
    checksum: str
    published_at: str


@dataclass(frozen=True, slots=True)
class GuardrailControlBinding:
    control_id: str
    control_version: int
    parameter_values: tuple[tuple[str, str], ...] = ()
    enabled_rails: tuple[RailType, ...] = ("input", "output")


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
    """A version-pinned built-in Control or custom Control in a Guardrail."""

    id: str
    name: str
    kind: Literal["built_in", "custom"]
    runtime_risk: str
    control_id: str | None
    control_version: str | None
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
    source_pack_id: str | None
    parameters: tuple[tuple[str, str], ...]
    draft_version: int
    active_version: int | None
    updated_at: str
    control_configurations: tuple[GuardrailControlConfig, ...] = ()
    control_bindings: tuple[GuardrailControlBinding, ...] = ()

@dataclass(frozen=True, slots=True)
class GuardrailVersion:
    guardrail_id: str
    version: int
    source_draft_version: int
    compiler_version: str
    plan_checksum: str
    created_at: str
    active: bool
    runtime_engine: str = "nemo"
    config_checksum: str = ""
    execution_mode: Literal["nemo_only"] = "nemo_only"


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
class IntegrationCredential:
    id: str
    key_hint: str
    created_at: str


@dataclass(frozen=True, slots=True)
class IntegrationCredentialSecret:
    id: str
    value: str
    key_hint: str
    created_at: str


@dataclass(frozen=True, slots=True)
class Integration:
    id: str
    adapter_id: str
    protocol: str
    name: str
    description: str
    enabled: bool
    key_hint: str
    credentials: tuple[IntegrationCredential, ...]
    setup_status: IntegrationSetupStatus
    runtime_status: str
    first_seen_at: str | None
    last_seen_at: str | None
    input_seen_at: str | None
    output_seen_at: str | None
    request_count: int
    error_count: int
    last_error_at: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class IntegrationRegistration:
    integration: Integration
    credential: IntegrationCredentialSecret


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
    case_type: str = "unit"
    required: bool = True
    expected_failure: str | None = None
    concurrency_group: str | None = None


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
    case_type: str = "unit"
    required: bool = True
    expected_failure: str | None = None
    concurrency_group: str | None = None


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
    case_type: str = "unit"
    required: bool = True
    expected_failure: str | None = None
    actual_failure: str | None = None
    concurrency_group: str | None = None


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
    integration_id: str | None = None


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
    rail_invocations: int = 0
    action_invocations: int = 0
    model_invocations: int = 0
    queue_latency_ms: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    runtime_engine: str = ""
    config_checksum: str = ""
    fail_closed: bool = False
    active_concurrency: int = 0
    provider_latency_ms: int = 0
    slo_breached: bool = False


@dataclass(frozen=True, slots=True)
class RuntimeStepMetricEvent:
    """Privacy-safe timing and outcome for one activated NeMo rail or Action."""

    id: str
    created_at: str
    guardrail_id: str
    guardrail_version: int
    assignment_id: str | None
    integration_id: str | None
    protocol: str
    phase: str
    kind: str
    name: str
    risk: str | None
    stage: str | None
    outcome: str
    latency_ms: int
    timed_out: bool
    runtime_engine: str
    config_checksum: str
    control_id: str | None = None
    control_version: int | None = None
    rail_type: str | None = None
    flow_name: str | None = None
    action_name: str | None = None
    action_version: str | None = None
    parallel_group: str | None = None
    timeout_ms: int | None = None
    provider_latency_ms: int = 0


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


class ConflictError(ControlPlaneError):
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
    nemo_config: NeMoConfigSnapshot | None = None
