import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Deployment, GuardrailPolicyBinding, GuardrailVersion, GuardrailVersionDetail, Metrics, Policy, TestCase } from "@/lib/api";

import { GuardrailRuntimeView, ImmutableVersionView, TestCases } from "./guardrails";

vi.mock("react-i18next", () => ({
  initReactI18next: { type: "3rdParty", init: () => undefined },
  useTranslation: () => ({
    t: (key: string, values?: Record<string, string | number>) => Object.entries(values ?? {}).reduce((label, [name, value]) => `${label} ${name}:${value}`, key),
    i18n: { language: "en", exists: () => false },
  }),
}));

vi.mock("@/components/dashboard/runtime-health-alert", () => ({ RuntimeHealthAlert: () => null }));
vi.mock("@/components/dashboard/runtime-metric-chart", () => ({ RuntimeMetricChart: () => <div>runtime-chart</div> }));
vi.mock("@/routes/create-guardrail-wizard", () => ({ CreateGuardrailWizard: () => null }));
vi.mock("@/routes/deployments", () => ({
  CreateDeploymentSheet: () => null,
  TrafficScopeBadges: ({ deployment }: { deployment: Deployment }) => <span>{deployment.name} scope</span>,
}));

const deployment: Deployment = {
  id: "deployment-observed",
  name: "Observed traffic",
  guardrail_id: "guardrail-observed",
  guardrail_version: 2,
  traffic_scope: { combinator: "and", conditions: [{ field: "protocol", operator: "equals", value: "litellm" }] },
  enabled: true,
  is_default: false,
  system_managed: false,
  updated_at: "2026-08-13T08:00:00Z",
};

