export type SafetyLevel = "balanced" | "strict";
export type OutputDelivery = "interruptible" | "window_buffered" | "full_buffered";
export type TargetSource = "user_input" | "retrieved_content" | "tool_output" | "model_output";

export type GroundingFilterAssessment = {
  type: "grounding" | "relevance";
  score: number;
  threshold: number;
  detected: boolean;
};

export type GroundingClaimEvidence = {
  id: string;
  claim: string;
  support: "supported" | "unsupported" | "uncertain";
  confidence: number;
  source_block_ids: string[];
  rationale: string;
};

export type AutomatedReasoningResult = "valid" | "invalid" | "satisfiable" | "impossible" | "translation_ambiguous" | "too_complex" | "no_translations";

export type AutomatedReasoningFinding = {
  id: string;
  result: AutomatedReasoningResult;
  confidence: number;
  translation?: { premises: string[]; claims: string[]; untranslated: string[] } | null;
  supporting_rules: Array<{ id: string; expression: string; description: string }>;
  contradicting_rules: Array<{ id: string; expression: string; description: string }>;
  claims_true_scenario?: { assignments: Array<[string, string]> } | null;
  claims_false_scenario?: { assignments: Array<[string, string]> } | null;
  message: string;
};

export type Collection<T> = { items: T[]; count: number };

export type GuardrailControl = {
  risk: string;
  action: string;
  reasoning_policy?: {
    policy_id: string;
    policy_version: string;
    confidence_threshold: number;
  } | null;
};

export type GuardrailRuleConfig = {
  id: string;
  name: string;
  detector: "regex" | "keyword" | "category" | "classifier" | "judge";
  action: string;
  phases: Array<"input" | "output">;
  enabled: boolean;
  description: string;
  expression: string | null;
  keywords: string[];
};

export type GuardrailControlConfig = {
  id: string;
  name: string;
  kind: "template" | "custom";
  runtime_risk: string;
  template_id: string | null;
  template_version: string | null;
  rules: GuardrailRuleConfig[];
};

export type GuardrailNativeControlBinding = {
  control_id: string;
  control_version: number;
  parameter_values: Record<string, string>;
  enabled_rails: NativeRailType[];
};

export type EvaluationMetrics = {
  total: number;
  passed: number;
  compliance_rate: number;
  false_positive_rate: number;
  false_negative_rate: number;
  deep_escalation_rate: number;
  p95_latency_ms: number;
};

export type EvaluationFinding = {
  risk: string;
  verdict: string;
  confidence: number;
  evidence: string;
  recommended_action: string;
  replacement?: string | null;
  grounding?: GroundingFilterAssessment[];
  claims?: GroundingClaimEvidence[];
  reasoning?: AutomatedReasoningFinding[];
};

export type EvaluationTraceStep = {
  id: string;
  kind?: string;
  name: string;
  status: string;
  detail: string;
  duration_ms: number;
  stage?: string | null;
  verdict?: string | null;
  route?: string | null;
  risk?: string | null;
  confidence?: number | null;
};

export type EvaluationCaseResult = {
  case_id: string;
  name: string;
  risk: string;
  expected_decision: string;
  actual_decision: string;
  passed: boolean;
  stage_reached: string;
  latency_ms: number;
  reason: string;
  phase: "input" | "output";
  input_content: string;
  action: string;
  output_content: string;
  findings: EvaluationFinding[];
  trace: EvaluationTraceStep[];
  trusted_instruction: string;
  target_source: TargetSource;
  query: string;
  grounding_sources: string[];
  expected_reasoning_result: AutomatedReasoningResult | null;
  actual_reasoning_result: AutomatedReasoningResult | null;
};

export type TestRun = {
  id: string;
  guardrail_id: string;
  guardrail_version: number | null;
  source_draft_version: number;
  status: "passed" | "failed" | "incomplete";
  metrics: EvaluationMetrics;
  results: EvaluationCaseResult[];
  created_at: string;
};

