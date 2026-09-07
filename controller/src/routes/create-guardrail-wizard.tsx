import { useEffect, useId, useMemo, useState, type ReactNode } from "react";
import { boundPolicy } from "@/lib/bound-policy";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowRight,
  Braces,
  Check,
  CircleAlert,
  FileText,
  LoaderCircle,
  MessageSquareText,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { ComplianceDocumentImport } from "@/components/compliance-document-import";
import { CreationFlow } from "@/components/creation-flow";
import { EntitySheet } from "@/components/entity-sheet";
import { defaultPolicyBinding, getPolicyBindingValidation } from "@/components/policy-binding-editor";
import { ProtectionDirectoryEditor, ProtectionOrderEditor, ProtectionPresetPicker } from "@/components/protection-workspace";
import { ProtectionDependencies } from "@/components/protection-dependencies";
import { protectionDirectories } from "../../shared/protection-map";
import { completeResponsePolicies, mergeDirectoryBindings, mergePresetBindings, policyDirectory } from "@/lib/protection-composition";
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
import { policyRequiresTopicAllowlist } from "@/lib/protection-requirements";
import {
  analyzeGuardrailIntent,
  createGuardrail,
  getIntentAnalysisStatus,
  getPolicies,
  getProtectionPresets,
  previewGuardrailCandidate,
  type ComplianceDocumentAnalysis,
  type GuardrailPolicyBinding,
  type IntentAnalysis,
  type OutputDelivery,
  type Policy,
} from "@/lib/api";

