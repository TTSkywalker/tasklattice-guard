import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowRight,
  Braces,
  Check,
  CircleAlert,
  Clock3,
  Code2,
  FileCode2,
  FlaskConical,
  GitBranch,
  LoaderCircle,
  LockKeyhole,
  Network,
  PackageCheck,
  Plus,
  Search,
  ShieldCheck,
  Trash2,
  Workflow,
  X,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { CreationFlow } from "@/components/creation-flow";
import { EntitySheet } from "@/components/entity-sheet";
import { ErrorNotice } from "@/components/product-shell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { queryKeys } from "@/features/query-keys";
import { useAuth } from "@/lib/auth";
import { compilerLocation } from "@/lib/compiler-location";
import {
  createNativeControl,
  getActionCatalog,
  getNativeControl,
  getNativeControls,
  publishNativeControl,
  runNativeControlTests,
  updateNativeControl,
  validateNativeControl,
  type ActionDefinition,
  type ControlActionReference,
  type ControlParameter,
  type ControlRailBinding,
  type ControlTestCase,
  type ControlTestRun,
  type NativeControl,
  type NativeControlDraft,
  type NativeRailType,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const RAILS: NativeRailType[] = ["input", "output", "retrieval", "dialog", "execution"];
const EMPTY_CONTROLS: NativeControl[] = [];
const DEFAULT_COLANG = `flow check_request $text
  # Invoke one or more registered Actions here.
  $result = await TaskLatticeCustomerIdentifierAction(text=$text)
  if $result["detected"]
    $recorded = await TaskLatticeRecordControlAction(flow_name="check_request", safe=False, text=$text, replacement=$result["redacted"])
  else
    $recorded = await TaskLatticeRecordControlAction(flow_name="check_request", safe=True, text=$text)
`;

export function NativeControlInventory({ source }: { source: "built-in" | "custom" }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const controlsQuery = useQuery({ queryKey: queryKeys.nativeControls, queryFn: getNativeControls });
  const controls = (controlsQuery.data?.items ?? EMPTY_CONTROLS).filter((item) => item.source === source);
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [studioControl, setStudioControl] = useState<NativeControl | null | undefined>(undefined);
  const filtered = useMemo(() => {
    const value = search.trim().toLowerCase();
    return value
      ? controls.filter((item) => [item.name, item.id, item.description, item.owner].join(" ").toLowerCase().includes(value))
      : controls;
  }, [controls, search]);

  async function refresh(controlId?: string) {
    await queryClient.invalidateQueries({ queryKey: queryKeys.nativeControls });
    if (controlId) await queryClient.invalidateQueries({ queryKey: queryKeys.nativeControl(controlId) });
  }

  return (
    <>
      <section className="overflow-hidden rounded-xl border bg-card shadow-xs">
        <header className="flex flex-col gap-3 border-b bg-muted/20 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-base font-semibold">{t(`controlStudio.inventory.${source}.title`)}</h2>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">{t(`controlStudio.inventory.${source}.description`)}</p>
          </div>
          {source === "custom" ? (
            <Button className="min-h-11" onClick={() => setStudioControl(null)}><Plus />{t("controlStudio.newControl")}</Button>
          ) : null}
        </header>

        <div className="border-b p-4">
          <label className="relative block max-w-xl">
            <span className="sr-only">{t("controlStudio.search")}</span>
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input className="min-h-11 pl-9" value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t("controlStudio.searchPlaceholder")} />
          </label>
        </div>

        {controlsQuery.error ? <div className="p-4"><ErrorNotice error={controlsQuery.error} /></div> : null}
        {controlsQuery.isLoading ? <div className="grid gap-3 p-4 md:grid-cols-2"><Skeleton className="h-40" /><Skeleton className="h-40" /></div> : null}
        {!controlsQuery.isLoading && !controlsQuery.error && filtered.length ? (
          <div className="divide-y">
            {filtered.map((control) => (
              <button
                key={control.id}
                type="button"
                className="grid min-h-24 w-full gap-3 px-4 py-4 text-left outline-none transition-colors hover:bg-muted/20 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring md:grid-cols-[minmax(0,1fr)_11rem_9rem_2rem] md:items-center"
                onClick={() => setSelectedId(control.id)}
              >
                <span className="min-w-0">
                  <span className="flex flex-wrap items-center gap-2"><strong className="text-sm font-medium">{control.name}</strong><Badge variant="outline">{control.draft.colang_version}</Badge></span>
                  <span className="mt-1 block line-clamp-2 text-xs leading-5 text-muted-foreground">{control.description || t("controlStudio.noDescription")}</span>
                  <code className="mt-1 block truncate text-[10px] text-muted-foreground">{control.id}</code>
                </span>
                <span className="flex flex-wrap gap-1.5">{uniqueRails(control).map((rail) => <RailBadge key={rail} rail={rail} />)}</span>
                <span className="text-xs text-muted-foreground"><span className="block font-medium text-foreground">{t("controlStudio.revision", { revision: control.draft_revision })}</span>{control.owner}</span>
                <ArrowRight className="size-4 text-muted-foreground" />
              </button>
            ))}
          </div>
        ) : null}
        {!controlsQuery.isLoading && !controlsQuery.error && !filtered.length ? (
          <div className="p-10 text-center"><Workflow className="mx-auto size-8 text-muted-foreground" /><p className="mt-3 text-sm font-medium">{t("controlStudio.emptyTitle")}</p><p className="mt-1 text-xs text-muted-foreground">{t("controlStudio.emptyDescription")}</p></div>
        ) : null}
      </section>

      <ControlDetailSheet
        controlId={selectedId}
        onClose={() => setSelectedId(null)}
        onEdit={(control) => { setSelectedId(null); setStudioControl(control); }}
      />
      <ControlStudioSheet
        control={studioControl}
        open={studioControl !== undefined}
        onOpenChange={(open) => { if (!open) setStudioControl(undefined); }}
        onSaved={async (controlId) => { await refresh(controlId); setStudioControl(undefined); setSelectedId(controlId); }}
      />
    </>
  );
}

