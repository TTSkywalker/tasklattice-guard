import { describe, expect, it } from "vitest";
import { boundPolicy } from "./bound-policy";
import { completeResponsePolicies } from "./protection-composition";
import type { Policy, GuardrailPolicyBinding } from "./api-types";

const old = { id: "custom", version: "1", name: "Old Policy", parameters: [{ name: "old-required", required: true }],
  rules: [{ id: "old-rule", rails: ["output"] }], rails: ["output"], protection: { outputStreaming: "complete_response" } } as Policy;
const latest = { ...old, version: "2", name: "New Policy", parameters: [], published_versions: [old],
  rules: [{ id: "new-rule", rails: ["input"] }], rails: ["input"] } as Policy;

describe("Pinned Policy lookup", () => {
  it("resolves exact versioned metadata and never implicitly upgrades a binding", () => {
    expect(boundPolicy([latest], { policy_id: "custom", policy_version: "1" })).toBe(old);
    expect(boundPolicy([latest], { policy_id: "custom", policy_version: "2" })).toBe(latest);
    expect(boundPolicy([latest], { policy_id: "custom", policy_version: "missing" })).toBeUndefined();
  });
  it("checks identity as well as version and does not fall back for an absent catalog entry", () => {
    expect(boundPolicy([{ ...latest, published_versions: [{ ...old, id: "different" }] }], { policy_id: "custom", policy_version: "1" })).toBeUndefined();
    expect(boundPolicy([], { policy_id: "custom", policy_version: "1" })).toBeUndefined();
  });
  it("uses the pinned Output delivery contract instead of a newer version's direction", () => {
    const binding = { policy_id: "custom", policy_version: "1", enabled_rails: ["output"], rule_actions: {} } as GuardrailPolicyBinding;
    expect(completeResponsePolicies([binding], [latest])).toEqual(["Old Policy"]);
  });
});
