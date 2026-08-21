import * as controllerApi from "@/lib/controller-api";
import type {
  ActionDefinition,
  Collection,
  ComplianceDocumentAnalysis,
  Deployment,
  DeploymentRuntimeTrace,
  DeploymentTraceFinding,
  EvidenceRecord,
  Guardrail,
  GuardrailCompilePreview,
  GuardrailDeletionImpact,
  GuardrailFindingPage,
  GuardrailLoggingSettings,
  GuardrailPolicyBinding,
  GuardrailVersion,
  GuardrailVersionDetail,
  Integration,
  IntegrationAdapterId,
  IntegrationDeletionImpact,
  IntegrationRegistration,
  IntentAnalysis,
  IntentAnalysisStatus,
  LoggingLevel,
  Metrics,
  MetricTrendPoint,
  MetricWindow,
  OneTimeIntegrationCredential,
  OutputDelivery,
  PlaygroundDraftPreview,
  PlaygroundInteraction,
  PlaygroundModel,
  PlaygroundTarget,
  Policy,
  PolicyDraftValidationRun,
  PolicyValidation,
  ProgrammablePolicyDraft,
  ProgrammablePolicyVersion,
  RuntimeLogInteraction,
  RuntimeLogPage,
  SafetyLevel,
  SystemStatus,
  TestCase,
  TrafficScopeExpression,
  TrafficScopeField,
  ValidationRun,
} from "@/lib/api";

const DEFAULT_GUARDRAIL_ID = "guardrail-default";
const DEFAULT_DEPLOYMENT_ID = "deployment-default";

type CurrentPolicyBinding = controllerApi.GuardrailDraftConfig["policyBindings"][number];
type DeleteConfirmation = {
  reason: string;
  confirm_recent_traffic: boolean;
  confirmation_name?: string;
};
type CurrentCredential = { id: string; keyHint: string; createdAt: string };
type CurrentIntegration = controllerApi.Integration & {
  credentials?: CurrentCredential[];
  setup?: Integration["setup"];
  credentialId?: string;
  credentialKeyHint?: string;
  credentialCreatedAt?: string;
  desiredGeneration?: number;
  distributionStatus?: "ready" | "syncing";
};
type CurrentTestCase = {
  id: string;
  guardrailId: string;
  name: string;
  policyId: string;
  phase: "input" | "output";
  content: string;
  expectedDecision: "allow" | "block" | "transform" | "intervene";
  origin: "generated" | "custom";
  updatedAt: string;
  trustedInstruction: string;
  targetSource: TestCase["target_source"];
  query: string;
  groundingSources: string[];
  expectedReasoningResult: TestCase["expected_reasoning_result"];
  sourcePolicyId: string | null;
  sourcePolicyVersion: string | null;
  sourceCaseId: string | null;
  coveredRuleIds: string[];
  caseType: string;
  required: boolean;
  excluded: boolean;
};

const emptyCollection = <T>(): Collection<T> => ({ items: [], count: 0 });

async function currentRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const formData = typeof FormData !== "undefined" && init?.body instanceof FormData;
  const response = await fetch(path, {
    credentials: "same-origin",
    ...init,
    headers: init?.body && !formData ? { "content-type": "application/json", ...init.headers } : init?.headers,
  });
  return parseResponse<T>(response);
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (response.status === 204) return undefined as T;
  const payload = await response.json().catch(() => ({})) as Record<string, unknown>;
  if (!response.ok) {
    if (response.status === 401) window.dispatchEvent(new CustomEvent("tasklattice:unauthorized"));
    const error = payload.error && typeof payload.error === "object"
      ? payload.error as Record<string, unknown>
      : undefined;
    throw new Error(apiErrorMessage(error?.detail ?? error?.message ?? payload.detail ?? payload.message, response.status));
  }
  return payload as T;
}

function apiErrorMessage(detail: unknown, status: number): string {
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const messages = detail.map((item) => {
      if (typeof item === "string") return item;
      if (!item || typeof item !== "object") return "";
      const issue = item as { loc?: unknown; msg?: unknown; message?: unknown };
      const message = typeof issue.msg === "string" ? issue.msg : typeof issue.message === "string" ? issue.message : "";
      const location = Array.isArray(issue.loc)
        ? issue.loc.filter((part) => part !== "body").map(String).join(".")
        : "";
      return message ? `${location ? `${location}: ` : ""}${message}` : "";
    }).filter(Boolean);
    if (messages.length) return messages.join("; ");
  }
  if (detail && typeof detail === "object") {
    const issue = detail as { msg?: unknown; message?: unknown };
    if (typeof issue.msg === "string" && issue.msg) return issue.msg;
    if (typeof issue.message === "string" && issue.message) return issue.message;
  }
  return `Request failed with status ${status}.`;
}

function toCurrentBinding(binding: GuardrailPolicyBinding): CurrentPolicyBinding {
  return {
    policyId: binding.policy_id,
    policyVersion: binding.policy_version,
    action: binding.action ?? null,
    parameterValues: binding.parameter_values,
    enabledRuleIds: binding.enabled_rule_ids,
    ruleActions: binding.rule_actions,
    enabledRails: binding.enabled_rails,
    reasoningPolicy: binding.reasoning_policy ? {
      policyId: binding.reasoning_policy.policy_id,
      policyVersion: binding.reasoning_policy.policy_version,
      confidenceThreshold: binding.reasoning_policy.confidence_threshold,
    } : null,
  };
}

function fromCurrentBinding(binding: CurrentPolicyBinding): GuardrailPolicyBinding {
  return {
    policy_id: binding.policyId,
    policy_version: binding.policyVersion,
    action: binding.action,
    parameter_values: binding.parameterValues,
    enabled_rule_ids: binding.enabledRuleIds,
    rule_actions: binding.ruleActions,
    enabled_rails: binding.enabledRails,
    reasoning_policy: binding.reasoningPolicy ? {
      policy_id: binding.reasoningPolicy.policyId,
      policy_version: binding.reasoningPolicy.policyVersion,
      confidence_threshold: binding.reasoningPolicy.confidenceThreshold,
    } : null,
  };
}

function mapGuardrail(
  value: controllerApi.Guardrail,
  deploymentCount: number,
  publishedVersionCount?: number,
): Guardrail {
  const isDefault = value.id === DEFAULT_GUARDRAIL_ID;
  const latestValidation = value.latestValidationRun ? mapValidationRun(value.latestValidationRun) : null;
  const testedCurrent = Boolean(latestValidation && latestValidation.source_draft_version === value.draftRevision && latestValidation.status === "passed");
  const published = value.status === "active" && value.activeVersion !== null;
  const publishedCurrent = published && value.activeSourceDraftRevision === value.draftRevision;
  return {
    id: value.id,
    name: value.name,
    purpose: value.description,
    allowed_topics: value.draftConfig.allowedTopics,
    restricted_topics: value.draftConfig.restrictedTopics,
    policy_bindings: value.draftConfig.policyBindings.map(fromCurrentBinding),
    safety_level: value.draftConfig.safetyLevel,
    output_delivery: value.draftConfig.outputDelivery,
    updated_at: value.updatedAt,
    status: publishedCurrent ? (deploymentCount > 0 ? "protected" : "ready") : "needs_validation",
    latest_validation_run: latestValidation,
    deployment_count: deploymentCount,
    test_case_count: value.testCaseCount,
    excluded_test_case_count: value.excludedTestCaseCount,
    excluded_test_case_ids: value.excludedTestCaseIds,
    draft_revision: value.draftRevision,
    tested_current: testedCurrent,
    published_current: publishedCurrent,
    published_version_count: publishedVersionCount,
    is_default: isDefault,
    system_managed: isDefault,
    local_only: isDefault,
    coverage: [],
  };
}

function deploymentCounts(values: controllerApi.Deployment[]): Map<string, number> {
  const result = new Map<string, number>();
  for (const deployment of values) {
    if (deployment.enabled) result.set(deployment.guardrailId, (result.get(deployment.guardrailId) ?? 0) + 1);
  }
  return result;
}

export async function getGuardrails(): Promise<Collection<Guardrail>> {
  const [guardrails, deployments] = await Promise.all([
    controllerApi.listControllerGuardrails(),
    controllerApi.listControllerDeployments(),
  ]);
  const counts = deploymentCounts(deployments.items);
  const items = guardrails.items.map((item) => mapGuardrail(item, counts.get(item.id) ?? 0));
  return { items, count: items.length };
}

export async function getGuardrail(id: string): Promise<Guardrail> {
  const [guardrail, deployments] = await Promise.all([
    controllerApi.getControllerGuardrail(id),
    controllerApi.listControllerDeployments(),
  ]);
  const count = deployments.items.filter((item) => item.enabled && item.guardrailId === id).length;
  return mapGuardrail(guardrail, count, guardrail.versions.length);
}

export async function createGuardrail(input: {
  name: string;
  purpose?: string;
  allowed_topics?: string[];
  restricted_topics?: string[];
  policy_bindings: GuardrailPolicyBinding[];
  safety_level?: SafetyLevel;
  output_delivery?: OutputDelivery;
}): Promise<Guardrail> {
  const created = await controllerApi.createControllerGuardrail({
    name: input.name,
    description: input.purpose ?? "",
    draftConfig: {
      allowedTopics: input.allowed_topics ?? [],
      restrictedTopics: input.restricted_topics ?? [],
      policyBindings: input.policy_bindings.map(toCurrentBinding),
      safetyLevel: input.safety_level ?? "balanced",
      outputDelivery: input.output_delivery ?? "window_buffered",
    },
    runtimeProfile: "auto",
  });
  return mapGuardrail(created, 0, 0);
}

export const updateGuardrail = (
  id: string,
  input: Partial<Pick<Guardrail, "name" | "purpose" | "allowed_topics" | "restricted_topics" | "policy_bindings" | "safety_level" | "output_delivery">>,
) => updateGuardrailDraft(id, input);