const EMPTY_POLICIES: Policy[] = [];
const DELIVERY_STEP = protectionDirectories.length + 1;
const REVIEW_STEP = DELIVERY_STEP + 1;
type PolicyWorkspace = "main" | "intent" | "documents";
type BoundarySource = "intent" | "documents" | null;

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
  const presetsQuery = useQuery({ queryKey: queryKeys.protectionPresets, queryFn: getProtectionPresets, enabled: open, retry: false });
  const intentStatusQuery = useQuery({ queryKey: queryKeys.intentAnalysisStatus, queryFn: getIntentAnalysisStatus, enabled: open, retry: false });
  const policies = policiesQuery.data?.items ?? EMPTY_POLICIES;
  const [step, setStep] = useState(0);
  const [policyWorkspace, setPolicyWorkspace] = useState<PolicyWorkspace>("main");
  const [name, setName] = useState("");
  const [selectedPreset, setSelectedPreset] = useState("blank");
  const [presetFeedback, setPresetFeedback] = useState("");
  const [intentText, setIntentText] = useState("");
  const [intentProposal, setIntentProposal] = useState<IntentAnalysis | null>(null);
  const [allowed, setAllowed] = useState("");
  const [boundarySource, setBoundarySource] = useState<BoundarySource>(null);
  const [bindings, setBindings] = useState<GuardrailPolicyBinding[]>([]);
  const [outputDelivery, setOutputDelivery] = useState<OutputDelivery>("window_buffered");
  const [showBoundaries, setShowBoundaries] = useState(false);
  const [documentImportReset, setDocumentImportReset] = useState(0);
  const nextBlockedReasonId = useId();

  const directory = protectionDirectories[step - 1];
  const directoryPolicies = directory ? policies.filter((policy) => policyDirectory(policy) === directory.id) : [];
  const directoryIds = new Set(directoryPolicies.map((policy) => policy.id));
  const directoryBindings = bindings.filter((binding) => directoryIds.has(binding.policy_id));
  const steps = [
    { label: t("protection.start"), description: t("protection.startDescription") },
    ...protectionDirectories.map((item) => {
      const selected = bindings.filter((binding) => policies.some((policy) => policy.id === binding.policy_id && policyDirectory(policy) === item.id));
      const needsSetup = selected.length > 0 && getPolicyBindingsBlocker(selected, policies, allowed);
      return { label: t(`protection.directories.${item.id}`), description: t(needsSetup ? "protection.needsSetup" : selected.length ? "protection.selected" : "protection.optional", { count: selected.length }) };
    }),
    { label: t("protection.delivery"), description: t("protection.order") },
    { label: t("protection.review"), description: t("guardrailWizard.steps.reviewDescription") },
  ];

  useEffect(() => {
    if (!open) return;
    setStep(0);
    setPolicyWorkspace("main");
    setName("");
    setSelectedPreset("blank");
    setPresetFeedback("");
    setShowBoundaries(false);
    setIntentText("");
    setIntentProposal(null);
    setAllowed("");
    setBoundarySource(null);
    setBindings([]);
    setOutputDelivery("window_buffered");
    setDocumentImportReset((current) => current + 1);
  }, [open]);

  const language = user?.preferred_language ?? (i18n.language.toLowerCase().startsWith("zh") ? "zh-CN" : "en");
  const analyzeIntent = useMutation({
    mutationFn: () => analyzeGuardrailIntent({ purpose: intentText.trim(), language }),
    onSuccess: (analysis) => setIntentProposal(analysis),
    onError: (error) => notifyError(error, t("guardrailWizard.operationFailed")),
  });

  const fullResponsePolicies = completeResponsePolicies(bindings, policies);
  const effectiveDelivery = fullResponsePolicies.length ? "full_buffered" : outputDelivery;

  const payload = useMemo(() => ({
    name: name.trim(),
    allowed_topics: lines(allowed),
    policy_bindings: bindings,
    safety_level: "balanced" as const,
    output_delivery: effectiveDelivery,
  }), [allowed, bindings, name, effectiveDelivery]);

  const preview = useQuery({
    queryKey: ["guardrail-candidate-preview", payload],
    queryFn: () => previewGuardrailCandidate(payload),
    enabled: open && step === REVIEW_STEP && Boolean(name.trim()) && bindingsValid(bindings, policies, allowed),
    retry: false,
  });

  const create = useMutation({
    mutationFn: () => createGuardrail(payload),
    // Creation is an explicit write, not a queued offline task. Surface a
    // network failure now rather than silently submitting after reconnection.
    networkMode: "always",
    retry: false,
    onSuccess: (guardrail) => {
      toast.success(t("guardrailWizard.created", { name: guardrail.name }));
      onCreated(guardrail.id);
    },
    // The persistent footer owns this error; a second toast obscures the
    // sheet heading on narrow screens and disappears before recovery.
  });
  const resetCreate = create.reset;
  useEffect(() => { if (open) resetCreate(); }, [open, resetCreate]);

  function addPolicies(policyIds: string[]) {
    setBindings((current) => {
      const selected = new Set(current.map((binding) => binding.policy_id));
      const additions = [...new Set(policyIds)]
        .map((id) => policies.find((policy) => policy.id === id))
        .filter(isBindablePolicy)
        .filter((policy) => !selected.has(policy.id))
        .map(defaultPolicyBinding);
      return [...current, ...additions];
    });
  }

  function applyIntentProposal() {
    if (!intentProposal) return;
    setAllowed(intentProposal.allowed_topics.join("\n"));
    setBoundarySource("intent");
    const topicPolicy = recommendedTopicPolicy(policies);
    if (topicPolicy) addPolicies([topicPolicy.id]);
    setPolicyWorkspace("main");
    toast.success(t("guardrailWizard.intentGenerated"));
  }

  function applyDocumentAnalysis(analysis: ComplianceDocumentAnalysis) {
    setAllowed(analysis.allowed_topics.join("\n"));
    setBoundarySource("documents");
    addPolicies(analysis.recommended_policy_ids);
    setPolicyWorkspace("main");
    toast.success(t("guardrailWizard.documentAppliedMessage"));
  }

  function changeStep(next: number) {
    setPolicyWorkspace("main");
    setStep(next);
  }

  const hasOutputPolicy = bindings.some((binding) => binding.enabled_rails.includes("output"));
  const policyBlocker = getPolicyBindingsBlocker(bindings, policies, allowed);
  const policyBlockedReason = policyBlocker ? t(policyBlocker.key, policyBlocker.values) : null;
  const localBlocker = directoryBindings.length ? getPolicyBindingsBlocker(directoryBindings, policies, allowed) : null;
  const nextBlockedReason = step === 0 && !name.trim()
    ? t("guardrailWizard.nextBlocked.name")
    : directory && localBlocker ? t(localBlocker.key, localBlocker.values)
    : step === REVIEW_STEP ? !name.trim() ? t("protection.missingName") : policyBlockedReason : null;
  const inPolicyWorkspace = directory?.id === "business_topics" && policyWorkspace !== "main";
  const canCreate = Boolean(name.trim() && !policyBlockedReason && preview.data && !preview.error && !preview.isFetching);

  return (
    <EntitySheet
      open={open}
      onOpenChange={onOpenChange}
      eyebrow={t("guardrailWizard.eyebrow")}
      title={t("guardrailWizard.title")}
      description={t("guardrailWizard.description")}
      width="workflow"
      bodyClassName="overflow-hidden p-0 sm:p-0"
      footer={inPolicyWorkspace ? (
        <Button className="mr-auto" variant="outline" onClick={() => setPolicyWorkspace("main")}>
          <ArrowLeft />{t("guardrailWizard.backToPolicies")}
        </Button>
      ) : (
        <div className="w-full space-y-3">
          {create.error ? <div className="space-y-2 [overflow-wrap:anywhere]">
            <ErrorNotice error={create.error} />
            <p className="text-xs leading-5 text-muted-foreground">{t("protection.createRecovery")}</p>
          </div> : null}
        <div className="flex w-full flex-col gap-3 sm:flex-row sm:items-center">
          {nextBlockedReason ? (
            <p id={nextBlockedReasonId} role="status" className="mr-auto flex min-w-0 flex-1 items-start gap-2 text-left text-xs leading-5 text-amber-800">
              <CircleAlert className="mt-0.5 size-4 shrink-0" />
              <span>{nextBlockedReason}</span>
            </p>
          ) : null}
          <div className="ml-auto flex shrink-0 items-center gap-2">
            <Button variant="outline" onClick={() => step ? changeStep(step - 1) : onOpenChange(false)}>
              {step ? <><ArrowLeft />{t("common.previous")}</> : t("common.cancel")}
            </Button>
            {step < steps.length - 1 ? (
              <Button
                aria-describedby={nextBlockedReason ? nextBlockedReasonId : undefined}
                disabled={Boolean(nextBlockedReason)}
                title={nextBlockedReason ?? undefined}
                onClick={() => changeStep(step + 1)}
              >
                {t(directory && !directoryBindings.length ? "protection.skip" : "common.next")}<ArrowRight />
              </Button>
            ) : (
              <Button disabled={!canCreate || create.isPending} onClick={() => create.mutate()}>
                {create.isPending ? <LoaderCircle className="animate-spin" /> : <ShieldCheck />}
                {t(create.isPending ? "guardrailWizard.creatingDraft" : "guardrailWizard.createDraft")}
              </Button>
            )}
          </div>
        </div>
        </div>
      )}
    >
      <CreationFlow orientation="sidebar" freelyNavigable contained currentStep={step} onStepChange={changeStep} progressLabel={t("protection.overview")} steps={steps}>
        {step === 0 ? (
          <WizardSection title={t("protection.startTitle")} description={t("protection.startHint")}>
            <div className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-5">
              <Field label={`${t("guardrailWizard.name")} *`}>
                <Input autoFocus className="min-h-11 bg-card" value={name} onChange={(event) => setName(event.target.value)} placeholder={t("guardrailWizard.namePlaceholder")} />
              </Field>
              <InfoNotice title={t("guardrailWizard.draftOnlyTitle")}>{t("guardrailWizard.draftOnlyDescription")}</InfoNotice>
              {presetsQuery.isLoading ? <Skeleton className="h-32" /> : presetsQuery.error ? <div className="space-y-2"><p className="text-sm text-muted-foreground">{t("protection.presetUnavailable")}</p><Button variant="outline" onClick={() => void presetsQuery.refetch()}>{t("common.retry")}</Button></div> : (
                <ProtectionPresetPicker presets={presetsQuery.data?.items ?? []} policies={policies} selected={selectedPreset} onSelect={setSelectedPreset}
                  onApply={(preset) => {
                    const next = mergePresetBindings(bindings, preset.bindings);
                    setBindings(next);
                    setPresetFeedback(t("protection.applied", { count: next.length }));
                  }} />
              )}
              {presetFeedback ? <p role="status" className="text-sm font-medium text-primary">{presetFeedback}</p> : null}
            </div>
          </WizardSection>
        ) : null}

        {directory && policyWorkspace === "main" ? (
          <WizardSection title={t(`protection.directories.${directory.id}`)} description={t("protection.directoryHint")}>
            <div className="space-y-6">
              {directory.id === "business_topics" ? <section className="rounded-xl border bg-muted/15 p-4">
                <header className="mb-4">
                  <h4 className="text-sm font-semibold">{t("guardrailWizard.policyAssistantTitle")}</h4>
                  <p className="mt-1 text-xs leading-5 text-muted-foreground">{t("guardrailWizard.policyAssistantDescription")}</p>
                </header>
                <div className="grid gap-3 sm:grid-cols-2">
                  <PolicyChoiceCard
                    icon={<MessageSquareText />}
                    title={t("guardrailWizard.generateFromIntent")}
                    description={t("guardrailWizard.generateFromIntentDescription")}
                    disabled={!intentStatusQuery.data?.available}
                    onClick={() => setPolicyWorkspace("intent")}
                  />
                  <PolicyChoiceCard
                    icon={<FileText />}
                    title={t("guardrailWizard.generateFromDocuments")}
                    description={t("guardrailWizard.generateFromDocumentsDescription")}
                    disabled={!intentStatusQuery.data?.document_analysis_available}
                    onClick={() => setPolicyWorkspace("documents")}
                  />
                </div>
                {!intentStatusQuery.isLoading && !intentStatusQuery.data?.available ? (
                  <p className="mt-3 text-xs leading-5 text-muted-foreground">{t("guardrailWizard.policyAssistantUnavailable")}</p>
                ) : null}
              </section> : null}

              {hasTopicControlBinding(directoryBindings, policies) || (directory.id === "business_topics" && (showBoundaries || boundarySource || allowed.trim())) ? (
                <TopicBoundaryEditor
                  allowed={allowed}
                  source={boundarySource}
                  onAllowedChange={setAllowed}
                />
              ) : directory.id === "business_topics" ? <Button variant="outline" onClick={() => setShowBoundaries(true)}>{t("guardrailWizard.addBoundaries")}</Button> : null}

              {policiesQuery.isLoading ? <Skeleton className="h-80 rounded-xl" /> : policiesQuery.error ? <ErrorNotice error={policiesQuery.error} /> : (
                <><ProtectionDirectoryEditor directory={directory.id} policies={policies} bindings={directoryBindings} onChange={(next) => setBindings((current) => mergeDirectoryBindings(current, directoryIds, next))} /><ProtectionDependencies bindings={directoryBindings} policies={policies} /></>
              )}

            </div>
          </WizardSection>
        ) : null}

        {directory?.id === "business_topics" && policyWorkspace === "intent" ? (
          <IntentPolicyWorkspace
            available={Boolean(intentStatusQuery.data?.available)}
            intent={intentText}
            proposal={intentProposal}
            pending={analyzeIntent.isPending}
            error={analyzeIntent.error}
            onIntentChange={(value) => {
              setIntentText(value);
              setIntentProposal(null);
              analyzeIntent.reset();
            }}
            onAnalyze={() => analyzeIntent.mutate()}
            onApply={applyIntentProposal}
          />
        ) : null}

        {directory?.id === "business_topics" && policyWorkspace === "documents" ? (
          <ComplianceDocumentImport
            available={Boolean(intentStatusQuery.data?.document_analysis_available)}
            analystProvider={intentStatusQuery.data?.provider}
            analystModel={intentStatusQuery.data?.model}
            language={language}
            policies={policies}
            resetKey={documentImportReset}
            onApply={applyDocumentAnalysis}
          />
        ) : null}

        {step === DELIVERY_STEP ? (
          <WizardSection title={t("protection.delivery")} description={t("protection.deliveryHint")}>
            <div className="space-y-5">
              {hasOutputPolicy ? <OutputDeliveryField value={effectiveDelivery} onChange={setOutputDelivery} requiredComplete={fullResponsePolicies} /> : <InfoNotice title={t("protection.output")}>{t("protection.noOutput")}</InfoNotice>}
              {fullResponsePolicies.length ? <InfoNotice title={t("protection.completeResponse")}>
                {t("protection.bufferSummary", { count: fullResponsePolicies.length })}
                <details className="mt-2"><summary className="min-h-11 cursor-pointer rounded-sm py-3 font-medium outline-none focus-visible:ring-2 focus-visible:ring-ring">{t("protection.included")}</summary><ul className="mt-2 list-disc space-y-1 pl-4">{fullResponsePolicies.map((policy) => <li key={policy}>{policy}</li>)}</ul></details>
              </InfoNotice> : hasOutputPolicy && effectiveDelivery !== "full_buffered" ? <InfoNotice title={t("protection.effectiveDelivery")}>{t("protection.incrementalHint")}</InfoNotice> : null}
              <ProtectionOrderEditor bindings={bindings} policies={policies} onChange={setBindings} />
            </div>
          </WizardSection>
        ) : null}

        {step === REVIEW_STEP ? (
          <WizardSection title={t("guardrailWizard.reviewTitle")} description={t("guardrailWizard.reviewDescription")}>
            <InfoNotice title={t("guardrailWizard.reviewDraftTitle")}>{t("guardrailWizard.reviewDraftDescription")}</InfoNotice>
            <section className="mt-4 overflow-hidden rounded-xl border bg-card">
              <ReviewRow label={t("guardrailWizard.name")} value={name} />
              <ReviewRow label={t("guardrailWizard.policies")} value={t("protection.selected", { count: bindings.length })} />
              <ReviewRow label={t("guardrailWizard.policyRules")} value={String(bindings.reduce((total, binding) => total + binding.enabled_rule_ids.length, 0))} />
              {boundarySource || allowed.trim() ? <ReviewRow label={t("guardrailWizard.topicControl")} value={t("guardrailWizard.topicControlSummary", { allowed: lines(allowed).length })} /> : null}
              {hasOutputPolicy ? <ReviewRow label={t("protection.effectiveDelivery")} value={t(`guardrailWizard.outputDeliveryOptions.${effectiveDelivery}`)} /> : null}
            </section>

            <section className="mt-4 divide-y overflow-hidden rounded-xl border bg-card">
              {protectionDirectories.map((item, index) => {
                const selected = bindings.filter((binding) => policies.some((policy) => policy.id === binding.policy_id && policyDirectory(policy) === item.id));
                return <button key={item.id} type="button" className="flex min-h-12 w-full items-center justify-between gap-3 px-4 py-3 text-left text-sm hover:bg-muted/40 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring" onClick={() => changeStep(index + 1)}>
                  <span>{t(`protection.directories.${item.id}`)}</span><span className="text-muted-foreground">{selected.length ? t("protection.selected", { count: selected.length }) : t("protection.unset")}</span>
                </button>;
              })}
            </section>
            <p className="mt-4 text-sm leading-6 text-muted-foreground">{t("protection.selectedNotValidated")}</p>
            <div className="mt-4"><ProtectionDependencies bindings={bindings} policies={policies} /></div>
            {!hasOutputPolicy ? <p className="mt-3 text-sm text-amber-800">{t("protection.noOutput")}</p> : null}
            {!bindings.some((binding) => binding.enabled_rails.includes("input")) ? <p className="mt-3 text-sm text-amber-800">{t("protection.noInput")}</p> : null}

            {preview.isFetching ? <div className="mt-4 flex items-center gap-2 text-sm text-muted-foreground"><LoaderCircle className="size-4 animate-spin" />{t("guardrailWizard.validatingPlan")}</div> : null}
            {preview.error ? <div className="mt-4 space-y-3"><ErrorNotice error={preview.error} /><Button className="min-h-11" variant="outline" onClick={() => void preview.refetch()}>{t("protection.retryPreview")}</Button></div> : null}
            {preview.data ? (
              <details className="mt-4 overflow-hidden rounded-xl border bg-card">
                <summary className="min-h-11 cursor-pointer list-none px-4 py-3 text-sm font-medium outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring [&::-webkit-details-marker]:hidden">
                  {t("guardrailWizard.advancedRuntimePreview")}
                </summary>
                <div className="border-t">
                  <ReviewRow label={t("guardrailWizard.runtimeProfile")} value={`${preview.data.engine} · Colang ${preview.data.colang_version}`} mono />
                  <ReviewRow label={t("guardrailWizard.planIdentity")} value={preview.data.checksum} mono />
                  <div className="flex flex-wrap gap-2 p-4">
                    <Badge variant="outline"><Braces />{preview.data.rails.length} Rails</Badge>
                    <Badge variant="outline">{preview.data.actions.length} Actions</Badge>
                    <Badge variant="outline">{preview.data.estimated_critical_path_ms} ms</Badge>
                    <Badge variant="outline"><Check />{t("guardrailWizard.planReady")}</Badge>
                  </div>
                </div>
              </details>
            ) : null}
          </WizardSection>
        ) : null}
      </CreationFlow>
    </EntitySheet>
  );
}

