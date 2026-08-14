import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Policy } from "@/lib/api";

import { PolicyDetail } from "./policy-library";

vi.mock("@/components/policy-studio", () => ({ PolicyStudioSheet: () => null }));

vi.mock("react-i18next", () => ({
  initReactI18next: { type: "3rdParty", init: () => undefined },
  useTranslation: () => ({
    t: (key: string, values?: Record<string, string | number>) => {
      const labels: Record<string, string> = {
        "common.close": "Close",
        "policyLibrary.detailEyebrow": "Policy Library / Policy",
        "policyLibrary.detailViews": "Policy detail views",
        "policyLibrary.tabs.policy": "Policy",
        "policyLibrary.tabs.testCases": "Test Cases",
        "policyLibrary.tabs.implementation": "NeMo implementation",
        "policyLibrary.ruleListTitle": "Rules ({{count}})",
        "policyLibrary.ruleListDescription": "Each Rule is linked to Test Cases.",
        "policyLibrary.testCasesTitle": "Test Cases ({{count}})",
        "policyLibrary.testCasesDescription": "Executable Test Cases.",
        "policyLibrary.implementationTitle": "NeMo Guardrails implementation",
        "policyLibrary.implementationDescription": "Technical Rule bindings.",
        "policyLibrary.stagesLabel": "Traffic stage",
        "policyLibrary.ruleForms": "Rule forms",
        "policyLibrary.ruleForm": "Rule form",
        "policyLibrary.effectLabel": "Effect",
        "policyLibrary.runtimeManaged": "Runtime managed",
        "policyLibrary.forms.category": "Category",
        "policyLibrary.stages.input": "Before model",
        "policyLibrary.effects.block": "Block",
        "policyLibrary.testKinds.rule_acceptance": "Rule acceptance",
        "policyLibrary.testKinds.scenario": "Policy scenario",
        "policyLibrary.expectedDecisions.allow": "Should allow",
        "policyLibrary.expectedDecisions.block": "Should block",
        "policyLibrary.coveredRules": "Covered Rules",
      };
      return Object.entries(values ?? {}).reduce(
        (label, [name, value]) => label.replace(`{{${name}}}`, String(value)),
        labels[key] ?? key,
      );
    },
  }),
}));

const policy: Policy = {
  implementation: "rules",
  id: "competitor-policy",
  name: "Competitor Discussion Policy",
  description: "Blocks competitor comparisons while allowing destination questions.",
  source: "built_in",
  version: "1.0.0",
  tags: [
    { id: "capability:topic-safety", namespace: "capability", value: "topic-safety", label: "Topic Safety", source: "declared" },
    { id: "engine:nemo-guardrails", namespace: "engine", value: "nemo-guardrails", label: "NeMo Guardrails", source: "derived" },
  ],
  parameters: [],
  stages: ["input"],
  effects: ["block"],
  forms: ["category"],
  rules: [{
    id: "competitor-policy/comparison-intent",
    name: "Competitor comparison intent",
    description: "Requires a competitor identity and comparison intent.",
    form: "category",
    effect: "block",
    stages: ["input"],
    implementation: {
      engine: "nemo-guardrails",
      form: "category",
      binding_id: "competitor-policy",
      implementation_rule_id: "comparison-intent",
      detector: "category",
      flow_name: null,
      action_name: "GuardPolicyRuleAction",
    },
    expression: null,
    context_expression: null,
    redaction: null,
    severity_threshold: null,
    identifiers: ["airline"],
    conditions: ["compare"],
    keywords: [],
    always_block: [],
    exceptions: [],
    phrase_patterns: [],
  }],
  test_count: 2,
  test_cases: [{
      id: "comparison-block",
      name: "Block airline comparison",
      description: "Proves the Rule can block.",
      stage: "input",
      content: "Compare these two airlines.",
      expected_decision: "block",
      covered_rule_ids: ["competitor-policy/comparison-intent"],
      group: "Rule acceptance",
      kind: "rule_acceptance",
      required: true,
      parameter_names: [],
    }, {
      id: "destination-allow",
      name: "Allow destination question",
      description: "Destination questions are not comparisons.",
      stage: "input",
      content: "Do you have flights to Qatar?",
      expected_decision: "allow",
      covered_rule_ids: ["competitor-policy/comparison-intent"],
      group: "Destination intent",
      kind: "scenario",
      required: true,
      parameter_names: [],
    }],
  safety_level: "balanced",
  output_delivery: "window_buffered",
};

function clickTab(tab: HTMLElement) {
  fireEvent.mouseDown(tab, { button: 0, ctrlKey: false });
  fireEvent.mouseUp(tab, { button: 0, ctrlKey: false });
  fireEvent.click(tab);
}

describe("Policy detail", () => {
  afterEach(cleanup);

  it("presents Policy, testable Rules, Test Cases, and NeMo implementation as three views", () => {
    render(<PolicyDetail policy={policy} onClose={vi.fn()} onEdit={vi.fn()} />);

    expect(screen.getByRole("heading", { name: "Competitor Discussion Policy" })).toBeTruthy();
    expect(screen.getByRole("tablist", { name: "Policy detail views" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Policy" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.queryByText("NeMo Guardrails")).toBeNull();
    expect(screen.getByText("Rules (1)")).toBeTruthy();
    expect(screen.getByText("Competitor comparison intent")).toBeTruthy();

    clickTab(screen.getByRole("tab", { name: "Test Cases" }));
    expect(screen.getByText("Test Cases (2)")).toBeTruthy();
    expect(screen.getByText("Block airline comparison")).toBeTruthy();
    expect(screen.getByText("Allow destination question")).toBeTruthy();

    clickTab(screen.getByRole("tab", { name: "NeMo implementation" }));
    expect(screen.getByRole("heading", { name: "NeMo Guardrails implementation" })).toBeTruthy();
    expect(screen.queryByText("Runtime engine")).toBeNull();
    const actionName = screen.getByText("GuardPolicyRuleAction");
    expect(actionName.tagName).toBe("CODE");
    expect(actionName.getAttribute("title")).toBe("GuardPolicyRuleAction");
  });
});