async function updateGuardrailDraft(
  id: string,
  input: Partial<Pick<Guardrail, "name" | "purpose" | "allowed_topics" | "restricted_topics" | "policy_bindings" | "safety_level" | "output_delivery">>,
): Promise<Guardrail> {
  const current = await controllerApi.getControllerGuardrail(id);
  const updated = await controllerApi.updateControllerGuardrail(id, {
    ...(input.name !== undefined ? { name: input.name } : {}),
    ...(input.purpose !== undefined ? { description: input.purpose } : {}),
    draftConfig: {
      allowedTopics: input.allowed_topics ?? current.draftConfig.allowedTopics,
      restrictedTopics: input.restricted_topics ?? current.draftConfig.restrictedTopics,
      policyBindings: (input.policy_bindings ?? current.draftConfig.policyBindings.map(fromCurrentBinding)).map(toCurrentBinding),
      safetyLevel: input.safety_level ?? current.draftConfig.safetyLevel,
      outputDelivery: input.output_delivery ?? current.draftConfig.outputDelivery,
    },
  });
  return mapGuardrail(updated, 0, current.versions.length);
}

export async function getGuardrailDeletionImpact(id: string): Promise<GuardrailDeletionImpact> {
  const [impact, guardrail] = await Promise.all([
    controllerApi.getControllerGuardrailDeletionImpact(id),
    controllerApi.getControllerGuardrail(id),
  ]);
  return {
    guardrail_id: impact.resourceId,
    guardrail_name: guardrail.name,
    window_minutes: impact.windowMinutes,
    incoming_request_count: impact.incomingRequestCount,
    last_request_at: impact.lastRequestAt,
    active_deployment_count: impact.activeDeploymentCount,
    telemetry_fresh: impact.telemetryFresh,
    telemetry_watermark: impact.telemetryWatermark,
    requires_second_confirmation: impact.requiresSecondConfirmation,
    requires_confirmation: impact.requiresSecondConfirmation,
  };
}

export const deleteGuardrail = (id: string, confirmation: DeleteConfirmation) => controllerApi.deleteControllerGuardrail(id, {
  reason: confirmation.reason,
  confirmRecentTraffic: confirmation.confirm_recent_traffic,
  ...(confirmation.confirmation_name ? { confirmationName: confirmation.confirmation_name } : {}),
});

function mapVersion(value: controllerApi.GuardrailVersion, guardrail: controllerApi.Guardrail): GuardrailVersion {
  const compiler = value.artifact?.compilerVersion ?? stringValue(value.plan.compiler_version) ?? "tasklattice-controller-plan-v1";
  return {
    guardrail_id: value.guardrailId,
    version: value.version,
    source_draft_version: value.sourceDraftRevision,
    compiler_version: compiler,
    plan_checksum: value.artifact?.checksum ?? "",
    created_at: value.createdAt,
    active: guardrail.activeVersion === value.version,
    runtime_engine: runtimeEngine(value.runtimeProfile),
    config_checksum: value.artifact?.checksum ?? "",
    execution_mode: "nemo_only",
    compile_status: value.status,
    failure_reason: value.failureReason,
  };
}

function mapVersionDetail(value: controllerApi.GuardrailVersion, guardrail: controllerApi.Guardrail): GuardrailVersionDetail {
  const base = mapVersion(value, guardrail);
  const steps = arrayOfRecords(value.plan.steps);
  const modules = arrayOfRecords(value.plan.modules);
  const artifactBindings = arrayOfRecords(value.artifact?.actionBindings);
  const dependencies = dependencyRecords(value.artifact?.dependencyManifest);
  const actions = artifactBindings.length ? artifactBindings.map((binding) => ({
    name: stringValue(binding.action_name) ?? stringValue(binding.name) ?? stringValue(binding.id) ?? "runtime-action",
    version: stringValue(binding.action_version) ?? stringValue(binding.version),
    flow: stringValue(binding.flow_name) ?? stringValue(binding.flow),
    phases: arrayOfStrings(binding.phases).filter((phase): phase is "input" | "output" => phase === "input" || phase === "output"),
    timeout_ms: numberValue(binding.timeout_ms) ?? 0,
    failure_mode: stringValue(binding.failure_mode) ?? "fail_closed",
  })) : steps.map((step) => ({
    name: stringValue(step.risk) ?? "controller-plan-step",
    version: null,
    flow: stringValue(step.id),
    phases: arrayOfStrings(step.phases).filter((phase): phase is "input" | "output" => phase === "input" || phase === "output"),
    timeout_ms: moduleTimeoutForStep(step, modules),
    failure_mode: "fail_closed",
  }));
  return {
    ...base,
    safety_level: enumValue(value.plan.safety_level, ["balanced", "strict"]) ?? guardrail.draftConfig.safetyLevel,
    output_delivery: enumValue(value.plan.output_delivery, ["interruptible", "window_buffered", "full_buffered"]) ?? guardrail.draftConfig.outputDelivery,
    runtime_profile: value.runtimeProfile,
    colang_version: colangVersion(value.runtimeProfile),
    rails: steps.flatMap((step) => arrayOfStrings(step.phases).map((phase) => ({
      rail_type: phase === "output" ? "output" as const : "input" as const,
      flow: stringValue(step.id) ?? stringValue(step.risk) ?? "controller-plan-step",
    }))),
    actions,
    models: dependencies.filter((item) => item.kind === "model").map((item) => item.name),
    features: dependencies.filter((item) => item.kind === "feature").map((item) => item.name),
    dependencies,
    estimated_critical_path_ms: Math.max(0, ...modules.map((item) => numberValue(item.timeout_ms) ?? 0)),
    policy_bindings: guardrail.draftConfig.policyBindings.map((currentBinding) => {
      const binding = fromCurrentBinding(currentBinding);
      return {
        policy_id: binding.policy_id,
        policy_version: binding.policy_version,
        action: binding.action ?? null,
        enabled_rule_ids: binding.enabled_rule_ids,
        enabled_rails: binding.enabled_rails,
      };
    }),
    artifacts: value.artifact ? [
      { path: "config/config.yml", language: "yaml", content: value.artifact.configYaml },
      ...(value.artifact.colangContent ? [{ path: "config/rails.co", language: "colang", content: value.artifact.colangContent }] : []),
      { path: "artifact/plan.json", language: "json", content: JSON.stringify(value.artifact.plan, null, 2) },
      { path: "artifact/prompts.json", language: "json", content: JSON.stringify(value.artifact.prompts, null, 2) },
      { path: "artifact/actions.json", language: "json", content: JSON.stringify(value.artifact.actionBindings, null, 2) },
      { path: "artifact/dependencies.json", language: "json", content: JSON.stringify(value.artifact.dependencyManifest, null, 2) },
    ] : [],
  };
}

function dependencyRecords(value: unknown): Array<{ kind: string; name: string; version: string }> {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (Array.isArray(item) && item.length >= 3 && item.slice(0, 3).every((part) => typeof part === "string")) {
      return [{ kind: item[0] as string, name: item[1] as string, version: item[2] as string }];
    }
    if (item && typeof item === "object") {
      const record = item as Record<string, unknown>;
      const kind = stringValue(record.kind);
      const name = stringValue(record.name);
      const version = stringValue(record.version);
      return kind && name && version ? [{ kind, name, version }] : [];
    }
    return [];
  });
}

export async function getGuardrailVersions(guardrailId: string): Promise<Collection<GuardrailVersion>> {
  const guardrail = await controllerApi.getControllerGuardrail(guardrailId);
  const items = guardrail.versions.map((item) => mapVersion(item, guardrail));
  return { items, count: items.length };
}

export async function getGuardrailVersion(guardrailId: string, version: number): Promise<GuardrailVersionDetail> {
  const guardrail = await controllerApi.getControllerGuardrail(guardrailId);
  const found = guardrail.versions.find((item) => item.version === version);
  if (!found) throw new Error(`Guardrail version ${version} was not found.`);
  return mapVersionDetail(found, guardrail);
}

export async function publishGuardrail(guardrailId: string): Promise<GuardrailVersion> {
  const result = await controllerApi.publishControllerGuardrail(guardrailId);
  for (let attempt = 0; attempt < 120; attempt += 1) {
    const guardrail = await controllerApi.getControllerGuardrail(guardrailId);
    const version = guardrail.versions.find((item) => item.version === result.version);
    if (version?.status === "ready") return mapVersion(version, guardrail);
    if (version?.status === "failed") throw new Error(version.failureReason || `Guardrail version ${result.version} failed to compile.`);
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`Guardrail version ${result.version} is still compiling. Check Controller activity for progress.`);
}

export const rollbackGuardrail = (guardrailId: string, version: number) =>
  controllerApi.rollbackControllerGuardrail(guardrailId, version).then(async (item) => {
    const guardrail = await controllerApi.getControllerGuardrail(guardrailId);
    return mapVersion(item, guardrail);
  });

export function previewGuardrailCandidate(input: {
  name: string;
  purpose: string;
  allowed_topics?: string[];
  restricted_topics?: string[];
  policy_bindings: GuardrailPolicyBinding[];
  safety_level?: SafetyLevel;
  output_delivery?: OutputDelivery;
}): Promise<GuardrailCompilePreview> {
  return controllerApi.previewControllerGuardrailPlan({
    name: input.name,
    description: input.purpose,
    draftConfig: {
      allowedTopics: input.allowed_topics ?? [],
      restrictedTopics: input.restricted_topics ?? [],
      policyBindings: input.policy_bindings.map(toCurrentBinding),
      safetyLevel: input.safety_level ?? "balanced",
      outputDelivery: input.output_delivery ?? "full_buffered",
    },
    runtimeProfile: "auto",
  }).then((value) => ({
    ...value,
    rails: value.rails.flatMap((rail) => ["input", "output", "retrieval", "dialog", "execution"].includes(rail.rail_type)
      ? [{ ...rail, rail_type: rail.rail_type as GuardrailCompilePreview["rails"][number]["rail_type"] }]
      : []),
  }));
}

export async function getGuardrailCompilePreview(id: string): Promise<GuardrailCompilePreview> {
  const guardrail = await controllerApi.getControllerGuardrail(id);
  return previewGuardrailCandidate({
    name: guardrail.name,
    purpose: guardrail.description,
    policy_bindings: guardrail.draftConfig.policyBindings.map(fromCurrentBinding),
    safety_level: guardrail.draftConfig.safetyLevel,
    output_delivery: guardrail.draftConfig.outputDelivery,
  });
}

export const getPolicies = () => currentRequest<Collection<Policy>>("/api/v1/policies");
export const getPolicy = (id: string) => currentRequest<Policy>(`/api/v1/policies/${encodeURIComponent(id)}`);
export const getActionCatalog = () => currentRequest<Collection<ActionDefinition>>("/api/v1/actions");