function ControlDetailSheet({ controlId, onClose, onEdit }: { controlId: string | null; onClose: () => void; onEdit: (control: NativeControl) => void }) {
  const { t } = useTranslation();
  const query = useQuery({ queryKey: queryKeys.nativeControl(controlId ?? ""), queryFn: () => getNativeControl(controlId!), enabled: Boolean(controlId) });
  const control = query.data;
  const versions = control?.versions ?? [];
  return (
    <EntitySheet
      open={Boolean(controlId)}
      onOpenChange={(open) => { if (!open) onClose(); }}
      eyebrow={t("controlStudio.detailEyebrow")}
      title={control?.name ?? t("controlStudio.control")}
      description={control?.description ?? t("controlStudio.detailDescription")}
      width="xl"
      footer={<>{control?.source === "custom" ? <Button onClick={() => onEdit(control)}><Code2 />{t("common.edit")}</Button> : null}<Button variant="outline" onClick={onClose}>{t("common.close")}</Button></>}
    >
      {query.isLoading ? <Skeleton className="h-[32rem]" /> : null}
      {query.error ? <ErrorNotice error={query.error} /> : null}
      {control ? (
        <Tabs defaultValue="overview">
          <TabsList variant="line" className="h-auto w-full justify-start overflow-x-auto pb-2 [scrollbar-width:none]">
            {(["overview", "rails", "colang", "actions", "parameters", "tests", "versions", "compatibility"] as const).map((tab) => <TabsTrigger key={tab} value={tab} className="min-h-11 px-3">{t(`controlStudio.tabs.${tab}`)}</TabsTrigger>)}
          </TabsList>
          <TabsContent value="overview" className="pt-4"><Overview control={control} /></TabsContent>
          <TabsContent value="rails" className="pt-4"><RailList rails={control.draft.rail_bindings} /></TabsContent>
          <TabsContent value="colang" className="pt-4"><SourceViewer sources={control.draft.sources} /></TabsContent>
          <TabsContent value="actions" className="pt-4"><DependencyList actions={control.draft.action_references} models={control.draft.model_dependencies} prompts={control.draft.prompt_dependencies} /></TabsContent>
          <TabsContent value="parameters" className="pt-4"><ParameterList parameters={control.draft.parameter_schema} /></TabsContent>
          <TabsContent value="tests" className="pt-4"><TestList tests={control.draft.tests} /></TabsContent>
          <TabsContent value="versions" className="pt-4"><VersionList versions={versions} /></TabsContent>
          <TabsContent value="compatibility" className="pt-4"><Compatibility control={control} /></TabsContent>
        </Tabs>
      ) : null}
    </EntitySheet>
  );
}