export type QuickTestResult = {
  guardrail_id: string;
  source_draft_version: number;
  phase: "input" | "output";
  input_content: string;
  decision: "allow" | "transform" | "block";
  action: string;
  output_content: string;
  stage_reached: string;
  latency_ms: number;
  reason: string;
  findings: EvaluationFinding[];
  trace: EvaluationTraceStep[];
};

export type TestCase = {
  id: string;
  guardrail_id: string;
  name: string;
  risk: string;
  phase: "input" | "output";
  content: string;
  expected_decision: "allow" | "block" | "transform" | "intervene";
  origin: "generated" | "custom";
  updated_at: string;
  trusted_instruction: string;
  target_source: TargetSource;
  query: string;
  grounding_sources: string[];
  expected_reasoning_result: AutomatedReasoningResult | null;
};

export type RiskCoverage = {
  risk: string;
  passed: number;
  total: number;
  score: number | null;
};

export type GuardrailAssignment = {
  id: string;
  name: string;
  guardrail_id: string;
  guardrail_version: number;
  traffic_scope: TrafficScopeExpression;
  enabled: boolean;
  is_default: boolean;
  system_managed: boolean;
  updated_at: string;
};

export type TrafficScopeSource = "field" | "header" | "jwt_claim";
export type TrafficScopeOperator = "equals" | "contains" | "starts_with" | "glob";

export type TrafficScopeRule = {
  field: string;
  key?: string;
  operator: TrafficScopeOperator;
  value: string;
};

export type TrafficScopeExpression = {
  combinator: "and" | "or";
  rules: Array<TrafficScopeRule | TrafficScopeExpression>;
};

export type TrafficScopeField = {
  id: string;
  group: "request" | "authentication" | "http" | "model" | "litellm" | "a2a";
  source: TrafficScopeSource;
  key: string;
  operators: TrafficScopeOperator[];
  values: string[];
  custom_key?: boolean;
};

export type Guardrail = {
  id: string;
  name: string;
  purpose: string;
  allowed_topics: string[];
  restricted_topics: string[];
  controls: GuardrailControl[];
  control_configurations: GuardrailControlConfig[];
  control_bindings: GuardrailNativeControlBinding[];
  safety_level: SafetyLevel;
  output_delivery: OutputDelivery;
  source_template_id: string | null;
  template_parameters: Record<string, string>;
  updated_at: string;
  status: "needs_testing" | "ready" | "protected";
  latest_test_run: TestRun | null;
  assignment_count: number;
  test_case_count: number;
  tested_current: boolean;
  is_default: boolean;
  system_managed: boolean;
  local_only: boolean;
  coverage: RiskCoverage[];
};

export type GuardrailVersion = {
  guardrail_id: string;
  version: number;
  source_draft_version: number;
  compiler_version: string;
  plan_checksum: string;
  created_at: string;
  active: boolean;
  runtime_engine: "iorails" | "llmrails" | string;
  config_checksum: string;
  execution_mode: "nemo_only";
};

export type GuardrailTemplate = {
  id: string;
  name: string;
  description: string;
  purpose: string;
  allowed_topics: string[];
  restricted_topics: string[];
  default_controls: GuardrailControl[];
  safety_level: SafetyLevel;
  output_delivery: OutputDelivery;
  source?: string;
  version?: string;
  domain?: string;
  collections?: string[];
  tags?: string[];
  limitations?: string[];
  controls?: string[];
  parameters?: Array<{
    name: string;
    label: string;
    kind: string;
    required: boolean;
    placeholder: string;
    description: string;
  }>;
};

export type ControlTemplateRule = {
  id: string;
  name: string;
  detector: "regex" | "keyword" | "category";
  action: "MASK" | "BLOCK" | string;
  description: string;
  expression: string | null;
  context_expression: string | null;
  redaction: string | null;
  severity_threshold: string | null;
  identifiers: string[];
  conditions: string[];
  keywords: string[];
  always_block: string[];
  exceptions: string[];
  phrase_patterns: string[];
};