export const createProgrammablePolicy = (input: { name: string; description: string; owner: string; draft: ProgrammablePolicyDraft }) => currentRequest<Policy>("/api/v1/policies", {
  method: "POST", body: JSON.stringify(input),
});
export const updateProgrammablePolicy = (id: string, input: { name?: string; description?: string; owner?: string; draft?: ProgrammablePolicyDraft }) => currentRequest<Policy>(`/api/v1/policies/${encodeURIComponent(id)}`, {
  method: "PATCH", body: JSON.stringify(input),
});
export const deleteProgrammablePolicy = (id: string) => currentRequest<void>(`/api/v1/policies/${encodeURIComponent(id)}`, { method: "DELETE" });
export const validateProgrammablePolicy = (id: string) => currentRequest<PolicyValidation>(`/api/v1/policies/${encodeURIComponent(id)}/validate`, { method: "POST" });
export const getLatestProgrammablePolicyValidation = (id: string) => currentRequest<PolicyDraftValidationRun>(`/api/v1/policies/${encodeURIComponent(id)}/validation-runs/latest`);
export async function runProgrammablePolicyValidation(id: string): Promise<PolicyDraftValidationRun> {
  const initial = await currentRequest<PolicyDraftValidationRun>(`/api/v1/policies/${encodeURIComponent(id)}/validation-runs`, { method: "POST" });
  const deadline = Date.now() + 5 * 60_000;
  let current = initial;
  while ((current.status === "queued" || current.status === "running") && Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 1_000));
    current = await getLatestProgrammablePolicyValidation(id);
  }
  if (current.status === "queued" || current.status === "running") throw new Error("Policy Validation timed out while waiting for GuardRails 0.");
  return current;
}
export const publishProgrammablePolicy = (id: string) => currentRequest<ProgrammablePolicyVersion>(`/api/v1/policies/${encodeURIComponent(id)}/publish`, { method: "POST" });

export const getIntentAnalysisStatus = () => currentRequest<IntentAnalysisStatus>("/api/v1/intent-analysis-status");
export const analyzeGuardrailIntent = (input: { purpose: string; language: "en" | "zh-CN" }) => currentRequest<IntentAnalysis>("/api/v1/intent-analyses", {
  method: "POST",
  body: JSON.stringify(input),
});
export const analyzeComplianceDocuments = (files: File[], language: "en" | "zh-CN") => {
  const form = new FormData();
  for (const file of files) form.append("files", file, file.name);
  form.append("language", language);
  return currentRequest<ComplianceDocumentAnalysis>("/api/v1/compliance-document-analyses", { method: "POST", body: form });
};

function runtimeEngine(profile: string): string {
  if (profile === "iorails_native") return "iorails";
  return "llmrails";
}

function colangVersion(profile: string): string {
  if (profile === "llmrails_colang1_standard") return "1.0";
  if (profile === "llmrails_colang2_programmable") return "2.x";
  if (profile === "iorails_native") return "n/a";
  return "auto";
}

function moduleTimeoutForStep(step: Record<string, unknown>, modules: Record<string, unknown>[]): number {
  const stepId = stringValue(step.id);
  if (!stepId) return 0;
  return modules.find((item) => arrayOfStrings(item.step_ids).includes(stepId))
    ? numberValue(modules.find((item) => arrayOfStrings(item.step_ids).includes(stepId))?.timeout_ms) ?? 0
    : 0;
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function enumValue<T extends string>(value: unknown, values: readonly T[]): T | null {
  return typeof value === "string" && values.includes(value as T) ? value as T : null;
}

function arrayOfRecords(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object" && !Array.isArray(item)) : [];
}

function arrayOfStrings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

export const getGuardrailLoggingSettings = (id: string) => currentRequest<CurrentLoggingSettings>(`/api/v1/guardrails/${encodeURIComponent(id)}/logging`).then(mapLogging);
export const updateGuardrailLoggingSettings = (id: string, level: LoggingLevel, acknowledgeCost = false) => currentRequest<CurrentLoggingSettings>(`/api/v1/guardrails/${encodeURIComponent(id)}/logging`, { method: "PATCH", body: JSON.stringify({ level, acknowledgeCost }) }).then(mapLogging);

export const createValidationRun = (guardrailId: string) => currentRequest<controllerApi.ValidationRun>("/api/v1/validation-runs", { method: "POST", body: JSON.stringify({ guardrailId }) }).then(waitForValidation);
export async function getValidationRuns(guardrailId?: string): Promise<Collection<ValidationRun>> {
  const suffix = guardrailId ? `?guardrailId=${encodeURIComponent(guardrailId)}` : "";
  const response = await currentRequest<{ items: controllerApi.ValidationRun[]; count: number }>(`/api/v1/validation-runs${suffix}`);
  return { items: response.items.map(mapValidationRun), count: response.count };
}
export const getValidationRun = (runId: string) => currentRequest<controllerApi.ValidationRun>(`/api/v1/validation-runs/${encodeURIComponent(runId)}`).then(mapValidationRun);
export const getPlaygroundModels = () => currentRequest<Collection<PlaygroundModel>>("/api/v1/playground/models");
export const preparePlaygroundDraftPreview = (guardrailId: string) =>
  currentRequest<PlaygroundDraftPreview>(`/api/v1/playground/draft-previews/${encodeURIComponent(guardrailId)}`, {
    method: "POST",
    body: JSON.stringify({}),
  });
export const createPlaygroundInteraction = (
  guardrailId: string,
  input: {
    target: PlaygroundTarget;
    model_id: string;
    message: string;
    history?: { role: "user" | "assistant"; content: string }[];
  },
) => currentRequest<PlaygroundInteraction>(input.target.kind === "draft"
  ? `/api/v1/playground/draft-interactions/${encodeURIComponent(guardrailId)}`
  : `/api/v1/playground/interactions/${encodeURIComponent(guardrailId)}`, {
  method: "POST",
  body: JSON.stringify({
    model_id: input.model_id,
    message: input.message,
    history: input.history,
    ...(input.target.kind === "draft"
      ? { preview_id: input.target.preview_id }
      : { guardrail_version: input.target.version }),
  }),
});
export async function getTestCases(guardrailId: string): Promise<Collection<TestCase>> {
  const response = await currentRequest<{ items: CurrentTestCase[]; count: number }>(`/api/v1/test-cases?guardrailId=${encodeURIComponent(guardrailId)}`);
  return { items: response.items.map(mapTestCase), count: response.count };
}
export const createTestCase = (
  guardrailId: string,
  input: Pick<TestCase, "name" | "policy_id" | "phase" | "content" | "expected_decision" | "trusted_instruction" | "target_source" | "query" | "grounding_sources" | "expected_reasoning_result">,
) => currentRequest<CurrentTestCase>("/api/v1/test-cases", { method: "POST", body: JSON.stringify({
  guardrailId,
  name: input.name,
  policyId: input.policy_id,
  phase: input.phase,
  content: input.content,
  expectedDecision: input.expected_decision,
  trustedInstruction: input.trusted_instruction,
  targetSource: input.target_source,
  query: input.query,
  groundingSources: input.grounding_sources,
  expectedReasoningResult: input.expected_reasoning_result,
}) }).then(mapTestCase);
export const deleteTestCase = (caseId: string) => currentRequest<void>(`/api/v1/test-cases/${encodeURIComponent(caseId)}`, { method: "DELETE" });
export const excludeGuardrailTestCase = (guardrailId: string, caseId: string) => currentRequest<TestCase>(
  `/api/v1/guardrails/${encodeURIComponent(guardrailId)}/validation-scope`,
  { method: "PATCH", body: JSON.stringify({ caseId, excluded: true }) },
);
export const restoreGuardrailTestCase = (guardrailId: string, caseId: string) => currentRequest<TestCase>(
  `/api/v1/guardrails/${encodeURIComponent(guardrailId)}/validation-scope`,
  { method: "PATCH", body: JSON.stringify({ caseId, excluded: false }) },
);

type CurrentLoggingSettings = { id: string; level: LoggingLevel; updatedAt?: string; retentionDays?: number; contentCaptureEnabled?: boolean };

function mapLogging(item: CurrentLoggingSettings): GuardrailLoggingSettings {
  return {
    guardrail_id: item.id,
    level: item.level,
    updated_at: item.updatedAt ?? new Date().toISOString(),
    updated_by: null,
    retention_days: item.retentionDays ?? 30,
    content_capture_enabled: item.contentCaptureEnabled ?? false,
  };
}

function mapValidationRun(value: controllerApi.ValidationRun): ValidationRun {
  return {
    id: value.id,
    guardrail_id: value.guardrailId,
    guardrail_version: value.guardrailVersion,
    source_draft_version: value.sourceDraftRevision,
    status: value.status === "passed" ? "passed" : value.status === "failed" ? "failed" : "incomplete",
    metrics: {
      total: value.metrics.total,
      passed: value.metrics.passed,
      compliance_rate: value.metrics.complianceRate,
      false_positive_rate: value.metrics.falsePositiveRate,
      false_negative_rate: value.metrics.falseNegativeRate,
      deep_escalation_rate: value.metrics.deepEscalationRate,
      p95_latency_ms: value.metrics.p95LatencyMs,
    },
    results: value.results.map(mapValidationResult),
    excluded_case_ids: value.excludedCaseIds,
    created_at: value.createdAt,
  };
}

function mapValidationResult(value: Record<string, unknown>): ValidationRun["results"][number] {
  const phase = stringValue(value.phase) === "output" ? "output" : "input";
  return {
    case_id: stringValue(value.caseId) ?? "",
    name: stringValue(value.name) ?? "",
    policy_id: stringValue(value.policyId) ?? "",
    expected_decision: stringValue(value.expectedDecision) ?? "",
    actual_decision: stringValue(value.actualDecision) ?? "error",
    passed: Boolean(value.passed),
    stage_reached: stringValue(value.stageReached) ?? "none",
    latency_ms: numberValue(value.latencyMs) ?? 0,
    reason: stringValue(value.reason) ?? "",
    phase,
    input_content: stringValue(value.inputContent) ?? "",
    action: stringValue(value.action) ?? "pass",
    output_content: stringValue(value.outputContent) ?? "",
    findings: arrayOfRecords(value.findings) as ValidationRun["results"][number]["findings"],
    trace: arrayOfRecords(value.trace) as ValidationRun["results"][number]["trace"],
    trusted_instruction: stringValue(value.trustedInstruction) ?? "",
    target_source: (stringValue(value.targetSource) ?? (phase === "output" ? "model_output" : "user_input")) as TestCase["target_source"],
    query: stringValue(value.query) ?? "",
    grounding_sources: arrayOfStrings(value.groundingSources),
    expected_reasoning_result: stringValue(value.expectedReasoningResult) as ValidationRun["results"][number]["expected_reasoning_result"],
    actual_reasoning_result: stringValue(value.actualReasoningResult) as ValidationRun["results"][number]["actual_reasoning_result"],
    case_type: stringValue(value.caseType) ?? "scenario",
    required: value.required !== false,
    expected_failure: stringValue(value.expectedFailure),
    actual_failure: stringValue(value.actualFailure),
    concurrency_group: stringValue(value.concurrencyGroup),
    source_policy_id: stringValue(value.sourcePolicyId),
    source_policy_version: stringValue(value.sourcePolicyVersion),
    source_case_id: stringValue(value.sourceCaseId),
    covered_rule_ids: arrayOfStrings(value.coveredRuleIds),
    matched_rule_ids: arrayOfStrings(value.matchedRuleIds),
  };
}

async function waitForValidation(initial: controllerApi.ValidationRun): Promise<ValidationRun> {
  let current = initial;
  const deadline = Date.now() + 5 * 60_000;
  while ((current.status === "queued" || current.status === "running") && Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 1_000));
    current = await currentRequest<controllerApi.ValidationRun>(`/api/v1/validation-runs/${encodeURIComponent(initial.id)}`);
  }
  return mapValidationRun(current);
}

