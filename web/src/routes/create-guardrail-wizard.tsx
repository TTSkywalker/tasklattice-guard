import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowRight,
  Braces,
  Check,
  ChevronDown,
  FilePlus2,
  LibraryBig,
  LoaderCircle,
  Plus,
  Search,
  ShieldCheck,
  Sparkles,
  Trash2,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { CreationFlow } from "@/components/creation-flow";
import { EntitySheet } from "@/components/entity-sheet";
import { ErrorNotice, InfoNotice } from "@/components/product-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { queryKeys } from "@/features/query-keys";
import { useAuth } from "@/lib/auth";
import {
  analyzeGuardrailIntent,
  createGuardrail,
  getControlTemplates,
  getIntentAnalysisStatus,
  type ControlTemplate,
  type GuardrailControl,
  type GuardrailControlConfig,
  type GuardrailRuleConfig,
  type OutputDelivery,
  type SafetyLevel,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const INTENT_CONTROL_ID = "custom:intent-boundary";

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
  const templatesQuery = useQuery({ queryKey: queryKeys.controlTemplates, queryFn: getControlTemplates, enabled: open });
  const intentStatusQuery = useQuery({ queryKey: queryKeys.intentAnalysisStatus, queryFn: getIntentAnalysisStatus, enabled: open, retry: false });
  const templates = templatesQuery.data?.items ?? [];
  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [purpose, setPurpose] = useState("");
  const [allowed, setAllowed] = useState("");
  const [restricted, setRestricted] = useState("");
  const [configurations, setConfigurations] = useState<GuardrailControlConfig[]>([]);
  const [activeControlId, setActiveControlId] = useState("");
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [manualOpen, setManualOpen] = useState(false);
  const [safetyLevel, setSafetyLevel] = useState<SafetyLevel>("balanced");
  const [outputDelivery, setOutputDelivery] = useState<OutputDelivery>("window_buffered");

  const steps = [
    { label: t("guardrailWizard.steps.details"), description: t("guardrailWizard.steps.detailsDescription") },
    { label: t("guardrailWizard.steps.controls"), description: t("guardrailWizard.steps.controlsDescription") },
    { label: t("guardrailWizard.steps.rules"), description: t("guardrailWizard.steps.rulesDescription") },
    { label: t("guardrailWizard.steps.behavior"), description: t("guardrailWizard.steps.behaviorDescription") },
    { label: t("guardrailWizard.steps.review"), description: t("guardrailWizard.steps.reviewDescription") },
  ];

  useEffect(() => {
    if (!open) return;
    setStep(0);
    setName("");
    setPurpose("");
    setAllowed("");
    setRestricted("");
    setConfigurations([]);
    setActiveControlId("");
    setLibraryOpen(false);
    setManualOpen(false);
    setSafetyLevel("balanced");
    setOutputDelivery("window_buffered");
  }, [open]);

  useEffect(() => {
    if (!configurations.some((item) => item.id === activeControlId)) {
      setActiveControlId(configurations[0]?.id ?? "");
    }
  }, [activeControlId, configurations]);

  const profileLanguage = user?.preferred_language ?? (i18n.language.toLowerCase().startsWith("zh") ? "zh-CN" : "en");
  const analyzeIntent = useMutation({
    mutationFn: () => analyzeGuardrailIntent({ purpose: purpose.trim(), language: profileLanguage }),
    onSuccess: (analysis) => {
      setAllowed(analysis.allowed_topics.join("\n"));
      setRestricted(analysis.restricted_topics.join("\n"));
      setConfigurations((current) => [
        ...current.filter((item) => item.id !== INTENT_CONTROL_ID),
        intentControl(t, analysis.summary),
      ]);
      setActiveControlId(INTENT_CONTROL_ID);
      toast.success(t("guardrailWizard.intentGenerated"));
    },
    onError: (error) => notifyError(error, t("guardrailWizard.operationFailed")),
  });

  const createMutation = useMutation({
    mutationFn: () => createGuardrail({
      name: name.trim(),
      purpose: purpose.trim(),
      allowed_topics: lines(allowed),
      restricted_topics: lines(restricted),
      controls: runtimeControls(configurations),
      control_configurations: configurations,
      safety_level: safetyLevel,
      output_delivery: outputDelivery,
    }),
    onSuccess: (guardrail) => {
      toast.success(t("guardrailWizard.created", { name: guardrail.name }));
      onCreated(guardrail.id);
    },
    onError: (error) => notifyError(error, t("guardrailWizard.operationFailed")),
  });

  const enabledRules = configurations.flatMap((item) => item.rules).filter((rule) => rule.enabled);
  const intentBoundariesValid = !configurations.some((item) => item.id === INTENT_CONTROL_ID) || (lines(allowed).length > 0 && lines(restricted).length > 0);
  const stepValid = [
    Boolean(name.trim() && purpose.trim()),
    configurations.length > 0 && intentBoundariesValid,
    configurations.length > 0 && configurations.every((item) => item.rules.some((rule) => rule.enabled) && item.rules.every(ruleReady)),
    true,
    true,
  ];

  return (
    <>
      <EntitySheet
        open={open}
        onOpenChange={onOpenChange}
        eyebrow={t("guardrailWizard.eyebrow")}
        title={t("guardrailWizard.title")}
        description={t("guardrailWizard.description")}
        width="xl"
        bodyClassName="p-0 sm:p-0"
        footer={
          <>
            <Button variant="outline" onClick={() => step ? setStep(step - 1) : onOpenChange(false)}>
              {step ? <><ArrowLeft />{t("common.previous")}</> : t("common.cancel")}
            </Button>
            {step < steps.length - 1 ? (
              <Button disabled={!stepValid[step]} onClick={() => setStep(step + 1)}>
                {t("common.next")}<ArrowRight />
              </Button>
            ) : (
              <Button disabled={!stepValid.every(Boolean) || createMutation.isPending} onClick={() => createMutation.mutate()}>
                {createMutation.isPending ? <LoaderCircle className="animate-spin" /> : <ShieldCheck />}
                {t(createMutation.isPending ? "common.creating" : "guardrailWizard.create")}
              </Button>
            )}
          </>
        }
      >
        <CreationFlow orientation="sidebar" currentStep={step} onStepChange={setStep} progressLabel={t("guardrailWizard.title")} steps={steps}>
          {step === 0 ? (
            <WizardSection title={t("guardrailWizard.detailsTitle")} description={t("guardrailWizard.detailsDescription")}>
              <div className="grid gap-5">
                <Field label={`${t("guardrailWizard.name")} *`}>
                  <Input autoFocus className="min-h-11 bg-card" value={name} onChange={(event) => setName(event.target.value)} placeholder={t("guardrailWizard.namePlaceholder")} />
                </Field>
                <Field label={`${t("guardrailWizard.purpose")} *`} hint={t("guardrailWizard.purposeHint")}>
                  <Textarea className="min-h-36 bg-card" value={purpose} onChange={(event) => setPurpose(event.target.value)} placeholder={t("guardrailWizard.purposePlaceholder")} />
                </Field>
                {!stepValid[0] ? <p className="text-xs text-muted-foreground">{t("guardrailWizard.detailsRequired")}</p> : null}
              </div>
            </WizardSection>
          ) : null}

          {step === 1 ? (
            <WizardSection title={t("guardrailWizard.controlsTitle")} description={t("guardrailWizard.controlsDescription")}>
              <div className="grid gap-3 sm:grid-cols-3">
                <AddMethod icon={LibraryBig} title={t("guardrailWizard.fromLibrary")} description={t("guardrailWizard.fromLibraryDescription")} onClick={() => setLibraryOpen(true)} />
                <AddMethod
                  icon={Sparkles}
                  title={t("guardrailWizard.fromIntent")}
                  description={t("guardrailWizard.fromIntentDescription")}
                  disabled={purpose.trim().length < 20 || !intentStatusQuery.data?.available || analyzeIntent.isPending}
                  loading={analyzeIntent.isPending}
                  onClick={() => analyzeIntent.mutate()}
                />
                <AddMethod icon={FilePlus2} title={t("guardrailWizard.customControl")} description={t("guardrailWizard.customControlDescription")} onClick={() => setManualOpen(true)} />
              </div>

              {!intentStatusQuery.isLoading && !intentStatusQuery.data?.available ? (
                <div className="mt-4"><InfoNotice title={t("guardrailWizard.intentUnavailableTitle")}>{t("guardrailWizard.intentUnavailable")}</InfoNotice></div>
              ) : null}

              <section className="mt-6">
                <div className="flex items-center justify-between gap-3">
                  <div><h4 className="text-sm font-semibold">{t("guardrailWizard.selectedControls", { count: configurations.length })}</h4><p className="mt-1 text-xs text-muted-foreground">{t("guardrailWizard.selectedControlsDescription")}</p></div>
                </div>
                {configurations.length ? (
                  <div className="mt-3 divide-y overflow-hidden rounded-lg border bg-card">
                    {configurations.map((configuration) => (
                      <div key={configuration.id} className="flex items-start gap-3 p-4">
                        <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-lg border bg-muted/30 text-muted-foreground"><Braces className="size-4" /></span>
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2"><strong className="text-sm font-medium">{configuration.name}</strong><Badge variant="outline" className="rounded-md text-[10px]">{t(`guardrailWizard.kinds.${configuration.kind}`)}</Badge></div>
                          <p className="mt-1 font-mono text-[11px] text-muted-foreground">{configuration.template_id ? `${configuration.template_id} · ${configuration.template_version}` : configuration.id}</p>
                          <p className="mt-2 text-xs text-muted-foreground">{t("guardrailWizard.availableRules", { count: configuration.rules.length })}</p>
                        </div>
                        <Button size="icon" variant="ghost" aria-label={t("guardrailWizard.removeControl", { name: configuration.name })} onClick={() => setConfigurations((current) => current.filter((item) => item.id !== configuration.id))}><Trash2 /></Button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="mt-3 rounded-lg border border-dashed p-8 text-center"><p className="text-sm font-medium">{t("guardrailWizard.noControls")}</p><p className="mt-1 text-xs text-muted-foreground">{t("guardrailWizard.noControlsDescription")}</p></div>
                )}
              </section>

              {configurations.some((item) => item.id === INTENT_CONTROL_ID) ? (
                <section className="mt-5 grid gap-4 rounded-lg border bg-muted/20 p-4 sm:grid-cols-2">
                  <Field label={t("guardrailWizard.allowedDomains")} hint={t("guardrailWizard.onePerLine")}><Textarea className="min-h-32 bg-card" value={allowed} onChange={(event) => setAllowed(event.target.value)} /></Field>
                  <Field label={t("guardrailWizard.restrictedDomains")} hint={t("guardrailWizard.onePerLine")}><Textarea className="min-h-32 bg-card" value={restricted} onChange={(event) => setRestricted(event.target.value)} /></Field>
                  {!intentBoundariesValid ? <p className="text-xs text-destructive sm:col-span-2">{t("guardrailWizard.boundariesRequired")}</p> : null}
                </section>
              ) : null}
            </WizardSection>
          ) : null}

          {step === 2 ? (
            <WizardSection title={t("guardrailWizard.rulesTitle")} description={t("guardrailWizard.rulesDescription")}>
              <div className="grid overflow-hidden rounded-lg border bg-card md:grid-cols-[13rem_minmax(0,1fr)]">
                <div className="border-b bg-muted/20 p-2 md:border-r md:border-b-0">
                  <p className="px-2 py-2 text-xs font-medium text-muted-foreground">{t("guardrailWizard.controls")}</p>
                  <div className="flex gap-1 overflow-x-auto md:block md:space-y-1 md:overflow-visible">
                    {configurations.map((configuration) => {
                      const active = configuration.id === activeControlId;
                      const count = configuration.rules.filter((rule) => rule.enabled).length;
                      return <button key={configuration.id} type="button" onClick={() => setActiveControlId(configuration.id)} className={cn("min-h-11 min-w-44 rounded-md px-3 py-2 text-left text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring md:w-full md:min-w-0", active ? "bg-card font-medium text-foreground shadow-xs" : "text-muted-foreground hover:bg-card/60")}><span className="block truncate">{configuration.name}</span><span className="mt-1 block font-mono text-[10px]">{count}/{configuration.rules.length} {t("guardrailWizard.rules")}</span></button>;
                    })}
                  </div>
                </div>
                <RuleEditor
                  configuration={configurations.find((item) => item.id === activeControlId) ?? configurations[0]}
                  template={templates.find((item) => item.id === (configurations.find((configuration) => configuration.id === activeControlId)?.template_id ?? configurations[0]?.template_id))}
                  onChange={(next) => setConfigurations((current) => current.map((item) => item.id === next.id ? next : item))}
                />
              </div>
            </WizardSection>
          ) : null}

          {step === 3 ? (
            <WizardSection title={t("guardrailWizard.behaviorTitle")} description={t("guardrailWizard.behaviorDescription")}>
              <Pipeline configurations={configurations} />
              <div className="mt-5 grid gap-4 sm:grid-cols-2">
                <Field label={t("guardrailWizard.evaluationMode")} hint={t("guardrailWizard.evaluationModeHint")}>
                  <Select value={safetyLevel} onValueChange={(value) => setSafetyLevel(value as SafetyLevel)}><SelectTrigger className="min-h-11 bg-card"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="balanced">{t("guardrailWizard.balanced")}</SelectItem><SelectItem value="strict">{t("guardrailWizard.strict")}</SelectItem></SelectContent></Select>
                </Field>
                <Field label={t("guardrailWizard.outputDelivery")} hint={t("guardrailWizard.outputDeliveryHint")}>
                  <Select value={outputDelivery} onValueChange={(value) => setOutputDelivery(value as OutputDelivery)}><SelectTrigger className="min-h-11 bg-card"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="interruptible">{t("guardrailWizard.interruptible")}</SelectItem><SelectItem value="window_buffered">{t("guardrailWizard.windowBuffered")}</SelectItem><SelectItem value="full_buffered">{t("guardrailWizard.fullBuffered")}</SelectItem></SelectContent></Select>
                </Field>
              </div>
              <div className="mt-5"><InfoNotice title={t("guardrailWizard.assignmentSeparateTitle")}>{t("guardrailWizard.assignmentSeparate")}</InfoNotice></div>
            </WizardSection>
          ) : null}

          {step === 4 ? (
            <WizardSection title={t("guardrailWizard.reviewTitle")} description={t("guardrailWizard.reviewDescription")}>
              <section className="overflow-hidden rounded-lg border bg-card">
                <div className="border-b bg-muted/20 p-4"><h4 className="text-lg font-semibold">{name}</h4><p className="mt-1 text-sm leading-6 text-muted-foreground">{purpose}</p></div>
                <div className="grid grid-cols-3 divide-x border-b text-center"><ReviewMetric label={t("guardrailWizard.controls")} value={configurations.length} /><ReviewMetric label={t("guardrailWizard.activeRules")} value={enabledRules.length} /><ReviewMetric label={t("guardrailWizard.boundaries")} value={boundaryLabel(enabledRules, t)} /></div>
                <div className="divide-y">
                  {configurations.map((configuration) => <ReviewControl key={configuration.id} configuration={configuration} />)}
                </div>
              </section>
              <div className="mt-5"><Pipeline configurations={configurations} compact /></div>
              <p className="mt-4 text-xs leading-5 text-muted-foreground">{t("guardrailWizard.afterCreate")}</p>
            </WizardSection>
          ) : null}
        </CreationFlow>
      </EntitySheet>

      <ControlLibraryPicker open={libraryOpen} onOpenChange={setLibraryOpen} templates={templates} loading={templatesQuery.isLoading} existing={configurations} onAdd={(items) => setConfigurations((current) => [...current.filter((item) => !items.some((next) => next.id === item.id)), ...items])} />
      <CustomControlSheet open={manualOpen} onOpenChange={setManualOpen} onAdd={(item) => { setConfigurations((current) => [...current, item]); setActiveControlId(item.id); }} />
    </>
  );
}

function WizardSection({ title, description, children }: { title: string; description: string; children: React.ReactNode }) {
  return <section><header className="mb-5"><h3 className="text-xl font-semibold tracking-[-0.02em]">{title}</h3><p className="mt-1.5 text-sm leading-6 text-muted-foreground">{description}</p></header>{children}</section>;
}

function AddMethod({ icon: Icon, title, description, onClick, disabled, loading }: { icon: typeof LibraryBig; title: string; description: string; onClick: () => void; disabled?: boolean; loading?: boolean }) {
  return <button type="button" disabled={disabled} onClick={onClick} className="min-h-36 rounded-lg border bg-card p-4 text-left outline-none transition-colors hover:border-primary/50 hover:bg-muted/20 focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"><span className="grid size-9 place-items-center rounded-lg border bg-muted/20 text-primary">{loading ? <LoaderCircle className="size-4 animate-spin" /> : <Icon className="size-4" />}</span><strong className="mt-4 block text-sm font-medium">{title}</strong><span className="mt-1 block text-xs leading-5 text-muted-foreground">{description}</span></button>;
}

function ControlLibraryPicker({ open, onOpenChange, templates, loading, existing, onAdd }: { open: boolean; onOpenChange: (open: boolean) => void; templates: ControlTemplate[]; loading: boolean; existing: GuardrailControlConfig[]; onAdd: (items: GuardrailControlConfig[]) => void }) {
  const { t } = useTranslation();
  const [search, setSearch] = useState("");
  const [pack, setPack] = useState("all");
  const [selected, setSelected] = useState<string[]>([]);
  useEffect(() => { if (open) { setSearch(""); setPack("all"); setSelected([]); } }, [open]);
  const packs = useMemo(() => { const values = new Map<string, string>(); templates.forEach((template) => template.packs.forEach((item) => values.set(item.id, item.name))); return [...values].sort((a, b) => a[1].localeCompare(b[1])); }, [templates]);
  const existingIds = new Set(existing.map((item) => item.template_id).filter(Boolean));
  const filtered = templates.filter((template) => (pack === "all" || template.packs.some((item) => item.id === pack)) && `${template.name} ${template.id} ${template.description} ${template.rules.map((rule) => rule.name).join(" ")}`.toLowerCase().includes(search.trim().toLowerCase()));
  const submit = () => { onAdd(selected.map((id) => templateControl(templates.find((item) => item.id === id)!))); onOpenChange(false); };
  return <EntitySheet open={open} onOpenChange={onOpenChange} eyebrow={t("guardrailWizard.libraryEyebrow")} title={t("guardrailWizard.libraryTitle")} description={t("guardrailWizard.libraryDescription")} width="lg" footer={<><span className="mr-auto text-xs text-muted-foreground">{t("guardrailWizard.selectedCount", { count: selected.length })}</span><Button variant="outline" onClick={() => onOpenChange(false)}>{t("common.cancel")}</Button><Button disabled={!selected.length} onClick={submit}>{t("guardrailWizard.addSelected", { count: selected.length })}</Button></>}>
    <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_16rem]"><label className="relative"><span className="sr-only">{t("guardrailWizard.searchLibrary")}</span><Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" /><Input className="min-h-11 pl-9" value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t("guardrailWizard.searchLibrary")} /></label><Select value={pack} onValueChange={setPack}><SelectTrigger className="min-h-11" aria-label={t("guardrailWizard.filterPack")}><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">{t("guardrailWizard.allPacks")}</SelectItem>{packs.map(([id, label]) => <SelectItem key={id} value={id}>{label}</SelectItem>)}</SelectContent></Select></div>
    {loading ? <Skeleton className="mt-4 h-80" /> : <div className="mt-4 divide-y overflow-hidden rounded-lg border bg-card">{filtered.map((template) => { const checked = selected.includes(template.id); const alreadyAdded = existingIds.has(template.id); return <label key={template.id} className={cn("flex min-h-20 cursor-pointer items-start gap-3 p-4 hover:bg-muted/20", alreadyAdded && "cursor-not-allowed opacity-50")}><Checkbox className="mt-1" checked={alreadyAdded || checked} disabled={alreadyAdded} onCheckedChange={(value) => setSelected((current) => value ? [...current, template.id] : current.filter((id) => id !== template.id))} /><span className="min-w-0 flex-1"><strong className="block text-sm font-medium">{template.name}</strong><span className="mt-1 block font-mono text-[11px] text-muted-foreground">{template.id} · {template.version}</span><span className="mt-2 block text-xs text-muted-foreground">{t("guardrailWizard.rulePackSummary", { rules: template.rules.length, packs: template.packs.length })}</span></span></label>; })}{!filtered.length ? <p className="p-8 text-center text-sm text-muted-foreground">{t("guardrailWizard.noLibraryResults")}</p> : null}</div>}
  </EntitySheet>;
}

function CustomControlSheet({ open, onOpenChange, onAdd }: { open: boolean; onOpenChange: (open: boolean) => void; onAdd: (item: GuardrailControlConfig) => void }) {
  const { t } = useTranslation();
  const [mode, setMode] = useState("keyword");
  const [name, setName] = useState("");
  const [definition, setDefinition] = useState("");
  const [action, setAction] = useState("BLOCK");
  useEffect(() => { if (open) { setMode("keyword"); setName(""); setDefinition(""); setAction("BLOCK"); } }, [open]);
  const local = mode === "keyword" || mode === "regex";
  const valid = Boolean(name.trim() && (!local || definition.trim()));
  const add = () => {
    const id = `custom:${Date.now().toString(36)}`;
    const runtimeRisk = mode === "classifier" ? "content_safety" : mode === "judge" ? "company_policy" : "builtin_content_filter";
    const phases: Array<"input" | "output"> = ["input", "output"];
    onAdd({ id, name: name.trim(), kind: "custom", runtime_risk: runtimeRisk, template_id: null, template_version: null, rules: [{ id: `${id}:rule`, name: name.trim(), detector: mode as GuardrailRuleConfig["detector"], action, phases, enabled: true, description: local ? "" : definition.trim(), expression: mode === "regex" ? definition.trim() : null, keywords: mode === "keyword" ? lines(definition) : [] }] });
    onOpenChange(false);
  };
  return <EntitySheet open={open} onOpenChange={onOpenChange} eyebrow={t("guardrailWizard.customEyebrow")} title={t("guardrailWizard.customTitle")} description={t("guardrailWizard.customDescription")} width="md" footer={<><Button variant="outline" onClick={() => onOpenChange(false)}>{t("common.cancel")}</Button><Button disabled={!valid} onClick={add}><Plus />{t("guardrailWizard.addControl")}</Button></>}>
    <div className="grid gap-5"><Field label={t("guardrailWizard.controlType")}><Select value={mode} onValueChange={(value) => { setMode(value); setAction(value === "keyword" || value === "regex" ? "BLOCK" : "reject"); }}><SelectTrigger className="min-h-11"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="keyword">{t("guardrailWizard.types.keyword")}</SelectItem><SelectItem value="regex">{t("guardrailWizard.types.regex")}</SelectItem><SelectItem value="classifier">{t("guardrailWizard.types.classifier")}</SelectItem><SelectItem value="judge">{t("guardrailWizard.types.judge")}</SelectItem></SelectContent></Select></Field><Field label={`${t("guardrailWizard.controlName")} *`}><Input value={name} onChange={(event) => setName(event.target.value)} /></Field><Field label={t(local ? "guardrailWizard.ruleDefinition" : "guardrailWizard.policyInstruction")} hint={t(mode === "keyword" ? "guardrailWizard.keywordHint" : mode === "regex" ? "guardrailWizard.regexHint" : "guardrailWizard.policyHint")}><Textarea className="min-h-36 font-mono text-sm" value={definition} onChange={(event) => setDefinition(event.target.value)} /></Field><Field label={t("guardrailWizard.whenDetected")}><Select value={action} onValueChange={setAction}><SelectTrigger className="min-h-11"><SelectValue /></SelectTrigger><SelectContent>{local ? <><SelectItem value="BLOCK">{t("guardrailWizard.actions.block")}</SelectItem><SelectItem value="MASK">{t("guardrailWizard.actions.mask")}</SelectItem></> : <><SelectItem value="reject">{t("guardrailWizard.actions.block")}</SelectItem><SelectItem value="rewrite">{t("guardrailWizard.actions.rewrite")}</SelectItem></>}</SelectContent></Select></Field></div>
  </EntitySheet>;
}

function RuleEditor({ configuration, template, onChange }: { configuration?: GuardrailControlConfig; template?: ControlTemplate; onChange: (value: GuardrailControlConfig) => void }) {
  const { t } = useTranslation();
  if (!configuration) return <div className="p-8 text-center text-sm text-muted-foreground">{t("guardrailWizard.noControlsDescription")}</div>;
  const activeCount = configuration.rules.filter((rule) => rule.enabled).length;
  const actions = template?.allowed_actions ?? (configuration.runtime_risk === "content_safety" || configuration.runtime_risk === "company_policy" ? ["reject", "rewrite"] : ["BLOCK", "MASK"]);
  const updateRule = (id: string, patch: Partial<GuardrailRuleConfig>) => onChange({ ...configuration, rules: configuration.rules.map((rule) => rule.id === id ? { ...rule, ...patch } : rule) });
  return <section className="min-w-0"><header className="border-b p-4"><div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between"><div><h4 className="text-base font-semibold">{configuration.name}</h4><p className="mt-1 font-mono text-[11px] text-muted-foreground">{configuration.template_id ? `${configuration.template_id} · ${configuration.template_version}` : configuration.id}</p></div><label className="flex min-h-11 items-center gap-2 text-xs font-medium"><Checkbox checked={activeCount === configuration.rules.length} onCheckedChange={(checked) => onChange({ ...configuration, rules: configuration.rules.map((rule) => ({ ...rule, enabled: Boolean(checked) })) })} />{t("guardrailWizard.selectAll")}</label></div><p className="mt-3 text-xs text-muted-foreground">{t("guardrailWizard.activeRuleCount", { active: activeCount, total: configuration.rules.length })}</p></header><div className="divide-y">{configuration.rules.map((rule) => <details key={rule.id} className="group"><summary className="grid min-h-20 cursor-pointer list-none gap-3 p-4 hover:bg-muted/20 sm:grid-cols-[28px_minmax(0,1fr)_9rem_20px] sm:items-center [&::-webkit-details-marker]:hidden" onClick={(event) => { if ((event.target as HTMLElement).closest("button,[role=checkbox],[role=combobox]")) event.preventDefault(); }}><Checkbox checked={rule.enabled} aria-label={t("guardrailWizard.toggleRule", { name: rule.name })} onCheckedChange={(checked) => updateRule(rule.id, { enabled: Boolean(checked) })} /><div className="min-w-0"><strong className={cn("block text-sm font-medium", !rule.enabled && "text-muted-foreground")}>{rule.name}</strong><span className="mt-1 block text-xs text-muted-foreground">{t(`guardrailWizard.detectors.${rule.detector}`)} · {rule.phases.map((phase) => t(`guardrailWizard.phases.${phase}`)).join(", ")}</span>{!ruleReady(rule) ? <span className="mt-1 block text-[11px] text-amber-700">{t("guardrailWizard.parameterRequired")}</span> : null}</div><Select disabled={!rule.enabled} value={rule.action} onValueChange={(action) => updateRule(rule.id, { action })}><SelectTrigger className="min-h-10 bg-card" aria-label={t("guardrailWizard.ruleAction", { name: rule.name })}><SelectValue /></SelectTrigger><SelectContent>{actions.map((action) => <SelectItem key={action} value={action}>{actionLabel(action, t)}</SelectItem>)}</SelectContent></Select><ChevronDown className="size-4 text-muted-foreground transition-transform group-open:rotate-180" /></summary><div className="border-t bg-muted/15 p-4 text-xs leading-5"><p className="text-muted-foreground">{rule.description || t("guardrailWizard.noRuleDescription")}</p>{rule.expression ? <pre className="mt-3 max-w-full overflow-x-auto rounded-md border bg-card p-3 font-mono text-[11px]">{rule.expression}</pre> : null}{rule.id.startsWith("dynamic-") ? <label className="mt-4 grid gap-2 text-xs font-medium"><span>{t("guardrailWizard.reviewedValues")}</span><Textarea className="min-h-24 bg-card font-mono text-xs" value={rule.keywords.filter((keyword) => !keyword.includes("{{")).join("\n")} onChange={(event) => updateRule(rule.id, { keywords: lines(event.target.value) })} placeholder={t("guardrailWizard.reviewedValuesPlaceholder")} /><span className="font-normal text-muted-foreground">{t("guardrailWizard.reviewedValuesHint")}</span></label> : rule.keywords.length ? <div className="mt-3 flex flex-wrap gap-1.5">{rule.keywords.map((keyword) => <code key={keyword} className="rounded border bg-card px-2 py-1 text-[11px]">{keyword}</code>)}</div> : null}</div></details>)}</div></section>;
}

function Pipeline({ configurations, compact = false }: { configurations: GuardrailControlConfig[]; compact?: boolean }) {
  const { t } = useTranslation();
  const countFor = (predicate: (configuration: GuardrailControlConfig, rule: GuardrailRuleConfig) => boolean) => configurations.reduce((total, configuration) => total + configuration.rules.filter((rule) => rule.enabled && predicate(configuration, rule)).length, 0);
  const stages = [
    { id: "fast", label: t("guardrailWizard.pipeline.fast"), description: t("guardrailWizard.pipeline.fastDescription"), count: countFor((configuration) => configuration.runtime_risk === "builtin_content_filter") },
    { id: "safety", label: t("guardrailWizard.pipeline.safety"), description: t("guardrailWizard.pipeline.safetyDescription"), count: countFor((configuration, rule) => configuration.runtime_risk === "content_safety" || rule.detector === "classifier") },
    { id: "deep", label: t("guardrailWizard.pipeline.deep"), description: t("guardrailWizard.pipeline.deepDescription"), count: countFor((configuration, rule) => ["topic_control", "company_policy"].includes(configuration.runtime_risk) || rule.detector === "judge") },
  ];
  return <section className="overflow-hidden rounded-lg border bg-card"><div className="grid sm:grid-cols-3">{stages.map((stage, index) => <div key={stage.id} className="border-b p-4 last:border-b-0 sm:border-r sm:border-b-0 sm:last:border-r-0"><div className="flex items-center justify-between gap-3"><span className="grid size-7 place-items-center rounded-full bg-primary/10 text-xs font-semibold text-primary">{index + 1}</span><span className="font-mono text-xs text-muted-foreground">{t("guardrailWizard.ruleCount", { count: stage.count })}</span></div><h4 className="mt-3 text-sm font-semibold">{stage.label}</h4>{!compact ? <p className="mt-1 text-xs leading-5 text-muted-foreground">{stage.description}</p> : null}</div>)}</div></section>;
}

function ReviewControl({ configuration }: { configuration: GuardrailControlConfig }) {
  const { t } = useTranslation();
  const active = configuration.rules.filter((rule) => rule.enabled);
  return <details className="group"><summary className="flex min-h-16 cursor-pointer list-none items-center gap-3 p-4 hover:bg-muted/20 [&::-webkit-details-marker]:hidden"><Check className="size-4 text-emerald-600" /><div className="min-w-0 flex-1"><strong className="block text-sm font-medium">{configuration.name}</strong><span className="mt-1 block text-xs text-muted-foreground">{t("guardrailWizard.activeRuleCount", { active: active.length, total: configuration.rules.length })}</span></div><ChevronDown className="size-4 text-muted-foreground transition-transform group-open:rotate-180" /></summary><div className="border-t bg-muted/15 px-4 py-3"><ul className="space-y-2">{active.map((rule) => <li key={rule.id} className="grid gap-1 text-xs sm:grid-cols-[minmax(0,1fr)_7rem_7rem]"><span className="font-medium">{rule.name}</span><span className="text-muted-foreground">{t(`guardrailWizard.detectors.${rule.detector}`)}</span><span className="text-muted-foreground">{actionLabel(rule.action, t)}</span></li>)}</ul></div></details>;
}

function ReviewMetric({ label, value }: { label: string; value: React.ReactNode }) { return <div className="p-4"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 text-lg font-semibold tabular-nums">{value}</p></div>; }
function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) { return <label className="grid gap-2 text-sm font-medium"><span>{label}</span>{children}{hint ? <span className="text-xs font-normal leading-5 text-muted-foreground">{hint}</span> : null}</label>; }

function templateControl(template: ControlTemplate): GuardrailControlConfig {
  return { id: `template:${template.id}`, name: template.name, kind: "template", runtime_risk: "builtin_content_filter", template_id: template.id, template_version: template.version, rules: template.rules.map((rule) => ({ id: rule.id, name: rule.name, detector: rule.detector, action: rule.action, phases: template.phases, enabled: true, description: rule.description, expression: rule.expression, keywords: rule.keywords })) };
}

function intentControl(t: ReturnType<typeof useTranslation>["t"], summary: string): GuardrailControlConfig {
  return { id: INTENT_CONTROL_ID, name: t("guardrailWizard.intentControlName"), kind: "custom", runtime_risk: "topic_control", template_id: null, template_version: null, rules: [
    { id: "approved-domains", name: t("guardrailWizard.approvedDomainsRule"), detector: "category", action: "allow", phases: ["input", "output"], enabled: true, description: summary, expression: null, keywords: [] },
    { id: "restricted-domains", name: t("guardrailWizard.restrictedDomainsRule"), detector: "category", action: "redirect", phases: ["input", "output"], enabled: true, description: summary, expression: null, keywords: [] },
  ] };
}

function runtimeControls(configurations: GuardrailControlConfig[]): GuardrailControl[] {
  const actions = new Map<string, string>();
  for (const configuration of configurations) {
    const enabled = configuration.rules.filter((rule) => rule.enabled);
    if (!enabled.length) continue;
    const action = configuration.runtime_risk === "builtin_content_filter" ? "reject" : configuration.runtime_risk === "topic_control" ? "redirect" : enabled[0].action.toLowerCase();
    actions.set(configuration.runtime_risk, action);
  }
  return [...actions].map(([risk, action]) => ({ risk, action, reasoning_policy: null }));
}

function boundaryLabel(rules: GuardrailRuleConfig[], t: ReturnType<typeof useTranslation>["t"]): string {
  const phases = new Set(rules.flatMap((rule) => rule.phases));
  return phases.size === 2 ? t("guardrailWizard.inputOutput") : phases.has("input") ? t("guardrailWizard.inputOnly") : t("guardrailWizard.outputOnly");
}

function actionLabel(action: string, t: ReturnType<typeof useTranslation>["t"]): string {
  const normalized = action.toLowerCase();
  if (["block", "reject"].includes(normalized)) return t("guardrailWizard.actions.block");
  if (["mask", "redact"].includes(normalized)) return t("guardrailWizard.actions.mask");
  if (normalized === "rewrite") return t("guardrailWizard.actions.rewrite");
  if (normalized === "redirect") return t("guardrailWizard.actions.redirect");
  if (normalized === "allow") return t("guardrailWizard.actions.allow");
  return action;
}

function lines(value: string): string[] { return value.split("\n").map((item) => item.trim()).filter(Boolean); }
function ruleReady(rule: GuardrailRuleConfig): boolean { return !rule.enabled || !rule.id.startsWith("dynamic-") || (rule.keywords.length > 0 && rule.keywords.every((keyword) => !keyword.includes("{{"))); }
function notifyError(error: unknown, fallback: string) { toast.error(error instanceof Error ? error.message : fallback); }
