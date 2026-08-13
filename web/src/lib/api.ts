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
  kind: "built_in" | "custom";
  runtime_risk: string;
  control_id: string | null;
  control_version: string | null;
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
  parent_id?: string | null;
  stage?: string | null;
  verdict?: string | null;
  route?: string | null;
  risk?: string | null;
  confidence?: number | null;
  control_id?: string | null;
  control_version?: number | null;
  rail_type?: string | null;
  flow_name?: string | null;
  action_name?: string | null;
  action_version?: string | null;
  outcome?: string | null;
  engine?: string | null;
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
  case_type: "rule_acceptance" | "scenario" | "custom" | string;
  required: boolean;
  expected_failure: string | null;
  actual_failure: string | null;
  concurrency_group: string | null;
  source_control_id: string | null;
  source_control_version: string | null;
  source_suite_id: string | null;
  source_case_id: string | null;
  covered_rule_ids: string[];
  matched_rule_ids: string[];
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

export type PlaygroundCheckControl = {
  id: string;
  name: string;
  risk: string;
  status: "matched" | "not_matched" | "error";
  duration_ms: number;
};

export type PlaygroundCheckFinding = {
  id: string;
  severity: "high" | "medium" | "low";
  title: string;
  detail: string;
  confidence: number;
  recommended_action: string;
  control_id: string | null;
  rule_id: string | null;
};

export type PlaygroundCheckResult = {
  check_id: string;
  trace_id: string;
  evidence_id: string | null;
  guardrail: {
    id: string;
    name: string;
    draft_version: number;
    compiler_version: string;
  };
  phase: "input" | "output";
  decision: "allow" | "transform" | "block";
  action: string;
  output_content: string;
  latency_ms: number;
  reason: string;
  runtime: string;
  triggered_control: { id: string; name: string } | null;
  triggered_rule: { id: string; name: string } | null;
  controls: PlaygroundCheckControl[];
  findings: PlaygroundCheckFinding[];
  trace_summary: { steps: number; matched_steps: number };
  trace: EvaluationTraceStep[];
};

export type PlaygroundModel = {
  id: string;
  provider: string;
  name: string;
  icon: string;
};