function ControlStudioSheet({ control, open, onOpenChange, onSaved }: { control: NativeControl | null | undefined; open: boolean; onOpenChange: (open: boolean) => void; onSaved: (id: string) => Promise<void> }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const actionsQuery = useQuery({ queryKey: queryKeys.actionCatalog, queryFn: getActionCatalog, enabled: open });
  const actions = actionsQuery.data?.items ?? [];
  const [step, setStep] = useState(0);
  const [controlId, setControlId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [owner, setOwner] = useState("");
  const [draft, setDraft] = useState<NativeControlDraft>(emptyDraft());
  const [compileError, setCompileError] = useState<string | null>(null);
  const [validatedRevision, setValidatedRevision] = useState<number | null>(null);
  const [testRun, setTestRun] = useState<ControlTestRun | null>(null);

  useEffect(() => {
    if (!open) return;
    setStep(0);
    setControlId(control?.id ?? null);
    setName(control?.name ?? "");
    setDescription(control?.description ?? "");
    setOwner(control?.owner ?? user?.email ?? "security-platform");
    setDraft(control ? cloneDraft(control.draft) : emptyDraft());
    setCompileError(null);
    setValidatedRevision(null);
    setTestRun(null);
  }, [control, open, user?.email]);

  async function persistDraft() {
    const payload = { name: name.trim(), description: description.trim(), owner: owner.trim(), draft };
    const saved = controlId
      ? await updateNativeControl(controlId, payload)
      : await createNativeControl(payload);
    setControlId(saved.id);
    return saved;
  }

  const validateMutation = useMutation({
    mutationFn: async () => {
      const saved = await persistDraft();
      const result = await validateNativeControl(saved.id);
      return { saved, result };
    },
    onSuccess: ({ saved, result }) => {
      setCompileError(null);
      setValidatedRevision(result.draft_revision);
      toast.success(t("controlStudio.validationPassed"));
      setStep(6);
      setControlId(saved.id);
    },
    onError: (error) => {
      const message = errorMessage(error, t("controlStudio.validationFailed"));
      setCompileError(message);
      toast.error(message);
    },
  });
  const testMutation = useMutation({
    mutationFn: async () => {
      const saved = await persistDraft();
      await validateNativeControl(saved.id);
      return runNativeControlTests(saved.id);
    },
    onSuccess: (result) => {
      setCompileError(null);
      setTestRun(result);
      setValidatedRevision(result.draft_revision ?? null);
      if (result.status === "passed") {
        toast.success(t("controlStudio.testsPassed"));
        setStep(7);
      } else toast.error(t("controlStudio.testsFailed"));
    },
    onError: (error) => {
      const message = errorMessage(error, t("controlStudio.testsFailed"));
      setCompileError(message);
      toast.error(message);
    },
  });
  const publishMutation = useMutation({
    mutationFn: async () => {
      if (!controlId) throw new Error(t("controlStudio.saveFirst"));
      return publishNativeControl(controlId);
    },
    onSuccess: async (version) => {
      toast.success(t("controlStudio.published", { version: version.version }));
      await onSaved(version.control_id);
    },
    onError: (error) => toast.error(errorMessage(error, t("controlStudio.publishFailed"))),
  });

  const steps = (["definition", "rails", "colang", "actions", "parameters", "validate", "test", "publish"] as const).map((key) => ({ label: t(`controlStudio.steps.${key}`), description: t(`controlStudio.stepDescriptions.${key}`) }));
  const canContinue = [Boolean(name.trim() && description.trim() && owner.trim()), draft.rail_bindings.length > 0 && draft.rail_bindings.every(railReady), draft.sources.length > 0 && draft.sources.every((source) => source.path.trim() && source.content.trim()), true, draft.parameter_schema.every(parameterReady), true, draft.tests.length > 0 && draft.tests.every(testReady), testRun?.status === "passed"];
  const busy = validateMutation.isPending || testMutation.isPending || publishMutation.isPending;

  return (
    <EntitySheet
      open={open}
      onOpenChange={onOpenChange}
      eyebrow={t("controlStudio.builderEyebrow")}
      title={control ? t("controlStudio.editTitle", { name: control.name }) : t("controlStudio.createTitle")}
      description={t("controlStudio.createDescription")}
      width="xl"
      bodyClassName="p-0 sm:p-0"
      footer={
        <>
          <Button variant="outline" disabled={busy} onClick={() => step ? setStep(step - 1) : onOpenChange(false)}>{step ? <><ArrowLeft />{t("common.previous")}</> : t("common.cancel")}</Button>
          {step < 5 ? <Button disabled={!canContinue[step] || busy} onClick={() => setStep(step + 1)}>{t("common.next")}<ArrowRight /></Button> : null}
          {step === 5 ? <Button disabled={!canContinue.slice(0, 5).every(Boolean) || busy} onClick={() => validateMutation.mutate()}>{validateMutation.isPending ? <LoaderCircle className="animate-spin" /> : <PackageCheck />}{t("controlStudio.validate")}</Button> : null}
          {step === 6 ? <Button disabled={!canContinue[6] || busy} onClick={() => testMutation.mutate()}>{testMutation.isPending ? <LoaderCircle className="animate-spin" /> : <FlaskConical />}{t("controlStudio.runTests")}</Button> : null}
          {step === 7 ? <Button disabled={testRun?.status !== "passed" || testRun.draft_revision !== validatedRevision || busy} onClick={() => publishMutation.mutate()}>{publishMutation.isPending ? <LoaderCircle className="animate-spin" /> : <ShieldCheck />}{t("controlStudio.publish")}</Button> : null}
        </>
      }
    >
      <CreationFlow orientation="sidebar" currentStep={step} onStepChange={setStep} progressLabel={t("controlStudio.createTitle")} steps={steps}>
        {step === 0 ? <StudioSection title={t("controlStudio.definitionTitle")} description={t("controlStudio.definitionDescription")}><div className="grid gap-5"><Field label={`${t("controlStudio.name")} *`}><Input autoFocus className="min-h-11" value={name} onChange={(event) => setName(event.target.value)} /></Field><Field label={`${t("controlStudio.description")} *`}><Textarea className="min-h-28" value={description} onChange={(event) => setDescription(event.target.value)} /></Field><Field label={`${t("controlStudio.owner")} *`}><Input className="min-h-11" value={owner} onChange={(event) => setOwner(event.target.value)} /></Field><Field label={t("controlStudio.colangVersion")}><Select value={draft.colang_version} onValueChange={(value) => setDraft({ ...draft, colang_version: value as "1.0" | "2.x" })}><SelectTrigger className="min-h-11"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="2.x">Colang 2.x</SelectItem><SelectItem value="1.0">Colang 1.0</SelectItem></SelectContent></Select></Field></div></StudioSection> : null}
        {step === 1 ? <RailEditor rails={draft.rail_bindings} onChange={(rail_bindings) => setDraft({ ...draft, rail_bindings })} /> : null}
        {step === 2 ? <ColangEditor sources={draft.sources} error={compileError} onChange={(sources) => { setCompileError(null); setDraft({ ...draft, sources }); }} /> : null}
        {step === 3 ? <ActionEditor actions={actions} selected={draft.action_references} onChange={(action_references) => setDraft({ ...draft, action_references })} loading={actionsQuery.isLoading} /> : null}
        {step === 4 ? <ParameterEditor parameters={draft.parameter_schema} onChange={(parameter_schema) => setDraft({ ...draft, parameter_schema })} /> : null}
        {step === 5 ? <ValidationReview name={name} draft={draft} error={compileError} /> : null}
        {step === 6 ? <TestEditor tests={draft.tests} run={testRun} error={compileError} onChange={(tests) => { setTestRun(null); setDraft({ ...draft, tests }); }} /> : null}
        {step === 7 ? <PublishReview name={name} draft={draft} run={testRun} /> : null}
      </CreationFlow>
    </EntitySheet>
  );
}

function RailEditor({ rails, onChange }: { rails: ControlRailBinding[]; onChange: (rails: ControlRailBinding[]) => void }) {
  const { t } = useTranslation();
  return <StudioSection title={t("controlStudio.railsTitle")} description={t("controlStudio.railsDescription")} action={<Button variant="outline" onClick={() => onChange([...rails, emptyRail(rails.length)])}><Plus />{t("controlStudio.addRail")}</Button>}><div className="space-y-4">{rails.map((rail, index) => <section key={index} className="rounded-lg border bg-card"><header className="flex items-center justify-between border-b bg-muted/20 px-4 py-3"><div className="flex items-center gap-2"><GitBranch className="size-4 text-primary" /><strong className="text-sm">{t("controlStudio.railBinding", { number: index + 1 })}</strong></div><Button size="icon" variant="ghost" aria-label={t("common.remove")} onClick={() => onChange(rails.filter((_, itemIndex) => itemIndex !== index))}><Trash2 /></Button></header><div className="grid gap-4 p-4 sm:grid-cols-2"><Field label={`${t("controlStudio.rail")} *`}><Select value={rail.rail_type} onValueChange={(value) => replaceAt(rails, index, { ...rail, rail_type: value as NativeRailType }, onChange)}><SelectTrigger className="min-h-11"><SelectValue /></SelectTrigger><SelectContent>{RAILS.map((item) => <SelectItem key={item} value={item}>{t(`controlStudio.railNames.${item}`)}</SelectItem>)}</SelectContent></Select></Field><Field label={`${t("controlStudio.flowName")} *`}><Input className="min-h-11 font-mono text-xs" value={rail.flow_name} onChange={(event) => replaceAt(rails, index, { ...rail, flow_name: event.target.value }, onChange)} /></Field><Field label={t("controlStudio.executionMode")}><Select value={rail.execution_mode} onValueChange={(value) => replaceAt(rails, index, { ...rail, execution_mode: value as "detect" | "mutate" }, onChange)}><SelectTrigger className="min-h-11"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="detect">{t("controlStudio.detect")}</SelectItem><SelectItem value="mutate">{t("controlStudio.mutate")}</SelectItem></SelectContent></Select></Field><Field label={t("controlStudio.unsafeAction")}><Select value={rail.on_unsafe} onValueChange={(value) => replaceAt(rails, index, { ...rail, on_unsafe: value as ControlRailBinding["on_unsafe"] }, onChange)}><SelectTrigger className="min-h-11"><SelectValue /></SelectTrigger><SelectContent>{["reject", "redact", "rewrite", "regenerate", "redirect", "fallback", "clarify", "pass"].map((item) => <SelectItem key={item} value={item}>{item}</SelectItem>)}</SelectContent></Select></Field><Field label={t("controlStudio.parallelGroup")} hint={t("controlStudio.parallelHint")}><Input className="min-h-11 font-mono text-xs" value={rail.parallel_group ?? ""} onChange={(event) => replaceAt(rails, index, { ...rail, parallel_group: event.target.value || null }, onChange)} /></Field><Field label={t("controlStudio.timeout")}><Input className="min-h-11" type="number" min={1} max={120000} value={rail.timeout_ms} onChange={(event) => replaceAt(rails, index, { ...rail, timeout_ms: Number(event.target.value) }, onChange)} /></Field></div></section>)}</div></StudioSection>;
}

function ColangEditor({ sources, error, onChange }: { sources: NativeControlDraft["sources"]; error: string | null; onChange: (sources: NativeControlDraft["sources"]) => void }) {
  const { t } = useTranslation();
  const source = sources[0] ?? { path: "main.co", content: "" };
  const location = error ? compilerLocation(error) : null;
  return <StudioSection title={t("controlStudio.colangTitle")} description={t("controlStudio.colangDescription")}><div className="overflow-hidden rounded-lg border bg-[#111827] text-slate-100"><div className="flex items-center justify-between border-b border-white/10 px-3 py-2"><div className="flex items-center gap-2"><FileCode2 className="size-4 text-blue-400" /><Input aria-label={t("controlStudio.sourcePath")} className="h-9 w-52 border-white/10 bg-white/5 font-mono text-xs text-white" value={source.path} onChange={(event) => onChange([{ ...source, path: event.target.value }])} /></div><Badge variant="outline" className="border-white/15 bg-white/5 text-slate-300">Colang</Badge></div><div className="grid grid-cols-[3rem_minmax(0,1fr)]"><pre aria-hidden="true" className="select-none overflow-hidden border-r border-white/10 py-3 text-right font-mono text-xs leading-5 text-slate-500">{lineNumbers(source.content)}</pre><Textarea aria-label={t("controlStudio.colangSource")} wrap="off" spellCheck={false} className="min-h-[25rem] resize-y overflow-x-auto rounded-none border-0 bg-transparent px-3 py-3 font-mono text-xs leading-5 whitespace-pre text-slate-100 shadow-none focus-visible:ring-0" value={source.content} onChange={(event) => onChange([{ ...source, content: event.target.value }])} /></div><div className="flex items-center justify-between border-t border-white/10 px-3 py-2 font-mono text-[10px] text-slate-400"><span>{source.content.split("\n").length} {t("controlStudio.lines")}</span><span>{location ? `${location.path}:${location.line}:${location.column}` : t("controlStudio.compileReady")}</span></div></div>{error ? <Alert variant="destructive" className="mt-4"><CircleAlert /><AlertTitle>{t("controlStudio.compileError")}{location ? ` · ${location.path}:${location.line}:${location.column}` : ""}</AlertTitle><AlertDescription className="break-words font-mono text-xs">{error}</AlertDescription></Alert> : null}</StudioSection>;
}

function ActionEditor({ actions, selected, onChange, loading }: { actions: ActionDefinition[]; selected: ControlActionReference[]; onChange: (actions: ControlActionReference[]) => void; loading: boolean }) {
  const { t } = useTranslation();
  return <StudioSection title={t("controlStudio.actionsTitle")} description={t("controlStudio.actionsDescription")}><Alert variant="info" className="mb-4"><LockKeyhole /><AlertTitle>{t("controlStudio.registeredOnly")}</AlertTitle><AlertDescription>{t("controlStudio.noPython")}</AlertDescription></Alert>{loading ? <Skeleton className="h-64" /> : <div className="divide-y rounded-lg border bg-card">{actions.map((action) => { const checked = selected.some((item) => item.name === action.name && item.version === action.version); return <label key={`${action.name}@${action.version}`} className="grid min-h-20 cursor-pointer grid-cols-[2rem_minmax(0,1fr)] gap-3 p-4 hover:bg-muted/20 sm:grid-cols-[2rem_minmax(0,1fr)_12rem]"><Checkbox className="mt-0.5" checked={checked} onCheckedChange={(value) => onChange(value ? [...selected, { name: action.name, version: action.version }] : selected.filter((item) => item.name !== action.name || item.version !== action.version))} /><span className="min-w-0"><strong className="block truncate font-mono text-xs">{action.name}@{action.version}</strong><span className="mt-1 flex flex-wrap gap-1.5">{action.supported_rails.map((rail) => <RailBadge key={rail} rail={rail} />)}{action.concurrent ? <Badge variant="outline">{t("controlStudio.concurrent")}</Badge> : null}{action.network_access ? <Badge variant="outline"><Network />{t("controlStudio.network")}</Badge> : null}</span></span><span className="text-xs text-muted-foreground sm:text-right"><Clock3 className="mr-1 inline size-3" />{action.timeout_ms}ms<br />{action.failure_mode}</span></label>; })}</div>}</StudioSection>;
}

function ParameterEditor({ parameters, onChange }: { parameters: ControlParameter[]; onChange: (parameters: ControlParameter[]) => void }) {
  const { t } = useTranslation();
  return <StudioSection title={t("controlStudio.parametersTitle")} description={t("controlStudio.parametersDescription")} action={<Button variant="outline" onClick={() => onChange([...parameters, { name: "", kind: "string", required: false, default: null, description: "" }])}><Plus />{t("controlStudio.addParameter")}</Button>}><div className="space-y-3">{parameters.length ? parameters.map((parameter, index) => <section key={index} className="grid gap-3 rounded-lg border bg-card p-4 sm:grid-cols-[minmax(0,1fr)_9rem_10rem_2.5rem]"><Field label={t("controlStudio.parameterName")}><Input className="min-h-11 font-mono text-xs" value={parameter.name} onChange={(event) => replaceAt(parameters, index, { ...parameter, name: event.target.value }, onChange)} /></Field><Field label={t("controlStudio.type")}><Select value={parameter.kind} onValueChange={(value) => replaceAt(parameters, index, { ...parameter, kind: value as ControlParameter["kind"] }, onChange)}><SelectTrigger className="min-h-11"><SelectValue /></SelectTrigger><SelectContent>{["string", "number", "boolean", "secret"].map((item) => <SelectItem key={item} value={item}>{item}</SelectItem>)}</SelectContent></Select></Field><Field label={t("controlStudio.defaultValue")}><Input className="min-h-11" disabled={parameter.kind === "secret"} value={parameter.default ?? ""} onChange={(event) => replaceAt(parameters, index, { ...parameter, default: event.target.value || null }, onChange)} /></Field><Button className="mt-6" size="icon" variant="ghost" aria-label={t("common.remove")} onClick={() => onChange(parameters.filter((_, itemIndex) => itemIndex !== index))}><Trash2 /></Button><label className="flex min-h-11 items-center gap-2 sm:col-span-4"><Checkbox checked={parameter.required} onCheckedChange={(value) => replaceAt(parameters, index, { ...parameter, required: Boolean(value) }, onChange)} /><span className="text-xs">{t("controlStudio.requiredAtBinding")}</span></label></section>) : <EmptyInline icon={Braces} text={t("controlStudio.noParameters")} />}</div></StudioSection>;
}

function TestEditor({ tests, run, error, onChange }: { tests: ControlTestCase[]; run: ControlTestRun | null; error: string | null; onChange: (tests: ControlTestCase[]) => void }) {
  const { t } = useTranslation();
  return <StudioSection title={t("controlStudio.testsTitle")} description={t("controlStudio.testsDescription")} action={<Button variant="outline" onClick={() => onChange([...tests, { name: "", rail_type: "input", content: "", expected_decision: "allow" }])}><Plus />{t("controlStudio.addCase")}</Button>}>{error ? <Alert variant="destructive" className="mb-4"><CircleAlert /><AlertTitle>{t("controlStudio.cannotRun")}</AlertTitle><AlertDescription>{error}</AlertDescription></Alert> : null}<div className="space-y-3">{tests.map((test, index) => { const result = run?.results?.[index]; return <section key={index} className={cn("rounded-lg border bg-card", result && (result.passed ? "border-emerald-200" : "border-destructive/30"))}><header className="flex items-center justify-between border-b bg-muted/20 px-4 py-3"><strong className="text-sm">{t("controlStudio.testCase", { number: index + 1 })}</strong><Button size="icon" variant="ghost" aria-label={t("common.remove")} onClick={() => onChange(tests.filter((_, itemIndex) => itemIndex !== index))}><Trash2 /></Button></header><div className="grid gap-4 p-4 sm:grid-cols-2"><Field label={`${t("controlStudio.caseName")} *`}><Input className="min-h-11" value={test.name} onChange={(event) => replaceAt(tests, index, { ...test, name: event.target.value }, onChange)} /></Field><Field label={t("controlStudio.rail")}><Select value={test.rail_type} onValueChange={(value) => replaceAt(tests, index, { ...test, rail_type: value as NativeRailType }, onChange)}><SelectTrigger className="min-h-11"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="input">Input</SelectItem><SelectItem value="output">Output</SelectItem></SelectContent></Select></Field><Field label={`${t("controlStudio.content")} *`}><Textarea className="min-h-24" value={test.content} onChange={(event) => replaceAt(tests, index, { ...test, content: event.target.value }, onChange)} /></Field><Field label={t("controlStudio.expectedDecision")}><Select value={test.expected_decision} onValueChange={(value) => replaceAt(tests, index, { ...test, expected_decision: value as ControlTestCase["expected_decision"] }, onChange)}><SelectTrigger className="min-h-11"><SelectValue /></SelectTrigger><SelectContent>{["allow", "block", "transform"].map((item) => <SelectItem key={item} value={item}>{item}</SelectItem>)}</SelectContent></Select></Field>{result ? <div className="sm:col-span-2"><Alert variant={result.passed ? "default" : "destructive"}>{result.passed ? <Check /> : <X />}<AlertTitle>{result.passed ? t("controlStudio.casePassed") : t("controlStudio.caseFailed")}</AlertTitle><AlertDescription>{result.actual_decision} · {result.latency_ms}ms{result.reason ? ` · ${result.reason}` : ""}</AlertDescription></Alert></div> : null}</div></section>; })}{!tests.length ? <EmptyInline icon={FlaskConical} text={t("controlStudio.noTests")} /> : null}</div></StudioSection>;
}

function ValidationReview({ name, draft, error }: { name: string; draft: NativeControlDraft; error: string | null }) { const { t } = useTranslation(); return <StudioSection title={t("controlStudio.validateTitle")} description={t("controlStudio.validateDescription")}><ReviewGrid items={[{ label: t("controlStudio.control"), value: name }, { label: t("controlStudio.colangVersion"), value: draft.colang_version }, { label: t("controlStudio.rails"), value: String(draft.rail_bindings.length) }, { label: t("controlStudio.actions"), value: String(draft.action_references.length) }, { label: t("controlStudio.parameters"), value: String(draft.parameter_schema.length) }, { label: t("controlStudio.timeoutBudget"), value: `${criticalPath(draft.rail_bindings)}ms` }]} />{error ? <Alert variant="destructive" className="mt-4"><CircleAlert /><AlertTitle>{t("controlStudio.validationFailed")}</AlertTitle><AlertDescription>{error}</AlertDescription></Alert> : <Alert variant="info" className="mt-4"><PackageCheck /><AlertTitle>{t("controlStudio.readyToValidate")}</AlertTitle><AlertDescription>{t("controlStudio.validationChecks")}</AlertDescription></Alert>}</StudioSection>; }
function PublishReview({ name, draft, run }: { name: string; draft: NativeControlDraft; run: ControlTestRun | null }) { const { t } = useTranslation(); return <StudioSection title={t("controlStudio.publishTitle")} description={t("controlStudio.publishDescription")}><Alert className="mb-4"><LockKeyhole /><AlertTitle>{t("controlStudio.immutableTitle")}</AlertTitle><AlertDescription>{t("controlStudio.immutableDescription")}</AlertDescription></Alert><ReviewGrid items={[{ label: t("controlStudio.control"), value: name }, { label: t("controlStudio.rails"), value: uniqueRailBindings(draft.rail_bindings).join(", ") }, { label: t("controlStudio.actions"), value: String(draft.action_references.length) }, { label: t("controlStudio.evaluation"), value: run?.status ?? "not_run" }, { label: t("controlStudio.testCases"), value: String(draft.tests.length) }, { label: t("controlStudio.timeoutBudget"), value: `${criticalPath(draft.rail_bindings)}ms` }]} /></StudioSection>; }

function Overview({ control }: { control: NativeControl }) { const { t } = useTranslation(); return <ReviewGrid items={[{ label: t("controlStudio.controlId"), value: control.id, mono: true }, { label: t("controlStudio.source"), value: control.source }, { label: t("controlStudio.owner"), value: control.owner }, { label: t("controlStudio.draftRevision"), value: String(control.draft_revision) }, { label: t("controlStudio.colangVersion"), value: control.draft.colang_version }, { label: t("controlStudio.updated"), value: new Date(control.updated_at).toLocaleString() }]} />; }
function RailList({ rails }: { rails: ControlRailBinding[] }) { const { t } = useTranslation(); return <div className="space-y-3">{rails.map((rail) => <section key={`${rail.rail_type}:${rail.flow_name}`} className="rounded-lg border bg-card p-4"><div className="flex flex-wrap items-center gap-2"><RailBadge rail={rail.rail_type} /><strong className="font-mono text-xs">{rail.flow_name}</strong><Badge variant="outline">{rail.execution_mode}</Badge></div><dl className="mt-3 grid gap-3 text-xs sm:grid-cols-3"><div><dt className="text-muted-foreground">{t("controlStudio.unsafeAction")}</dt><dd className="mt-1 font-medium">{rail.on_unsafe}</dd></div><div><dt className="text-muted-foreground">{t("controlStudio.parallelGroup")}</dt><dd className="mt-1 font-mono">{rail.parallel_group ?? "—"}</dd></div><div><dt className="text-muted-foreground">{t("controlStudio.timeout")}</dt><dd className="mt-1 font-mono">{rail.timeout_ms}ms · {rail.failure_mode}</dd></div></dl></section>)}</div>; }
function SourceViewer({ sources }: { sources: NativeControlDraft["sources"] }) { return <div className="space-y-3">{sources.map((source) => <section key={source.path} className="overflow-hidden rounded-lg border bg-[#111827] text-slate-100"><header className="border-b border-white/10 px-3 py-2 font-mono text-xs text-slate-400">{source.path}</header><pre className="max-h-[32rem] overflow-auto p-4 font-mono text-xs leading-5"><code>{source.content}</code></pre></section>)}</div>; }
function DependencyList({ actions, models, prompts }: { actions: ControlActionReference[]; models: string[]; prompts: string[] }) { const { t } = useTranslation(); return <div className="space-y-4"><DependencyGroup title={t("controlStudio.actions")} items={actions.map((item) => `${item.name}@${item.version}`)} /><DependencyGroup title={t("controlStudio.models")} items={models} /><DependencyGroup title={t("controlStudio.prompts")} items={prompts} /></div>; }
function DependencyGroup({ title, items }: { title: string; items: string[] }) { return <section className="rounded-lg border bg-card p-4"><h3 className="text-sm font-medium">{title}</h3>{items.length ? <div className="mt-3 flex flex-wrap gap-2">{items.map((item) => <code key={item} className="rounded border bg-muted/30 px-2 py-1 text-[11px]">{item}</code>)}</div> : <p className="mt-2 text-xs text-muted-foreground">—</p>}</section>; }
function ParameterList({ parameters }: { parameters: ControlParameter[] }) { const { t } = useTranslation(); return parameters.length ? <div className="divide-y rounded-lg border bg-card">{parameters.map((item) => <div key={item.name} className="grid gap-2 p-4 sm:grid-cols-[minmax(0,1fr)_8rem_10rem]"><code className="text-xs">{item.name}</code><Badge variant="outline">{item.kind}</Badge><span className="text-xs text-muted-foreground">{item.required ? t("controlStudio.required") : t("controlStudio.optional")}</span></div>)}</div> : <EmptyInline icon={Braces} text={t("controlStudio.noParameters")} />; }
function TestList({ tests }: { tests: ControlTestCase[] }) { const { t } = useTranslation(); return tests.length ? <div className="divide-y rounded-lg border bg-card">{tests.map((item) => <div key={item.name} className="grid gap-2 p-4 sm:grid-cols-[minmax(0,1fr)_7rem_8rem]"><span><strong className="block text-sm">{item.name}</strong><span className="mt-1 block truncate text-xs text-muted-foreground">{item.content}</span></span><RailBadge rail={item.rail_type} /><Badge variant="outline">{item.expected_decision}</Badge></div>)}</div> : <EmptyInline icon={FlaskConical} text={t("controlStudio.noTests")} />; }
function VersionList({ versions }: { versions: NonNullable<NativeControl["versions"]> }) { const { t } = useTranslation(); return versions.length ? <div className="divide-y rounded-lg border bg-card">{versions.map((version) => <div key={version.version} className="grid gap-2 p-4 sm:grid-cols-[5rem_minmax(0,1fr)_13rem]"><strong>v{version.version}</strong><code className="truncate text-[11px] text-muted-foreground">{version.checksum}</code><span className="text-xs text-muted-foreground">{new Date(version.published_at).toLocaleString()}</span></div>)}</div> : <EmptyInline icon={PackageCheck} text={t("controlStudio.noVersions")} />; }
function Compatibility({ control }: { control: NativeControl }) { const { t } = useTranslation(); const mutate = control.draft.rail_bindings.some((item) => item.execution_mode === "mutate"); return <div className="space-y-4"><Alert variant="info"><ShieldCheck /><AlertTitle>{t("controlStudio.nemoNative")}</AlertTitle><AlertDescription>{t("controlStudio.nemoNativeDescription")}</AlertDescription></Alert><ReviewGrid items={[{ label: t("controlStudio.runtime"), value: "LLMRails" }, { label: t("controlStudio.colangVersion"), value: control.draft.colang_version }, { label: t("controlStudio.rails"), value: uniqueRails(control).join(", ") }, { label: t("controlStudio.contentMutation"), value: mutate ? t("common.yes") : t("common.no") }, { label: t("controlStudio.timeoutBudget"), value: `${criticalPath(control.draft.rail_bindings)}ms` }, { label: t("controlStudio.pythonUpload"), value: t("controlStudio.notAllowed") }]} /></div>; }

function StudioSection({ title, description, action, children }: { title: string; description: string; action?: ReactNode; children: ReactNode }) { return <section><header className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between"><div><h3 className="text-lg font-semibold">{title}</h3><p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">{description}</p></div>{action}</header>{children}</section>; }
function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) { return <label className="grid gap-2"><Label>{label}</Label>{children}{hint ? <span className="text-xs leading-5 text-muted-foreground">{hint}</span> : null}</label>; }
function RailBadge({ rail }: { rail: NativeRailType }) { return <Badge variant="outline" className="font-mono text-[10px] uppercase">{rail}</Badge>; }
function EmptyInline({ icon: Icon, text }: { icon: typeof Braces; text: string }) { return <div className="rounded-lg border border-dashed p-8 text-center"><Icon className="mx-auto size-7 text-muted-foreground" /><p className="mt-2 text-xs text-muted-foreground">{text}</p></div>; }
function ReviewGrid({ items }: { items: Array<{ label: string; value: string; mono?: boolean }> }) { return <dl className="divide-y rounded-lg border bg-card px-4">{items.map((item) => <div key={item.label} className="grid gap-1 py-3 text-sm sm:grid-cols-[12rem_minmax(0,1fr)] sm:gap-5"><dt className="text-muted-foreground">{item.label}</dt><dd className={cn("min-w-0 break-words font-medium", item.mono && "font-mono text-xs")}>{item.value || "—"}</dd></div>)}</dl>; }

