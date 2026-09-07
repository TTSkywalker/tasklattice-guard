import { useState } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { GuardrailPolicyBinding, Policy } from "@/lib/api";

import { PolicyBindingEditor, defaultPolicyBinding } from "./policy-binding-editor";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, string | number>) => {
      const labels: Record<string, string> = {
        "guardrailWizard.searchPolicies": "Search Policies",
        "guardrailWizard.selectPolicies": "Select Policies",
        "guardrailWizard.policyPickerHint": "Type to filter existing Policies.",
        "guardrailWizard.noMatchingPolicies": "No Policies match",
        "guardrailWizard.noMatchingPoliciesDescription": "Try another keyword.",
        "guardrailWizard.noPublishedPolicies": "No published Policies",
        "guardrailWizard.noPublishedPoliciesDescription": "Publish a Policy first.",
        "guardrailWizard.boundPolicies": "Bound Policies ({{count}})",
        "guardrailWizard.boundPoliciesDescription": "Pinned Policy bindings.",
        "guardrailWizard.boundPolicyDetails": "Review Rule details for {{name}}",
        "guardrailWizard.boundPolicyDetailsRequiresConfiguration": "Review required configuration for {{name}}",
        "guardrailWizard.enabledRuleCount": "{{count}} Rules",
        "guardrailWizard.missingRequiredFieldCount": "Required fields remaining: {{count}}",
        "guardrailWizard.reasoningConfigurationRequired": "Reasoning configuration required",
        "guardrailWizard.noEnabledRules": "No Rules enabled",
        "guardrailWizard.policyAction": "Policy action",
        "guardrailWizard.usePolicyBehavior": "Use Policy behavior",
        "guardrailWizard.enabledRails": "Enabled Rails",
        "protection.input": "Requests",
        "protection.output": "Responses",
        "protection.selectDirection": "Select requests, responses or both.",
        "protection.moveRuleUp": "Move {{name}} earlier in {{policy}}",
        "protection.moveRuleDown": "Move {{name}} later in {{policy}}",
        "guardrailWizard.policyRules": "Policy Rules",
        "guardrailWizard.noPolicies": "No Policies",
        "guardrailWizard.noPoliciesDescription": "Select a Policy.",
        "policyLibrary.ruleCount": "{{count}} Rules",
        "policyLibrary.testCount": "{{count}} Test Cases",
        "common.multiSelect.available": "{{count}} available",
        "common.multiSelect.matching": "{{count}} matching",
        "common.multiSelect.clearAll": "Clear all",
        "common.multiSelect.remove": "Remove {{name}}",
        "common.multiSelect.open": "Open options for {{name}}",
        "common.multiSelect.close": "Close options for {{name}}",
        "common.multiSelect.options": "{{name}} options",
      };
      return Object.entries(values ?? {}).reduce(
        (label, [name, value]) => label.replace(`{{${name}}}`, String(value)),
        labels[key] ?? key,
      );
    },
    i18n: { language: "en" },
  }),
}));

const policy = {
  implementation: "rules",
  id: "customer-data-policy",
  name: "Customer data Policy",
  description: "Protect customer identifiers.",
  source: "built_in",
  version: "1",
  tags: [],
  parameters: [],
  rails: ["input"],
  effects: ["redact"],
  forms: ["regex"],
  rules: [
    {
      id: "customer-data-policy/account-id",
      name: "Protect account IDs",
      description: "Redact account identifiers.",
      form: "regex",
      effect: "redact",
      rails: ["input"],
      implementation: {
        engine: "nemo-guardrails",
        form: "regex",
        binding_id: "customer-data-policy",
        implementation_rule_id: "account-id",
        detector: "regex",
        flow_name: null,
        action_name: "PolicyRuleAction",
      },
      expression: "account-[0-9]+",
      context_expression: null,
      redaction: "[ACCOUNT]",
      severity_threshold: null,
      identifiers: [],
      conditions: [],
      keywords: [],
      always_block: [],
      exceptions: [],
      phrase_patterns: [],
    },
  ],
  test_cases: [],
  test_count: 1,
  safety_level: "balanced",
  output_delivery: "window_buffered",
} satisfies Policy;