export type ControlTemplate = {
  id: string;
  name: string;
  description: string;
  source: string;
  version: string;
  status: "built_in" | "registered";
  phases: Array<"input" | "output">;
  default_action: "MASK" | "BLOCK" | "POLICY" | string;
  allowed_actions: string[];
  detector_types: Array<ControlTemplateRule["detector"]>;
  rules: ControlTemplateRule[];
  packs: Array<{ id: string; name: string; domain: string }>;
  tags: string[];
  limitations: string[];
};

export type ControlDefinition = {
  id: string;
  display_name: string;
  description: string;
  domain: string;
  default_phases: Array<"input" | "output">;
  default_action: string;
  allowed_actions: string[];
  available_stages: string[];
  limitations: string[];
};

export type NativeRailType = "input" | "output" | "retrieval" | "dialog" | "execution";
export type ControlSourceFile = { path: string; content: string };
export type ControlParameter = {
  name: string;
  kind: "string" | "number" | "boolean" | "secret";
  required: boolean;
  default: string | null;
  description: string;
};
export type ControlRailBinding = {
  rail_type: NativeRailType;
  flow_name: string;
  execution_mode: "detect" | "mutate";
  on_unsafe: "pass" | "redact" | "rewrite" | "regenerate" | "redirect" | "reject" | "fallback" | "clarify";
  parallel_group: string | null;
  priority: number | null;
  timeout_ms: number;
  failure_mode: "fail_open" | "fail_closed";
  required: boolean;
  depends_on: string[];
};
export type ControlActionReference = { name: string; version: string };
export type ControlTestCase = {
  name: string;
  rail_type: NativeRailType;
  content: string;
  expected_decision: "allow" | "block" | "transform";
  case_type: "unit" | "input_rail" | "output_rail" | "block" | "transform" | "timeout" | "provider_failure" | "concurrency";
  required: boolean;
  expected_failure: "timeout" | "provider_failure" | null;
  concurrency_group: string | null;
};
export type NativeControlDraft = {
  colang_version: "1.0" | "2.x";
  sources: ControlSourceFile[];
  parameter_schema: ControlParameter[];
  rail_bindings: ControlRailBinding[];
  action_references: ControlActionReference[];
  model_dependencies: string[];
  prompt_dependencies: string[];
  execution_contract: Array<[string, string]>;
  tests: ControlTestCase[];
};
export type NativeControlVersion = Omit<NativeControlDraft, "execution_contract"> & {
  control_id: string;
  version: number;
  name: string;
  description: string;
  source: "built-in" | "custom";
  owner: string;
  execution_contract: Array<[string, string]>;
  checksum: string;
  published_at: string;
};
export type NativeControl = {
  id: string;
  name: string;
  description: string;
  source: "built-in" | "custom";
  owner: string;
  draft: NativeControlDraft;
  draft_revision: number;
  updated_at: string;
  versions?: NativeControlVersion[];
};
export type ActionDefinition = {
  name: string;
  version: string;
  input_schema: Array<[string, string]>;
  output_schema: Array<[string, string]>;
  supported_rails: NativeRailType[];
  timeout_ms: number;
  failure_mode: "fail_open" | "fail_closed";
  side_effects: boolean;
  concurrent: boolean;
  network_access: boolean;
  secret_names: string[];
  provider_ready: boolean;
};
export type ControlValidation = {
  valid: boolean;
  control_id: string;
  draft_revision: number;
  colang_version: string;
  rails: NativeRailType[];
};
export type ControlTestRun = {
  id?: string;
  control_id?: string;
  draft_revision?: number;
  status: "not_run" | "passed" | "failed";
  results?: Array<{
    name: string;
    case_type: ControlTestCase["case_type"];
    required: boolean;
    rail_type: NativeRailType;
    concurrency_group: string | null;
    expected_decision: string;
    expected_failure: ControlTestCase["expected_failure"];
    actual_decision: string;
    actual_failure?: ControlTestCase["expected_failure"];
    passed: boolean;
    latency_ms: number;
    reason: string;
    trace: Array<Record<string, unknown>>;
  }>;
  created_at?: string;
};
export type GuardrailCompilePreview = {
  guardrail_id: string;
  candidate_version: number;
  engine: string;
  colang_version: string;
  compiler_version: string;
  checksum: string;
  rails: Array<{ rail_type: NativeRailType; flow: string }>;
  parallel_groups: string[];
  actions: Array<{ name: string; version: string; flow: string; timeout_ms: number; failure_mode: string }>;
  models: string[];
  dependency_manifest: Array<{ kind: string; name: string; version: string }>;
  estimated_critical_path_ms: number;
};