function mapTestCase(value: CurrentTestCase): TestCase {
  return {
    id: value.id,
    guardrail_id: value.guardrailId,
    name: value.name,
    policy_id: value.policyId,
    phase: value.phase,
    content: value.content,
    expected_decision: value.expectedDecision,
    origin: value.origin,
    updated_at: value.updatedAt,
    trusted_instruction: value.trustedInstruction,
    target_source: value.targetSource,
    query: value.query,
    grounding_sources: value.groundingSources,
    expected_reasoning_result: value.expectedReasoningResult,
    source_policy_id: value.sourcePolicyId,
    source_policy_version: value.sourcePolicyVersion,
    source_case_id: value.sourceCaseId,
    covered_rule_ids: value.coveredRuleIds,
    case_type: value.caseType,
    required: value.required,
    excluded: value.excluded,
  };
}

function normalizeTrafficScope(value: Record<string, unknown>): TrafficScopeExpression {
  if ((value.combinator === "and" || value.combinator === "or") && Array.isArray(value.conditions)) {
    return value as TrafficScopeExpression;
  }
  if (Object.keys(value).length === 0) return { combinator: "and", conditions: [] };
  throw new Error("Controller 返回了旧 UI 无法表达的 Traffic Scope。");
}

function mapDeployments(
  values: controllerApi.Deployment[],
  guardrails: controllerApi.Guardrail[],
): Deployment[] {
  const guardrailById = new Map(guardrails.map((item) => [item.id, item]));
  return values.map((item) => {
    const isDefault = item.id === DEFAULT_DEPLOYMENT_ID;
    return {
      id: item.id,
      name: item.name,
      guardrail_id: item.guardrailId,
      guardrail_version: item.guardrailVersion ?? guardrailById.get(item.guardrailId)?.activeVersion ?? 0,
      integration_id: item.integrationId,
      route_order: item.routeOrder,
      traffic_scope: normalizeTrafficScope(item.trafficScope),
      enabled: item.enabled,
      is_default: isDefault,
      system_managed: isDefault,
      updated_at: item.updatedAt,
    };
  });
}

export async function getDeployments(): Promise<Collection<Deployment>> {
  const [deployments, guardrails] = await Promise.all([
    controllerApi.listControllerDeployments(),
    controllerApi.listControllerGuardrails(),
  ]);
  const items = mapDeployments(deployments.items, guardrails.items);
  return { items, count: items.length };
}

export async function getDeployment(id: string): Promise<Deployment> {
  const deployments = await getDeployments();
  const found = deployments.items.find((item) => item.id === id);
  if (!found) throw new Error(`Deployment ${id} was not found.`);
  return found;
}

export async function createDeployment(input: {
  name: string;
  guardrail_id: string;
  integration_id?: string | null;
  traffic_scope: TrafficScopeExpression;
  enabled: boolean;
}): Promise<Deployment> {
  if (!input.integration_id) throw new Error("Controller 部署必须选择 Integration。");
  const created = await controllerApi.createControllerDeployment({
    name: input.name,
    guardrailId: input.guardrail_id,
    integrationId: input.integration_id,
    poolId: "default",
    trafficScope: input.traffic_scope,
    enabled: input.enabled,
  });
  const guardrail = await controllerApi.getControllerGuardrail(created.guardrailId);
  return mapDeployments([created], [guardrail])[0] as Deployment;
}

export async function createDeploymentBindings(input: {
  name: string;
  guardrail_id: string;
  integration_ids: string[];
  traffic_scope: TrafficScopeExpression;
  enabled: boolean;
}): Promise<Collection<Deployment>> {
  if (!input.integration_ids.length) return emptyCollection();
  const response = await currentRequest<{ items: controllerApi.Deployment[]; count: number }>("/api/v1/deployment-bindings", {
    method: "POST",
    body: JSON.stringify({
      name: input.name,
      guardrailId: input.guardrail_id,
      integrationIds: input.integration_ids,
      poolId: "default",
      trafficScope: input.traffic_scope,
      enabled: input.enabled,
    }),
  });
  const guardrail = await controllerApi.getControllerGuardrail(input.guardrail_id);
  return { items: mapDeployments(response.items, [guardrail]), count: response.count };
}

export async function reorderDeploymentRoutes(integrationId: string, deploymentIds: string[]): Promise<Collection<Deployment>> {
  const response = await controllerApi.reorderControllerDeployments(integrationId, deploymentIds);
  const guardrails = await controllerApi.listControllerGuardrails();
  const items = mapDeployments(response.items, guardrails.items);
  return { items, count: items.length };
}
export async function setDeploymentEnabled(id: string, enabled: boolean): Promise<Deployment> {
  const item = await controllerApi.setControllerDeploymentEnabled(id, enabled);
  const guardrail = await controllerApi.getControllerGuardrail(item.guardrailId);
  return mapDeployments([item], [guardrail])[0]!;
}
export async function updateDeploymentTrafficScope(id: string, trafficScope: TrafficScopeExpression): Promise<Deployment> {
  const item = await controllerApi.updateControllerDeploymentTrafficScope(id, trafficScope);
  const guardrail = await controllerApi.getControllerGuardrail(item.guardrailId);
  return mapDeployments([item], [guardrail])[0]!;
}
export const getTrafficScopeFields = (): Promise<Collection<TrafficScopeField>> => currentRequest<Collection<TrafficScopeField>>("/api/v1/traffic-scope-fields");

export async function getDeploymentTraces(id: string, limit = 100): Promise<Collection<DeploymentRuntimeTrace>> {
  const events = await controllerApi.listRuntimeEvents(Math.min(10_000, Math.max(1, limit)), { deploymentId: id });
  const matching = events.items;
  return { items: matching.slice(0, limit).map(mapDeploymentTrace), count: matching.length };
}

function mapDeploymentTrace(event: controllerApi.RuntimeEvent): DeploymentRuntimeTrace {
  const outcome = normalizeOutcome(event.decision);
  const findings = runtimeFindings(event);
  const steps = runtimeTraceSteps(event);
  const usage = metadataRecord(event.metadata.usage);
  return {
    id: event.id,
    created_at: event.occurredAt,
    deployment_id: event.deploymentId ?? "",
    guardrail_id: event.guardrailId,
    guardrail_version: event.guardrailVersion,
    integration_id: event.integrationId,
    protocol: stringValue(event.metadata.protocol) ?? "unknown",
    phase: event.direction === "incoming" ? "input" : "output",
    outcome,
    action: stringValue(event.metadata.action) ?? event.decision,
    risk: findings[0]?.risk ?? arrayOfStrings(event.metadata.risks)[0] ?? null,
    severity: findings[0]?.severity ?? null,
    latency_ms: event.durationMs,
    timed_out: isTimedOut(event),
    runtime_engine: stringValue(usage.runtime_engine) ?? stringValue(event.metadata.runtimeEngine) ?? "unknown",
    config_checksum: stringValue(usage.config_checksum) ?? stringValue(event.metadata.configChecksum) ?? "",
    detail: `Runner ${event.runnerId} reported ${event.direction} decision “${event.decision}” in ${event.durationMs} ms.`,
    findings,
    steps,
    evidence_status: event.metadata.captureLevel ? "collected" : "not_collected",
  };
}

function runtimeFindings(event: controllerApi.RuntimeEvent): DeploymentTraceFinding[] {
  return arrayOfRecords(event.metadata.findings).map((finding, index) => {
    const verdict = stringValue(finding.verdict) ?? "unknown";
    const confidence = numberValue(finding.confidence) ?? 0;
    const risk = stringValue(finding.risk) ?? "unknown";
    return {
      id: stringValue(finding.id) ?? `${event.id}:finding:${index + 1}`,
      trace_id: event.requestId,
      created_at: event.occurredAt,
      guardrail_id: event.guardrailId,
      guardrail_version: event.guardrailVersion,
      deployment_id: event.deploymentId,
      integration_id: event.integrationId,
      phase: event.direction === "incoming" ? "input" : "output",
      severity: findingSeverity(verdict, confidence),
      risk,
      verdict,
      confidence,
      recommended_action: stringValue(finding.recommendedAction) ?? stringValue(event.metadata.action) ?? event.decision,
      policy_id: stringValue(finding.policyId),
      rule_id: stringValue(finding.ruleId),
      detail: `Runner reported a ${verdict} ${risk.replaceAll("_", " ")} finding. Raw protected content was not retained.`,
      protocol: stringValue(event.metadata.protocol),
    };
  });
}

