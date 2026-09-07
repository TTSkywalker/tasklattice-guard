import type { Policy } from "./api-types";

/** A business/category label is navigation, never an executable dependency. */
export function policyRequiresTopicAllowlist(policy: (Pick<Policy, "id"> & Partial<Pick<Policy, "protection">>) | undefined): boolean {
  if (!policy) return false;
  if (policy.protection) return policy.protection.requiredContext.includes("allowed_topics");
  return ["builtin-topic-safety", "builtin-company-policy"].includes(policy.id);
}