export type Integration = {
  id: string;
  protocol: "litellm" | "http" | "a2a";
  name: string;
  description: string;
  environment: string;
  enabled: boolean;
  credential_prefix: string;
  verification_status: string;
  runtime_status: string;
  last_seen_at: string | null;
  request_count: number;
  error_count: number;
  created_at: string;
  updated_at: string;
};

export type DecisionEvent = {
  id: string;
  created_at: string;
  kind: string;
  outcome: string;
  guardrail_id: string | null;
  assignment_id: string | null;
  risk: string | null;
  detail: string;
};

export type SystemStatus = {
  status: "healthy" | "degraded";
  status_reason: "runtime_ready" | "integration_degraded";
  active_assignments: number;
  online_integrations: number;
  total_integrations: number;
  capabilities: {
    deterministic: boolean;
    fast_semantic: boolean;
    deep_judge: boolean;
    automated_reasoning: boolean;
  };
};

export type Metrics = {
  window: "24h" | "7d" | "30d";
  window_start: string;
  scope: {
    guardrail_id: string | null;
    guardrail_name: string | null;
    environment: string | null;
  };
  comparison: {
    previous_total_decisions: number;
    request_delta_pct: number | null;
  };
  total_decisions: number;
  allowed: number;
  blocked: number;
  intervened: number;
  errors: number;
  block_rate: number;
  intervention_rate: number;
  error_rate: number;
  timeout_count: number;
  rail_invocations: number;
  action_invocations: number;
  model_invocations: number;
  cache_hits: number;
  cache_misses: number;
  cache_hit_rate: number;
  queue_p50_ms: number;
  queue_p95_ms: number;
  queue_p99_ms: number;
  provider_p50_ms: number;
  provider_p95_ms: number;
  provider_p99_ms: number;
  fail_closed_count: number;
  peak_active_concurrency: number;
  slo_breach_count: number;
  runtime_engine_counts: Array<{ runtime_engine: string; count: number }>;
  rail_metrics: RuntimeComponentMetric[];
  action_metrics: RuntimeComponentMetric[];
  comparison_count: number;
  decision_match_rate: number;
  action_match_rate: number;
  finding_match_rate: number;
  runtime_p50_ms: number;
  runtime_p95_ms: number;
  runtime_p99_ms: number;
  latency_slo: {
    p95_budget_ms: number;
    p99_budget_ms: number;
    p95_status: "healthy" | "breached";
    p99_status: "healthy" | "breached";
  };
  latest_test_p95_ms: number;
  active_assignments: number;
  total_assignments: number;
  guardrails_needing_test: number;
  total_guardrails: number;
  degraded_integrations: number;
  total_integrations: number;
  risk_counts: Array<{ risk: string; count: number }>;
  guardrail_distribution: Array<{
    guardrail_id: string;
    name: string;
    total: number;
    share: number;
    allowed: number;
    blocked: number;
    intervened: number;
    errors: number;
    block_rate: number;
    intervention_rate: number;
    error_rate: number;
    p50_latency_ms: number;
    p95_latency_ms: number;
    p99_latency_ms: number;
    timeout_count: number;
    rail_invocations: number;
    action_invocations: number;
    model_invocations: number;
    cache_hits: number;
    cache_misses: number;
    queue_p95_ms: number;
    rail_p95_ms: number;
    action_p95_ms: number;
    provider_p95_ms: number;
    fail_closed_count: number;
    peak_active_concurrency: number;
    slo_breach_count: number;
    runtime_engines: string[];
    config_checksums: string[];
    versions: number[];
  }>;
  version_distribution: Array<{
    guardrail_id: string;
    guardrail_name: string;
    guardrail_version: number;
    requests: number;
    share: number;
    p95_latency_ms: number;
    errors: number;
    slo_breaches: number;
  }>;
  control_distribution: Array<{
    control_id: string;
    control_version: number | null;
    invocations: number;
    hit_share: number;
    hits_per_request: number;
    passed: number;
    intervened: number;
    errors: number;
    timeouts: number;
    p50_latency_ms: number;
    p95_latency_ms: number;
    p99_latency_ms: number;
    provider_p95_ms: number;
    rail_types: string[];
    parallel_groups: string[];
  }>;
  unassigned_requests: number;
  trend: Array<{ date: string; total: number; blocked: number; intervened: number; errored: number }>;
  system_status: "healthy" | "degraded";
};

