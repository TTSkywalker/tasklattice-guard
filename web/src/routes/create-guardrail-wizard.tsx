import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Braces, Check, LoaderCircle, ShieldCheck, Sparkles } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { CreationFlow } from "@/components/creation-flow";
import { EntitySheet } from "@/components/entity-sheet";
import { PolicyBindingEditor } from "@/components/policy-binding-editor";
import { ErrorNotice, InfoNotice } from "@/components/product-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { queryKeys } from "@/features/query-keys";
import { useAuth } from "@/lib/auth";
import {
  analyzeGuardrailIntent,
  createGuardrail,
  getIntentAnalysisStatus,
  getPolicies,
  previewGuardrailCandidate,
  type GuardrailPolicyBinding,
  type OutputDelivery,
  type Policy,
  type SafetyLevel,
} from "@/lib/api";

const EMPTY_POLICIES: Policy[] = [];

export function CreateGuardrailWizard({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (id: string) => void;
}) {
  const { t, i18n } = useTranslation();
  const { user } = useAuth();
  const policiesQuery = useQuery({ queryKey: queryKeys.policies, queryFn: getPolicies, enabled: open });
  const intentStatusQuery = useQuery({ queryKey: queryKeys.intentAnalysisStatus, queryFn: getIntentAnalysisStatus, enabled: open, retry: false });
  const policies = policiesQuery.data?.items ?? EMPTY_POLICIES;
  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [purpose, setPurpose] = useState("");
  const [allowed, setAllowed] = useState("");
  const [restricted, setRestricted] = useState("");
  const [bindings, setBindings] = useState<GuardrailPolicyBinding[]>([]);
  const [safetyLevel, setSafetyLevel] = useState<SafetyLevel>("balanced");
  const [outputDelivery, setOutputDelivery] = useState<OutputDelivery>("window_buffered");

  const steps = [
    { label: t("guardrailWizard.steps.details"), description: t("guardrailWizard.steps.detailsDescription") },
    { label: t("guardrailWizard.steps.policies"), description: t("guardrailWizard.steps.policiesDescription") },
    { label: t("guardrailWizard.steps.runtime"), description: t("guardrailWizard.steps.runtimeDescription") },
    { label: t("guardrailWizard.steps.review"), description: t("guardrailWizard.steps.reviewDescription") },
  ];

  useEffect(() => {
    if (!open) return;
    setStep(0);
    setName("");
    setPurpose("");
    setAllowed("");
    setRestricted("");
    setBindings([]);
    setSafetyLevel("balanced");
    setOutputDelivery("window_buffered");
  }, [open]);

  const language = user?.preferred_language ?? (i18n.language.toLowerCase().startsWith("zh") ? "zh-CN" : "en");
  const analyzeIntent = useMutation({
    mutationFn: () => analyzeGuardrailIntent({ purpose: purpose.trim(), language }),
    onSuccess: (analysis) => {
      setAllowed(analysis.allowed_topics.join("\n"));
      setRestricted(analysis.restricted_topics.join("\n"));
      toast.success(t("guardrailWizard.intentGenerated"));
    },
    onError: (error) => notifyError(error, t("guardrailWizard.operationFailed")),
  });

  const payload = useMemo(() => ({
    name: name.trim(),
    purpose: purpose.trim(),
    allowed_topics: lines(allowed),
    restricted_topics: lines(restricted),
    policy_bindings: bindings,
    safety_level: safetyLevel,
    output_delivery: outputDelivery,
  }), [allowed, bindings, name, outputDelivery, purpose, restricted, safetyLevel]);

  const preview = useMutation({ mutationFn: () => previewGuardrailCandidate(payload) });
  useEffect(() => {
    if (step === 3 && bindings.length && bindingsValid(bindings, policies)) preview.mutate();
    // The preview is a point-in-time review; edits happen on previous steps.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step]);

  const create = useMutation({
    mutationFn: () => createGuardrail(payload),
    onSuccess: (guardrail) => {
      toast.success(t("guardrailWizard.created", { name: guardrail.name }));
      onCreated(guardrail.id);
    },
    onError: (error) => notifyError(error, t("guardrailWizard.operationFailed")),
  });

  const stepValid = [
    Boolean(name.trim() && purpose.trim()),
    bindingsValid(bindings, policies),
    true,
    Boolean(preview.data && !preview.error),
  ];

  return (
    <EntitySheet
      open={open}
      onOpenChange={onOpenChange}
      eyebrow={t("guardrailWizard.eyebrow")}
      title={t("guardrailWizard.title")}
      description={t("guardrailWizard.description")}
      width="xl"
      bodyClassName="p-0 sm:p-0"
      footer={(
        <>
          <Button variant="outline" onClick={() => step ? setStep(step - 1) : onOpenChange(false)}>
            {step ? <><ArrowLeft />{t("common.previous")}</> : t("common.cancel")}
          </Button>
          {step < steps.length - 1 ? (
            <Button disabled={!stepValid[step]} onClick={() => setStep(step + 1)}>{t("common.next")}<ArrowRight /></Button>
          ) : (
            <Button disabled={!stepValid.every(Boolean) || create.isPending} onClick={() => create.mutate()}>
              {create.isPending ? <LoaderCircle className="animate-spin" /> : <ShieldCheck />}{t(create.isPending ? "common.creating" : "guardrailWizard.create")}
            </Button>
          )}
        </>
      )}
    >
      <CreationFlow orientation="sidebar" currentStep={step} onStepChange={setStep} progressLabel={t("guardrailWizard.title")} steps={steps}>
        {step === 0 ? (
          <WizardSection title={t("guardrailWizard.detailsTitle")} description={t("guardrailWizard.detailsDescription")}>
            <div className="grid gap-5">
              <Field label={`${t("guardrailWizard.name")} *`}><Input autoFocus className="min-h-11 bg-card" value={name} onChange={(event) => setName(event.target.value)} placeholder={t("guardrailWizard.namePlaceholder")} /></Field>
              <Field label={`${t("guardrailWizard.purpose")} *`} hint={t("guardrailWizard.purposeHint")}><Textarea className="min-h-32 bg-card" value={purpose} onChange={(event) => setPurpose(event.target.value)} placeholder={t("guardrailWizard.purposePlaceholder")} /></Field>
              <div className="flex flex-wrap items-center gap-3 rounded-xl border bg-muted/20 p-4">
                <div className="min-w-0 flex-1"><p className="text-sm font-medium">{t("guardrailWizard.intentTitle")}</p><p className="mt-1 text-xs leading-5 text-muted-foreground">{t("guardrailWizard.intentDescription")}</p></div>
                <Button variant="outline" disabled={purpose.trim().length < 20 || !intentStatusQuery.data?.available || analyzeIntent.isPending} onClick={() => analyzeIntent.mutate()}>{analyzeIntent.isPending ? <LoaderCircle className="animate-spin" /> : <Sparkles />}{t("guardrailWizard.generateBoundaries")}</Button>
              </div>
              {!intentStatusQuery.isLoading && !intentStatusQuery.data?.available ? <InfoNotice title={t("guardrailWizard.intentUnavailable")}>{t("guardrailWizard.intentUnavailableDescription")}</InfoNotice> : null}
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label={t("guardrailWizard.allowedDomains")}><Textarea className="min-h-28 bg-card" value={allowed} onChange={(event) => setAllowed(event.target.value)} placeholder={t("guardrailWizard.onePerLine")} /></Field>
                <Field label={t("guardrailWizard.restrictedDomains")}><Textarea className="min-h-28 bg-card" value={restricted} onChange={(event) => setRestricted(event.target.value)} placeholder={t("guardrailWizard.onePerLine")} /></Field>
              </div>
            </div>
          </WizardSection>
        ) : null}

        {step === 1 ? (
          <WizardSection title={t("guardrailWizard.policiesTitle")} description={t("guardrailWizard.policiesDescription")}>
            {policiesQuery.isLoading ? <Skeleton className="h-80 rounded-xl" /> : policiesQuery.error ? <ErrorNotice error={policiesQuery.error} /> : <PolicyBindingEditor policies={policies} value={bindings} onChange={setBindings} />}
          </WizardSection>
        ) : null}

        {step === 2 ? (
          <WizardSection title={t("guardrailWizard.runtimeTitle")} description={t("guardrailWizard.runtimeDescription")}>
            <div className="grid gap-5 sm:grid-cols-2">
              <Field label={t("guardrailWizard.safetyLevel")}><Select value={safetyLevel} onValueChange={(next) => setSafetyLevel(next as SafetyLevel)}><SelectTrigger className="min-h-11 bg-card"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="balanced">{t("guardrails.balanced")}</SelectItem><SelectItem value="strict">{t("guardrails.strict")}</SelectItem></SelectContent></Select></Field>
              <Field label={t("guardrailWizard.outputDelivery")}><Select value={outputDelivery} onValueChange={(next) => setOutputDelivery(next as OutputDelivery)}><SelectTrigger className="min-h-11 bg-card"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="interruptible">{t("guardrails.outputRealtime")}</SelectItem><SelectItem value="window_buffered">{t("guardrails.outputWindow")}</SelectItem><SelectItem value="full_buffered">{t("guardrails.outputFull")}</SelectItem></SelectContent></Select></Field>
            </div>
            <InfoNotice title={t("guardrailWizard.deploymentSeparateTitle")}>{t("guardrailWizard.deploymentSeparate")}</InfoNotice>
          </WizardSection>
        ) : null}

        {step === 3 ? (
          <WizardSection title={t("guardrailWizard.reviewTitle")} description={t("guardrailWizard.reviewDescription")}>
            <section className="overflow-hidden rounded-xl border bg-card">
              <ReviewRow label={t("guardrailWizard.name")} value={name} />
              <ReviewRow label={t("guardrailWizard.purpose")} value={purpose} />
              <ReviewRow label={t("guardrailWizard.policies")} value={bindings.map((binding) => policies.find((policy) => policy.id === binding.policy_id)?.name ?? binding.policy_id).join(", ")} />
              <ReviewRow label={t("guardrailWizard.policyRules")} value={String(bindings.reduce((total, binding) => total + binding.enabled_rule_ids.length, 0))} />
              <ReviewRow label={t("guardrailWizard.runtimeProfile")} value={preview.data ? `${preview.data.engine} · Colang ${preview.data.colang_version}` : t("guardrailWizard.compilingPreview")} mono />
              <ReviewRow label={t("guardrailWizard.compilationChecksum")} value={preview.data?.checksum ?? "—"} mono />
            </section>
            {preview.isPending ? <div className="mt-4 flex items-center gap-2 text-sm text-muted-foreground"><LoaderCircle className="size-4 animate-spin" />{t("guardrailWizard.compilingPreview")}</div> : null}
            {preview.error ? <div className="mt-4"><ErrorNotice error={preview.error} /></div> : null}
            {preview.data ? <div className="mt-4 flex flex-wrap gap-2"><Badge variant="outline"><Braces />{preview.data.rails.length} Rails</Badge><Badge variant="outline">{preview.data.actions.length} Actions</Badge><Badge variant="outline">{preview.data.estimated_critical_path_ms} ms</Badge><Badge variant="outline"><Check />{t("guardrailWizard.compileReady")}</Badge></div> : null}
          </WizardSection>
        ) : null}
      </CreationFlow>
    </EntitySheet>
  );
}

function bindingsValid(bindings: GuardrailPolicyBinding[], policies: Policy[]) {
  if (!bindings.length) return false;
  return bindings.every((binding) => {
    const policy = policies.find((item) => item.id === binding.policy_id);
    if (!policy || !binding.enabled_rule_ids.length) return false;
    if (policy.parameters.some((parameter) => parameter.required && !(binding.parameter_values[parameter.name] ?? parameter.default ?? "").trim())) return false;
    if (binding.policy_id === "builtin-automated-reasoning") return Boolean(binding.reasoning_policy?.policy_id.trim() && binding.reasoning_policy.policy_version.trim());
    return true;
  });
}

function WizardSection({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return <section><header className="mb-5"><h3 className="text-lg font-semibold">{title}</h3><p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">{description}</p></header>{children}</section>;
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return <label className="grid gap-2"><Label>{label}</Label>{children}{hint ? <span className="text-xs leading-5 text-muted-foreground">{hint}</span> : null}</label>;
}

function ReviewRow({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return <div className="grid gap-1 border-b p-4 last:border-b-0 sm:grid-cols-[12rem_minmax(0,1fr)]"><span className="text-xs text-muted-foreground">{label}</span><strong className={mono ? "break-all font-mono text-xs font-medium" : "text-sm font-medium"}>{value || "—"}</strong></div>;
}

function lines(value: string) { return value.split("\n").map((item) => item.trim()).filter(Boolean); }
function notifyError(error: unknown, fallback: string) { toast.error(error instanceof Error ? error.message : fallback); }