function IntentPolicyWorkspace({
  available,
  intent,
  proposal,
  pending,
  error,
  onIntentChange,
  onAnalyze,
  onApply,
}: {
  available: boolean;
  intent: string;
  proposal: IntentAnalysis | null;
  pending: boolean;
  error: unknown;
  onIntentChange: (value: string) => void;
  onAnalyze: () => void;
  onApply: () => void;
}) {
  const { t } = useTranslation();
  return (
    <WizardSection title={t("guardrailWizard.intentWorkspaceTitle")} description={t("guardrailWizard.intentWorkspaceDescription")}>
      <div className="space-y-4">
        {!available ? <InfoNotice title={t("guardrailWizard.intentUnavailable")}>{t("guardrailWizard.intentUnavailableDescription")}</InfoNotice> : null}
        <Field label={t("guardrailWizard.intentInputLabel")} hint={t("guardrailWizard.intentInputHint")}>
          <Textarea
            autoFocus
            className="min-h-40 bg-card"
            disabled={!available || pending}
            value={intent}
            onChange={(event) => onIntentChange(event.target.value)}
            placeholder={t("guardrailWizard.intentInputPlaceholder")}
          />
        </Field>
        {error ? <ErrorNotice error={error} /> : null}
        {!proposal ? (
          <div className="flex justify-end">
            <Button disabled={!available || intent.trim().length < 20 || pending} onClick={onAnalyze}>
              {pending ? <LoaderCircle className="animate-spin" /> : <Sparkles />}
              {t(pending ? "guardrailWizard.intentAnalyzing" : "guardrailWizard.intentAnalyze")}
            </Button>
          </div>
        ) : (
          <section className="overflow-hidden rounded-xl border bg-card" aria-live="polite">
            <header className="flex items-start justify-between gap-3 border-b bg-muted/20 p-4">
              <div>
                <h4 className="text-sm font-semibold">{t("guardrailWizard.intentProposalTitle")}</h4>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">{t("guardrailWizard.intentProposalDescription")}</p>
              </div>
              <Badge variant="outline"><Sparkles />{t("guardrailWizard.aiProposal")}</Badge>
            </header>
            <div className="space-y-4 p-4">
              <p className="text-sm leading-6">{proposal.summary}</p>
              {proposal.structured_purpose ? <div className="rounded-lg border">
                <ReviewRow label={t("guardrailWizard.purposeAudience")} value={proposal.structured_purpose.audience} />
                <ReviewRow label={t("guardrailWizard.purposeTasks")} value={proposal.structured_purpose.tasks} />
                <ReviewRow label={t("guardrailWizard.purposeProtect")} value={proposal.structured_purpose.protect} />
                <ReviewRow label={t("guardrailWizard.purposeOutOfScope")} value={proposal.structured_purpose.out_of_scope} />
              </div> : null}
              <BoundaryPreview label={t("guardrailWizard.allowedDomains")} values={proposal.allowed_topics} />
              {proposal.review_notes.length ? <InfoNotice title={t("guardrailWizard.documentReviewNotes")}>{proposal.review_notes.join(" · ")}</InfoNotice> : null}
              <div className="flex flex-col gap-2 border-t pt-4 sm:flex-row sm:items-center sm:justify-between">
                <p className="text-xs leading-5 text-muted-foreground">{t("guardrailWizard.intentApplyDescription")}</p>
                <Button onClick={onApply}><Check />{t("guardrailWizard.applyProposal")}</Button>
              </div>
            </div>
          </section>
        )}
      </div>
    </WizardSection>
  );
}

