import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { PolicyCatalog } from "../policy-catalog/catalog.js";
import { recommendationCatalog } from "./recommendation-catalog.js";

const source = PolicyCatalog.load(resolve("../runner/toolkit/policy_library/assets")).list();

describe("Document recommendation catalog", () => {
  it("excludes retired mixed collections without removing them from the source library", () => {
    const legacy = source.filter((policy) => policy.protection.legacyCollection);
    expect(legacy.length).toBeGreaterThan(0);
    const recommendations = recommendationCatalog(source);
    expect(recommendations.map((policy) => policy.id)).not.toEqual(expect.arrayContaining(legacy.map((policy) => policy.id)));
    for (const policy of legacy) expect(recommendations.some((item) => item.id === policy.id)).toBe(false);
    const focusedEmail = source.find((policy) => !policy.protection.legacyCollection && policy.rules.some((rule) => rule.id === "pattern/email"));
    expect(focusedEmail).toBeDefined();
    expect(recommendations.some((policy) => policy.id === focusedEmail!.id)).toBe(true);
    expect(source.some((policy) => policy.id === "baseline-pii-protection")).toBe(true);
  });

  it("provides real direction, dependency and limitation metadata without implementation bodies", () => {
    const recommendations = recommendationCatalog(source);
    const model = recommendations.find((policy) => policy.id === "builtin-content-safety")!;
    expect(model).toMatchObject({ directory: "content_safety", rails: ["input", "output"], execution: "model", model_capabilities: ["content_safety"] });
    expect(model.limitations.length).toBeGreaterThan(0);
    expect(model).not.toHaveProperty("rules");
    expect(model).not.toHaveProperty("implementation_detail");
  });

  it("excludes unpublished custom Policies and keeps unclassified published requirements unknown", () => {
    const custom = { id: "custom", name: "Custom", description: "Custom flow", source: "custom" as const, rails: ["output"], version: "0" };
    expect(recommendationCatalog([custom])).toEqual([]);
    expect(recommendationCatalog([{ ...custom, version: "1" }])[0]).toMatchObject({ execution: "custom", directory: null, model_capabilities: null, required_context: null });
  });
});