function runtimeTraceSteps(event: controllerApi.RuntimeEvent): DeploymentRuntimeTrace["steps"] {
  return arrayOfRecords(event.metadata.trace).map((step, index) => ({
    id: stringValue(step.id) ?? `${event.id}:step:${index + 1}`,
    trace_id: event.requestId,
    created_at: event.occurredAt,
    guardrail_id: event.guardrailId ?? "",
    guardrail_version: event.guardrailVersion ?? 0,
    deployment_id: event.deploymentId,
    integration_id: event.integrationId,
    protocol: stringValue(event.metadata.protocol) ?? "unknown",
    phase: event.direction === "incoming" ? "input" : "output",
    kind: stringValue(step.kind) ?? "action",
    name: stringValue(step.name) ?? "Runtime step",
    risk: stringValue(step.risk),
    stage: stringValue(step.stage),
    outcome: stringValue(step.outcome) ?? stringValue(step.status) ?? "unknown",
    latency_ms: numberValue(step.durationMs) ?? 0,
    timed_out: step.timedOut === true,
    runtime_engine: stringValue(step.engine) ?? "unknown",
    config_checksum: stringValue(step.configChecksum) ?? "",
    policy_id: stringValue(step.policyId),
    policy_version: stringValue(step.policyVersion),
    rail_type: stringValue(step.railType),
    flow_name: stringValue(step.flowName),
    action_name: stringValue(step.actionName),
    action_version: stringValue(step.actionVersion),
    parallel_group: stringValue(step.parallelGroup),
    timeout_ms: numberValue(step.timeoutMs),
    provider_latency_ms: numberValue(step.providerLatencyMs) ?? 0,
  }));
}

function findingSeverity(verdict: string, confidence: number): DeploymentTraceFinding["severity"] {
  if (verdict === "error") return "critical";
  if (verdict === "unsafe" && confidence >= 0.9) return "high";
  if (verdict === "unsafe" || confidence >= 0.7) return "medium";
  return "low";
}

function metadataRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function integrationAdapter(adapter: string): { id: IntegrationAdapterId; protocol: "litellm" | "http" | "a2a" } {
  const normalized = adapter.toLowerCase();
  if (normalized.includes("litellm")) return { id: "litellm-generic-guardrail", protocol: "litellm" };
  if (normalized.includes("a2a")) return { id: "a2a-guard", protocol: "a2a" };
  if (normalized === "http" || normalized === "generic-http-guard") return { id: "generic-http-guard", protocol: "http" };
  throw new Error(`Unknown Integration adapter: ${adapter}`);
}

function integrationSetup(): Integration["setup"] {
  return {
    api_base_url: "",
    callback_url: "",
    auth_header: "x-api-key",
    credential_env_var: "",
    api_base_env_var: "",
    recommended_modes: [],
    default_on: false,
    fail_on_error: true,
    unreachable_fallback: "fail_closed",
    yaml_template: "",
  };
}

function mapCredential(value: CurrentCredential) {
  return { id: value.id, key_hint: value.keyHint, created_at: value.createdAt };
}

function integrationEvents(value: controllerApi.Integration, events: controllerApi.RuntimeEvent[]): controllerApi.RuntimeEvent[] {
  return events.filter((event) => event.integrationId === value.id);
}

function mapIntegration(value: CurrentIntegration, events: controllerApi.RuntimeEvent[]): Integration {
  const adapter = integrationAdapter(value.adapter);
  const matching = integrationEvents(value, events);
  const incoming = matching.filter((event) => event.direction === "incoming").map((event) => event.occurredAt).sort();
  const outgoing = matching.filter((event) => event.direction === "outgoing").map((event) => event.occurredAt).sort();
  const errors = matching.filter((event) => normalizeOutcome(event.decision) === "error");
  const timestamps = matching.map((event) => event.occurredAt).sort();
  const credentials = (value.credentials ?? []).map(mapCredential);
  return {
    id: value.id,
    adapter_id: adapter.id,
    protocol: adapter.protocol,
    name: value.name,
    description: "",
    enabled: value.status === "active",
    key_hint: credentials[0]?.key_hint ?? "",
    credentials,
    setup_status: value.status === "disabled"
      ? "disabled"
      : value.distributionStatus === "syncing"
        ? "applying"
        : matching.length
          ? "verified"
          : "awaiting_callback",
    desired_generation: value.desiredGeneration,
    runtime_status: errors.length ? "degraded" : matching.length ? "healthy" : "unknown",
    first_seen_at: timestamps[0] ?? null,
    input_seen_at: incoming[0] ?? null,
    output_seen_at: outgoing[0] ?? null,
    last_seen_at: timestamps.at(-1) ?? null,
    last_error_at: errors.map((event) => event.occurredAt).sort().at(-1) ?? null,
    request_count: new Set(matching.map((event) => event.requestId)).size,
    error_count: errors.length,
    setup: value.setup ?? integrationSetup(),
    created_at: value.createdAt,
    updated_at: value.updatedAt,
  };
}

export async function getIntegrations(): Promise<Collection<Integration>> {
  const [integrations, events] = await Promise.all([
    controllerApi.listControllerIntegrations(),
    controllerApi.listRuntimeEvents(500),
  ]);
  const items = integrations.items.map((item) => mapIntegration(item as CurrentIntegration, events.items));
  return { items, count: items.length };
}

export async function getIntegration(id: string): Promise<Integration> {
  const [integration, events] = await Promise.all([
    currentRequest<CurrentIntegration>(`/api/v1/integrations/${encodeURIComponent(id)}`),
    controllerApi.listRuntimeEvents(500),
  ]);
  return mapIntegration(integration, events.items);
}

function oneTimeRegistration(value: CurrentIntegration): IntegrationRegistration {
  if (!value.credential) throw new Error("Controller did not return the one-time Integration credential.");
  const credential: OneTimeIntegrationCredential = {
    id: value.credentialId ?? "",
    key_hint: value.credentialKeyHint ?? credentialHint(value.credential),
    created_at: value.credentialCreatedAt ?? value.createdAt,
    value: value.credential,
  };
  const credentials = value.credentials?.length
    ? value.credentials
    : [{ id: credential.id, keyHint: credential.key_hint, createdAt: credential.created_at }];
  return {
    integration: mapIntegration({ ...value, credentials }, []),
    credential,
  };
}

export async function createIntegration(input: { name: string; adapter_id: IntegrationAdapterId }): Promise<IntegrationRegistration> {
  const created = await controllerApi.createControllerIntegration({ name: input.name, adapter: input.adapter_id }) as CurrentIntegration;
  return oneTimeRegistration(created);
}

