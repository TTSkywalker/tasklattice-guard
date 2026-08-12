from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol


GuardrailPhase = Literal["input", "output"]
RailType = Literal["input", "output", "retrieval", "dialog", "execution"]
EvaluationStage = Literal["deterministic", "fast_semantic", "deep_judge"]
EvaluatorVerdict = Literal["safe", "unsafe", "uncertain", "error"]
RouteDecision = Literal["complete", "enforce", "escalate", "fail_open", "fail_closed"]
PolicyDecision = Literal["allow", "transform", "block"]
ControlModule = Literal[
    "data_protection",
    "interaction_safety",
    "business_assurance",
]
ContentView = Literal["original", "masked", "previous_output", "complete_output"]
ContentRole = Literal[
    "trusted_instruction",
    "user_input",
    "query",
    "retrieved_content",
    "grounding_source",
    "tool_output",
    "model_output",
]
ContentTrust = Literal["trusted", "untrusted"]
ContentQualifier = Literal["guard_content", "query", "grounding_source"]
GroundingFilterType = Literal["grounding", "relevance"]
ClaimSupport = Literal["supported", "unsupported", "uncertain"]
AutomatedReasoningResult = Literal[
    "valid",
    "invalid",
    "satisfiable",
    "impossible",
    "translation_ambiguous",
    "too_complex",
    "no_translations",
]
FailureMode = Literal["fail_open", "fail_closed"]
FragmentStatus = Literal["pass", "intervene", "needs_context", "uncovered", "error"]
CoverageStatus = Literal["complete", "partial", "none"]
EvaluationMode = Literal["enforce", "detect"]
EvidenceScope = Literal["interventions", "full"]
EnforcementAction = Literal[
    "pass",
    "redact",
    "rewrite",
    "regenerate",
    "redirect",
    "reject",
    "fallback",
    "clarify",
]
SafetyLevel = Literal["balanced", "strict"]
OutputDeliveryMode = Literal["interruptible", "window_buffered", "full_buffered"]
EscalationMode = Literal["never", "on_uncertain", "always"]
MatcherKind = Literal["header", "jwt_claim", "field"]
NeMoRuntimeEngine = Literal["iorails", "llmrails"]
RuntimeExecutionMode = Literal["nemo_only"]
ControlExecutionMode = Literal["detect", "mutate"]


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
    content_block_id: str | None = None


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Integration-normalized, trusted attributes used for Assignment resolution."""

    protocol: str
    integration_id: str | None = None
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
class GuardContentBlock:
    """One immutable content unit crossing a guardrail trust boundary."""

    id: str
    text: str
    role: ContentRole
    trust: ContentTrust
    source: str
    qualifiers: tuple[ContentQualifier, ...] = ("guard_content",)

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("Content block identifiers cannot be empty.")
        if not self.source.strip():
            raise ValueError("Content block sources cannot be empty.")
        if len(set(self.qualifiers)) != len(self.qualifiers):
            raise ValueError("Content block qualifiers must be unique.")
        if self.trust == "trusted" and self.role != "trusted_instruction":
            raise ValueError("Only trusted-instruction blocks may cross as trusted content.")
        if self.role == "trusted_instruction" and (
            self.trust != "trusted" or "guard_content" in self.qualifiers
        ):
            raise ValueError(
                "Trusted instructions must be trusted context, not guard targets."
            )

    @property
    def guard_content(self) -> bool:
        return "guard_content" in self.qualifiers


@dataclass(frozen=True, slots=True)
class ContentViewSnapshot:
    """An immutable projection over content blocks with one active evaluation target."""

    kind: ContentView
    blocks: tuple[GuardContentBlock, ...]
    active_block_id: str
    source_digest: str

    def __post_init__(self) -> None:
        ids = tuple(block.id for block in self.blocks)
        if len(set(ids)) != len(ids):
            raise ValueError("Content block identifiers must be unique within a view.")
        if self.active_block_id not in ids:
            raise ValueError("The active content block is unavailable in the content view.")

    @property
    def active_block(self) -> GuardContentBlock:
        return next(block for block in self.blocks if block.id == self.active_block_id)


@dataclass(frozen=True, slots=True)
class EvaluationRequest:
    phase: GuardrailPhase
    texts: tuple[str, ...]
    context: RequestContext
    content_blocks: tuple[GuardContentBlock, ...] = ()
    call_id: str | None = None
    messages: tuple[dict[str, Any], ...] = ()
    mode: EvaluationMode = "enforce"
    evidence_scope: EvidenceScope = "interventions"


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
class GuardrailPlanModule:
    """One independently schedulable control module in a compiled plan."""

    id: str
    module: ControlModule
    phase: GuardrailPhase
    step_ids: tuple[str, ...]
    depends_on: tuple[str, ...] = ()
    input_view: ContentView = "original"
    required_for_release: bool = True
    timeout_ms: int = 2_000
    failure_mode: FailureMode = "fail_closed"


@dataclass(frozen=True, slots=True)
class AutomatedReasoningPolicySnapshot:
    """Immutable reference to one deployed formal policy version."""

    id: str
    policy_id: str
    policy_version: str
    confidence_threshold: float = 0.8

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.policy_id.strip() or not self.policy_version.strip():
            raise ValueError("Automated Reasoning policy identifiers cannot be empty.")
        if not 0 <= self.confidence_threshold <= 1:
            raise ValueError("Automated Reasoning confidence threshold must be between 0 and 1.")


@dataclass(frozen=True, slots=True)
class ControlSourceSnapshot:
    """One immutable Colang source file embedded in a released Control version."""

    path: str
    content: str


@dataclass(frozen=True, slots=True)
class ControlRailBindingSnapshot:
    """A version-pinned mapping from a Control flow to a NeMo rail."""

    rail_type: RailType
    flow_name: str
    execution_mode: ControlExecutionMode
    on_unsafe: EnforcementAction
    parallel_group: str | None = None
    priority: int | None = None
    timeout_ms: int = 2_000
    failure_mode: FailureMode = "fail_closed"
    required: bool = True
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ControlActionReferenceSnapshot:
    name: str
    version: str


@dataclass(frozen=True, slots=True)
class ControlVersionSnapshot:
    """Immutable Control implementation resolved into a Guardrail plan."""

    control_id: str
    version: int
    name: str
    source: str
    colang_version: str
    sources: tuple[ControlSourceSnapshot, ...]
    parameter_schema: tuple[tuple[str, str], ...]
    rail_bindings: tuple[ControlRailBindingSnapshot, ...]
    action_references: tuple[ControlActionReferenceSnapshot, ...]
    model_dependencies: tuple[str, ...]
    prompt_dependencies: tuple[str, ...]
    execution_contract: tuple[tuple[str, str], ...]
    tests: tuple[tuple[str, str], ...]
    checksum: str


@dataclass(frozen=True, slots=True)
class GuardrailControlBindingSnapshot:
    control_id: str
    control_version: int
    parameter_values: tuple[tuple[str, str], ...] = ()
    enabled_rails: tuple[RailType, ...] = ("input", "output")


@dataclass(frozen=True, slots=True)
class GuardrailPlanSnapshot:
    guardrail_id: str
    guardrail_version: int
    compiler_version: str
    safety_level: SafetyLevel
    output_delivery: OutputDeliveryMode
    steps: tuple[GuardrailPlanStep, ...]
    modules: tuple[GuardrailPlanModule, ...] = ()
    reasoning_policies: tuple[AutomatedReasoningPolicySnapshot, ...] = ()
    control_versions: tuple[ControlVersionSnapshot, ...] = ()
    control_bindings: tuple[GuardrailControlBindingSnapshot, ...] = ()

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

    def modules_for(self, phase: GuardrailPhase) -> tuple[GuardrailPlanModule, ...]:
        return tuple(module for module in self.modules if module.phase == phase)

    def reasoning_policy(self, snapshot_id: str) -> AutomatedReasoningPolicySnapshot:
        try:
            return next(item for item in self.reasoning_policies if item.id == snapshot_id)
        except StopIteration as error:
            raise KeyError(f"Unknown Automated Reasoning policy snapshot {snapshot_id!r}.") from error


@dataclass(frozen=True, slots=True)
class NeMoActionBinding:
    """One version-pinned TaskLattice evaluator exposed as a NeMo action."""

    id: str
    risk: str
    stage: EvaluationStage
    phases: tuple[GuardrailPhase, ...]
    on_unsafe: EnforcementAction
    escalation: EscalationMode = "never"
    timeout_ms: int = 2_000
    parameters: tuple[tuple[str, str], ...] = ()
    control_id: str | None = None
    control_version: int | None = None
    flow_name: str | None = None
    action_name: str | None = None
    action_version: str | None = None
    parallel_group: str | None = None
    execution_mode: ControlExecutionMode = "detect"
    failure_mode: FailureMode = "fail_closed"
    depends_on: tuple[str, ...] = ()

    def parameter(self, name: str) -> str | None:
        return next((value for key, value in self.parameters if key == name), None)


@dataclass(frozen=True, slots=True)
class NeMoConfigSnapshot:
    """Immutable NeMo configuration compiled for one released Guardrail version."""

    guardrail_id: str
    guardrail_version: int
    compiler_version: str
    output_delivery: OutputDeliveryMode
    config_yaml: str
    colang_content: str
    prompts_yaml: str = ""
    action_bindings: tuple[NeMoActionBinding, ...] = ()
    required_models: tuple[str, ...] = ()
    required_features: tuple[str, ...] = ()
    runtime_engine: NeMoRuntimeEngine = "llmrails"
    colang_version: str = "2.x"
    rail_flows: tuple[tuple[str, str], ...] = ()
    dependency_manifest: tuple[tuple[str, str, str], ...] = ()
    estimated_critical_path_ms: int = 0

    def bindings_for(
        self,
        phase: GuardrailPhase,
        risk: str | None = None,
    ) -> tuple[NeMoActionBinding, ...]:
        return tuple(
            binding
            for binding in self.action_bindings
            if phase in binding.phases and (risk is None or binding.risk == risk)
        )


@dataclass(frozen=True, slots=True)
class GroundingFilterAssessment:
    type: GroundingFilterType
    score: float
    threshold: float
    detected: bool


@dataclass(frozen=True, slots=True)
class GroundingClaimEvidence:
    id: str
    claim: str
    support: ClaimSupport
    confidence: float
    source_block_ids: tuple[str, ...] = ()
    rationale: str = ""


@dataclass(frozen=True, slots=True)
class AutomatedReasoningRuleEvidence:
    id: str
    expression: str
    description: str = ""


@dataclass(frozen=True, slots=True)
class AutomatedReasoningScenario:
    assignments: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class AutomatedReasoningTranslation:
    premises: tuple[str, ...] = ()
    claims: tuple[str, ...] = ()
    untranslated: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AutomatedReasoningFinding:
    """Detection-only proof result returned by a formal reasoning provider."""

    id: str
    result: AutomatedReasoningResult
    confidence: float
    translation: AutomatedReasoningTranslation | None = None
    supporting_rules: tuple[AutomatedReasoningRuleEvidence, ...] = ()
    contradicting_rules: tuple[AutomatedReasoningRuleEvidence, ...] = ()
    claims_true_scenario: AutomatedReasoningScenario | None = None
    claims_false_scenario: AutomatedReasoningScenario | None = None
    message: str = ""


@dataclass(frozen=True, slots=True)
class RiskFinding:
    risk: str
    verdict: EvaluatorVerdict
    confidence: float
    evidence: str
    recommended_action: EnforcementAction
    replacement: str | None = None
    grounding: tuple[GroundingFilterAssessment, ...] = ()
    claims: tuple[GroundingClaimEvidence, ...] = ()
    reasoning: tuple[AutomatedReasoningFinding, ...] = ()


@dataclass(frozen=True, slots=True)
class ContentPatch:
    """A proposed edit whose offsets always refer to the immutable source text."""

    start: int
    end: int
    replacement: str


@dataclass(frozen=True, slots=True)
class RuntimeCoverage:
    status: CoverageStatus = "complete"
    guarded_items: int = 0
    total_items: int = 0
    guarded_characters: int = 0
    total_characters: int = 0
    required_modules_completed: int = 0
    required_modules_total: int = 0


@dataclass(frozen=True, slots=True)
class EvaluationUsage:
    module_invocations: int = 0
    evaluator_invocations: int = 0
    text_characters: int = 0
    rail_invocations: int = 0
    action_invocations: int = 0
    model_invocations: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    queue_latency_ms: int = 0
    runtime_engine: str = ""
    config_checksum: str = ""
    fail_closed: bool = False


@dataclass(frozen=True, slots=True)
class DecisionFragment:
    """An immutable module proposal; fragments never mutate shared content."""

    id: str
    module_id: str
    module: ControlModule
    status: FragmentStatus
    action: EnforcementAction = "pass"
    findings: tuple[RiskFinding, ...] = ()
    patches: tuple[ContentPatch, ...] = ()
    replacement: str | None = None
    coverage: CoverageStatus = "complete"
    reason: str | None = None
    trace: tuple[EvaluationTraceStep, ...] = ()
    content_block_id: str | None = None


@dataclass(frozen=True, slots=True)
class ModuleAssessment:
    module_id: str
    module: ControlModule
    status: FragmentStatus
    fragments: tuple[DecisionFragment, ...]
    coverage: RuntimeCoverage
    latency_ms: int = 0
    trace: tuple[EvaluationTraceStep, ...] = ()
    content_block_id: str | None = None


@dataclass(frozen=True, slots=True)
class AppliedIntervention:
    kind: EnforcementAction
    module_id: str
    fragment_id: str
    reason: str | None = None
    patches: tuple[ContentPatch, ...] = ()
    replacement: str | None = None
    content_block_id: str | None = None


@dataclass(frozen=True, slots=True)
class ContentBlockResult:
    id: str
    role: ContentRole
    source: str
    decision: PolicyDecision
    action: EnforcementAction
    text: str | None = None
    evaluated: bool = True


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
    guardrail_id: str | None = None
    guardrail_version: int | None = None
    assignment_id: str | None = None
    integration_id: str | None = None
    output_delivery: OutputDeliveryMode | None = None
    findings: tuple[RiskFinding, ...] = ()
    trace: tuple[EvaluationTraceStep, ...] = ()
    assessments: tuple[ModuleAssessment, ...] = ()
    interventions: tuple[AppliedIntervention, ...] = ()
    coverage: RuntimeCoverage | None = None
    usage: EvaluationUsage | None = None
    mode: EvaluationMode = "enforce"
    content_results: tuple[ContentBlockResult, ...] = ()


@dataclass(frozen=True, slots=True)
class PlanResolution:
    plan: GuardrailPlanSnapshot
    assignment_id: str
    integration_id: str | None = None
    trace: tuple[EvaluationTraceStep, ...] = ()


@dataclass(frozen=True, slots=True)
class EngineRequest:
    phase: GuardrailPhase
    text: str
    plan: GuardrailPlanSnapshot
    context_messages: tuple[dict[str, Any], ...] = ()
    trusted_instruction: str = ""
    target_source: str = "user_input"
    mode: EvaluationMode = "enforce"
    evidence_scope: EvidenceScope = "interventions"
    content_view: ContentViewSnapshot | None = None
    active_block_id: str | None = None


class GuardrailStage(Protocol):
    name: str
    stage: EvaluationStage
    supported_phases: frozenset[GuardrailPhase]
    supported_risks: frozenset[str]

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