function TopicBoundaryEditor({
  allowed,
  source,
  onAllowedChange,
}: {
  allowed: string;
  source: BoundarySource;
  onAllowedChange: (value: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <section className="rounded-xl border bg-card p-4">
      <header className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h4 className="text-sm font-semibold">{t("guardrailWizard.topicControl")}</h4>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">{t("guardrailWizard.topicControlDescription")}</p>
        </div>
        {source ? <Badge variant="secondary"><Sparkles />{t(`guardrailWizard.boundarySources.${source}`)}</Badge> : null}
      </header>
      <Field label={t("guardrailWizard.allowedDomains")} hint={t("guardrailWizard.topicAllowlistHint")}><Textarea aria-label={t("guardrailWizard.allowedDomains")} className="min-h-32 bg-card" value={allowed} onChange={(event) => onAllowedChange(event.target.value)} placeholder={t("guardrailWizard.onePerLine")} /></Field>
    </section>
  );
}

function OutputDeliveryField({ value, onChange, requiredComplete = [] }: { value: OutputDelivery; onChange: (value: OutputDelivery) => void; requiredComplete?: string[] }) {
  const { t } = useTranslation();
  const id = useId();
  return (
    <section className="rounded-xl border bg-card p-4">
      <Label htmlFor={id}>{t("guardrailWizard.outputDelivery")}</Label>
      <p className="mt-1 text-xs leading-5 text-muted-foreground">{t("guardrailWizard.outputDeliveryConditionalDescription")}</p>
      <Select value={value} disabled={requiredComplete.length > 0} onValueChange={(next) => onChange(next as OutputDelivery)}>
        <SelectTrigger id={id} aria-describedby={`${id}-description`} className="mt-3 min-h-11 bg-card"><SelectValue /></SelectTrigger>
        <SelectContent>
          <SelectItem value="interruptible">{t("guardrailWizard.outputDeliveryOptions.interruptible")}</SelectItem>
          <SelectItem value="window_buffered">{t("guardrailWizard.outputDeliveryOptions.window_buffered")}</SelectItem>
          <SelectItem value="full_buffered">{t("guardrailWizard.outputDeliveryOptions.full_buffered")}</SelectItem>
        </SelectContent>
      </Select>
      <p id={`${id}-description`} aria-live="polite" className="mt-2 text-xs leading-5 text-muted-foreground">
        {t(`guardrailWizard.outputDeliveryDescriptions.${value}`)}
        {requiredComplete.length > 0 ? <span className="sr-only"> {t("protection.bufferReason", { policies: requiredComplete.join(", ") })}</span> : null}
      </p>
    </section>
  );
}

function PolicyChoiceCard({ icon, title, description, disabled, onClick }: { icon: ReactNode; title: string; description: string; disabled: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      disabled={disabled}
      className="group flex min-h-28 items-start gap-3 rounded-xl border bg-card p-4 text-left transition-colors hover:border-primary/50 hover:bg-primary/[0.03] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
      onClick={onClick}
    >
      <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary [&_svg]:size-4">{icon}</span>
      <span className="min-w-0">
        <strong className="block text-sm font-semibold">{title}</strong>
        <span className="mt-1 block text-xs leading-5 text-muted-foreground">{description}</span>
      </span>
      <ArrowRight className="ml-auto mt-1 size-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
    </button>
  );
}

function BoundaryPreview({ label, values }: { label: string; values: string[] }) {
  return (
    <div>
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <div className="mt-2 flex flex-wrap gap-2">{values.map((value) => <Badge key={value} variant="secondary">{value}</Badge>)}</div>
    </div>
  );
}

function recommendedTopicPolicy(policies: Policy[]) {
  const preferred = ["builtin-topic-safety", "builtin-company-policy"];
  for (const id of preferred) {
    const policy = policies.find((item) => item.id === id);
    if (policy && isBindablePolicy(policy)) return policy;
  }
  return undefined;
}

function isBindablePolicy(policy: Policy | undefined): policy is Policy {
  return Boolean(policy && (policy.source === "built_in" || policy.version !== "0"));
}

function getPolicyBindingsBlocker(bindings: GuardrailPolicyBinding[], policies: Policy[], allowedTopics: string) {
  if (!bindings.length) return { key: "guardrailWizard.nextBlocked.selectPolicy" };
  for (const binding of bindings) {
    const policy = boundPolicy(policies, binding);
    if (!policy) return { key: "guardrailWizard.nextBlocked.policyUnavailable", values: { name: `${binding.policy_id}@${binding.policy_version}` } };
    const validation = getPolicyBindingValidation(binding, policy);
    if (validation.missingRails) return { key: "protection.selectDirection" };
    if (validation.missingRules) return { key: "guardrailWizard.nextBlocked.enableRules", values: { name: policy.name } };
    if (validation.missingRequiredParameters.length) {
      return {
        key: "guardrailWizard.nextBlocked.requiredFields",
        values: {
          name: policy.name,
          fields: validation.missingRequiredParameters.map((parameter) => parameter.label ?? parameter.name).join(", "),
        },
      };
    }
    if (validation.missingReasoningPolicy) return { key: "guardrailWizard.nextBlocked.reasoningPolicy", values: { name: policy.name } };
  }
  if (hasTopicControlBinding(bindings, policies) && !lines(allowedTopics).length) {
    return { key: "guardrailWizard.nextBlocked.allowedTopics" };
  }
  return null;
}

function bindingsValid(bindings: GuardrailPolicyBinding[], policies: Policy[], allowedTopics: string) {
  return !getPolicyBindingsBlocker(bindings, policies, allowedTopics);
}

function hasTopicControlBinding(bindings: GuardrailPolicyBinding[], policies: Policy[]): boolean {
  return bindings.some((binding) => policyRequiresTopicAllowlist(boundPolicy(policies, binding) ?? { id: binding.policy_id }));
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