export type RuntimeComponentMetric = {
  name: string;
  risk: string | null;
  control_id: string | null;
  control_version: number | null;
  rail_type: string | null;
  flow_name: string | null;
  action_name: string | null;
  action_version: string | null;
  parallel_group: string | null;
  invocations: number;
  passed: number;
  intervened: number;
  uncertain: number;
  errors: number;
  timeouts: number;
  p50_latency_ms: number;
  p95_latency_ms: number;
  p99_latency_ms: number;
  provider_p50_ms: number;
  provider_p95_ms: number;
  provider_p99_ms: number;
};

export type IdentityRole = "admin" | "member";
export type IdentityUser = {
  id: string;
  display_name: string;
  email: string;
  role: IdentityRole;
  enabled: boolean;
  preferred_language: "en" | "zh-CN";
  last_login_at: string | null;
  created_at: string;
  updated_at: string;
};
export type AuthStatus = { authenticated: boolean; user: IdentityUser | null };
export type IntentAnalysisStatus = { available: boolean; provider: string | null; model: string | null };
export type IntentAnalysis = { summary: string; allowed_topics: string[]; restricted_topics: string[]; review_notes: string[] };

async function read<T>(path: string): Promise<T> { return parse<T>(await fetch(path)); }
async function mutate<T>(path: string, method: string, body?: unknown): Promise<T> {
  return parse<T>(await fetch(path, {
    method,
    headers: { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  }));
}
async function parse<T>(response: Response): Promise<T> {
  if (response.status === 204) return undefined as T;
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && !response.url.endsWith("/api/v1/session")) {
      window.dispatchEvent(new CustomEvent("tasklattice:unauthorized"));
    }
    throw new Error(payload.detail || `Request failed with status ${response.status}.`);
  }
  return payload as T;
}

const query = (params: Record<string, string | number | undefined>) => {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => { if (value !== undefined && value !== "") search.set(key, String(value)); });
  const value = search.toString();
  return value ? `?${value}` : "";
};

export const getAuthStatus = () => read<AuthStatus>("/api/v1/session");
export const login = (input: { email: string; password: string }) => mutate<{ user: IdentityUser }>("/api/v1/session", "POST", input);
export const logout = () => mutate<void>("/api/v1/session", "DELETE");
export const updateMe = (input: { preferred_language: "en" | "zh-CN" }) => mutate<{ user: IdentityUser }>("/api/v1/me", "PATCH", input);
export const changePassword = (input: { current_password: string; new_password: string }) => mutate<{ user: IdentityUser }>("/api/v1/me/password", "PATCH", input);
export const getUsers = () => read<{ users: IdentityUser[] }>("/api/v1/users");
export const createUser = (input: { display_name: string; email: string; password: string; role: IdentityRole; preferred_language: "en" | "zh-CN" }) => mutate<IdentityUser>("/api/v1/users", "POST", input);
export const updateUser = (id: string, input: { display_name?: string; role?: IdentityRole; enabled?: boolean; password?: string }) => mutate<IdentityUser>(`/api/v1/users/${encodeURIComponent(id)}`, "PATCH", input);

