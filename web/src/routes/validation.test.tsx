import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { TestCaseResult } from "@/lib/api";

import { TestCaseResultRow } from "./validation";

vi.mock("@/routes/guardrails", () => ({ AddTestCaseSheet: () => null }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => ({
      "validation.caseTypes.scenario": "Policy scenario",
      "validation.acceptanceProvenance": "Acceptance provenance",
      "validation.sourcePolicy": "Pinned Policy",
      "validation.sourceTestCase": "Source Test Case",
      "validation.coveredRules": "Contract Rules",
      "validation.matchedRules": "Actually matched Rules",
      "validation.noRulesMatched": "No covered Rule matched",
      "guardrails.expectedDecision": "Expected decision",
      "guardrails.actualDecision": "Actual decision",
    } as Record<string, string>)[key] ?? key,
    i18n: { language: "en", exists: () => false },
  }),
}));

const result: TestCaseResult = {
  case_id: "validation-case-1",
  name: "Competitor comparison",
  policy_id: "competitor-mention-detection",
  expected_decision: "block",
  actual_decision: "block",
  passed: false,
  stage_reached: "deterministic",
  latency_ms: 7,
  reason: "Matched the pinned Rule contract.",
  phase: "input",
  input_content: "Is Qatar Airways better than Emirates?",
  action: "reject",
  output_content: "",
  findings: [],
  trace: [],
  trusted_instruction: "",
  target_source: "user_input",
  query: "",
  grounding_sources: [],
  expected_reasoning_result: null,
  actual_reasoning_result: null,
  case_type: "scenario",
  required: true,
  expected_failure: null,
  actual_failure: null,
  concurrency_group: null,
  source_policy_id: "competitor-comparison-input-filter",
  source_policy_version: "1.95.0",
  source_case_id: "competitor-comparison-002",
  covered_rule_ids: ["competitor-comparison-intent"],
  matched_rule_ids: ["competitor-comparison-intent"],
};

describe("Validation Run acceptance evidence", () => {
  afterEach(cleanup);

  it("shows the pinned contract and actual Rule match", () => {
    render(<TestCaseResultRow result={result} />);

    expect(screen.getByText("Policy scenario")).toBeTruthy();
    expect(screen.getByText("Acceptance provenance")).toBeTruthy();
    expect(screen.getByText("competitor-comparison-input-filter@1.95.0")).toBeTruthy();
    expect(screen.getByText("competitor-comparison-002")).toBeTruthy();
    expect(screen.getAllByText("competitor-comparison-intent")).toHaveLength(2);
  });
});
