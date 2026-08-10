export type SafetyLevel = "balanced" | "strict";
export type OutputDelivery = "interruptible" | "window_buffered" | "full_buffered";
export type Decision = "allow" | "transform" | "block";
export type TargetSource = "user_input" | "retrieved_content" | "tool_output";

export type Collection<T> = { items: T[]; count: number };

export type SafeProtection = {
  risk: string;
  action: string;
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
};

export type TestRun = {
  id: string;
  safe_id: string;
  status: "passed" | "failed" | "incomplete";
  metrics: EvaluationMetrics;
  results: EvaluationCaseResult[];
  created_at: string;
};

export type TestCase = {
  id: string;
  safe_id: string;
  name: string;
  risk: string;
  phase: "input" | "output";
  content: string;
  expected_decision: "allow" | "block" | "transform" | "intervene";
  origin: "generated" | "custom";
  updated_at: string;
  trusted_instruction: string;
  target_source: TargetSource;
};

export type RiskCoverage = {
  risk: string;
  passed: number;
  total: number;
  score: number | null;
};

export type Workload = {
  id: string;
  name: string;
  safe_id: string;
  safe_revision: number;
  filter: WorkloadFilterExpression;
  enabled: boolean;
  updated_at: string;
};

export type WorkloadFilterSource = "field" | "header" | "jwt_claim";
export type WorkloadFilterOperator = "equals" | "contains" | "starts_with" | "glob";

export type WorkloadFilterRule = {
  field: string;
  key?: string;
  operator: WorkloadFilterOperator;
  value: string;
};

export type WorkloadFilterExpression = {
  combinator: "and" | "or";
  rules: Array<WorkloadFilterRule | WorkloadFilterExpression>;
};

export type WorkloadFilterField = {
  id: string;
  group: "request" | "authentication" | "http" | "model" | "litellm" | "a2a";
  source: WorkloadFilterSource;
  key: string;
  operators: WorkloadFilterOperator[];
  values: string[];
  custom_key?: boolean;
};

export type WorkloadBinding = {
  id: string;
  workload_id: string;
  safe_id: string;
  safe_revision: number;
  enabled: boolean;
  updated_at: string;
};

export type Safe = {
  id: string;
  name: string;
  purpose: string;
  allowed_topics: string[];
  restricted_topics: string[];
  protections: SafeProtection[];
  safety_level: SafetyLevel;
  output_delivery: OutputDelivery;
  source_template_id: string | null;
  template_parameters: Record<string, string>;
  updated_at: string;
  status: "needs_testing" | "ready" | "protected";
  latest_test_run: TestRun | null;
  workload_count: number;
  test_case_count: number;
  tested_current: boolean;
  coverage: RiskCoverage[];
};