export const getGuardrails = () => read<Collection<Guardrail>>("/api/v1/guardrails");
export const getGuardrail = (id: string) => read<Guardrail>(`/api/v1/guardrails/${encodeURIComponent(id)}`);
export const createGuardrail = (input: { name: string; purpose?: string; template_id?: string; template_parameters?: Record<string, string>; allowed_topics?: string[]; restricted_topics?: string[]; controls?: GuardrailControl[]; control_configurations?: GuardrailControlConfig[]; control_bindings?: GuardrailNativeControlBinding[]; safety_level?: SafetyLevel; output_delivery?: OutputDelivery }) => mutate<Guardrail>("/api/v1/guardrails", "POST", input);
export const updateGuardrail = (id: string, input: Partial<Pick<Guardrail, "name" | "purpose" | "allowed_topics" | "restricted_topics" | "controls" | "control_configurations" | "safety_level" | "output_delivery">>) => mutate<Guardrail>(`/api/v1/guardrails/${encodeURIComponent(id)}`, "PATCH", input);
export const getGuardrailVersions = (guardrailId: string) => read<Collection<GuardrailVersion>>(`/api/v1/guardrail-versions${query({ guardrail_id: guardrailId })}`);
export const rollbackGuardrail = (guardrailId: string, version: number) => mutate<GuardrailVersion>(`/api/v1/guardrails/${encodeURIComponent(guardrailId)}/rollback/${version}`, "POST");

export const getGuardrailTemplates = () => read<Collection<GuardrailTemplate>>("/api/v1/guardrail-templates");
export const getControlTemplates = () => read<Collection<ControlTemplate>>("/api/v1/control-templates");
export const getControlDefinitions = () => read<Collection<ControlDefinition>>("/api/v1/control-definitions");
export const getNativeControls = () => read<Collection<NativeControl>>("/api/v1/controls");
export const getNativeControl = (id: string) => read<NativeControl>(`/api/v1/controls/${encodeURIComponent(id)}`);
export const getActionCatalog = () => read<Collection<ActionDefinition>>("/api/v1/actions");
const nativeControlInput = (input: { name?: string; description?: string; owner?: string; draft?: NativeControlDraft }) => input.draft ? { ...input, draft: { ...input.draft, execution_contract: Object.fromEntries(input.draft.execution_contract) } } : input;
export const createNativeControl = (input: { name: string; description: string; owner: string; draft: NativeControlDraft }) => mutate<NativeControl>("/api/v1/controls", "POST", nativeControlInput(input));
export const updateNativeControl = (id: string, input: { name?: string; description?: string; owner?: string; draft?: NativeControlDraft }) => mutate<NativeControl>(`/api/v1/controls/${encodeURIComponent(id)}`, "PATCH", nativeControlInput(input));
export const validateNativeControl = (id: string) => mutate<ControlValidation>(`/api/v1/controls/${encodeURIComponent(id)}/validate`, "POST");
export const runNativeControlTests = (id: string) => mutate<ControlTestRun>(`/api/v1/controls/${encodeURIComponent(id)}/test-runs`, "POST");
export const getLatestNativeControlTest = (id: string) => read<ControlTestRun>(`/api/v1/controls/${encodeURIComponent(id)}/test-runs/latest`);
export const publishNativeControl = (id: string) => mutate<NativeControlVersion>(`/api/v1/controls/${encodeURIComponent(id)}/publish`, "POST");
export const getGuardrailCompilePreview = (id: string) => read<GuardrailCompilePreview>(`/api/v1/guardrails/${encodeURIComponent(id)}/compile-preview`);
export const previewGuardrailCandidate = (input: { name: string; purpose: string; allowed_topics?: string[]; restricted_topics?: string[]; controls?: GuardrailControl[]; control_configurations?: GuardrailControlConfig[]; control_bindings?: GuardrailNativeControlBinding[]; safety_level?: SafetyLevel; output_delivery?: OutputDelivery }) => mutate<GuardrailCompilePreview>("/api/v1/guardrail-compile-previews", "POST", input);
export const getIntentAnalysisStatus = () => read<IntentAnalysisStatus>("/api/v1/intent-analysis-status");
export const analyzeGuardrailIntent = (input: { purpose: string; language: "en" | "zh-CN" }) => mutate<IntentAnalysis>("/api/v1/intent-analyses", "POST", input);

