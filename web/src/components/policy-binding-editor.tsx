import { useMemo, useState } from "react";
import { CheckCircle2, ChevronDown, Search, ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { EnforcementAction, GuardrailPolicyBinding, Policy } from "@/lib/api";
import { cn } from "@/lib/utils";

const ACTIONS: EnforcementAction[] = [
  "reject",
  "redact",
  "rewrite",
  "regenerate",
  "redirect",
  "fallback",
  "clarify",
  "pass",
];

export function PolicyBindingEditor({
  policies,
  value,
  onChange,
}: {
  policies: Policy[];
  value: GuardrailPolicyBinding[];
  onChange: (next: GuardrailPolicyBinding[]) => void;
}) {
  const { t } = useTranslation();
  const [search, setSearch] = useState("");
  const selectedIds = new Set(value.map((binding) => binding.policy_id));
  const filtered = useMemo(() => {
    const term = search.trim().toLocaleLowerCase();
    if (!term) return policies;
    return policies.filter((policy) => [
      policy.name,
      policy.description,
      policy.id,
      ...policy.tags.map((tag) => tag.label),
      ...policy.rules.map((rule) => rule.name),
    ].join(" ").toLocaleLowerCase().includes(term));
  }, [policies, search]);

  function toggle(policy: Policy, checked: boolean) {
    if (checked) onChange([...value, defaultPolicyBinding(policy)]);
    else onChange(value.filter((binding) => binding.policy_id !== policy.id));
  }

  function update(policyId: string, patch: Partial<GuardrailPolicyBinding>) {
    onChange(value.map((binding) => binding.policy_id === policyId ? { ...binding, ...patch } : binding));
  }

  return (
    <div className="space-y-5">
      <label className="relative block">
        <span className="sr-only">{t("guardrailWizard.searchPolicies")}</span>
        <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          className="min-h-11 bg-card pl-9"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder={t("guardrailWizard.searchPolicies")}
        />
      </label>

      <div className="grid gap-3 md:grid-cols-2">
        {filtered.map((policy) => {
          const checked = selectedIds.has(policy.id);
          const bindable = policy.source === "built_in" || policy.version !== "0";
          return (
            <label
              key={policy.id}
              className={cn(
                "grid min-h-28 cursor-pointer grid-cols-[1.5rem_minmax(0,1fr)] gap-3 rounded-xl border bg-card p-4 transition-colors hover:border-primary/35",
                checked && "border-primary/40 bg-primary/[0.035] ring-1 ring-primary/10",
                !bindable && "cursor-not-allowed opacity-60",
              )}
            >
              <Checkbox
                className="mt-0.5"
                checked={checked}
                disabled={!bindable}
                onCheckedChange={(next) => toggle(policy, Boolean(next))}
              />
              <span className="min-w-0">
                <span className="flex flex-wrap items-center gap-2">
                  <strong className="text-sm">{policy.name}</strong>
                  <Badge variant="outline" className="font-mono text-[10px]">v{policy.version}</Badge>
                </span>
                <span className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">{policy.description}</span>
                <span className="mt-2 flex flex-wrap gap-1.5">
                  <Badge variant="secondary">{t("policyLibrary.ruleCount", { count: policy.rules.length })}</Badge>
                  <Badge variant="secondary">{t("policyLibrary.testCount", { count: policy.test_count })}</Badge>
                  {!bindable ? <Badge variant="outline">{t("guardrailWizard.publishPolicyFirst")}</Badge> : null}
                </span>
              </span>
            </label>
          );
        })}
      </div>

      {value.length ? (
        <section className="overflow-hidden rounded-xl border bg-card">
          <header className="border-b bg-muted/25 px-4 py-3">
            <h3 className="text-sm font-semibold">{t("guardrailWizard.boundPolicies", { count: value.length })}</h3>
            <p className="mt-1 text-xs text-muted-foreground">{t("guardrailWizard.boundPoliciesDescription")}</p>
          </header>
          <div className="divide-y">
            {value.map((binding) => {
              const policy = policies.find((item) => item.id === binding.policy_id);
              if (!policy) return null;
              return (
                <details key={binding.policy_id} open className="group">
                  <summary className="flex min-h-14 cursor-pointer list-none items-center gap-3 px-4 py-3 outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring [&::-webkit-details-marker]:hidden">
                    <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary"><ShieldCheck className="size-4" /></span>
                    <span className="min-w-0 flex-1"><strong className="block truncate text-sm">{policy.name}</strong><span className="font-mono text-xs text-muted-foreground">{binding.policy_id}@{binding.policy_version}</span></span>
                    <Badge variant="outline">{t("guardrailWizard.enabledRuleCount", { count: binding.enabled_rule_ids.length })}</Badge>
                    <ChevronDown className="size-4 text-muted-foreground transition-transform group-open:rotate-180" />
                  </summary>
                  <div className="space-y-5 border-t bg-muted/[0.12] p-4">
                    <div className="grid gap-4 sm:grid-cols-2">
                      <Field label={t("guardrailWizard.policyAction")}>
                        <Select value={binding.action ?? "policy_default"} onValueChange={(selected) => update(binding.policy_id, { action: selected === "policy_default" ? null : selected as EnforcementAction })}>
                          <SelectTrigger className="min-h-11 bg-card"><SelectValue /></SelectTrigger>
                          <SelectContent><SelectItem value="policy_default">{t("guardrailWizard.usePolicyBehavior")}</SelectItem>{ACTIONS.map((action) => <SelectItem key={action} value={action}>{action}</SelectItem>)}</SelectContent>
                        </Select>
                      </Field>
                      <div>
                        <Label>{t("guardrailWizard.enabledRails")}</Label>
                        <div className="mt-2 flex min-h-11 flex-wrap items-center gap-2">
                          {policy.stages.map((stage) => <Badge key={stage} variant="outline" className="font-mono uppercase">{stage}</Badge>)}
                        </div>
                      </div>
                    </div>

                    {policy.parameters.length ? (
                      <div className="grid gap-4 sm:grid-cols-2">
                        {policy.parameters.map((parameter) => (
                          <Field key={parameter.name} label={`${parameter.label ?? parameter.name}${parameter.required ? " *" : ""}`} hint={parameter.description}>
                            <Input
                              className="min-h-11 bg-card"
                              type={parameter.kind === "secret" ? "password" : "text"}
                              value={binding.parameter_values[parameter.name] ?? parameter.default ?? ""}
                              placeholder={parameter.placeholder}
                              onChange={(event) => update(binding.policy_id, { parameter_values: { ...binding.parameter_values, [parameter.name]: event.target.value } })}
                            />
                          </Field>
                        ))}
                      </div>
                    ) : null}

                    {binding.policy_id === "builtin-automated-reasoning" ? (
                      <div className="grid gap-4 rounded-lg border bg-card p-4 sm:grid-cols-3">
                        <Field label={t("guardrailWizard.reasoningPolicyId")}><Input className="min-h-11" value={binding.reasoning_policy?.policy_id ?? ""} onChange={(event) => update(binding.policy_id, { reasoning_policy: { policy_id: event.target.value, policy_version: binding.reasoning_policy?.policy_version ?? "", confidence_threshold: binding.reasoning_policy?.confidence_threshold ?? 0.8 } })} /></Field>
                        <Field label={t("guardrailWizard.reasoningPolicyVersion")}><Input className="min-h-11" value={binding.reasoning_policy?.policy_version ?? ""} onChange={(event) => update(binding.policy_id, { reasoning_policy: { policy_id: binding.reasoning_policy?.policy_id ?? "", policy_version: event.target.value, confidence_threshold: binding.reasoning_policy?.confidence_threshold ?? 0.8 } })} /></Field>
                        <Field label={t("guardrailWizard.confidenceThreshold")}><Input className="min-h-11" type="number" min={0} max={1} step={0.05} value={binding.reasoning_policy?.confidence_threshold ?? 0.8} onChange={(event) => update(binding.policy_id, { reasoning_policy: { policy_id: binding.reasoning_policy?.policy_id ?? "", policy_version: binding.reasoning_policy?.policy_version ?? "", confidence_threshold: Number(event.target.value) } })} /></Field>
                      </div>
                    ) : null}

                    <section>
                      <h4 className="text-xs font-semibold">{t("guardrailWizard.policyRules")}</h4>
                      <div className="mt-2 divide-y rounded-lg border bg-card">
                        {policy.rules.map((rule) => {
                          const enabled = binding.enabled_rule_ids.includes(rule.id);
                          return (
                            <div key={rule.id} className="grid gap-3 p-3 sm:grid-cols-[2rem_minmax(0,1fr)_10rem] sm:items-center">
                              <Checkbox checked={enabled} onCheckedChange={(next) => update(binding.policy_id, { enabled_rule_ids: next ? [...binding.enabled_rule_ids, rule.id] : binding.enabled_rule_ids.filter((id) => id !== rule.id) })} />
                              <span className="min-w-0"><strong className="block truncate text-xs">{rule.name}</strong><span className="mt-1 block truncate font-mono text-xs text-muted-foreground">{rule.id}</span></span>
                              <Select value={binding.rule_actions[rule.id] ?? "policy_default"} disabled={!enabled} onValueChange={(selected) => { const next = { ...binding.rule_actions }; if (selected === "policy_default") delete next[rule.id]; else next[rule.id] = selected as EnforcementAction; update(binding.policy_id, { rule_actions: next }); }}>
                                <SelectTrigger className="min-h-10"><SelectValue /></SelectTrigger>
                                <SelectContent><SelectItem value="policy_default">{rule.effect}</SelectItem>{ACTIONS.map((action) => <SelectItem key={action} value={action}>{action}</SelectItem>)}</SelectContent>
                              </Select>
                            </div>
                          );
                        })}
                      </div>
                    </section>
                  </div>
                </details>
              );
            })}
          </div>
        </section>
      ) : (
        <div className="rounded-xl border border-dashed bg-card p-8 text-center"><CheckCircle2 className="mx-auto size-7 text-muted-foreground" /><p className="mt-2 text-sm font-medium">{t("guardrailWizard.noPolicies")}</p><p className="mt-1 text-xs text-muted-foreground">{t("guardrailWizard.noPoliciesDescription")}</p></div>
      )}
    </div>
  );
}

export function defaultPolicyBinding(policy: Policy): GuardrailPolicyBinding {
  return {
    policy_id: policy.id,
    policy_version: policy.version,
    action: null,
    parameter_values: Object.fromEntries(policy.parameters.filter((parameter) => parameter.default != null).map((parameter) => [parameter.name, parameter.default ?? ""])),
    enabled_rule_ids: policy.rules.map((rule) => rule.id),
    rule_actions: {},
    enabled_rails: policy.stages,
    reasoning_policy: policy.id === "builtin-automated-reasoning" ? { policy_id: "", policy_version: "", confidence_threshold: 0.8 } : null,
  };
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return <label className="grid gap-2"><Label>{label}</Label>{children}{hint ? <span className="text-xs leading-5 text-muted-foreground">{hint}</span> : null}</label>;
}