function emptyDraft(): NativeControlDraft { return { colang_version: "2.x", sources: [{ path: "main.co", content: DEFAULT_COLANG }], parameter_schema: [], rail_bindings: [emptyRail(0)], action_references: [{ name: "TaskLatticeCustomerIdentifierAction", version: "1.0.0" }, { name: "TaskLatticeRecordControlAction", version: "1.0.0" }], model_dependencies: [], prompt_dependencies: [], execution_contract: [], tests: [] }; }
function emptyRail(index: number): ControlRailBinding { return { rail_type: index ? "output" : "input", flow_name: index ? "check_response" : "check_request", execution_mode: index ? "mutate" : "detect", on_unsafe: index ? "redact" : "reject", parallel_group: index ? null : "primary-detection", priority: index ? 100 : null, timeout_ms: 500, failure_mode: "fail_closed", required: true, depends_on: [] }; }
function cloneDraft(draft: NativeControlDraft): NativeControlDraft { return JSON.parse(JSON.stringify(draft)) as NativeControlDraft; }
function replaceAt<T>(items: T[], index: number, item: T, onChange: (items: T[]) => void) { onChange(items.map((current, currentIndex) => currentIndex === index ? item : current)); }
function railReady(rail: ControlRailBinding) { return Boolean(rail.flow_name.trim() && rail.timeout_ms > 0); }
function parameterReady(parameter: ControlParameter) { return Boolean(parameter.name.trim() && (!parameter.required || parameter.kind === "secret" || parameter.default !== "")); }
function testReady(test: ControlTestCase) { return Boolean(test.name.trim() && test.content.trim() && ["input", "output"].includes(test.rail_type)); }
function uniqueRails(control: NativeControl) { return uniqueRailBindings(control.draft.rail_bindings); }
function uniqueRailBindings(rails: ControlRailBinding[]) { return [...new Set(rails.map((item) => item.rail_type))]; }
function criticalPath(rails: ControlRailBinding[]) { const groups = new Map<string, number>(); for (const rail of rails) { const key = rail.parallel_group || `${rail.rail_type}:${rail.flow_name}`; groups.set(key, Math.max(groups.get(key) ?? 0, rail.timeout_ms)); } return [...groups.values()].reduce((total, value) => total + value, 0); }
function lineNumbers(content: string) { return Array.from({ length: content.split("\n").length }, (_, index) => index + 1).join("\n"); }
function errorMessage(error: unknown, fallback: string) { return error instanceof Error ? error.message : fallback; }