export type SafeTemplate = {
  id: string;
  name: string;
  description: string;
  purpose: string;
  allowed_topics: string[];
  restricted_topics: string[];
  protections: SafeProtection[];
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

export type ProtectionDefinition = {
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

export type Integration = {
  id: string;
  type: "litellm" | "http" | "a2a";
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
  safe_id: string | null;
  workload_id: string | null;
  risk: string | null;
  detail: string;
};

export type SystemStatus = {
  status: "healthy" | "degraded";
  active_workloads: number;
  online_gateways: number;
  total_gateways: number;
  capabilities: {
    deterministic: boolean;
    fast_semantic: boolean;
    deep_judge: boolean;
  };
};

export type Metrics = {
  window: "all_time";
  total_decisions: number;
  allowed: number;
  blocked: number;
  intervened: number;
  block_rate: number;
  intervention_rate: number;
  latest_test_p95_ms: number;
  active_workloads: number;
  total_workloads: number;
  safes_needing_test: number;
  total_safes: number;
  degraded_integrations: number;
  total_integrations: number;
  risk_counts: Array<{ risk: string; count: number }>;
  trend: Array<{ date: string; total: number; blocked: number; intervened: number }>;
  system_status: "healthy" | "degraded";
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
export type AuthStatus = { setup_required: boolean; authenticated: boolean; user: IdentityUser | null };
export type IntentAnalysisStatus = { available: boolean; provider: string | null; model: string | null };
export type IntentAnalysis = { summary: string; allowed_topics: string[]; restricted_topics: string[]; review_notes: string[] };

export type PlaygroundMessage = { role: "user" | "assistant"; content: string };
export type PlaygroundEvaluation = {
  id: string;
  decision: Decision;
  action: string;
  reason: string | null;
  content: string;
  role: "user" | "assistant";
  phase: "input" | "output";
  safe_id: string;
  safe_name: string;
  safe_version: "current";
  target_source: TargetSource;
  evaluated_context_count: number;
  findings: EvaluationFinding[];
  trace: EvaluationTraceStep[];
};

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
export const setupAdmin = (input: { display_name: string; email: string; password: string; preferred_language: "en" | "zh-CN" }) => mutate<{ user: IdentityUser }>("/api/v1/initial-admin", "POST", input);
export const login = (input: { email: string; password: string }) => mutate<{ user: IdentityUser }>("/api/v1/session", "POST", input);
export const logout = () => mutate<void>("/api/v1/session", "DELETE");
export const updateMe = (input: { preferred_language: "en" | "zh-CN" }) => mutate<{ user: IdentityUser }>("/api/v1/me", "PATCH", input);
export const getUsers = () => read<{ users: IdentityUser[] }>("/api/v1/users");
export const createUser = (input: { display_name: string; email: string; password: string; role: IdentityRole; preferred_language: "en" | "zh-CN" }) => mutate<IdentityUser>("/api/v1/users", "POST", input);
export const updateUser = (id: string, input: { display_name?: string; role?: IdentityRole; enabled?: boolean; password?: string }) => mutate<IdentityUser>(`/api/v1/users/${encodeURIComponent(id)}`, "PATCH", input);

export const getSafes = () => read<Collection<Safe>>("/api/v1/safes");
export const getSafe = (id: string) => read<Safe>(`/api/v1/safes/${encodeURIComponent(id)}`);
export const createSafe = (input: { name: string; purpose?: string; template_id?: string; template_parameters?: Record<string, string>; allowed_topics?: string[]; restricted_topics?: string[]; protections?: SafeProtection[]; safety_level?: SafetyLevel; output_delivery?: OutputDelivery }) => mutate<Safe>("/api/v1/safes", "POST", input);
export const updateSafe = (id: string, input: Partial<Pick<Safe, "name" | "purpose" | "allowed_topics" | "restricted_topics" | "protections" | "safety_level" | "output_delivery">>) => mutate<Safe>(`/api/v1/safes/${encodeURIComponent(id)}`, "PATCH", input);

export const getSafeTemplates = () => read<Collection<SafeTemplate>>("/api/v1/safe-templates");
export const getProtectionDefinitions = () => read<Collection<ProtectionDefinition>>("/api/v1/protection-definitions");
export const getIntentAnalysisStatus = () => read<IntentAnalysisStatus>("/api/v1/intent-analysis-status");
export const analyzeSafeIntent = (input: { purpose: string; language: "en" | "zh-CN" }) => mutate<IntentAnalysis>("/api/v1/intent-analyses", "POST", input);

export const getTestRuns = (safeId?: string) => read<Collection<TestRun>>(`/api/v1/test-runs${query({ safe_id: safeId })}`);
export const createTestRun = (safeId: string) => mutate<TestRun>("/api/v1/test-runs", "POST", { safe_id: safeId });
export const getTestCases = (safeId: string) => read<Collection<TestCase>>(`/api/v1/test-cases${query({ safe_id: safeId })}`);
export const createTestCase = (safeId: string, input: Pick<TestCase, "name" | "risk" | "phase" | "content" | "expected_decision" | "trusted_instruction" | "target_source">) => mutate<TestCase>("/api/v1/test-cases", "POST", { safe_id: safeId, ...input });
export const deleteTestCase = (caseId: string) => mutate<void>(`/api/v1/test-cases/${encodeURIComponent(caseId)}`, "DELETE");

export const createEvaluation = (input: { safe_id: string; role: "user" | "assistant"; content: string; messages: PlaygroundMessage[]; target_source?: TargetSource }) => mutate<PlaygroundEvaluation>("/api/v1/evaluations", "POST", input);

export const getWorkloads = () => read<Collection<Workload>>("/api/v1/workloads");
export const getWorkloadFilterFields = () => read<Collection<WorkloadFilterField>>("/api/v1/workload-filter-fields");
export const createWorkload = (input: { name: string; safe_id: string; filter: WorkloadFilterExpression; enabled: boolean }) => mutate<Workload>("/api/v1/workloads", "POST", input);
export const setWorkloadEnabled = (id: string, enabled: boolean) => mutate<Workload>(`/api/v1/workloads/${encodeURIComponent(id)}`, "PATCH", { enabled });
export const getWorkloadBindings = (filters: { safeId?: string; workloadId?: string } = {}) => read<Collection<WorkloadBinding>>(`/api/v1/workload-bindings${query({ safe_id: filters.safeId, workload_id: filters.workloadId })}`);

export const getIntegrations = () => read<Collection<Integration>>("/api/v1/integrations");
export const createIntegration = (input: { name: string; description: string; environment: "production" | "staging" | "development" | "test"; protocol: "litellm" | "http" | "a2a" }) => mutate<{ integration: Integration; credential: string }>("/api/v1/integrations", "POST", input);
export const getDecisions = (filters: { limit?: number; safeId?: string; workloadId?: string; outcome?: string; risk?: string } = {}) => read<Collection<DecisionEvent>>(`/api/v1/decisions${query({ limit: filters.limit, safe_id: filters.safeId, workload_id: filters.workloadId, outcome: filters.outcome, risk: filters.risk })}`);
export const getMetrics = () => read<Metrics>("/api/v1/metrics");
export const getSystemStatus = () => read<SystemStatus>("/api/v1/system-status");