const requiredPolicy = {
  ...policy,
  id: "aviation-operations-security",
  name: "Aviation Operations Security",
  parameters: [
    { name: "brand_name", label: "Your Airline / Brand Name", kind: "text", required: true, placeholder: "e.g. Acme Airlines", description: "" },
    { name: "competitors", label: "Competitors", kind: "textarea", required: true, placeholder: "One competitor per line", description: "Reviewed competitors." },
  ],
} satisfies Policy;

function Harness({ policies = [policy] }: { policies?: Policy[] }) {
  const [bindings, setBindings] = useState<GuardrailPolicyBinding[]>([]);
  return <><PolicyBindingEditor policies={policies} value={bindings} onChange={setBindings} /><output aria-label="Binding configuration">{JSON.stringify(bindings)}</output></>;
}

describe("PolicyBindingEditor", () => {
  afterEach(cleanup);

  it("renders and edits the pinned version's required parameters, not the latest version", () => {
    const old: Policy = { ...policy, source: "custom", name: "Published old", parameters: [{ name: "old_parameter", label: "Old required value", kind: "string", required: true, description: "" }] };
    const latest: Policy = { ...old, version: "2", name: "Published new", rules: [], parameters: [], published_versions: [old] };
    const onChange = vi.fn();
    render(<PolicyBindingEditor policies={[latest]} value={[defaultPolicyBinding(old)]} onChange={onChange} />);
    expect(screen.getAllByText("Published old").length).toBe(2);
    expect(screen.getByRole("button", { name: "Remove Published old" })).toBeTruthy();
    expect(screen.queryByText("Published new")).toBeNull();
    fireEvent.change(screen.getByLabelText("Old required value *"), { target: { value: "reviewed value" } });
    expect(onChange.mock.calls[0]?.[0][0]).toMatchObject({ policy_version: "1", parameter_values: { old_parameter: "reviewed value" } });
  });

  it("offers the latest version only after explicitly removing the old binding", () => {
    const old: Policy = { ...policy, name: "Published old", source: "custom" };
    const latest: Policy = { ...old, version: "2", name: "Published new", published_versions: [old] };
    const onChange = vi.fn();
    const { rerender } = render(<PolicyBindingEditor policies={[latest]} value={[defaultPolicyBinding(old)]} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "Remove Published old" }));
    expect(onChange).toHaveBeenLastCalledWith([]);
    rerender(<PolicyBindingEditor policies={[latest]} value={[]} onChange={onChange} />);
    fireEvent.keyDown(screen.getByRole("combobox", { name: "Select Policies" }), { key: "ArrowDown" });
    fireEvent.click(screen.getByRole("option", { name: /Published new/ }));
    expect(onChange.mock.calls.at(-1)?.[0][0]).toMatchObject({ policy_id: old.id, policy_version: "2" });
  });

  it("shows a missing pinned version instead of substituting latest and allows explicit removal", () => {
    const onChange = vi.fn();
    render(<PolicyBindingEditor policies={[{ ...policy, version: "2" }]} value={[defaultPolicyBinding(policy)]} onChange={onChange} />);
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.queryByText("Protect account IDs")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "common.remove" }));
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("keeps a newly bound Policy collapsed until the user opens its Rule details", () => {
    render(<Harness />);

    fireEvent.focus(screen.getByRole("combobox", { name: "Select Policies" }));
    fireEvent.click(screen.getByRole("option", { name: /Customer data Policy/ }));

    expect(screen.getByRole("button", { name: "Remove Customer data Policy" })).toBeTruthy();

    const details = document.querySelector("details");
    expect(details).not.toBeNull();
    expect(details!.open).toBe(false);
    expect(details!.querySelector("summary")?.getAttribute("aria-label")).toBe(
      "Review Rule details for Customer data Policy",
    );

    fireEvent.click(details!.querySelector("summary")!);

    expect(details!.open).toBe(true);
    expect(screen.getByText("Protect account IDs")).toBeTruthy();

    fireEvent.keyDown(details!.querySelector("summary")!, { key: "Enter" });
    expect(details!.open).toBe(false);
  });

  it("finds framework-tagged Policies by OWASP and shows the framework label", () => {
    const owaspPolicy: Policy = {
      ...policy,
      id: "prompt-injection-policy",
      name: "Prompt injection Policy",
      tags: [{
        id: "framework:owasp-llm-2025",
        namespace: "framework",
        value: "owasp-llm-2025",
        label: "OWASP LLM 2025",
        source: "declared",
      }],
    };
    render(<Harness policies={[policy, owaspPolicy]} />);

    const search = screen.getByRole("combobox", { name: "Select Policies" });
    fireEvent.focus(search);
    fireEvent.change(search, { target: { value: "OWASP" } });

    expect(screen.getByRole("option", { name: /Prompt injection Policy/ })).toBeTruthy();
    expect(screen.queryByRole("option", { name: /Customer data Policy/ })).toBeNull();
    expect(screen.getByText(/OWASP LLM 2025/)).toBeTruthy();
  });

  it("opens a newly selected Policy when required configuration is missing", () => {
    render(<Harness policies={[requiredPolicy]} />);

    fireEvent.focus(screen.getByRole("combobox", { name: "Select Policies" }));
    fireEvent.click(screen.getByRole("option", { name: /Aviation Operations Security/ }));

    const details = document.querySelector("details");
    expect(details).not.toBeNull();
    expect(details!.open).toBe(true);
    expect(details!.querySelector("summary")?.getAttribute("aria-label")).toBe(
      "Review required configuration for Aviation Operations Security",
    );
    expect(screen.getByTestId("required-configuration-indicator").getAttribute("aria-hidden")).toBe("true");
    expect(screen.getByText("Required fields remaining: 2")).toBeTruthy();
    expect(screen.getByPlaceholderText("e.g. Acme Airlines")).toBeTruthy();
    expect(screen.getByPlaceholderText("One competitor per line")).toBeTruthy();

    fireEvent.change(screen.getByPlaceholderText("e.g. Acme Airlines"), { target: { value: "TaskLattice Air" } });
    fireEvent.change(screen.getByPlaceholderText("One competitor per line"), { target: { value: "Example Air" } });

    expect(screen.queryByText("Required fields remaining: 2")).toBeNull();
    expect(screen.queryByTestId("required-configuration-indicator")).toBeNull();
    expect(details!.querySelector("summary")?.getAttribute("aria-label")).toBe(
      "Review Rule details for Aviation Operations Security",
    );
    expect(details!.open).toBe(true);
  });

  it("edits request/response scope and flags an empty direction without changing the source Policy", () => {
    const both: Policy = { ...policy, rails: ["input", "output"] };
    render(<Harness policies={[both]} />);
    fireEvent.focus(screen.getByRole("combobox", { name: "Select Policies" }));
    fireEvent.click(screen.getByRole("option", { name: /Customer data Policy/ }));
    fireEvent.click(document.querySelector("summary")!);
    fireEvent.click(screen.getByRole("checkbox", { name: "Customer data Policy: Responses" }));
    let bindings = JSON.parse(screen.getByLabelText("Binding configuration").textContent!);
    expect(bindings[0].enabled_rails).toEqual(["input"]);
    fireEvent.click(screen.getByRole("checkbox", { name: "Customer data Policy: Requests" }));
    expect(screen.getByText("Select requests, responses or both.")).toBeTruthy();
    fireEvent.click(screen.getByRole("checkbox", { name: "Customer data Policy: Responses" }));
    bindings = JSON.parse(screen.getByLabelText("Binding configuration").textContent!);
    expect(bindings[0].enabled_rails).toEqual(["output"]);
    expect(both.rails).toEqual(["input", "output"]);
  });

  it("persists local Rule order and disabling independently of source Rule order", () => {
    const rules = [policy.rules[0]!, { ...policy.rules[0]!, id: "another-rule", name: "Reject credentials" }];
    render(<Harness policies={[{ ...policy, rules }]} />);
    fireEvent.focus(screen.getByRole("combobox", { name: "Select Policies" }));
    fireEvent.click(screen.getByRole("option", { name: /Customer data Policy/ }));
    fireEvent.click(document.querySelector("summary")!);
    fireEvent.click(screen.getByRole("button", { name: "Move Reject credentials earlier in Customer data Policy" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Customer data Policy: Protect account IDs" }));
    const bindings = JSON.parse(screen.getByLabelText("Binding configuration").textContent!);
    expect(bindings[0].rule_order).toEqual(["another-rule", policy.rules[0]!.id]);
    expect(bindings[0].enabled_rule_ids).toEqual(["another-rule"]);
    expect(rules.map((rule) => rule.id)).toEqual([policy.rules[0]!.id, "another-rule"]);
  });
});
