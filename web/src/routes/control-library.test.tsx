import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { RulesControl } from "@/lib/api";

import { RulesControlDetail } from "./control-library";

vi.mock("@/components/native-control-studio", () => ({
  ControlDetailSheet: () => null,
  ControlStudioSheet: () => null,
}));

vi.mock("react-i18next", () => ({
  initReactI18next: { type: "3rdParty", init: () => undefined },
  useTranslation: () => ({
    t: (key: string, values?: Record<string, string | number>) => {
      const labels: Record<string, string> = {
        "common.close": "Close",
        "controlLibrary.auditEyebrow": "Control Library / audit",
        "controlLibrary.control": "Control",
        "controlLibrary.controlId": "Control ID",
        "controlLibrary.builtIn": "Built-in",
        "controlLibrary.detector": "Detector",
        "controlLibrary.phase": "Phase",
        "controlLibrary.defaultAction": "Default action",
        "controlLibrary.ruleCount": "Rule count",
        "controlLibrary.source": "Source",
        "controlLibrary.includedIn": "Included in Control Packs",
        "controlLibrary.contractViews": "Control contract views",
        "controlLibrary.rulesCount": "Rules ({{count}})",
        "controlLibrary.testsCount": "Tests ({{count}})",
        "controlLibrary.rulesDescription": "Inspect deterministic Rules.",
        "controlLibrary.rule": "Rule",
        "controlLibrary.action": "Action",
        "controlLibrary.openDetails": "Open details",
        "controlLibrary.toggleRule": "Toggle {{name}}",
        "controlLibrary.ruleAcceptance": "Tests covering this Rule",
        "controlLibrary.acceptanceContract": "Acceptance contract",
        "controlLibrary.testsDescription": "Versioned Rule and scenario tests.",
        "controlLibrary.evaluationHandoffTitle": "Runs in Evaluation.",
        "controlLibrary.evaluationHandoff": "Cases are copied into the Guardrail suite.",
        "controlLibrary.testKind": "Test type",
        "controlLibrary.coveredRules": "Covered Rules",
        "controlLibrary.parameterizedCase": "Parameters {{parameters}} are resolved before execution.",
        "controlLibrary.testKinds.rule_acceptance": "Rule acceptance",
        "controlLibrary.testKinds.scenario": "Policy scenario",
        "controlLibrary.expectedDecisions.allow": "Should allow",
        "controlLibrary.expectedDecisions.block": "Should block",
        "controlLibrary.expectedDecisions.transform": "Should transform",
        "controlLibrary.expectedDecisions.intervene": "Should intervene",
        "controlLibrary.detectors.category": "Category",
        "controlLibrary.phases.input": "Input",
        "controlLibrary.phases.output": "Output",
        "controlLibrary.actions.block": "Block",
        "controlLibrary.identifiers": "Identifiers",
        "controlLibrary.conditions": "Conditional terms",
        "controlLibrary.exceptions": "Exceptions",
        "controlLibrary.phrasePatterns": "Phrase patterns",
        "controlLibrary.keywords": "Keywords",
        "controlLibrary.alwaysBlock": "Always-block phrases",
      };
      return Object.entries(values ?? {}).reduce(
        (label, [name, value]) => label.replace(`{{${name}}}`, String(value)),
        labels[key] ?? key,
      );
    },
  }),
}));

const control: RulesControl = {
  implementation: "rules",
  id: "competitor-comparison-input-filter",
  name: "Competitor Comparison Input Filter",
  description: "Blocks competitor comparisons while allowing destination questions.",
  source: "built_in",
  version: "1.95.0",
  phases: ["input"],
  default_action: "BLOCK",
  allowed_actions: ["BLOCK"],
  detector_types: ["category"],
  packs: [{ id: "aviation-operations-security", name: "Aviation Operations Security" }],
  rules: [{
    id: "competitor-comparison-intent",
    name: "Competitor comparison intent",
    detector: "category",
    action: "BLOCK",
    phases: ["input"],
    description: "Requires a competitor identity and comparison intent.",
    expression: null,
    context_expression: null,
    redaction: null,
    severity_threshold: null,
    identifiers: ["{{competitors}}"],
    conditions: ["better than", "compare"],
    keywords: [],
    always_block: [],
    exceptions: [],
    phrase_patterns: [],
  }],
  test_count: 2,
  test_suites: [{
    id: "rule-acceptance",
    name: "Rule acceptance",
    description: "Required implementation checks.",
    cases: [{
      id: "rule-competitor-comparison-intent-acceptance",
      name: "Trigger competitor comparison intent",
      description: "Proves the Rule can block.",
      phase: "input",
      content: "{{competitors}} is better than {{brand_name}}.",
      expected_decision: "block",
      covered_rule_ids: ["competitor-comparison-intent"],
      kind: "rule_acceptance",
      required: true,
      parameter_names: ["competitors", "brand_name"],
    }],
  }, {
    id: "destination-intent",
    name: "Destination intent",
    description: "Questions about destinations should remain allowed.",
    cases: [{
      id: "destination-intent-001",
      name: "Flights to a destination",
      description: "A destination mention is not a competitor comparison.",
      phase: "input",
      content: "Do you have flights to Qatar?",
      expected_decision: "allow",
      covered_rule_ids: ["competitor-comparison-intent"],
      kind: "scenario",
      required: true,
      parameter_names: [],
    }],
  }],
};

function clickTab(tab: HTMLElement) {
  fireEvent.mouseDown(tab, { button: 0, ctrlKey: false });
  fireEvent.mouseUp(tab, { button: 0, ctrlKey: false });
  fireEvent.click(tab);
}

describe("RulesControlDetail acceptance contracts", () => {
  afterEach(cleanup);

  it("connects each Rule to its acceptance test and exposes complete suites", () => {
    render(<RulesControlDetail control={control} onClose={vi.fn()} />);

    const tablist = screen.getByRole("tablist", { name: "Control contract views" });
    const rulesTab = screen.getByRole("tab", { name: "Rules (1)" });
    const testsTab = screen.getByRole("tab", { name: "Tests (2)" });
    expect(tablist).toBeTruthy();
    expect(rulesTab.getAttribute("aria-selected")).toBe("true");

    fireEvent.click(screen.getByRole("button", { name: "Toggle Competitor comparison intent" }));
    expect(screen.getByText("Tests covering this Rule")).toBeTruthy();
    expect(screen.getByText("{{competitors}} is better than {{brand_name}}.")).toBeTruthy();
    expect(screen.getByText(/Parameters competitors, brand_name/)).toBeTruthy();

    clickTab(testsTab);
    expect(testsTab.getAttribute("aria-selected")).toBe("true");
    expect(screen.getByRole("heading", { name: "Acceptance contract" })).toBeTruthy();
    expect(screen.getByText("Runs in Evaluation.")).toBeTruthy();
    expect(screen.getByText("Should block")).toBeTruthy();
    expect(screen.getAllByText("Rule acceptance").length).toBeGreaterThan(0);
    expect(screen.getAllByText("competitor-comparison-intent").length).toBeGreaterThan(0);
  });
});