describe("Guardrail detail information hierarchy", () => {
  afterEach(cleanup);

  it("makes caller distribution the primary runtime evidence", () => {
    const metrics = {
      total_decisions: 40,
      intervention_rate: 12.5,
      blocked: 4,
      intervened: 1,
      runtime_p95_ms: 86,
      error_rate: 2.5,
      errors: 1,
      caller_distribution: [{
        integration_id: "integration-observed",
        integration_name: "Observed LiteLLM",
        deployment_id: deployment.id,
        deployment_name: deployment.name,
        protocol: "litellm",
        requests: 40,
        share: 100,
        allowed: 34,
        blocked: 4,
        intervened: 1,
        errors: 1,
        intervention_rate: 12.5,
        error_rate: 2.5,
        p95_latency_ms: 86,
        guardrail_versions: [2],
      }],
    } as Metrics;

    render(<GuardrailRuntimeView metrics={metrics} loading={false} error={null} deployments={[deployment]} window="24h" onWindowChange={() => undefined} />);

    expect(screen.getByText("Observed LiteLLM")).toBeTruthy();
    expect(screen.getByText("Observed traffic")).toBeTruthy();
    expect(screen.getByText("Observed traffic scope")).toBeTruthy();
    expect(screen.getByText("v2")).toBeTruthy();
    expect(screen.getByText("runtime-chart")).toBeTruthy();
  });

  it("shows immutable configuration before generated artifacts", () => {
    const version: GuardrailVersion = {
      guardrail_id: "guardrail-observed",
      version: 2,
      source_draft_version: 3,
      compiler_version: "tasklattice-nemo-config-v6",
      plan_checksum: "plan-checksum",
      created_at: "2026-08-13T08:00:00Z",
      active: true,
      runtime_engine: "llmrails",
      config_checksum: "config-checksum",
      execution_mode: "nemo_only",
    };
    const detail: GuardrailVersionDetail = {
      ...version,
      safety_level: "balanced",
      output_delivery: "window_buffered",
      runtime_profile: "llmrails_colang2_programmable",
      colang_version: "2.x",
      rails: [{ rail_type: "input", flow: "protect input" }],
      actions: [],
      models: ["content_safety"],
      features: [],
      dependencies: [{ kind: "policy", name: "pii", version: "1.95.0" }],
      estimated_critical_path_ms: 100,
      policy_bindings: [{ policy_id: "pii", policy_version: "1.95.0", action: "block", enabled_rule_ids: ["email"], enabled_rails: ["input"] }],
      artifacts: [{ path: "config.yml", language: "yaml", content: "rails:\n  input: protect input" }],
    };

    const client = new QueryClient();
    render(<QueryClientProvider client={client}><ImmutableVersionView detail={detail} activeVersion={version} versions={[version]} loading={false} guardrailId="guardrail-observed" validation={null} onChanged={async () => undefined} onOpenDraft={() => undefined} /></QueryClientProvider>);

    const configuration = screen.getByText(/guardrails\.immutableConfiguration/);
    const artifacts = screen.getByText("guardrails.generatedArtifacts");
    expect(configuration.compareDocumentPosition(artifacts) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByText("pii@1.95.0")).toBeTruthy();
    expect(screen.getByText("config.yml")).toBeTruthy();
  });

  it("groups inherited and Guardrail-specific Test Cases by source and keeps groups collapsed", () => {
    const bindings = [
      { policy_id: "policy-one", policy_version: "1.0.0", enabled_rule_ids: ["rule-1", "rule-2"], enabled_rails: ["input"] },
      { policy_id: "policy-two", policy_version: "2.0.0", enabled_rule_ids: ["rule-3"], enabled_rails: ["input"] },
    ] as GuardrailPolicyBinding[];
    const policies = [
      { id: "policy-one", name: "First Policy" },
      { id: "policy-two", name: "Second Policy" },
    ] as Policy[];
    const baseCase = {
      guardrail_id: "guardrail-observed",
      phase: "input",
      content: "reviewed content",
      expected_decision: "transform",
      updated_at: "2026-08-13T08:00:00Z",
      trusted_instruction: "",
      target_source: "user_input",
      query: "",
      grounding_sources: [],
      expected_reasoning_result: null,
      case_type: "rule_acceptance",
      required: true,
    } satisfies Partial<TestCase>;
    const cases = [
      { ...baseCase, id: "case-1", name: "First inherited Case", policy_id: "policy-one", origin: "generated", source_policy_id: "policy-one", source_policy_version: "1.0.0", source_case_id: "source-1", covered_rule_ids: ["rule-1"] },
      { ...baseCase, id: "case-2", name: "Second inherited Case", policy_id: "policy-one", origin: "generated", source_policy_id: "policy-one", source_policy_version: "1.0.0", source_case_id: "source-2", covered_rule_ids: ["rule-2"] },
      { ...baseCase, id: "case-3", name: "Other Policy Case", policy_id: "policy-two", origin: "generated", source_policy_id: "policy-two", source_policy_version: "2.0.0", source_case_id: "source-3", covered_rule_ids: ["rule-3"] },
      { ...baseCase, id: "case-4", name: "Guardrail regression Case", policy_id: "policy-one", origin: "custom", source_policy_id: null, source_policy_version: null, source_case_id: null, covered_rule_ids: [] },
    ] as TestCase[];
    const onAdd = vi.fn();

    render(<TestCases cases={cases} bindings={bindings} policies={policies} loading={false} onAdd={onAdd} />);

    expect(screen.getByText("First Policy")).toBeTruthy();
    expect(screen.getByText("Second Policy")).toBeTruthy();
    expect(screen.getByText("guardrails.guardrailCustomTests")).toBeTruthy();
    expect(screen.getByText(/inherited:3 policies:2 custom:1/)).toBeTruthy();

    const firstPolicyGroup = screen.getByTestId("test-source-policy:policy-one") as HTMLDetailsElement;
    const secondPolicyGroup = screen.getByTestId("test-source-policy:policy-two") as HTMLDetailsElement;
    const customGroup = screen.getByTestId("test-source-guardrail:custom") as HTMLDetailsElement;
    expect(firstPolicyGroup.open).toBe(false);
    expect(secondPolicyGroup.open).toBe(false);
    expect(customGroup.open).toBe(false);

    fireEvent.click(firstPolicyGroup.querySelector("summary")!);
    expect(firstPolicyGroup.open).toBe(true);
    fireEvent.click(screen.getAllByRole("button", { name: "guardrails.addTestCase" })[0]);
    expect(onAdd).toHaveBeenCalledOnce();
  });
});