export const createTestRun = (guardrailId: string) => mutate<TestRun>("/api/v1/test-runs", "POST", { guardrail_id: guardrailId });
export const getTestRuns = (guardrailId?: string) => read<Collection<TestRun>>(`/api/v1/test-runs${query({ guardrail_id: guardrailId })}`);
export const getTestRun = (runId: string) => read<TestRun>(`/api/v1/test-runs/${encodeURIComponent(runId)}`);
export const runQuickTest = (guardrailId: string, input: { phase: "input" | "output"; content: string }) => mutate<QuickTestResult>("/api/v1/quick-tests", "POST", { guardrail_id: guardrailId, ...input });
export const getTestCases = (guardrailId: string) => read<Collection<TestCase>>(`/api/v1/test-cases${query({ guardrail_id: guardrailId })}`);
export const createTestCase = (guardrailId: string, input: Pick<TestCase, "name" | "risk" | "phase" | "content" | "expected_decision" | "trusted_instruction" | "target_source" | "query" | "grounding_sources" | "expected_reasoning_result">) => mutate<TestCase>("/api/v1/test-cases", "POST", { guardrail_id: guardrailId, ...input });
export const deleteTestCase = (caseId: string) => mutate<void>(`/api/v1/test-cases/${encodeURIComponent(caseId)}`, "DELETE");

export const getAssignments = () => read<Collection<GuardrailAssignment>>("/api/v1/assignments");
export const getTrafficScopeFields = () => read<Collection<TrafficScopeField>>("/api/v1/traffic-scope-fields");
export const createAssignment = (input: { name: string; guardrail_id: string; traffic_scope: TrafficScopeExpression; enabled: boolean }) => mutate<GuardrailAssignment>("/api/v1/assignments", "POST", input);
export const setAssignmentEnabled = (id: string, enabled: boolean) => mutate<GuardrailAssignment>(`/api/v1/assignments/${encodeURIComponent(id)}`, "PATCH", { enabled });
export const getIntegrations = () => read<Collection<Integration>>("/api/v1/integrations");
export const createIntegration = (input: { name: string; environment: "production" | "staging" | "development" | "test"; protocol: "litellm" | "http" | "a2a" }) => mutate<{ integration: Integration; credential: string }>("/api/v1/integrations", "POST", input);
export const getDecisions = (filters: { limit?: number; guardrailId?: string; assignmentId?: string; outcome?: string; risk?: string } = {}) => read<Collection<DecisionEvent>>(`/api/v1/decisions${query({ limit: filters.limit, guardrail_id: filters.guardrailId, assignment_id: filters.assignmentId, outcome: filters.outcome, risk: filters.risk })}`);
export const getMetrics = (filters: { guardrailId?: string; environment?: string; window?: "24h" | "7d" | "30d" } = {}) => read<Metrics>(`/api/v1/metrics${query({ guardrail_id: filters.guardrailId, environment: filters.environment, window: filters.window })}`);
export const getSystemStatus = () => read<SystemStatus>("/api/v1/system-status");
