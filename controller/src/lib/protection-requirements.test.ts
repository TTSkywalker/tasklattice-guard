import { describe, expect, it } from "vitest";
import type { Policy } from "./api-types";
import { policyRequiresTopicAllowlist } from "./protection-requirements";

describe("Business classification is not runtime configuration", () => {
  it("does not force financial local rules to configure a topic model or allowlist", () => {
    const financial = {
      id: "banking-customer-protection",
      tags: [{ namespace: "guardrail_category", value: "topic_control" }],
      protection: { directory: "business_rules", execution: "local", requiredContext: [] },
    } as unknown as Policy;
    expect(policyRequiresTopicAllowlist(financial)).toBe(false);
    expect(policyRequiresTopicAllowlist({ ...financial, id: "builtin-topic-safety", protection: { ...financial.protection!, requiredContext: ["allowed_topics"] } })).toBe(true);
    expect(policyRequiresTopicAllowlist(undefined)).toBe(false);
  });
});
