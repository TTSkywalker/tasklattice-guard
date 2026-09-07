import type { GuardrailPolicyBinding, Policy } from "./api-types";

/** Never substitute latest/draft metadata for a pinned, unavailable version. */
export function boundPolicy(policies: readonly Policy[], binding: Pick<GuardrailPolicyBinding, "policy_id" | "policy_version">): Policy | undefined {
  const policy = policies.find((item) => item.id === binding.policy_id);
  if (policy?.version === binding.policy_version) return policy;
  return policy?.published_versions?.find((item) => item.id === binding.policy_id && item.version === binding.policy_version);
}