export type PlaygroundInteraction = {
  interaction_id: string;
  state: "completed" | "input_blocked" | "output_blocked";
  user_message: string;
  effective_user_message: string | null;
  assistant_message: string | null;
  model: PlaygroundModel & { latency_ms: number | null };
  input_check: PlaygroundCheckResult;
  output_check: PlaygroundCheckResult | null;
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
  source_control_id: string | null;
  source_control_version: string | null;
  source_suite_id: string | null;
  source_case_id: string | null;
  covered_rule_ids: string[];
  case_type: string;
  required: boolean;
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
  source_pack_id: string | null;
  parameters: Record<string, string>;
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

export type ControlPack = {
  id: string;
  name: string;
  description: string;
  source: string;
  version: string;
  control_ids: string[];
  parameters: Array<{
    name: string;
    label: string;
    kind: string;
    required: boolean;
    placeholder: string;
    description: string;
  }>;
  examples: string[];
  safety_level: SafetyLevel;
  output_delivery: OutputDelivery;
  test_suite_count: number;
  test_case_count: number;
};

export type ControlRuleKeyword = {
  value: string;
  severity: string;
};

export type ControlRule = {
  id: string;
  name: string;
  detector: "regex" | "keyword" | "category";
  action: "MASK" | "BLOCK" | string;
  phases: Array<"input" | "output">;
  description: string;
  expression: string | null;
  context_expression: string | null;
  redaction: string | null;
  severity_threshold: string | null;
  identifiers: string[];
  conditions: string[];
  keywords: ControlRuleKeyword[];
  always_block: ControlRuleKeyword[];
  exceptions: string[];
  phrase_patterns: string[];
};

export type RulesControlTestCase = {
  id: string;
  name: string;
  description: string;
  phase: "input" | "output";
  content: string;
  expected_decision: "allow" | "block" | "transform" | "intervene";
  covered_rule_ids: string[];
  kind: "rule_acceptance" | "scenario";
  required: boolean;
  parameter_names: string[];
};

export type RulesControlTestSuite = {
  id: string;
  name: string;
  description: string;
  cases: RulesControlTestCase[];
};

export type RulesControl = {
  implementation: "rules";
  id: string;
  name: string;
  description: string;
  source: "built_in";
  version: string;
  phases: Array<"input" | "output">;
  default_action: "MASK" | "BLOCK" | "POLICY" | string;
  allowed_actions: string[];
  detector_types: Array<ControlRule["detector"]>;
  rules: ControlRule[];
  test_suites: RulesControlTestSuite[];
  test_count: number;
  packs: Array<{ id: string; name: string }>;
};

export type ControlDefinition = {
  id: string;
  display_name: string;
  description: string;
  default_phases: Array<"input" | "output">;
  default_action: string;
  allowed_actions: string[];
  available_stages: string[];
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
  source: "built_in" | "custom";
  owner: string;
  execution_contract: Array<[string, string]>;
  checksum: string;
  published_at: string;
};
export type NativeControl = {
  implementation: "nemo_native";
  id: string;
  name: string;
  description: string;
  source: "built_in" | "custom";
  owner: string;
  draft: NativeControlDraft;
  draft_revision: number;
  updated_at: string;
  versions?: NativeControlVersion[];
};

export type Control = RulesControl | NativeControl;
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

export type IntegrationAdapterId = "litellm-generic-guardrail" | "generic-http-guard" | "a2a-guard";
export type IntegrationProtocol = "litellm" | "http" | "a2a";
export type IntegrationSetupStatus = "awaiting_callback" | "verified" | "disabled";

export type IntegrationSetup = {
  api_base_url: string;
  callback_url: string;
  auth_header: string;
  credential_env_var: string;
  api_base_env_var: string;
  recommended_modes: string[];
  default_on: boolean;
  fail_on_error: boolean;
  unreachable_fallback: "fail_closed" | "fail_open";
  yaml_template: string;
};

export type IntegrationCredential = {
  id: string;
  key_hint: string;
  created_at: string;
};

export type OneTimeIntegrationCredential = IntegrationCredential & {
  value: string;
};

export type Integration = {
  id: string;
  adapter_id: IntegrationAdapterId;
  protocol: IntegrationProtocol;
  name: string;
  description: string;
  enabled: boolean;
  key_hint: string;
  credentials: IntegrationCredential[];
  setup_status: IntegrationSetupStatus;
  runtime_status: string;
  first_seen_at: string | null;
  input_seen_at: string | null;
  output_seen_at: string | null;
  last_seen_at: string | null;
  last_error_at: string | null;
  request_count: number;
  error_count: number;
  setup: IntegrationSetup;
  created_at: string;
  updated_at: string;
};

export type IntegrationRegistration = {
  integration: Integration;
  credential: OneTimeIntegrationCredential;
};

export type DecisionEvent = {
  id: string;
  created_at: string;
  kind: string;
  outcome: string;
  guardrail_id: string | null;
  assignment_id: string | null;
  integration_id: string | null;
  risk: string | null;
  detail: string;
};

export type MetricWindow = "1h" | "24h" | "7d" | "15d" | "30d";

export type MetricTrendPoint = {
  timestamp: string;
  total: number;
  allowed: number;
  blocked: number;
  transformed: number;
  errored: number;
  timed_out: number;
  p50_latency_ms: number;
  p95_latency_ms: number;
  p99_latency_ms: number;
};

export type MetricTrendSeries = {
  name: string;
  points: MetricTrendPoint[];
};

export type SystemStatus = {
  status: "healthy" | "degraded";
  status_reason: "runtime_ready" | "integration_degraded";
  active_assignments: number;
  enabled_integrations: number;
  total_integrations: number;
  capabilities: {
    deterministic: boolean;
    fast_semantic: boolean;
    deep_judge: boolean;
    automated_reasoning: boolean;
  };
};

export type Metrics = {
  window: MetricWindow;
  window_start: string;
  scope: {
    guardrail_id: string | null;
    guardrail_name: string | null;
  };
  comparison: {
    previous_total_decisions: number;
    request_delta_pct: number | null;
    previous_intervention_rate: number | null;
    intervention_rate_delta_pp: number | null;
    previous_runtime_p95_ms: number | null;
    runtime_p95_delta_ms: number | null;
    previous_error_rate: number | null;
    error_rate_delta_pp: number | null;
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
  interval: "1m" | "15m" | "1h" | "6h" | "1d";
  trend: MetricTrendPoint[];
  trend_series: {
    none: MetricTrendSeries[];
    guardrail: MetricTrendSeries[];
  };
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
export const createGuardrail = (input: { name: string; purpose?: string; pack_id?: string; parameters?: Record<string, string>; allowed_topics?: string[]; restricted_topics?: string[]; controls?: GuardrailControl[]; control_configurations?: GuardrailControlConfig[]; control_bindings?: GuardrailNativeControlBinding[]; safety_level?: SafetyLevel; output_delivery?: OutputDelivery }) => mutate<Guardrail>("/api/v1/guardrails", "POST", input);
export const updateGuardrail = (id: string, input: Partial<Pick<Guardrail, "name" | "purpose" | "allowed_topics" | "restricted_topics" | "controls" | "control_configurations" | "safety_level" | "output_delivery">>) => mutate<Guardrail>(`/api/v1/guardrails/${encodeURIComponent(id)}`, "PATCH", input);
export const getGuardrailVersions = (guardrailId: string) => read<Collection<GuardrailVersion>>(`/api/v1/guardrail-versions${query({ guardrail_id: guardrailId })}`);
export const rollbackGuardrail = (guardrailId: string, version: number) => mutate<GuardrailVersion>(`/api/v1/guardrails/${encodeURIComponent(guardrailId)}/rollback/${version}`, "POST");

export const getControlPacks = () => read<Collection<ControlPack>>("/api/v1/control-packs");
export const getControlDefinitions = () => read<Collection<ControlDefinition>>("/api/v1/control-definitions");
export const getControls = () => read<Collection<Control>>("/api/v1/controls");
export const getRuleControls = () => read<Collection<RulesControl>>("/api/v1/controls?implementation=rules");
export const getNativeControls = () => read<Collection<NativeControl>>("/api/v1/controls?implementation=nemo_native");
export const getNativeControl = (id: string) => read<NativeControl>(`/api/v1/controls/${encodeURIComponent(id)}?implementation=nemo_native`);
export const getActionCatalog = () => read<Collection<ActionDefinition>>("/api/v1/actions");
const nativeControlInput = (input: { name?: string; description?: string; owner?: string; draft?: NativeControlDraft }) => input.draft ? { ...input, draft: { ...input.draft, execution_contract: Object.fromEntries(input.draft.execution_contract) } } : input;
export const createNativeControl = (input: { name: string; description: string; owner: string; draft: NativeControlDraft }) => mutate<NativeControl>("/api/v1/controls?implementation=nemo_native", "POST", nativeControlInput(input));
export const updateNativeControl = (id: string, input: { name?: string; description?: string; owner?: string; draft?: NativeControlDraft }) => mutate<NativeControl>(`/api/v1/controls/${encodeURIComponent(id)}?implementation=nemo_native`, "PATCH", nativeControlInput(input));
export const validateNativeControl = (id: string) => mutate<ControlValidation>(`/api/v1/controls/${encodeURIComponent(id)}/validate?implementation=nemo_native`, "POST");
export const runNativeControlTests = (id: string) => mutate<ControlTestRun>(`/api/v1/controls/${encodeURIComponent(id)}/test-runs?implementation=nemo_native`, "POST");
export const getLatestNativeControlTest = (id: string) => read<ControlTestRun>(`/api/v1/controls/${encodeURIComponent(id)}/test-runs/latest?implementation=nemo_native`);
export const publishNativeControl = (id: string) => mutate<NativeControlVersion>(`/api/v1/controls/${encodeURIComponent(id)}/publish?implementation=nemo_native`, "POST");
export const getGuardrailCompilePreview = (id: string) => read<GuardrailCompilePreview>(`/api/v1/guardrails/${encodeURIComponent(id)}/compile-preview`);
export const previewGuardrailCandidate = (input: { name: string; purpose: string; allowed_topics?: string[]; restricted_topics?: string[]; controls?: GuardrailControl[]; control_configurations?: GuardrailControlConfig[]; control_bindings?: GuardrailNativeControlBinding[]; safety_level?: SafetyLevel; output_delivery?: OutputDelivery }) => mutate<GuardrailCompilePreview>("/api/v1/guardrail-compile-previews", "POST", input);
export const getIntentAnalysisStatus = () => read<IntentAnalysisStatus>("/api/v1/intent-analysis-status");
export const analyzeGuardrailIntent = (input: { purpose: string; language: "en" | "zh-CN" }) => mutate<IntentAnalysis>("/api/v1/intent-analyses", "POST", input);

export const createTestRun = (guardrailId: string) => mutate<TestRun>("/api/v1/test-runs", "POST", { guardrail_id: guardrailId });
export const getTestRuns = (guardrailId?: string) => read<Collection<TestRun>>(`/api/v1/test-runs${query({ guardrail_id: guardrailId })}`);
export const getTestRun = (runId: string) => read<TestRun>(`/api/v1/test-runs/${encodeURIComponent(runId)}`);
export const getPlaygroundModels = () => read<Collection<PlaygroundModel>>("/api/v1/playground/models");
export const createPlaygroundInteraction = (
  guardrailId: string,
  input: {
    model_id: string;
    message: string;
    history?: { role: "user" | "assistant"; content: string }[];
  },
) => mutate<PlaygroundInteraction>("/api/v1/playground/interactions", "POST", { guardrail_id: guardrailId, ...input });
export const getTestCases = (guardrailId: string) => read<Collection<TestCase>>(`/api/v1/test-cases${query({ guardrail_id: guardrailId })}`);
export const createTestCase = (guardrailId: string, input: Pick<TestCase, "name" | "risk" | "phase" | "content" | "expected_decision" | "trusted_instruction" | "target_source" | "query" | "grounding_sources" | "expected_reasoning_result">) => mutate<TestCase>("/api/v1/test-cases", "POST", { guardrail_id: guardrailId, ...input });
export const deleteTestCase = (caseId: string) => mutate<void>(`/api/v1/test-cases/${encodeURIComponent(caseId)}`, "DELETE");

export const getAssignments = () => read<Collection<GuardrailAssignment>>("/api/v1/assignments");
export const getTrafficScopeFields = () => read<Collection<TrafficScopeField>>("/api/v1/traffic-scope-fields");
export const createAssignment = (input: { name: string; guardrail_id: string; traffic_scope: TrafficScopeExpression; enabled: boolean }) => mutate<GuardrailAssignment>("/api/v1/assignments", "POST", input);
export const setAssignmentEnabled = (id: string, enabled: boolean) => mutate<GuardrailAssignment>(`/api/v1/assignments/${encodeURIComponent(id)}`, "PATCH", { enabled });
export const getIntegrations = () => read<Collection<Integration>>("/api/v1/integrations");
export const getIntegration = (id: string) => read<Integration>(`/api/v1/integrations/${encodeURIComponent(id)}`);
export const createIntegration = (input: { name: string; adapter_id: IntegrationAdapterId }) => mutate<IntegrationRegistration>("/api/v1/integrations", "POST", input);
export const setIntegrationEnabled = (id: string, enabled: boolean) => mutate<Integration>(`/api/v1/integrations/${encodeURIComponent(id)}`, "PATCH", { enabled });
export const rotateIntegrationCredential = (id: string) => mutate<IntegrationRegistration>(`/api/v1/integrations/${encodeURIComponent(id)}/credentials`, "POST");
export const revokeIntegrationCredential = (integrationId: string, credentialId: string) => mutate<void>(`/api/v1/integrations/${encodeURIComponent(integrationId)}/credentials/${encodeURIComponent(credentialId)}`, "DELETE");
export const getDecisions = (filters: { limit?: number; guardrailId?: string; assignmentId?: string; kind?: string; outcome?: string; risk?: string; window?: MetricWindow } = {}) => read<Collection<DecisionEvent>>(`/api/v1/decisions${query({ limit: filters.limit, guardrail_id: filters.guardrailId, assignment_id: filters.assignmentId, kind: filters.kind, outcome: filters.outcome, risk: filters.risk, window: filters.window })}`);
export const getMetrics = (filters: { guardrailId?: string; window?: MetricWindow } = {}) => read<Metrics>(`/api/v1/metrics${query({ guardrail_id: filters.guardrailId, window: filters.window })}`);
export const getSystemStatus = () => read<SystemStatus>("/api/v1/system-status");