export async function setIntegrationEnabled(id: string, enabled: boolean): Promise<Integration> {
  const updated = await currentRequest<CurrentIntegration>(`/api/v1/integrations/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify({ enabled }),
  });
  const events = await controllerApi.listRuntimeEvents(500);
  return mapIntegration(updated, events.items);
}

export async function rotateIntegrationCredential(id: string): Promise<IntegrationRegistration> {
  const updated = await currentRequest<CurrentIntegration>(`/api/v1/integrations/${encodeURIComponent(id)}/credentials`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  return oneTimeRegistration(updated);
}

export const revokeIntegrationCredential = (integrationId: string, credentialId: string) => currentRequest<void>(
  `/api/v1/integrations/${encodeURIComponent(integrationId)}/credentials/${encodeURIComponent(credentialId)}`,
  { method: "DELETE" },
);

export async function getIntegrationDeletionImpact(id: string): Promise<IntegrationDeletionImpact> {
  const [impact, integration] = await Promise.all([
    controllerApi.getControllerIntegrationDeletionImpact(id),
    currentRequest<CurrentIntegration>(`/api/v1/integrations/${encodeURIComponent(id)}`),
  ]);
  return {
    integration_id: impact.resourceId,
    integration_name: integration.name,
    window_minutes: impact.windowMinutes,
    incoming_request_count: impact.incomingRequestCount,
    last_request_at: impact.lastRequestAt,
    active_deployment_count: impact.activeDeploymentCount,
    active_credential_count: integration.credentials?.length ?? 0,
    telemetry_fresh: impact.telemetryFresh,
    telemetry_watermark: impact.telemetryWatermark,
    requires_second_confirmation: impact.requiresSecondConfirmation,
    requires_confirmation: impact.requiresSecondConfirmation,
  };
}

export const deleteIntegration = (id: string, confirmation: DeleteConfirmation) => controllerApi.deleteControllerIntegration(id, {
  reason: confirmation.reason,
  confirmRecentTraffic: confirmation.confirm_recent_traffic,
  ...(confirmation.confirmation_name ? { confirmationName: confirmation.confirmation_name } : {}),
});

function credentialHint(value: string): string {
  if (value.length <= 10) return value;
  return `${value.slice(0, 5)}…${value.slice(-4)}`;
}

function normalizeOutcome(decision: string): "allow" | "transform" | "block" | "error" | string {
  const value = decision.toLowerCase();
  if (["allow", "allowed", "pass", "passed"].includes(value)) return "allow";
  if (["transform", "transformed", "redact", "redacted", "rewrite", "rewritten", "intervene", "intervened"].includes(value)) return "transform";
  if (["block", "blocked", "reject", "rejected", "deny", "denied"].includes(value)) return "block";
  if (["error", "failed", "failure", "timeout", "timed_out"].includes(value)) return "error";
  return decision;
}

function isTimedOut(event: controllerApi.RuntimeEvent): boolean {
  const decision = event.decision.toLowerCase();
  return decision === "timeout" || decision === "timed_out" || event.metadata.timedOut === true || event.metadata.timed_out === true;
}

function windowMilliseconds(window: MetricWindow): number {
  return {
    "1h": 60 * 60 * 1_000,
    "24h": 24 * 60 * 60 * 1_000,
    "7d": 7 * 24 * 60 * 60 * 1_000,
    "15d": 15 * 24 * 60 * 60 * 1_000,
    "30d": 30 * 24 * 60 * 60 * 1_000,
  }[window];
}

function inWindow(timestamp: string, window: MetricWindow, now = Date.now()): boolean {
  const value = Date.parse(timestamp);
  return Number.isFinite(value) && value >= now - windowMilliseconds(window) && value <= now;
}

function metadataStrings(metadata: Record<string, unknown>): Record<string, string> {
  return Object.fromEntries(Object.entries(metadata).map(([key, value]) => [
    key,
    typeof value === "string" ? value : JSON.stringify(value) ?? String(value),
  ]));
}

function runtimeEvidence(event: controllerApi.RuntimeEvent): EvidenceRecord {
  return {
    id: event.id,
    created_at: event.occurredAt,
    kind: "interaction.decision",
    outcome: normalizeOutcome(event.decision),
    guardrail_id: event.guardrailId,
    deployment_id: event.deploymentId,
    integration_id: event.integrationId,
    risk: stringValue(event.metadata.risk),
    detail: `Runner ${event.runnerId} reported ${event.direction} decision “${event.decision}” in ${event.durationMs} ms.`,
    actor_id: null,
    metadata: {
      ...metadataStrings(event.metadata),
      request_id: event.requestId,
      runner_id: event.runnerId,
      direction: event.direction,
      duration_ms: String(event.durationMs),
    },
  };
}

function auditEvidence(event: controllerApi.AuditEvent): EvidenceRecord {
  return {
    id: event.id,
    created_at: event.occurredAt,
    kind: event.kind,
    outcome: "recorded",
    guardrail_id: event.resourceType === "guardrail" ? event.resourceId : stringValue(event.detail.guardrailId),
    deployment_id: event.resourceType === "deployment" ? event.resourceId : stringValue(event.detail.deploymentId),
    integration_id: event.resourceType === "integration" ? event.resourceId : stringValue(event.detail.integrationId),
    risk: stringValue(event.detail.risk),
    detail: JSON.stringify(event.detail),
    actor_id: event.actorId,
    metadata: metadataStrings(event.detail),
  };
}

export async function getEvidence(filters: {
  limit?: number;
  guardrailId?: string;
  deploymentId?: string;
  kind?: string;
  outcome?: string;
  risk?: string;
  window?: MetricWindow;
} = {}): Promise<Collection<EvidenceRecord>> {
  const window = filters.window ?? "24h";
  const now = Date.now();
  const since = new Date(now - windowMilliseconds(window)).toISOString();
  const [runtime, audit] = await Promise.all([
    controllerApi.listRuntimeEvents(10_000, {
      guardrailId: filters.guardrailId,
      deploymentId: filters.deploymentId,
      since,
    }),
    controllerApi.listAuditEvents(500),
  ]);
  const matching = [...runtime.items.map(runtimeEvidence), ...audit.items.map(auditEvidence)]
    .filter((item) => inWindow(item.created_at, window, now))
    .filter((item) => !filters.guardrailId || item.guardrail_id === filters.guardrailId)
    .filter((item) => !filters.deploymentId || item.deployment_id === filters.deploymentId)
    .filter((item) => !filters.kind || item.kind === filters.kind)
    .filter((item) => !filters.outcome || item.outcome === filters.outcome)
    .filter((item) => !filters.risk || item.risk === filters.risk)
    .sort((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at));
  return {
    items: matching.slice(0, Math.min(500, Math.max(1, filters.limit ?? 100))),
    count: matching.length,
  };
}

export const getGuardrailFindings = async (
  guardrailId: string,
  window: MetricWindow,
  limit = 200,
): Promise<GuardrailFindingPage> => {
  const since = new Date(Date.now() - windowMilliseconds(window)).toISOString();
  const events = await controllerApi.listRuntimeEvents(10_000, { guardrailId, since });
  const all = events.items.flatMap(runtimeFindings).sort((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at));
  const items = all.slice(0, Math.min(1_000, Math.max(1, limit)));
  return {
    items,
    count: items.length,
    summary: {
      total: all.length,
      critical: all.filter((item) => item.severity === "critical").length,
      high: all.filter((item) => item.severity === "high").length,
      medium: all.filter((item) => item.severity === "medium").length,
      low: all.filter((item) => item.severity === "low").length,
      affected_traces: new Set(all.map((item) => item.trace_id)).size,
      latest_at: all[0]?.created_at ?? null,
    },
    collection_status: !events.items.length ? "no_events" : events.items.every((event) => Boolean(event.metadata.captureLevel)) ? "collected" : "not_collected",
  };
};

function runtimeLogEntry(event: controllerApi.RuntimeEvent): RuntimeLogInteraction["entries"][number] {
  const before = runtimeLogContent(event.metadata.contentBefore);
  const after = runtimeLogContent(event.metadata.contentAfter);
  return {
    id: event.id,
    trace_id: event.requestId,
    created_at: event.occurredAt,
    phase: event.direction === "incoming" ? "input" : "output",
    outcome: normalizeOutcome(event.decision),
    action: stringValue(event.metadata.action) ?? event.decision,
    risk: runtimeFindings(event)[0]?.risk ?? arrayOfStrings(event.metadata.risks)[0] ?? null,
    latency_ms: event.durationMs,
    timed_out: isTimedOut(event),
    detail: `Runner ${event.runnerId} reported ${event.direction} decision “${event.decision}” in ${event.durationMs} ms.`,
    content_before: before,
    content_after: after,
    content_available: Boolean(event.metadata.contentAvailable) && (before !== null || after !== null),
    findings: runtimeFindings(event),
    steps: runtimeTraceSteps(event),
  };
}

function worstOutcome(values: string[]): string {
  const rank = (value: string) => ({ error: 4, block: 3, transform: 2, allow: 1 }[normalizeOutcome(value)] ?? 0);
  return [...values].sort((left, right) => rank(right) - rank(left))[0] ?? "allow";
}

export async function getRuntimeLogs(filters: {
  limit?: number;
  guardrailId?: string;
  phase?: "input" | "output";
  outcome?: "allow" | "transform" | "block" | "error";
  window?: MetricWindow;
  cursor?: string;
} = {}): Promise<RuntimeLogPage> {
  const runtime = await controllerApi.listRuntimeEvents(10_000, {
    ...(filters.guardrailId ? { guardrailId: filters.guardrailId } : {}),
    since: new Date(Date.now() - windowMilliseconds(filters.window ?? "24h")).toISOString(),
  });
  const window = filters.window ?? "24h";
  const matching = runtime.items
    .filter((event): event is controllerApi.RuntimeEvent & { guardrailId: string } => Boolean(event.guardrailId))
    .filter((event) => event.metadata.runtimeLogCaptured === true)
    .filter((event) => inWindow(event.occurredAt, window))
    .filter((event) => !filters.guardrailId || event.guardrailId === filters.guardrailId)
    .filter((event) => !filters.phase || (event.direction === "incoming" ? "input" : "output") === filters.phase)
    .filter((event) => !filters.outcome || normalizeOutcome(event.decision) === filters.outcome);
  const grouped = new Map<string, typeof matching>();
  for (const event of matching) {
    const key = `${event.requestId}:${event.guardrailId}`;
    grouped.set(key, [...(grouped.get(key) ?? []), event]);
  }
  const allItems: RuntimeLogInteraction[] = [...grouped.values()].map((events) => {
    const ordered = [...events].sort((left, right) => Date.parse(left.occurredAt) - Date.parse(right.occurredAt));
    const first = ordered[0] as typeof events[number];
    const last = ordered.at(-1) as typeof events[number];
    return {
      id: first.requestId,
      created_at: first.occurredAt,
      completed_at: last.occurredAt,
      guardrail_id: first.guardrailId,
      guardrail_version: last.guardrailVersion,
      deployment_id: last.deploymentId,
      integration_id: last.integrationId,
      protocol: stringValue(last.metadata.protocol) ?? "unknown",
      outcome: worstOutcome(ordered.map((event) => event.decision)),
      capture_level: enumValue(last.metadata.captureLevel, ["info", "debug", "trace"]) ?? "info",
      entries: ordered.map(runtimeLogEntry),
    };
  }).sort((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at));
  const offset = parseCursor(filters.cursor);
  const limit = Math.min(500, Math.max(1, filters.limit ?? 100));
  const items = allItems.slice(offset, offset + limit);
  return {
    items,
    count: allItems.length,
    next_cursor: offset + limit < allItems.length ? `offset:${offset + limit}` : null,
  };
}

function runtimeLogContent(value: unknown): RuntimeLogInteraction["entries"][number]["content_before"] {
  if (!Array.isArray(value)) return null;
  return value.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const record = item as Record<string, unknown>;
    const id = stringValue(record.id);
    const role = stringValue(record.role);
    const source = stringValue(record.source);
    const text = stringValue(record.text);
    if (!id || !role || !source || text === null) return [];
    return [{ id, role, source, text, truncated: record.truncated === true }];
  });
}

function parseCursor(cursor: string | undefined): number {
  if (!cursor?.startsWith("offset:")) return 0;
  const value = Number.parseInt(cursor.slice("offset:".length), 10);
  return Number.isFinite(value) && value >= 0 ? value : 0;
}

type EventSummary = {
  total: number;
  allowed: number;
  blocked: number;
  transformed: number;
  errors: number;
  timeouts: number;
  p50: number;
  p95: number;
  p99: number;
};

function summarizeEvents(events: controllerApi.RuntimeEvent[]): EventSummary {
  const outcomes = events.map((event) => normalizeOutcome(event.decision));
  const latencies = events.map((event) => event.durationMs);
  return {
    total: events.length,
    allowed: outcomes.filter((value) => value === "allow").length,
    blocked: outcomes.filter((value) => value === "block").length,
    transformed: outcomes.filter((value) => value === "transform").length,
    errors: outcomes.filter((value) => value === "error").length,
    timeouts: events.filter(isTimedOut).length,
    p50: percentile(latencies, 0.5),
    p95: percentile(latencies, 0.95),
    p99: percentile(latencies, 0.99),
  };
}

function percentile(values: number[], quantile: number): number {
  if (!values.length) return 0;
  const sorted = [...values].sort((left, right) => left - right);
  const index = Math.min(sorted.length - 1, Math.max(0, Math.ceil(sorted.length * quantile) - 1));
  return Math.round(sorted[index] ?? 0);
}

function percentage(numerator: number, denominator: number): number {
  return denominator ? Math.round(numerator / denominator * 10_000) / 100 : 0;
}

function percentageDelta(current: number, previous: number): number | null {
  if (previous === 0) return current === 0 ? 0 : null;
  return Math.round((current - previous) / previous * 10_000) / 100;
}

function metricInterval(window: MetricWindow): Metrics["interval"] {
  return { "1h": "1m", "24h": "15m", "7d": "1h", "15d": "6h", "30d": "1d" }[window] as Metrics["interval"];
}

function intervalMilliseconds(interval: Metrics["interval"]): number {
  return { "1m": 60_000, "15m": 15 * 60_000, "1h": 60 * 60_000, "6h": 6 * 60 * 60_000, "1d": 24 * 60 * 60_000 }[interval];
}

function buildTrend(events: controllerApi.RuntimeEvent[], window: MetricWindow, now: number): MetricTrendPoint[] {
  const interval = metricInterval(window);
  const step = intervalMilliseconds(interval);
  const first = Math.floor((now - windowMilliseconds(window)) / step) * step;
  const buckets = new Map<number, controllerApi.RuntimeEvent[]>();
  for (const event of events) {
    const timestamp = Date.parse(event.occurredAt);
    const bucket = Math.floor(timestamp / step) * step;
    buckets.set(bucket, [...(buckets.get(bucket) ?? []), event]);
  }
  const points: MetricTrendPoint[] = [];
  for (let timestamp = first; timestamp <= now; timestamp += step) {
    const summary = summarizeEvents(buckets.get(timestamp) ?? []);
    points.push({
      timestamp: new Date(timestamp).toISOString(),
      total: summary.total,
      allowed: summary.allowed,
      blocked: summary.blocked,
      transformed: summary.transformed,
      errored: summary.errors,
      timed_out: summary.timeouts,
      p50_latency_ms: summary.p50,
      p95_latency_ms: summary.p95,
      p99_latency_ms: summary.p99,
    });
  }
  return points;
}

function scopedEvents(
  values: controllerApi.RuntimeEvent[],
  filters: { guardrailId?: string; deploymentId?: string },
): controllerApi.RuntimeEvent[] {
  return values
    .filter((event) => !filters.guardrailId || event.guardrailId === filters.guardrailId)
    .filter((event) => !filters.deploymentId || event.deploymentId === filters.deploymentId);
}

function eventUsage(event: controllerApi.RuntimeEvent): Record<string, unknown> {
  return metadataRecord(event.metadata.usage);
}

function usageValues(events: controllerApi.RuntimeEvent[], key: string): number[] {
  return events.map((event) => numberValue(eventUsage(event)[key])).filter((value): value is number => value !== null);
}

function usageTotal(events: controllerApi.RuntimeEvent[], key: string): number {
  return usageValues(events, key).reduce((total, value) => total + value, 0);
}

function componentMetrics(events: controllerApi.RuntimeEvent[], kind: "rail" | "action"): Metrics["rail_metrics"] {
  const groups = new Map<string, Array<Record<string, unknown>>>();
  for (const event of events) {
    for (const step of arrayOfRecords(event.metadata.trace)) {
      const stepKind = stringValue(step.kind) ?? "";
      if (kind === "rail" ? stepKind !== "rail" : stepKind !== "action") continue;
      const name = stringValue(step.name) ?? stringValue(step.actionName) ?? stringValue(step.flowName) ?? "runtime-step";
      groups.set(name, [...(groups.get(name) ?? []), step]);
    }
  }
  return [...groups.entries()].map(([name, steps]) => {
    const durations = steps.map((step) => numberValue(step.durationMs) ?? 0);
    const providers = steps.map((step) => numberValue(step.providerLatencyMs) ?? 0);
    const outcomes = steps.map((step) => stringValue(step.outcome) ?? stringValue(step.status) ?? "unknown");
    const first = steps[0] ?? {};
    const timeouts = steps.filter((step) => step.timedOut === true).length;
    return {
      name,
      risk: stringValue(first.risk),
      policy_id: stringValue(first.policyId),
      policy_version: numberValue(first.policyVersion),
      rail_type: stringValue(first.railType),
      flow_name: stringValue(first.flowName),
      action_name: stringValue(first.actionName),
      action_version: stringValue(first.actionVersion),
      parallel_group: stringValue(first.parallelGroup),
      invocations: steps.length,
      passed: outcomes.filter((value) => ["passed", "safe", "allow", "complete"].includes(value)).length,
      intervened: outcomes.filter((value) => ["unsafe", "block", "transform", "intervene", "enforce"].includes(value)).length,
      uncertain: outcomes.filter((value) => value === "uncertain").length,
      errors: outcomes.filter((value) => value === "error").length,
      timeouts,
      p50_latency_ms: percentile(durations, 0.5),
      p95_latency_ms: percentile(durations, 0.95),
      p99_latency_ms: percentile(durations, 0.99),
      provider_p50_ms: percentile(providers, 0.5),
      provider_p95_ms: percentile(providers, 0.95),
      provider_p99_ms: percentile(providers, 0.99),
    };
  });
}

function policyMetrics(events: controllerApi.RuntimeEvent[], requestCount: number): Metrics["policy_distribution"] {
  const groups = new Map<string, Array<Record<string, unknown>>>();
  for (const event of events) {
    for (const step of arrayOfRecords(event.metadata.trace)) {
      const policyId = stringValue(step.policyId);
      if (!policyId) continue;
      groups.set(policyId, [...(groups.get(policyId) ?? []), step]);
    }
  }
  const totalInvocations = [...groups.values()].reduce((total, steps) => total + steps.length, 0);
  return [...groups.entries()].map(([policyId, steps]) => {
    const durations = steps.map((step) => numberValue(step.durationMs) ?? 0);
    const providerDurations = steps.map((step) => numberValue(step.providerLatencyMs) ?? 0);
    const outcomes = steps.map((step) => stringValue(step.outcome) ?? stringValue(step.verdict) ?? stringValue(step.status) ?? "unknown");
    const versionText = stringValue(steps[0]?.policyVersion);
    const parsedVersion = versionText ? Number.parseInt(versionText, 10) : Number.NaN;
    return {
      policy_id: policyId,
      policy_version: Number.isFinite(parsedVersion) ? parsedVersion : null,
      invocations: steps.length,
      hit_share: percentage(steps.length, totalInvocations),
      hits_per_request: requestCount ? Math.round(steps.length / requestCount * 100) / 100 : 0,
      passed: outcomes.filter((value) => ["passed", "safe", "allow", "complete"].includes(value)).length,
      intervened: outcomes.filter((value) => ["unsafe", "block", "transform", "intervene", "enforce"].includes(value)).length,
      errors: outcomes.filter((value) => value === "error").length,
      timeouts: steps.filter((step) => step.timedOut === true).length,
      p50_latency_ms: percentile(durations, 0.5),
      p95_latency_ms: percentile(durations, 0.95),
      p99_latency_ms: percentile(durations, 0.99),
      provider_p95_ms: percentile(providerDurations, 0.95),
      rail_types: unique(steps.map((step) => stringValue(step.railType)).filter((item): item is string => Boolean(item))),
      parallel_groups: unique(steps.map((step) => stringValue(step.parallelGroup)).filter((item): item is string => Boolean(item))),
    };
  });
}

export async function getMetrics(filters: {
  guardrailId?: string;
  deploymentId?: string;
  window?: MetricWindow;
} = {}): Promise<Metrics> {
  const window = filters.window ?? "24h";
  const duration = windowMilliseconds(window);
  const now = Date.now();
  const windowStart = now - duration;
  const [runtime, guardrails, deployments, integrations, status] = await Promise.all([
    controllerApi.listRuntimeEvents(10_000, {
      ...(filters.guardrailId ? { guardrailId: filters.guardrailId } : {}),
      ...(filters.deploymentId ? { deploymentId: filters.deploymentId } : {}),
      since: new Date(windowStart - duration).toISOString(),
      before: new Date(now).toISOString(),
    }),
    controllerApi.listControllerGuardrails(),
    controllerApi.listControllerDeployments(),
    controllerApi.listControllerIntegrations(),
    controllerApi.getControllerSystemStatus(),
  ]);
  const allScoped = scopedEvents(runtime.items, filters);
  const currentEvents = allScoped.filter((event) => {
    const timestamp = Date.parse(event.occurredAt);
    return timestamp >= windowStart && timestamp <= now;
  });
  const previousEvents = allScoped.filter((event) => {
    const timestamp = Date.parse(event.occurredAt);
    return timestamp >= windowStart - duration && timestamp < windowStart;
  });
  const current = summarizeEvents(currentEvents);
  const previous = summarizeEvents(previousEvents);
  const currentInterventionRate = percentage(current.blocked + current.transformed, current.total);
  const previousInterventionRate = percentage(previous.blocked + previous.transformed, previous.total);
  const currentErrorRate = percentage(current.errors, current.total);
  const previousErrorRate = percentage(previous.errors, previous.total);
  const guardrailById = new Map(guardrails.items.map((item) => [item.id, item]));
  const deploymentById = new Map(deployments.items.map((item) => [item.id, item]));
  const integrationById = new Map(integrations.items.map((item) => [item.id, item]));
  const scopedDeployments = deployments.items.filter((item) =>
    (!filters.guardrailId || item.guardrailId === filters.guardrailId)
    && (!filters.deploymentId || item.id === filters.deploymentId));
  const sloP95 = 2_500;
  const sloP99 = 5_000;
  const trend = buildTrend(currentEvents, window, now);
  const guardrailGroups = groupEvents(currentEvents, (event) => event.guardrailId);
  const callerGroups = groupEvents(currentEvents, (event) => `${event.integrationId ?? ""}\u0000${event.deploymentId ?? ""}`);
  const versionGroups = groupEvents(currentEvents, (event) => `${event.guardrailId ?? ""}\u0000${event.guardrailVersion ?? 0}`);
  const riskCounts = new Map<string, number>();
  for (const finding of currentEvents.flatMap(runtimeFindings)) riskCounts.set(finding.risk, (riskCounts.get(finding.risk) ?? 0) + 1);
  const engineGroups = groupEvents(currentEvents, (event) => stringValue(eventUsage(event).runtime_engine) ?? stringValue(event.metadata.runtimeEngine) ?? "unknown");
  const queueLatencies = usageValues(currentEvents, "queue_latency_ms");
  const providerLatencies = usageValues(currentEvents, "provider_latency_ms");
  const evidenceCount = currentEvents.filter((event) => Boolean(event.metadata.captureLevel)).length;
  const railMetrics = componentMetrics(currentEvents, "rail");
  const actionMetrics = componentMetrics(currentEvents, "action");
  const degradedIntegrationIds = new Set(currentEvents
    .filter((event) => normalizeOutcome(event.decision) === "error" && event.integrationId)
    .map((event) => event.integrationId as string));
  return {
    data_availability: {
      runtime_events: (runtime.count ?? runtime.items.length) > runtime.items.length ? "truncated" : "complete",
      execution_evidence: !currentEvents.length || evidenceCount === currentEvents.length ? "collected" : evidenceCount ? "partial" : "not_collected",
      returned_events: runtime.items.length,
      matching_events: runtime.count ?? runtime.items.length,
    },
    window,
    window_start: new Date(windowStart).toISOString(),
    scope: {
      guardrail_id: filters.guardrailId ?? null,
      guardrail_name: filters.guardrailId ? guardrailById.get(filters.guardrailId)?.name ?? null : null,
    },
    comparison: {
      previous_total_decisions: previous.total,
      request_delta_pct: percentageDelta(current.total, previous.total),
      previous_intervention_rate: previous.total ? previousInterventionRate : null,
      intervention_rate_delta_pp: previous.total ? Math.round((currentInterventionRate - previousInterventionRate) * 100) / 100 : null,
      previous_runtime_p95_ms: previous.total ? previous.p95 : null,
      runtime_p95_delta_ms: previous.total ? current.p95 - previous.p95 : null,
      previous_error_rate: previous.total ? previousErrorRate : null,
      error_rate_delta_pp: previous.total ? Math.round((currentErrorRate - previousErrorRate) * 100) / 100 : null,
    },
    total_decisions: current.total,
    allowed: current.allowed,
    blocked: current.blocked,
    intervened: current.transformed,
    errors: current.errors,
    block_rate: percentage(current.blocked, current.total),
    intervention_rate: currentInterventionRate,
    error_rate: currentErrorRate,
    timeout_count: current.timeouts,
    rail_invocations: usageTotal(currentEvents, "rail_invocations"),
    action_invocations: usageTotal(currentEvents, "action_invocations"),
    model_invocations: usageTotal(currentEvents, "model_invocations"),
    cache_hits: usageTotal(currentEvents, "cache_hits"),
    cache_misses: usageTotal(currentEvents, "cache_misses"),
    cache_hit_rate: percentage(usageTotal(currentEvents, "cache_hits"), usageTotal(currentEvents, "cache_hits") + usageTotal(currentEvents, "cache_misses")),
    queue_p50_ms: percentile(queueLatencies, 0.5),
    queue_p95_ms: percentile(queueLatencies, 0.95),
    queue_p99_ms: percentile(queueLatencies, 0.99),
    provider_p50_ms: percentile(providerLatencies, 0.5),
    provider_p95_ms: percentile(providerLatencies, 0.95),
    provider_p99_ms: percentile(providerLatencies, 0.99),
    fail_closed_count: currentEvents.filter((event) => eventUsage(event).fail_closed === true).length,
    peak_active_concurrency: Math.max(0, ...usageValues(currentEvents, "active_concurrency")),
    slo_breach_count: currentEvents.filter((event) => event.durationMs > sloP95).length,
    runtime_engine_counts: [...engineGroups.entries()].map(([runtime_engine, values]) => ({ runtime_engine, count: values.length })),
    rail_metrics: railMetrics,
    action_metrics: actionMetrics,
    runtime_p50_ms: current.p50,
    runtime_p95_ms: current.p95,
    runtime_p99_ms: current.p99,
    latency_slo: {
      p95_budget_ms: sloP95,
      p99_budget_ms: sloP99,
      p95_status: current.p95 <= sloP95 ? "healthy" : "breached",
      p99_status: current.p99 <= sloP99 ? "healthy" : "breached",
    },
    latest_validation_p95_ms: Math.max(0, ...guardrails.items.map((item) => item.latestValidationRun?.metrics.p95LatencyMs ?? 0)),
    active_deployments: scopedDeployments.filter((item) => item.enabled).length,
    total_deployments: scopedDeployments.length,
    guardrails_needing_test: guardrails.items.filter((item) => !item.latestValidationRun || item.latestValidationRun.sourceDraftRevision !== item.draftRevision || item.latestValidationRun.status !== "passed").length,
    total_guardrails: guardrails.items.length,
    degraded_integrations: degradedIntegrationIds.size,
    total_integrations: integrations.items.length,
    risk_counts: [...riskCounts.entries()].map(([risk, count]) => ({ risk, count })),
    guardrail_distribution: [...guardrailGroups.entries()].filter(([id]) => Boolean(id)).map(([id, values]) => {
      const summary = summarizeEvents(values);
      return {
        guardrail_id: id,
        name: guardrailById.get(id)?.name ?? id,
        total: summary.total,
        share: percentage(summary.total, current.total),
        allowed: summary.allowed,
        blocked: summary.blocked,
        intervened: summary.transformed,
        errors: summary.errors,
        block_rate: percentage(summary.blocked, summary.total),
        intervention_rate: percentage(summary.blocked + summary.transformed, summary.total),
        error_rate: percentage(summary.errors, summary.total),
        p50_latency_ms: summary.p50,
        p95_latency_ms: summary.p95,
        p99_latency_ms: summary.p99,
        timeout_count: summary.timeouts,
        rail_invocations: usageTotal(values, "rail_invocations"),
        action_invocations: usageTotal(values, "action_invocations"),
        model_invocations: usageTotal(values, "model_invocations"),
        cache_hits: usageTotal(values, "cache_hits"),
        cache_misses: usageTotal(values, "cache_misses"),
        queue_p95_ms: percentile(usageValues(values, "queue_latency_ms"), 0.95),
        rail_p95_ms: percentile(componentMetrics(values, "rail").map((item) => item.p95_latency_ms), 0.95),
        action_p95_ms: percentile(componentMetrics(values, "action").map((item) => item.p95_latency_ms), 0.95),
        provider_p95_ms: percentile(usageValues(values, "provider_latency_ms"), 0.95),
        fail_closed_count: values.filter((event) => eventUsage(event).fail_closed === true).length,
        peak_active_concurrency: Math.max(0, ...usageValues(values, "active_concurrency")),
        slo_breach_count: values.filter((event) => event.durationMs > sloP95).length,
        runtime_engines: unique(values.map((event) => stringValue(eventUsage(event).runtime_engine) ?? stringValue(event.metadata.runtimeEngine) ?? "unknown")),
        config_checksums: unique(values.map((event) => stringValue(eventUsage(event).config_checksum) ?? stringValue(event.metadata.configChecksum)).filter((item): item is string => Boolean(item))),
        versions: unique(values.map((event) => event.guardrailVersion).filter((item): item is number => item !== null)),
      };
    }),
    caller_distribution: [...callerGroups.entries()].map(([key, values]) => {
      const [integrationId = "", deploymentId = ""] = key.split("\u0000");
      const summary = summarizeEvents(values);
      return {
        integration_id: integrationId || null,
        integration_name: integrationId ? integrationById.get(integrationId)?.name ?? integrationId : "Unassigned",
        deployment_id: deploymentId || null,
        deployment_name: deploymentId ? deploymentById.get(deploymentId)?.name ?? deploymentId : "Unassigned",
        protocol: stringValue(values[0]?.metadata.protocol) ?? "unknown",
        requests: summary.total,
        share: percentage(summary.total, current.total),
        allowed: summary.allowed,
        blocked: summary.blocked,
        intervened: summary.transformed,
        errors: summary.errors,
        intervention_rate: percentage(summary.blocked + summary.transformed, summary.total),
        error_rate: percentage(summary.errors, summary.total),
        p95_latency_ms: summary.p95,
        guardrail_versions: unique(values.map((event) => event.guardrailVersion).filter((item): item is number => item !== null)),
      };
    }),
    version_distribution: [...versionGroups.entries()].filter(([key]) => !key.startsWith("\u0000")).map(([key, values]) => {
      const [guardrailId = "", version = "0"] = key.split("\u0000");
      const summary = summarizeEvents(values);
      return {
        guardrail_id: guardrailId,
        guardrail_name: guardrailById.get(guardrailId)?.name ?? guardrailId,
        guardrail_version: Number(version),
        requests: summary.total,
        share: percentage(summary.total, current.total),
        p95_latency_ms: summary.p95,
        errors: summary.errors,
        slo_breaches: values.filter((event) => event.durationMs > sloP95).length,
      };
    }),
    policy_distribution: policyMetrics(currentEvents, current.total),
    unassigned_requests: currentEvents.filter((event) => !event.deploymentId).length,
    interval: metricInterval(window),
    trend,
    trend_series: {
      none: [{ name: "All traffic", points: trend }],
      guardrail: [...guardrailGroups.entries()].filter(([id]) => Boolean(id)).map(([id, values]) => ({
        name: guardrailById.get(id)?.name ?? id,
        points: buildTrend(values, window, now),
      })),
    },
    system_status: status.status === "ready" ? "healthy" : "degraded",
  };
}

function groupEvents(
  events: controllerApi.RuntimeEvent[],
  key: (event: controllerApi.RuntimeEvent) => string | null,
): Map<string, controllerApi.RuntimeEvent[]> {
  const result = new Map<string, controllerApi.RuntimeEvent[]>();
  for (const event of events) {
    const value = key(event);
    if (value === null) continue;
    result.set(value, [...(result.get(value) ?? []), event]);
  }
  return result;
}

function unique<T>(values: T[]): T[] {
  return [...new Set(values)];
}

export async function getSystemStatus(): Promise<SystemStatus> {
  const [status, deployments, integrations] = await Promise.all([
    controllerApi.getControllerSystemStatus(),
    controllerApi.listControllerDeployments(),
    controllerApi.listControllerIntegrations(),
  ]);
  return {
    status: status.status === "ready" ? "healthy" : "degraded",
    status_reason: status.defaultRunnerReady ? "runtime_ready" : "default_runner_unavailable",
    active_deployments: deployments.items.filter((item) => item.enabled).length,
    enabled_integrations: integrations.items.filter((item) => item.status === "active").length,
    total_integrations: integrations.items.length,
    capabilities: {
      deterministic: true,
      fast_semantic: true,
      specialized_evaluators: unique([
        "secrets", "pii", "builtin_content_filter", "prompt_injection", "jailbreak",
        ...status.modelConnections.dataPlane.models.map((item) => item.capability),
      ]),
      generic_runtime_llm: false,
      automated_reasoning: status.modelConnections.dataPlane.models.some((item) => item.capability === "automatedReasoning"),
    },
  };
}
