import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { EvaluationCaseResult } from "@/lib/api";

import { EvaluationResultRow } from "./validation";

vi.mock("@/routes/guardrails", () => ({ AddTestCaseSheet: () => null }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => ({
      "validation.caseTypes.scenario": "Policy scenario",
      "validation.acceptanceProvenance": "Acceptance provenance",
      "validation.sourceControl": "Pinned Control",
      "validation.sourceSuiteCase": "Suite / case",
      "validation.coveredRules": "Contract Rules",
      "validation.matchedRules": "Actually matched Rules",
      "validation.noRulesMatched": "No covered Rule matched",
      "guardrails.expectedDecision": "Expected decision",
      "guardrails.actualDecision": "Actual decision",
    } as Record<string, string>)[key] ?? key,
    i18n: { language: "en", exists: () => false },
  }),
}));

const result: EvaluationCaseResult = {
  case_id: "evaluation-case-1",
  name: "Competitor comparison",
  risk: "builtin_content_filter",
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
  source_control_id: "competitor-comparison-input-filter",
  source_control_version: "1.95.0",
  source_suite_id: "competitor-comparison",
  source_case_id: "competitor-comparison-002",
  covered_rule_ids: ["competitor-comparison-intent"],
  matched_rule_ids: ["competitor-comparison-intent"],
};

describe("Evaluation acceptance evidence", () => {
  afterEach(cleanup);

  it("shows the pinned contract and actual Rule match", () => {
    render(<EvaluationResultRow result={result} />);

    expect(screen.getByText("Policy scenario")).toBeTruthy();
    expect(screen.getByText("Acceptance provenance")).toBeTruthy();
    expect(screen.getByText("competitor-comparison-input-filter@1.95.0")).toBeTruthy();
    expect(screen.getByText("competitor-comparison / competitor-comparison-002")).toBeTruthy();
    expect(screen.getAllByText("competitor-comparison-intent")).toHaveLength(2);
  });
});
