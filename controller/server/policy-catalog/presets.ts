import type { GuardrailPolicyBindingConfig } from "../domain/guardrail-plan.js";
import type { ProtectionPreset } from "../../shared/protection-map.js";
import type { PolicyDto } from "./catalog.js";

/** Validate a preset against this exact installed catalog, never best-effort. */
export function expandProtectionPreset(preset: ProtectionPreset, policies: readonly PolicyDto[], current: readonly GuardrailPolicyBindingConfig[] = []): GuardrailPolicyBindingConfig[] {
  const byId = new Map(policies.map((policy) => [policy.id, policy]));
  const selected = new Set(current.map((binding) => binding.policyId));
  const result = structuredClone([...current]);
  for (const reference of preset.policies) {
    const policy = byId.get(reference.policyId);
    if (!policy) throw new Error(`Preset ${preset.id}: Policy ${reference.policyId} is unavailable.`);
    if (policy.version !== reference.policyVersion) throw new Error(`Preset ${preset.id}: Policy ${policy.id} requires version ${reference.policyVersion}, found ${policy.version}.`);
    if (!reference.enabledRails.length || reference.enabledRails.some((rail) => !policy.rails.includes(rail))) {
      throw new Error(`Preset ${preset.id}: Policy ${policy.id} has unsupported Rails.`);
    }
    const parameterValues = Object.fromEntries(policy.parameters.flatMap((parameter) => parameter.default == null ? [] : [[parameter.name, parameter.default]]));
    Object.assign(parameterValues, reference.parameterValues);
    for (const parameter of policy.parameters) {
      if (parameter.required && !parameterValues[parameter.name]?.trim()) throw new Error(`Preset ${preset.id}: Policy ${policy.id} needs ${parameter.name}.`);
    }
    if (selected.has(policy.id)) continue; // Never replace user overrides, versions, directions or order.
    selected.add(policy.id);
    result.push({
      policyId: policy.id, policyVersion: policy.version, action: null,
      parameterValues, enabledRuleIds: policy.rules.map((rule) => rule.id), ruleOrder: [],
      testCaseOverrides: {}, ruleActions: {}, enabledRails: [...reference.enabledRails], reasoningPolicy: null,
    });
  }
  return result;
}
