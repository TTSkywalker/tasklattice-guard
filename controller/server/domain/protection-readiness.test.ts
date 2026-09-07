import { describe, expect, it } from "vitest";
import { isModelIndependent, publishedProtectionCoverage } from "./protection-readiness.js";
import { flowRuleId } from "../policy-studio/model.js";

const step = (contract: string, phases = ["input", "output"]) => ({
  contract_ref: contract, phases, parameters: [["policy_id", "policy-1"]],
});
const plan = (steps: unknown[]) => ({ steps, policy_bindings: [{ policy_id: "policy-1", policy_version: "1" }] });

describe("published protection coverage", () => {
  it("derives local coverage from executable phases, not a preset or draft", () => {
    const coverage = publishedProtectionCoverage(plan([
      step("tali.guard.content-filter.rules.v1"), step("tali.guard.pii.exact.v1", ["output"]),
      step("tali.guard.content-safety.v1", []),
    ]));
    expect(coverage).toEqual({ policyCount: 1, inputChecks: 1, outputChecks: 2, requiredModelBindings: [], hasUnknownDependencies: false });
    expect(isModelIndependent(coverage)).toBe(true);
  });
  it("requires each actual rail binding, deduplicating models used by many steps", () => {
    const coverage = publishedProtectionCoverage(plan([
      step("tali.guard.content-safety.v1"), step("tali.guard.content-safety.v1", ["output"]),
      step("tali.guard.jailbreak.v1", ["input"]),
    ]));
    expect(coverage?.requiredModelBindings).toEqual(["content_safety.input", "content_safety.output", "jailbreak.input"]);
    expect(isModelIndependent(coverage)).toBe(false);
  });
  it("does not infer model-free protection from unknown contracts or empty plans", () => {
    for (const value of [null, {}, plan([]), plan([step("custom.contract")]), plan([step("tali.guard.jailbreak.v1", ["output"])])]) {
      expect(isModelIndependent(publishedProtectionCoverage(value))).toBeNull();
    }
  });
  it("counts enabled native Policy flows without pretending arbitrary actions are local", () => {
    const coverage = publishedProtectionCoverage({
      steps: [],
      policy_bindings: [{ policy_id: "native", policy_version: "1", enabled_rails: ["output"], enabled_rule_ids: [flowRuleId("output", "inspect response")] }],
      policy_versions: [{ policy_id: "native", version: 1, rail_bindings: [
        { rail_type: "output", flow_name: "inspect response" }, { rail_type: "input", flow_name: "inspect input" },
      ] }],
    });
    expect(coverage).toMatchObject({ inputChecks: 0, outputChecks: 1, policyCount: 1, hasUnknownDependencies: true });
    expect(isModelIndependent(coverage)).toBeNull();
  });
  it("does not hide custom-flow dependencies behind a local product step", () => {
    const coverage = publishedProtectionCoverage({ ...plan([step("tali.guard.pii.exact.v1")]),
      policy_bindings: [{ policy_id: "policy-1", policy_version: "1", enabled_rails: [], enabled_rule_ids: [flowRuleId("output", "custom check")] }],
      policy_versions: [{ policy_id: "policy-1", version: 1, rail_bindings: [{ rail_type: "output", flow_name: "custom check" }] }],
    });
    expect(coverage).toMatchObject({ inputChecks: 1, outputChecks: 1, policyCount: 1, hasUnknownDependencies: true });
    expect(isModelIndependent(coverage)).toBeNull();
  });
});
