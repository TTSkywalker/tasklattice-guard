import { policyProtectionDirectory, type PolicyProtection } from "../../shared/protection-map.js";
import { evaluationContractDependencies } from "../../shared/protection-dependencies.js";
import type { ProgrammablePolicyDraft } from "./model.js";

/** Published source metadata owns navigation. Neither category nor an empty
 * action/dependency list certifies arbitrary Colang as model-independent. */
export function programmablePolicyProtection(policy: Pick<ProgrammablePolicyDraft, "guardrail_category" | "protection_directory" | "rail_bindings" | "evaluation_contracts">): PolicyProtection {
  const rails = [...new Set(policy.rail_bindings.map(item => item.rail_type))];
  const contracts = [...new Set(policy.evaluation_contracts)];
  const bindings = contracts.flatMap(contract => rails.flatMap(rail => evaluationContractDependencies(contract, rail).bindings));
  return {
    directory: policyProtectionDirectory(policy), execution: "custom",
    modelCapabilities: [...new Set(bindings.map(item => item.capabilityRef))],
    // Custom flows may supply context internally; do not invent caller inputs
    // from a model name. Unknown context is retained by execution="custom".
    evaluationContracts: contracts, requiredContext: [],
    outputStreaming: rails.includes("output") ? "complete_response" : "not_applicable",
    limitations: [
      "Declared dependencies are a lower bound. Custom Colang actions may require additional models, context or services; no model-free guarantee is inferred.",
      "The business directory describes author-declared intent, not verified detector coverage or regulatory compliance.",
    ],
  };
}
