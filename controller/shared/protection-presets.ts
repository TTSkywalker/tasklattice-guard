import type { ProtectionPreset } from "./protection-map.js";

const legacy = (policyId: string, enabledRails: Array<"input" | "output"> = ["input", "output"]) => ({
  policyId, policyVersion: "1.95.0", enabledRails, parameterValues: {},
});
const focused = (policyId: string) => ({ ...legacy(policyId), policyVersion: "2.0.0" });

// Each industry preset expands to real, pinned Policies. No anonymous Rules or
// runtime inheritance is created. Shared baseline order is authored, not sorted
// by action or severity. Users can review, remove and reorder every binding.
const baseline = [
  focused("local-credentials"),
  legacy("filter-denied-insults"),
  legacy("filter-harmful-self-harm"),
  legacy("filter-harmful-violence"),
  legacy("filter-harmful-child-safety"),
  legacy("filter-harmful-illegal-weapons"),
  legacy("filter-bias-racial"),
  legacy("filter-bias-gender"),
  legacy("filter-bias-religious"),
  legacy("filter-bias-sexual-orientation"),
  legacy("filter-harm-toxic-abuse"),
  focused("local-prompt-manipulation"),
  legacy("filter-prompt-injection-data-exfiltration"),
  focused("local-payment-data"),
  focused("local-passports"),
  focused("local-contact-data"),
];
const limitations = [
  "Local patterns provide basic screening, not complete semantic coverage or guaranteed attack prevention.",
  "Selected output transformations require complete-response buffering, including streaming requests.",
  "Optional model-backed protection is not enabled until explicitly selected, configured and validated.",
];
const financialLimitations = [
  ...limitations,
  "Financial reference controls are text checks, not regulatory compliance, suitability decisions, transaction authorization or certification.",
];
const enhancements = ["builtin-content-safety", "builtin-jailbreak", "builtin-topic-safety", "builtin-contextual-grounding"];

export const protectionPresets: readonly ProtectionPreset[] = [
  {
    id: "common-baseline", version: "1.0.0", name: "Common baseline", industry: "general", jurisdictions: [],
    description: "Basic local protection for credentials, personal data, harmful phrases and prompt attacks. No external model required.",
    policies: baseline, suggestedTopics: [], optionalPolicyIds: enhancements, limitations,
  },
  {
    id: "banking-assistant", version: "1.0.0", name: "Banking customer service", industry: "banking", jurisdictions: [],
    description: "Common baseline plus identity-check evasion and misleading investment-guarantee patterns. Banking education stays available.",
    policies: [...baseline, focused("banking-customer-protection")],
    suggestedTopics: ["Accounts, cards and payments", "Banking product information", "Customer service and fraud reporting"],
    optionalPolicyIds: [...enhancements, "singapore-customer-identifiers", "singapore-financial-conduct"], limitations: financialLimitations,
  },
  {
    id: "securities-assistant", version: "1.0.0", name: "Securities & brokerage", industry: "securities", jurisdictions: [],
    description: "Common baseline plus insider-trading, market-manipulation and misleading return-guarantee patterns.",
    policies: [...baseline, focused("banking-customer-protection"), focused("securities-market-integrity")],
    suggestedTopics: ["Securities products and risk education", "Brokerage account support", "Public market information"],
    optionalPolicyIds: [...enhancements, "singapore-customer-identifiers", "singapore-financial-conduct"], limitations: financialLimitations,
  },
  {
    id: "internet-customer-support", version: "1.0.0", name: "Internet platform support", industry: "internet", jurisdictions: [],
    description: "Common baseline plus phishing, session theft, SQL/code and rendered-content injection patterns.",
    policies: [...baseline, focused("internet-account-abuse"), focused("local-sql-injection"), focused("local-code-injection"), focused("local-rendered-content-injection")],
    suggestedTopics: ["Product support and troubleshooting", "Account and subscription help", "Trust and safety reporting"],
    optionalPolicyIds: [...enhancements, "keyword-blocking", "competitor-mention-detection"],
    limitations: [...limitations, "Content screening does not replace output encoding, parameterized queries, sandboxing or access control."],
  },
  {
    id: "singapore-financial-assistant", version: "1.0.0", name: "Singapore financial reference", industry: "banking", jurisdictions: ["singapore"],
    description: "Banking baseline plus Singapore customer identifiers and reviewed financial-conduct/data-use phrase checks.",
    policies: [...baseline, focused("banking-customer-protection"), focused("singapore-customer-identifiers"), focused("singapore-data-use-boundaries"), focused("singapore-financial-conduct")],
    suggestedTopics: ["Singapore banking customer support", "Financial products and risk education", "Personal-data handling requests"],
    optionalPolicyIds: [...enhancements, "securities-market-integrity"], limitations: financialLimitations,
  },
];
