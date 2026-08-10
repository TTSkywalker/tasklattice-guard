import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "@tanstack/react-router";
import {
  ArrowLeft,
  ArrowRight,
  Building2,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  FileText,
  FlaskConical,
  Library,
  LoaderCircle,
  Plus,
  Save,
  ShieldCheck,
  Sparkles,
  Trash2,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";

import { CreationFlow } from "@/components/creation-flow";
import { EntitySheet } from "@/components/entity-sheet";
import { EmptyState, ErrorNotice, InfoNotice, Metric, PageHeader, StateBadge } from "@/components/product-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { queryKeys } from "@/features/query-keys";
import { useAuth } from "@/lib/auth";
import {
  analyzeSafeIntent,
  createSafe,
  createTestCase,
  createTestRun,
  deleteTestCase,
  getSafe,
  getSafes,
  getTestCases,
  getIntentAnalysisStatus,
  getProtectionDefinitions,
  getSafeTemplates,
  getWorkloads,
  updateSafe,
  type SafeProtection,
  type EvaluationCaseResult,
  type IntentAnalysis,
  type TestCase,
  type ProtectionDefinition,
  type Safe,
  type SafeTemplate,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { countTrafficRules } from "@/components/traffic-filter";
import { CreateWorkloadSheet, WorkloadFilterBadges } from "@/routes/protected-workloads";

const defaultRisks: SafeProtection[] = [
  { risk: "topic_control", action: "redirect" },
  { risk: "secrets", action: "reject" },
  { risk: "pii", action: "redact" },
];

export function SafetyProfilesPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const profilesQuery = useQuery({ queryKey: queryKeys.safes, queryFn: getSafes });
  const [createOpen, setCreateOpen] = useState(false);
  const profiles = profilesQuery.data?.items ?? [];

  return (
    <section className="py-6 sm:py-8">
      <PageHeader
        eyebrow={t("profiles.eyebrow")}
        title={t("pages.profiles.title")}
        description={t("profiles.description")}
        action={<Button className="min-h-11 self-start" onClick={() => setCreateOpen(true)}><Plus />{t("profiles.create")}</Button>}
      />

      {profilesQuery.error ? <div className="mt-5"><ErrorNotice error={profilesQuery.error} /></div> : null}
      {profilesQuery.isLoading ? <Skeleton className="mt-5 h-80 rounded-xl" /> : null}
      {!profilesQuery.isLoading && !profiles.length ? (
        <div className="mt-5">
          <EmptyState
            title={t("profiles.emptyTitle")}
            description={t("profiles.emptyDescription")}
            action={<Button onClick={() => setCreateOpen(true)}><Plus />{t("profiles.createFirst")}</Button>}
          />
        </div>
      ) : null}

      {profiles.length ? (
        <section className="mt-5 overflow-hidden rounded-xl border bg-card shadow-xs">
          <div className="flex items-center justify-between gap-3 border-b bg-muted/30 px-5 py-3">
            <p className="text-xs font-medium text-muted-foreground">{t("profiles.registry", { count: profiles.length })}</p>
            <p className="hidden text-xs text-muted-foreground sm:block">{t("profiles.openSafeHint")}</p>
          </div>
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="min-w-64 px-5">{t("profiles.safe")}</TableHead>
                <TableHead>{t("common.status")}</TableHead>
                <TableHead className="hidden lg:table-cell">{t("profiles.protections")}</TableHead>
                <TableHead>{t("profiles.testEvidence")}</TableHead>
                <TableHead className="hidden xl:table-cell">{t("profiles.workloads")}</TableHead>
                <TableHead className="hidden xl:table-cell">{t("profiles.lastUpdated")}</TableHead>
                <TableHead className="w-12"><span className="sr-only">{t("profiles.openDetails")}</span></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {profiles.map((profile) => (
                <TableRow key={profile.id} className="group">
                  <TableCell className="px-5 py-4 whitespace-normal">
                    <Link
                      to="/governance/safes/$safeId"
                      params={{ safeId: profile.id }}
                      className="block rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      <strong className="text-sm font-medium text-foreground group-hover:text-primary">{profile.name}</strong>
                      <span className="mt-1 block max-w-xl line-clamp-2 text-xs leading-5 text-muted-foreground">{profile.purpose}</span>
                    </Link>
                  </TableCell>
                  <TableCell><StateBadge state={profile.status} /></TableCell>
                  <TableCell className="hidden tabular-nums lg:table-cell">{profile.protections.length}</TableCell>
                  <TableCell>
                    <p className="text-sm tabular-nums">{t("profiles.testCount", { count: profile.test_case_count })}</p>
                    <p className="mt-1 text-xs text-muted-foreground">{profile.latest_test_run ? t("profiles.compliance", { rate: profile.latest_test_run.metrics.compliance_rate }) : t("profiles.noEvidence")}</p>
                  </TableCell>
                  <TableCell className="hidden tabular-nums xl:table-cell">{profile.workload_count}</TableCell>
                  <TableCell className="hidden text-xs text-muted-foreground xl:table-cell">{new Date(profile.updated_at).toLocaleDateString(i18n.language)}</TableCell>
                  <TableCell className="pr-4">
                    <Button asChild size="icon" variant="ghost" aria-label={t("profiles.openNamedSafe", { name: profile.name })}>
                      <Link to="/governance/safes/$safeId" params={{ safeId: profile.id }}><ChevronRight /></Link>
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </section>
      ) : null}

      <CreateProfileSheet
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={async (id) => {
          setCreateOpen(false);
          await queryClient.invalidateQueries({ queryKey: queryKeys.safes });
          await navigate({ to: "/governance/safes/$safeId", params: { safeId: id } });
        }}
      />
    </section>
  );
}

export function SafeDetailPage() {
  const { safeId } = useParams({ from: "/governance/safes/$safeId" });
  const queryClient = useQueryClient();
  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.safes }),
      queryClient.invalidateQueries({ queryKey: queryKeys.safe(safeId) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.testCases(safeId) }),
    ]);
  };
  return <ProfileDetail profileId={safeId} onRefresh={refresh} />;
}

function ProfileDetail({ profileId, onRefresh }: { profileId: string; onRefresh: () => Promise<void> }) {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const profileQuery = useQuery({ queryKey: queryKeys.safe(profileId), queryFn: () => getSafe(profileId), enabled: Boolean(profileId) });
  const casesQuery = useQuery({ queryKey: queryKeys.testCases(profileId), queryFn: () => getTestCases(profileId), enabled: Boolean(profileId) });
  const templatesQuery = useQuery({ queryKey: queryKeys.safeTemplates, queryFn: getSafeTemplates });
  const protectionsQuery = useQuery({ queryKey: queryKeys.protectionDefinitions, queryFn: getProtectionDefinitions });
  const workloadsQuery = useQuery({ queryKey: queryKeys.workloads, queryFn: getWorkloads });
  const [editOpen, setEditOpen] = useState(false);
  const [addCaseOpen, setAddCaseOpen] = useState(false);
  const [applyOpen, setApplyOpen] = useState(false);

  const test = useMutation({
    mutationFn: () => createTestRun(profileId),
    onSuccess: async (run) => {
      await onRefresh();
      await queryClient.invalidateQueries({ queryKey: queryKeys.workloads });
      toast[run.status === "passed" ? "success" : "error"](
        run.status === "passed" ? t("profiles.testsPassed") : t("profiles.testsFailed", { rate: run.metrics.compliance_rate }),
      );
    },
    onError: (error) => notifyError(error, t("profiles.operationFailed")),
  });

  const removeCase = useMutation({
    mutationFn: (caseId: string) => deleteTestCase(caseId),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.testCases(profileId) }),
        onRefresh(),
      ]);
      toast.success(t("profiles.caseRemoved"));
    },
    onError: (error) => notifyError(error, t("profiles.operationFailed")),
  });

  const profile = profileQuery.data;
  if (profileQuery.error) return <section className="py-6 sm:py-8"><SafeBackLink /><div className="mt-4"><ErrorNotice error={profileQuery.error} /></div></section>;
  if (profileQuery.isLoading || !profile) return <section className="py-6 sm:py-8"><SafeBackLink /><Skeleton className="mt-4 h-[680px] rounded-xl" /></section>;

  const testCases = casesQuery.data?.items ?? [];
  const template = templatesQuery.data?.items.find((item) => item.id === profile.source_template_id);
  const definitions = protectionsQuery.data?.items ?? [];
  const workloads = (workloadsQuery.data?.items ?? []).filter((item) => item.safe_id === profile.id);

  return (
    <section className="min-w-0 py-6 sm:py-8">
      <SafeBackLink />
      <div className="mt-4">
        <PageHeader
          eyebrow={template ? t("profiles.builtFrom", { name: template.name }) : t("profiles.customIntent")}
          title={profile.name}
          description={profile.purpose}
          action={<div className="flex flex-wrap gap-2">
            <Button variant="outline" className="min-h-11" onClick={() => setEditOpen(true)}><Save />{t("profiles.editIntent")}</Button>
            {profile.tested_current ? (
              <Button className="min-h-11" onClick={() => setApplyOpen(true)}><Building2 />{t("profiles.applyWorkload")}</Button>
            ) : (
              <Button className="min-h-11" disabled={test.isPending || !testCases.length} onClick={() => test.mutate()}><FlaskConical />{t(test.isPending ? "profiles.runningTests" : "profiles.runReviewed")}</Button>
            )}
          </div>}
        />
      </div>

      <div className="mt-5 overflow-hidden rounded-xl border bg-card shadow-xs">
        <div className="flex items-center justify-between gap-3 border-b bg-muted/20 px-4 py-3 sm:px-5">
          <StateBadge state={profile.status} />
          <span className="text-xs text-muted-foreground">{t("profiles.lastUpdatedValue", { date: new Date(profile.updated_at).toLocaleString(i18n.language) })}</span>
        </div>
        <WorkflowStatus profile={profile} testCaseCount={testCases.length} onApply={() => setApplyOpen(true)} />

        <div className="grid grid-cols-2 gap-3 border-b p-4 sm:grid-cols-4">
          <Metric label={t("profiles.protections")} value={profile.protections.length} detail={t("profiles.reviewedControls")} />
          <Metric label={t("profiles.testCases")} value={testCases.length} detail={t("profiles.visibleEditable")} />
          <Metric label={t("profiles.testStatus")} value={t(profile.tested_current ? "profiles.passed" : "profiles.required")} detail={profile.latest_test_run ? t("profiles.compliance", { rate: profile.latest_test_run.metrics.compliance_rate }) : t("profiles.noEvidence")} />
          <Metric label={t("profiles.workloads")} value={profile.workload_count} detail={t("profiles.trafficAssignments")} />
        </div>

        <Tabs defaultValue="intent" className="p-5 sm:p-6">
        <TabsList className="min-h-10 w-full justify-start rounded-lg bg-muted p-1">
          <TabsTrigger value="intent" className="min-h-8 rounded-md px-3">{t("profiles.intent")}</TabsTrigger>
          <TabsTrigger value="protections" className="min-h-8 rounded-md px-3">{t("profiles.protections")}</TabsTrigger>
          <TabsTrigger value="tests" className="min-h-8 rounded-md px-3">{t("profiles.testCases")}</TabsTrigger>
          <TabsTrigger value="workloads" className="min-h-8 rounded-md px-3">{t("profiles.workloads")}</TabsTrigger>
        </TabsList>

        <TabsContent value="intent" className="mt-5 grid gap-5 xl:grid-cols-2">
          <TopicPanel title={t("profiles.allowedDomains")} items={profile.allowed_topics} empty={t(template ? "profiles.templateDefined" : "profiles.noAllowed")} />
          <TopicPanel title={t("profiles.restrictedDomains")} items={profile.restricted_topics} empty={t(template ? "profiles.templateDefined" : "profiles.noRestricted")} danger />
          <section className="rounded-lg border bg-card p-4 xl:col-span-2">
            <h3 className="text-lg">{t("profiles.decisionPosture")}</h3>
            <div className="mt-4 grid gap-3 sm:grid-cols-3">
              <Fact label={t("profiles.evaluation")} value={t(profile.safety_level === "strict" ? "profiles.strict" : "profiles.balanced")} />
              <Fact label={t("profiles.modelOutput")} value={deliveryLabel(profile.output_delivery, t)} />
              <Fact label={t("profiles.ownership")} value={t("profiles.organizationOwned")} />
            </div>
          </section>
          <InfoNotice title={t("profiles.runtimeBoundary")}>
            {t("profiles.runtimeBoundaryDescription")}
          </InfoNotice>
        </TabsContent>

        <TabsContent value="protections" className="mt-5 space-y-5">
          {template ? <TemplateProtectionSummary template={template} parameters={profile.template_parameters} /> : null}
          <section className="overflow-hidden rounded-lg border bg-card">
            <div className="grid grid-cols-[minmax(0,1fr)_140px_150px] border-b bg-muted/40 px-4 py-3 text-xs font-medium text-muted-foreground"><span>{t("profiles.protection")}</span><span>{t("profiles.modelBoundary")}</span><span>{t("profiles.whenDetected")}</span></div>
            <div className="divide-y divide-border">
              {profile.protections.map((risk) => <RiskRow key={risk.risk} risk={risk} definition={definitions.find((item) => item.id === risk.risk)} template={template} />)}
            </div>
          </section>
        </TabsContent>

        <TabsContent value="tests" className="mt-5 space-y-5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div><h3 className="text-lg">{t("profiles.reviewedCases")}</h3><p className="mt-1 text-xs text-muted-foreground">{t("profiles.reviewedCasesDescription")}</p></div>
            <div className="flex gap-2"><Button variant="outline" onClick={() => setAddCaseOpen(true)}><Plus />{t("profiles.addCase")}</Button><Button disabled={test.isPending || !testCases.length} onClick={() => test.mutate()}><FlaskConical />{t(test.isPending ? "profiles.running" : "profiles.runTests")}</Button></div>
          </div>
          {!profile.tested_current ? <InfoNotice title={t("profiles.notReady")}>{t("profiles.notReadyDescription")}</InfoNotice> : null}
          {casesQuery.isLoading ? <Skeleton className="h-48 rounded-lg" /> : testCases.length ? (
            <section className="overflow-hidden rounded-lg border bg-card">
              <div className="divide-y divide-border">{testCases.map((item) => <TestCaseRow key={item.id} item={item} onDelete={() => removeCase.mutate(item.id)} deleting={removeCase.isPending} />)}</div>
            </section>
          ) : <EmptyState title={t("profiles.noCases")} description={t("profiles.noCasesDescription")} action={<Button onClick={() => setAddCaseOpen(true)}><Plus />{t("profiles.addTestCase")}</Button>} />}
          {profile.latest_test_run ? <TestEvidence profile={profile} testCases={testCases} /> : null}
        </TabsContent>

        <TabsContent value="workloads" className="mt-5 space-y-4">
          <div className="flex items-center justify-between gap-3"><div><h3 className="text-lg">{t("profiles.protectedWorkloads")}</h3><p className="mt-1 text-xs text-muted-foreground">{t("profiles.protectedWorkloadsDescription")}</p></div>{profile.tested_current ? <Button onClick={() => setApplyOpen(true)}><Building2 />{t("profiles.apply")}</Button> : null}</div>
          {workloads.length ? <div className="overflow-hidden rounded-lg border bg-card"><div className="divide-y divide-border">{workloads.map((item) => <div key={item.id} className="grid gap-3 p-4 sm:grid-cols-[minmax(0,1fr)_minmax(240px,1fr)_auto] sm:items-center"><div><strong className="text-sm font-medium">{item.name}</strong><p className="mt-1 text-xs text-muted-foreground">{countTrafficRules(item.filter) ? t("workloads.conditionCount", { count: countTrafficRules(item.filter) }) : t("workloads.allTraffic")}</p></div><WorkloadFilterBadges workload={item} /><StateBadge state={item.enabled ? "protected" : "paused"} /></div>)}</div></div> : <EmptyState title={t("profiles.noWorkloads")} description={t(profile.tested_current ? "profiles.noWorkloadsReady" : "profiles.noWorkloadsNotReady")} action={profile.tested_current ? <Button onClick={() => setApplyOpen(true)}><Building2 />{t("profiles.applyWorkload")}</Button> : undefined} />}
        </TabsContent>
        </Tabs>
      </div>

      <EditProfileSheet profile={profile} open={editOpen} onOpenChange={setEditOpen} onSaved={async () => { setEditOpen(false); await onRefresh(); }} />
      <AddTestCaseSheet profile={profile} open={addCaseOpen} onOpenChange={setAddCaseOpen} onCreated={async () => { setAddCaseOpen(false); await onRefresh(); }} />
      <CreateWorkloadSheet
        open={applyOpen}
        onOpenChange={setApplyOpen}
        safes={[profile]}
        initialSafeId={profile.id}
        onCreated={async () => {
          setApplyOpen(false);
          await Promise.all([onRefresh(), queryClient.invalidateQueries({ queryKey: queryKeys.workloads }), queryClient.invalidateQueries({ queryKey: queryKeys.metrics })]);
        }}
      />
    </section>
  );
}

function SafeBackLink() {
  const { t } = useTranslation();
  return <Button asChild variant="ghost" className="-ml-3 min-h-10 px-3 text-muted-foreground"><Link to="/governance/safes"><ArrowLeft />{t("profiles.backToSafes")}</Link></Button>;
}

function WorkflowStatus({ profile, testCaseCount, onApply }: { profile: Safe; testCaseCount: number; onApply: () => void }) {
  const { t } = useTranslation();
  const steps = [
    { label: t("profiles.flowIntent"), complete: Boolean(profile.purpose) },
    { label: t("profiles.flowProtections"), complete: profile.protections.length > 0 },
    { label: t(profile.tested_current ? "profiles.flowTestsPassed" : "profiles.flowTestsRun", { count: testCaseCount }), complete: profile.tested_current },
    { label: profile.workload_count ? t("profiles.flowWorkloads", { count: profile.workload_count }) : t("profiles.flowApply"), complete: profile.workload_count > 0 },
  ];
  return (
    <section aria-label={t("profiles.workflowLabel")} className="grid border-b bg-muted/20 sm:grid-cols-4">
      {steps.map((step, index) => (
        <div key={step.label} className="flex min-h-14 items-center gap-2 border-b px-4 py-3 last:border-b-0 sm:border-b-0 sm:border-r sm:last:border-r-0">
          <span className={cn("grid size-6 shrink-0 place-items-center rounded-full border bg-card font-mono text-[10px] text-muted-foreground", step.complete && "border-emerald-200 bg-emerald-50 text-emerald-700")}>
            {step.complete ? <Check className="size-3.5" /> : index + 1}
          </span>
          {index === 3 && profile.tested_current && !profile.workload_count ? <button type="button" className="text-left text-xs font-medium text-primary hover:underline" onClick={onApply}>{step.label}</button> : <span className="text-xs font-medium">{step.label}</span>}
        </div>
      ))}
    </section>
  );
}

function CreateProfileSheet({ open, onOpenChange, onCreated }: { open: boolean; onOpenChange: (open: boolean) => void; onCreated: (id: string) => void }) {
  const { t, i18n } = useTranslation();
  const { user } = useAuth();
  const templatesQuery = useQuery({ queryKey: queryKeys.safeTemplates, queryFn: getSafeTemplates });
  const protectionsQuery = useQuery({ queryKey: queryKeys.protectionDefinitions, queryFn: getProtectionDefinitions });
  const [step, setStep] = useState(0);
  const [mode, setMode] = useState<"template" | "blank">("template");
  const intentAnalysisStatusQuery = useQuery({
    queryKey: queryKeys.intentAnalysisStatus,
    queryFn: getIntentAnalysisStatus,
    enabled: open && mode === "blank",
    retry: false,
  });
  const [templateId, setTemplateId] = useState("");
  const [search, setSearch] = useState("");
  const [name, setName] = useState("");
  const [purpose, setPurpose] = useState("");
  const [allowed, setAllowed] = useState("");
  const [restricted, setRestricted] = useState("");
  const [risks, setRisks] = useState<SafeProtection[]>(defaultRisks);
  const [parameters, setParameters] = useState<Record<string, string>>({});
  const [analysis, setAnalysis] = useState<IntentAnalysis | null>(null);
  const [analyzedPurpose, setAnalyzedPurpose] = useState("");
  const creationSteps = [
    { label: t("profiles.stepStart"), description: t("profiles.stepStartDescription") },
    { label: t("profiles.stepIntent"), description: t("profiles.stepIntentDescription") },
    { label: t("profiles.stepProtections"), description: t("profiles.stepProtectionsDescription") },
  ];

  const templates = templatesQuery.data?.items ?? [];
  const selected = templates.find((item) => item.id === templateId);
  const visibleTemplates = templates.filter((item) => `${item.name} ${item.description} ${item.domain}`.toLowerCase().includes(search.toLowerCase()));
  const definitions = protectionsQuery.data?.items.filter((item) => item.id !== "builtin_content_filter") ?? [];
  const missingParameter = selected?.parameters?.some((item) => item.required && !parameters[item.name]?.trim());
  const invalidCustomTopics = mode === "blank" && risks.some((item) => item.risk === "topic_control") && (!lines(allowed).length || !lines(restricted).length);
  const canContinue = step === 0 ? mode === "blank" || Boolean(templateId) : step === 1 ? Boolean(name.trim()) && (mode === "template" ? !missingParameter : Boolean(purpose.trim())) : true;
  const profileLanguage = user?.preferred_language ?? (i18n.language.toLowerCase().startsWith("zh") ? "zh-CN" : "en");
  const analysisStale = Boolean(analysis && purpose.trim() !== analyzedPurpose);

  const mutation = useMutation({
    mutationFn: createSafe,
    onSuccess: (profile) => { toast.success(t("profiles.created", { name: profile.name })); onCreated(profile.id); },
    onError: (error) => notifyError(error, t("profiles.operationFailed")),
  });

  const analyzeIntent = useMutation({
    mutationFn: () => analyzeSafeIntent({ purpose: purpose.trim(), language: profileLanguage }),
    onSuccess: (result) => {
      setAllowed(result.allowed_topics.join("\n"));
      setRestricted(result.restricted_topics.join("\n"));
      setAnalysis(result);
      setAnalyzedPurpose(purpose.trim());
      setRisks((current) => current.some((item) => item.risk === "topic_control") ? current : [...current, { risk: "topic_control", action: "redirect" }]);
      toast.success(t("profiles.analysisSucceeded"));
    },
    onError: (error) => notifyError(error, t("profiles.operationFailed")),
  });

  useEffect(() => {
    if (open) {
      setStep(0); setMode("template"); setTemplateId(""); setSearch(""); setName(""); setPurpose(""); setAllowed(""); setRestricted(""); setRisks(defaultRisks); setParameters({}); setAnalysis(null); setAnalyzedPurpose("");
    }
  }, [open]);

  const submit = () => mutation.mutate(mode === "template"
    ? { name, template_id: templateId, template_parameters: parameters }
    : { name, purpose, allowed_topics: lines(allowed), restricted_topics: lines(restricted), protections: risks, safety_level: "balanced", output_delivery: "window_buffered" });

  return (
    <EntitySheet
      open={open}
      onOpenChange={onOpenChange}
      eyebrow={t("profiles.createEyebrow")}
      title={t("profiles.create")}
      description={t("profiles.createDescription")}
      width="xl"
      footer={
        <>
          <Button variant="outline" onClick={() => step ? setStep(step - 1) : onOpenChange(false)}>{step ? <><ArrowLeft />{t("profiles.back")}</> : t("common.cancel")}</Button>
          {step < creationSteps.length - 1
            ? <Button disabled={!canContinue} onClick={() => setStep(step + 1)}>{t("profiles.continue")}<ArrowRight /></Button>
            : <Button disabled={!name.trim() || !risks.length || invalidCustomTopics || mutation.isPending} onClick={submit}><ShieldCheck />{t(mutation.isPending ? "common.creating" : "profiles.createShort")}</Button>}
        </>
      }
    >
      <CreationFlow currentStep={step} onStepChange={setStep} progressLabel={t("profiles.create")} steps={creationSteps}>
        {step === 0 ? (
          <div className="space-y-5">
            <div className="grid gap-3 sm:grid-cols-2">
              <SourceChoice active={mode === "template"} icon={Library} title={t("profiles.builtinTemplate")} description={t("profiles.builtinTemplateDescription")} onClick={() => setMode("template")} />
              <SourceChoice active={mode === "blank"} icon={FileText} title={t("profiles.blankIntent")} description={t("profiles.blankIntentDescription")} onClick={() => setMode("blank")} />
            </div>
            {mode === "template" ? (
              <section>
                <label className="grid gap-2 text-sm font-medium">{t("profiles.findTemplate")}<Input className="min-h-11 rounded-lg bg-card" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="MAS, PDPA, PII, Topic Control…" /></label>
                <div className="mt-3 grid max-h-[390px] gap-2 overflow-y-auto pr-1 sm:grid-cols-2">
                  {visibleTemplates.map((item) => (
                    <button key={item.id} type="button" aria-pressed={templateId === item.id} onClick={() => { setTemplateId(item.id); setName(item.name); setParameters({}); }} className={cn("min-h-36 rounded-lg border bg-card p-4 text-left transition-colors hover:border-primary/60 focus-visible:outline-2 focus-visible:outline-ring", templateId === item.id && "border-primary/40 bg-accent")}>
                      <span className="flex items-start justify-between gap-3"><strong className="font-medium">{item.name}</strong>{templateId === item.id ? <Check className="size-4 text-primary" /> : null}</span>
                      <span className="mt-2 block text-xs leading-5 text-muted-foreground">{item.description}</span>
                      <span className="mt-3 block text-xs font-medium text-muted-foreground">{t("profiles.localControls", { count: item.controls?.length ?? 0, version: item.version })}</span>
                    </button>
                  ))}
                </div>
              </section>
            ) : <InfoNotice title={t("profiles.blankStructured")}>{t("profiles.blankStructuredDescription")}</InfoNotice>}
          </div>
        ) : null}

        {step === 1 ? (
          <div className="grid gap-5">
            <Field label={t("profiles.profileName")}><Input autoFocus className="min-h-11 rounded-lg bg-card" value={name} onChange={(event) => setName(event.target.value)} placeholder="Finance Model Safety" /></Field>
            {mode === "template" && selected ? (
              <>
                <TemplateProtectionSummary template={selected} parameters={parameters} compact />
                {selected.parameters?.map((parameter) => (
                  <Field key={parameter.name} label={`${parameter.label}${parameter.required ? " *" : ""}`} hint={parameter.description}>
                    {parameter.kind === "multiline" ? <Textarea className="min-h-28 rounded-lg bg-card" value={parameters[parameter.name] ?? ""} onChange={(event) => setParameters((current) => ({ ...current, [parameter.name]: event.target.value }))} placeholder={parameter.placeholder} /> : <Input className="min-h-11 rounded-lg bg-card" value={parameters[parameter.name] ?? ""} onChange={(event) => setParameters((current) => ({ ...current, [parameter.name]: event.target.value }))} placeholder={parameter.placeholder} />}
                  </Field>
                ))}
              </>
            ) : (
              <>
                <Field label={t("profiles.businessPurpose")} hint={t("profiles.businessPurposeHint")}><Textarea className="min-h-32 rounded-lg bg-card" value={purpose} onChange={(event) => setPurpose(event.target.value)} placeholder="Finance employees use this assistant to analyze approved company and market data." /></Field>
                <section className="rounded-lg border bg-muted/30 p-4" aria-live="polite">
                  <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                    <div className="flex min-w-0 gap-3">
                      <span className="grid size-9 shrink-0 place-items-center rounded-lg border bg-card text-primary"><Sparkles className="size-4" /></span>
                      <div><h3 className="text-sm font-medium">{t("profiles.analyzeTitle")}</h3><p className="mt-1 max-w-2xl text-xs leading-5 text-muted-foreground">{t("profiles.analyzeDescription")}</p></div>
                    </div>
                    <Button
                      type="button"
                      variant="outline"
                      className="min-h-11 shrink-0 bg-card"
                      disabled={purpose.trim().length < 20 || intentAnalysisStatusQuery.isLoading || !intentAnalysisStatusQuery.data?.available || analyzeIntent.isPending}
                      onClick={() => analyzeIntent.mutate()}
                    >
                      {analyzeIntent.isPending ? <LoaderCircle className="animate-spin" /> : <Sparkles />}
                      {t(analyzeIntent.isPending ? "profiles.analyzingIntent" : analysis ? "profiles.reanalyzeAction" : "profiles.analyzeAction")}
                    </Button>
                  </div>
                  {intentAnalysisStatusQuery.isLoading ? <p className="mt-3 text-xs text-muted-foreground">{t("profiles.analysisChecking")}</p> : null}
                  {!intentAnalysisStatusQuery.isLoading && !intentAnalysisStatusQuery.data?.available ? <p className="mt-3 text-xs text-amber-700 dark:text-amber-300">{t("profiles.analysisUnavailable")}</p> : null}
                  {analysisStale ? <p className="mt-3 text-xs text-amber-700 dark:text-amber-300">{t("profiles.analysisStale")}</p> : null}
                </section>
                {analysis ? (
                  <section className="rounded-lg border border-emerald-200 bg-emerald-50/50 p-4 dark:border-emerald-900 dark:bg-emerald-950/20">
                    <div className="flex items-start gap-3"><CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-700 dark:text-emerald-400" /><div><h3 className="text-sm font-medium">{t("profiles.analysisComplete")}</h3><p className="mt-1 text-xs leading-5 text-muted-foreground">{t("profiles.analysisCompleteDescription")}</p></div></div>
                    <dl className="mt-4 grid gap-3 text-xs">
                      <div><dt className="font-medium text-muted-foreground">{t("profiles.analysisSummary")}</dt><dd className="mt-1 leading-5">{analysis.summary}</dd></div>
                      {analysis.review_notes.length ? <div><dt className="font-medium text-muted-foreground">{t("profiles.analysisReviewNotes")}</dt><dd className="mt-1"><ul className="list-disc space-y-1 pl-4 leading-5">{analysis.review_notes.map((note) => <li key={note}>{note}</li>)}</ul></dd></div> : null}
                    </dl>
                  </section>
                ) : null}
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label={t("profiles.allowedDomains")} hint={t("profiles.onePerLine")}><Textarea className="min-h-36 rounded-lg bg-card" value={allowed} onChange={(event) => setAllowed(event.target.value)} placeholder={"Financial data analysis\nAccounting and reporting\nSQL, Python, and statistics for finance"} /></Field>
                  <Field label={t("profiles.restrictedDomains")} hint={t("profiles.restrictedHint")}><Textarea className="min-h-36 rounded-lg bg-card" value={restricted} onChange={(event) => setRestricted(event.target.value)} placeholder={"Standalone physics questions\nBiomedical advice or research\nManufacturing process design\nChemical refining instructions"} /></Field>
                </div>
              </>
            )}
          </div>
        ) : null}

        {step === 2 ? (
          <div className="space-y-5">
            {mode === "template" && selected ? (
              <TemplateProtectionSummary template={selected} parameters={parameters} />
            ) : (
              <>
                <InfoNotice title={t("profiles.reviewBefore")}>{t("profiles.reviewBeforeDescription")}</InfoNotice>
                <ProtectionEditor definitions={definitions} risks={risks} onChange={setRisks} />
                {invalidCustomTopics ? <p className="text-sm text-destructive">{t("profiles.topicRequired")}</p> : null}
              </>
            )}
            <InfoNotice title={t("profiles.nextTitle")}>{t("profiles.nextDescription")}</InfoNotice>
          </div>
        ) : null}
      </CreationFlow>
    </EntitySheet>
  );
}

function EditProfileSheet({ profile, open, onOpenChange, onSaved }: { profile: Safe; open: boolean; onOpenChange: (open: boolean) => void; onSaved: () => void }) {
  const { t } = useTranslation();
  const protectionsQuery = useQuery({ queryKey: queryKeys.protectionDefinitions, queryFn: getProtectionDefinitions });
  const [name, setName] = useState(profile.name);
  const [purpose, setPurpose] = useState(profile.purpose);
  const [allowed, setAllowed] = useState(profile.allowed_topics.join("\n"));
  const [restricted, setRestricted] = useState(profile.restricted_topics.join("\n"));
  const [risks, setRisks] = useState(profile.protections);
  const [level, setLevel] = useState(profile.safety_level);
  const [delivery, setDelivery] = useState(profile.output_delivery);

  useEffect(() => {
    if (open) {
      setName(profile.name); setPurpose(profile.purpose); setAllowed(profile.allowed_topics.join("\n")); setRestricted(profile.restricted_topics.join("\n")); setRisks(profile.protections); setLevel(profile.safety_level); setDelivery(profile.output_delivery);
    }
  }, [open, profile]);

  const mutation = useMutation({
    mutationFn: () => updateSafe(profile.id, { name, purpose, allowed_topics: lines(allowed), restricted_topics: lines(restricted), protections: risks, safety_level: level, output_delivery: delivery }),
    onSuccess: () => { toast.success(t("profiles.updated")); onSaved(); },
    onError: (error) => notifyError(error, t("profiles.operationFailed")),
  });
  const definitions = protectionsQuery.data?.items.filter((item) => item.id !== "builtin_content_filter") ?? [];
  const editableRisks = risks.filter((item) => item.risk !== "builtin_content_filter");

  return (
    <EntitySheet open={open} onOpenChange={onOpenChange} eyebrow={t("profiles.editEyebrow")} title={t("profiles.editTitle", { name: profile.name })} description={t("profiles.editDescription")} width="xl" footer={<><Button variant="outline" onClick={() => onOpenChange(false)}>{t("common.cancel")}</Button><Button disabled={!name.trim() || !purpose.trim() || !risks.length || mutation.isPending} onClick={() => mutation.mutate()}><Save />{t(mutation.isPending ? "common.saving" : "common.save")}</Button></>}>
      <div className="grid gap-5">
        <Field label={t("common.name")}><Input className="min-h-11 rounded-lg bg-card" value={name} onChange={(event) => setName(event.target.value)} /></Field>
        <Field label={t("profiles.businessPurpose")}><Textarea className="min-h-32 rounded-lg bg-card" value={purpose} onChange={(event) => setPurpose(event.target.value)} /></Field>
        <div className="grid gap-4 sm:grid-cols-2"><Field label={t("profiles.allowedDomains")}><Textarea className="min-h-32 rounded-lg bg-card" value={allowed} onChange={(event) => setAllowed(event.target.value)} placeholder={t("profiles.onePerLine")} /></Field><Field label={t("profiles.restrictedDomains")}><Textarea className="min-h-32 rounded-lg bg-card" value={restricted} onChange={(event) => setRestricted(event.target.value)} placeholder={t("profiles.onePerLine")} /></Field></div>
        <div className="grid gap-4 sm:grid-cols-2"><Field label={t("profiles.evaluationMode")}><Select value={level} onValueChange={(value) => setLevel(value as typeof level)}><SelectTrigger className="min-h-11 rounded-lg bg-card"><SelectValue /></SelectTrigger><SelectContent className="rounded-lg"><SelectItem value="balanced">{t("profiles.balanced")}</SelectItem><SelectItem value="strict">{t("profiles.strict")}</SelectItem></SelectContent></Select></Field><Field label={t("profiles.modelOutput")}><Select value={delivery} onValueChange={(value) => setDelivery(value as typeof delivery)}><SelectTrigger className="min-h-11 rounded-lg bg-card"><SelectValue /></SelectTrigger><SelectContent className="rounded-lg"><SelectItem value="interruptible">{t("profiles.outputRealtime")}</SelectItem><SelectItem value="window_buffered">{t("profiles.outputWindow")}</SelectItem><SelectItem value="full_buffered">{t("profiles.outputFull")}</SelectItem></SelectContent></Select></Field></div>
        {profile.source_template_id ? <InfoNotice title={t("profiles.builtinAttached")}>{t("profiles.builtinAttachedDescription")}</InfoNotice> : null}
        <ProtectionEditor definitions={definitions} risks={editableRisks} onChange={(next) => setRisks([...profile.protections.filter((item) => item.risk === "builtin_content_filter"), ...next])} />
      </div>
    </EntitySheet>
  );
}

function AddTestCaseSheet({ profile, open, onOpenChange, onCreated }: { profile: Safe; open: boolean; onOpenChange: (open: boolean) => void; onCreated: () => void }) {
  const { t } = useTranslation();
  const [name, setName] = useState("");
  const [risk, setRisk] = useState(profile.protections[0]?.risk ?? "");
  const [phase, setPhase] = useState<"input" | "output">("input");
  const [content, setContent] = useState("");
  const [expected, setExpected] = useState<TestCase["expected_decision"]>("block");
  const [trustedInstruction, setTrustedInstruction] = useState("");
  const [targetSource, setTargetSource] = useState<TestCase["target_source"]>("user_input");
  const promptSecurity = risk === "prompt_injection" || risk === "jailbreak";
  useEffect(() => { if (open) { const initialRisk = profile.protections[0]?.risk ?? ""; const initialPromptSecurity = initialRisk === "prompt_injection" || initialRisk === "jailbreak"; setName(""); setRisk(initialRisk); setPhase("input"); setContent(""); setExpected("block"); setTrustedInstruction(initialPromptSecurity ? t("profiles.defaultTrustedInstruction", { purpose: profile.purpose }) : ""); setTargetSource("user_input"); } }, [open, profile.purpose, profile.protections, t]);
  const mutation = useMutation({ mutationFn: () => createTestCase(profile.id, { name, risk, phase, content, expected_decision: expected, trusted_instruction: trustedInstruction, target_source: targetSource }), onSuccess: () => { toast.success(t("profiles.customAdded")); onCreated(); }, onError: (error) => notifyError(error, t("profiles.operationFailed")) });
  function changeRisk(value: string) {
    setRisk(value);
    if (value === "prompt_injection" || value === "jailbreak") {
      setPhase("input");
      setTrustedInstruction((current) => current || t("profiles.defaultTrustedInstruction", { purpose: profile.purpose }));
    }
  }
  return (
    <EntitySheet open={open} onOpenChange={onOpenChange} eyebrow={t("profiles.testEyebrow")} title={t("profiles.testTitle")} description={t("profiles.testDescription")} width="md" footer={<><Button variant="outline" onClick={() => onOpenChange(false)}>{t("common.cancel")}</Button><Button disabled={!name.trim() || !risk || !content.trim() || mutation.isPending} onClick={() => mutation.mutate()}><Plus />{t(mutation.isPending ? "profiles.adding" : "profiles.addCase")}</Button></>}>
      <div className="grid gap-5">
        <Field label={t("profiles.caseName")}><Input autoFocus className="min-h-11 rounded-lg bg-card" value={name} onChange={(event) => setName(event.target.value)} placeholder="Allow finance analysis of chemical company" /></Field>
        <div className="grid gap-4 sm:grid-cols-2"><Field label={t("profiles.protection")}><Select value={risk} onValueChange={changeRisk}><SelectTrigger className="min-h-11 rounded-lg bg-card"><SelectValue /></SelectTrigger><SelectContent>{profile.protections.map((item) => <SelectItem key={item.risk} value={item.risk}>{riskLabel(item.risk, t)}</SelectItem>)}</SelectContent></Select></Field><Field label={t("profiles.modelBoundary")}><Select disabled={promptSecurity} value={phase} onValueChange={(value) => setPhase(value as typeof phase)}><SelectTrigger className="min-h-11 rounded-lg bg-card"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="input">{t("profiles.input")}</SelectItem><SelectItem value="output">{t("profiles.output")}</SelectItem></SelectContent></Select></Field></div>
        {promptSecurity ? (
          <section className="grid gap-4 rounded-lg border bg-muted/30 p-4">
            <div><h3 className="text-sm font-medium">{t("profiles.promptTrustBoundary")}</h3><p className="mt-1 text-xs leading-5 text-muted-foreground">{t("profiles.promptTrustBoundaryDescription")}</p></div>
            <Field label={t("profiles.trustedInstruction")} hint={t("profiles.trustedInstructionHint")}><Textarea className="min-h-32 rounded-lg bg-card" value={trustedInstruction} onChange={(event) => setTrustedInstruction(event.target.value)} /></Field>
            <Field label={t("profiles.untrustedSource")}><Select value={targetSource} onValueChange={(value) => setTargetSource(value as typeof targetSource)}><SelectTrigger className="min-h-11 rounded-lg bg-card"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="user_input">{t("profiles.sourceUserInput")}</SelectItem><SelectItem value="retrieved_content">{t("profiles.sourceRetrieved")}</SelectItem><SelectItem value="tool_output">{t("profiles.sourceToolOutput")}</SelectItem></SelectContent></Select></Field>
          </section>
        ) : null}
        <Field label={t(promptSecurity ? "profiles.untrustedTarget" : "profiles.modelContent")}><Textarea className="min-h-40 rounded-lg bg-card" value={content} onChange={(event) => setContent(event.target.value)} placeholder={promptSecurity ? t("profiles.untrustedTargetPlaceholder") : "Analyze the quarterly revenue and margin of this chemical manufacturer."} /></Field>
        <Field label={t("profiles.expectedDecision")}><Select value={expected} onValueChange={(value) => setExpected(value as typeof expected)}><SelectTrigger className="min-h-11 rounded-lg bg-card"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="allow">{t("states.allow")}</SelectItem><SelectItem value="block">{t("states.block")}</SelectItem><SelectItem value="transform">{t("profiles.transform")}</SelectItem><SelectItem value="intervene">{t("profiles.anyIntervention")}</SelectItem></SelectContent></Select></Field>
      </div>
    </EntitySheet>
  );
}

function ProtectionEditor({ definitions, risks, onChange }: { definitions: ProtectionDefinition[]; risks: SafeProtection[]; onChange: (risks: SafeProtection[]) => void }) {
  const { t } = useTranslation();
  return (
    <section>
      <h3 className="text-lg">{t("profiles.enforceTitle")}</h3>
      <p className="mt-1 text-xs text-muted-foreground">{t("profiles.enforceDescription")}</p>
      <div className="mt-3 divide-y divide-border overflow-hidden rounded-lg border bg-card">
        {definitions.map((definition) => {
          const configured = risks.find((item) => item.risk === definition.id);
          const enabled = Boolean(configured);
          return (
            <div key={definition.id} className="grid gap-3 p-4 sm:grid-cols-[minmax(0,1fr)_150px_44px] sm:items-center">
              <div><strong className="text-sm font-medium">{definition.display_name}</strong><p className="mt-1 text-xs leading-5 text-muted-foreground">{definition.description}</p></div>
              <Select disabled={!enabled} value={configured?.action ?? definition.default_action} onValueChange={(action) => onChange(risks.map((item) => item.risk === definition.id ? { ...item, action } : item))}><SelectTrigger aria-label={`${definition.display_name} action`} className="min-h-11 rounded-lg bg-card"><SelectValue /></SelectTrigger><SelectContent className="rounded-lg">{definition.allowed_actions.map((action) => <SelectItem key={action} value={action}>{actionLabel(action, t)}</SelectItem>)}</SelectContent></Select>
              <Switch checked={enabled} aria-label={`Control ${definition.display_name}`} onCheckedChange={(checked) => onChange(checked ? [...risks, { risk: definition.id, action: definition.default_action }] : risks.filter((item) => item.risk !== definition.id))} />
            </div>
          );
        })}
      </div>
    </section>
  );
}

function TemplateProtectionSummary({ template, parameters, compact = false }: { template: SafeTemplate; parameters: Record<string, string>; compact?: boolean }) {
  const { t } = useTranslation();
  return (
    <section className="overflow-hidden rounded-lg border bg-card">
      <div className="flex items-start justify-between gap-3 border-b bg-muted/40 p-4"><div><h3 className="text-lg">{template.name}</h3><p className="mt-1 text-xs leading-5 text-muted-foreground">{template.description}</p></div><StateBadge state="local" /></div>
      <div className="grid gap-4 p-4 sm:grid-cols-3"><Fact label={t("profiles.source")} value={template.source ?? "TaskLattice"} /><Fact label={t("profiles.version")} value={template.version ?? t("profiles.builtIn")} /><Fact label={t("profiles.localControlsLabel")} value={String(template.controls?.length ?? 0)} /></div>
      {!compact ? <div className="border-t p-4"><p className="text-xs font-medium text-muted-foreground">{t("profiles.includedControls")}</p><div className="mt-2 flex flex-wrap gap-2">{template.controls?.map((control) => <span key={control} className="rounded-md border bg-muted/40 px-2 py-1 font-mono text-[11px]">{control}</span>)}</div>{Object.keys(parameters).length ? <p className="mt-3 text-xs text-muted-foreground">{t("profiles.reviewedParameters", { parameters: Object.keys(parameters).join(", ") })}</p> : null}</div> : null}
    </section>
  );
}

function TestEvidence({ profile, testCases }: { profile: Safe; testCases: TestCase[] }) {
  const { t, i18n } = useTranslation();
  const latest = profile.latest_test_run;
  if (!latest) return null;
  return (
    <section className="overflow-hidden rounded-lg border bg-card">
      <div className="flex items-center justify-between gap-3 border-b bg-muted/40 p-4"><div><h3 className="text-lg">{t("profiles.latestEvidence")}</h3><p className="mt-1 text-xs text-muted-foreground">{new Date(latest.created_at).toLocaleString(i18n.language)}</p></div><StateBadge state={latest.status} /></div>
      <div className="grid grid-cols-2 gap-3 p-4 sm:grid-cols-4"><Metric label={t("profiles.complianceLabel")} value={`${latest.metrics.compliance_rate}%`} /><Metric label={t("profiles.falsePositive")} value={`${latest.metrics.false_positive_rate}%`} /><Metric label={t("profiles.deepEscalation")} value={`${latest.metrics.deep_escalation_rate}%`} /><Metric label={t("profiles.latency")} value={`${latest.metrics.p95_latency_ms} ms`} /></div>
      {profile.coverage?.length ? <div className="border-t"><div className="divide-y divide-border">{profile.coverage.map((item) => <div key={item.risk} className="grid gap-3 p-4 sm:grid-cols-[190px_minmax(0,1fr)_90px] sm:items-center"><span className="text-sm">{riskLabel(item.risk, t)}</span><Progress value={item.score ?? 0} aria-label={`${item.risk} coverage ${item.score ?? 0}%`} /><span className="text-right font-mono text-xs">{item.score === null ? t("profiles.noRiskEvidence") : `${item.score}%`}</span></div>)}</div></div> : null}
      <div className="divide-y border-t">
        {latest.results.map((result) => (
          <TestEvidenceRow
            key={result.case_id}
            result={result}
            testCase={testCases.find((item) => item.id === result.case_id)}
          />
        ))}
      </div>
    </section>
  );
}

function TestEvidenceRow({ result, testCase }: { result: EvaluationCaseResult; testCase?: TestCase }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(!result.passed);
  const input = result.input_content || testCase?.content || "";
  const phase = result.input_content ? result.phase : testCase?.phase ?? result.phase;
  const legacyEvidence = !result.input_content;
  const output = result.output_content || (result.actual_decision === "allow" ? input : "");
  const trustedInstruction = result.trusted_instruction || testCase?.trusted_instruction || "";
  const targetSource = result.target_source || testCase?.target_source || "user_input";

  return (
    <details open={open} onToggle={(event) => setOpen(event.currentTarget.open)} className="group">
      <summary className="grid min-h-16 cursor-pointer list-none gap-3 p-4 transition-colors hover:bg-muted/40 focus-visible:outline-2 focus-visible:outline-ring sm:grid-cols-[28px_minmax(0,1fr)_100px_90px_20px] sm:items-center [&::-webkit-details-marker]:hidden">
        {result.passed ? <CheckCircle2 className="size-4 text-emerald-600" /> : <XCircle className="size-4 text-destructive" />}
        <div className="min-w-0">
          <strong className="text-sm font-medium">{result.name}</strong>
          <p className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">
            {result.passed ? result.reason : t("profiles.testMismatch", { expected: t(`states.${result.expected_decision}`), actual: t(`states.${result.actual_decision}`) })}
          </p>
        </div>
        <StateBadge state={result.actual_decision} />
        <span className="font-mono text-xs text-muted-foreground">{result.latency_ms} ms</span>
        <ChevronDown className="size-4 text-muted-foreground transition-transform group-open:rotate-180" />
      </summary>

      <div className="border-t bg-muted/20 p-4 sm:p-5">
        {trustedInstruction ? (
          <section className="mb-4 overflow-hidden rounded-lg border border-primary/20 bg-primary/[0.03]">
            <header className="flex items-center gap-2 border-b border-primary/15 px-4 py-3"><ShieldCheck className="size-4 text-primary" /><h4 className="text-sm font-medium">{t("profiles.trustedInstruction")}</h4><span className="ml-auto text-xs text-muted-foreground">{t("profiles.trusted")}</span></header>
            <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words p-4 font-sans text-sm leading-6">{trustedInstruction}</pre>
          </section>
        ) : null}
        <div className="grid gap-4 xl:grid-cols-2">
          <EvidenceContent
            label={t("profiles.testInput")}
            meta={`${t(phase === "output" ? "profiles.output" : "profiles.input")} · ${targetSourceLabel(targetSource, t)}`}
            value={input || t("profiles.evidenceNotRecorded")}
          />
          <EvidenceContent
            label={t("profiles.testOutput")}
            meta={result.action ? actionLabel(result.action, t) : t("profiles.evidenceNotRecorded")}
            value={output || (result.actual_decision === "block" ? t("profiles.blockedNoOutput") : t("profiles.evidenceNotRecorded"))}
          />
        </div>

        <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <EvidenceFact label={t("profiles.expectedDecision")}><StateBadge state={result.expected_decision} /></EvidenceFact>
          <EvidenceFact label={t("profiles.actualDecision")}><StateBadge state={result.actual_decision} /></EvidenceFact>
          <EvidenceFact label={t("profiles.actualAction")}><strong className="text-sm font-medium">{result.action ? actionLabel(result.action, t) : t("profiles.evidenceNotRecorded")}</strong></EvidenceFact>
          <EvidenceFact label={t("profiles.stageReached")}><strong className="text-sm font-medium">{stageLabel(result.stage_reached, t)}</strong></EvidenceFact>
        </dl>

        <section className="mt-4 rounded-lg border bg-card p-4">
          <h4 className="text-xs font-medium text-muted-foreground">{t("profiles.decisionReason")}</h4>
          <p className="mt-2 text-sm leading-6">{result.reason || t("profiles.evidenceNotRecorded")}</p>
        </section>

        {result.findings.length ? (
          <section className="mt-4">
            <h4 className="text-sm font-medium">{t("profiles.triggeredFindings")}</h4>
            <div className="mt-2 divide-y rounded-lg border bg-card">
              {result.findings.map((finding, index) => (
                <div key={`${finding.risk}-${index}`} className="grid gap-2 p-4 sm:grid-cols-[160px_minmax(0,1fr)_70px]">
                  <strong className="text-sm font-medium">{riskLabel(finding.risk, t)}</strong>
                  <p className="text-xs leading-5 text-muted-foreground">{finding.evidence}</p>
                  <span className="text-right font-mono text-xs text-muted-foreground">{Math.round(finding.confidence * 100)}%</span>
                </div>
              ))}
            </div>
          </section>
        ) : null}

        {result.trace.length ? (
          <section className="mt-4">
            <h4 className="text-sm font-medium">{t("profiles.executionTrace")}</h4>
            <ol className="mt-2 divide-y rounded-lg border bg-card">
              {result.trace.map((step) => (
                <li key={step.id} className="grid gap-2 p-4 sm:grid-cols-[160px_minmax(0,1fr)_70px]">
                  <strong className="text-sm font-medium">{stageLabel(step.stage ?? step.name, t)}</strong>
                  <p className="text-xs leading-5 text-muted-foreground">{step.detail}</p>
                  <span className="text-right font-mono text-xs text-muted-foreground">{step.duration_ms} ms</span>
                </li>
              ))}
            </ol>
          </section>
        ) : legacyEvidence ? <p className="mt-4 text-xs leading-5 text-muted-foreground">{t("profiles.rerunForFullEvidence")}</p> : null}
      </div>
    </details>
  );
}

function EvidenceContent({ label, meta, value }: { label: string; meta: string; value: string }) {
  return (
    <section className="overflow-hidden rounded-lg border bg-card">
      <header className="flex items-center justify-between gap-3 border-b bg-muted/40 px-4 py-3">
        <h4 className="text-sm font-medium">{label}</h4>
        <span className="text-xs text-muted-foreground">{meta}</span>
      </header>
      <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words p-4 font-sans text-sm leading-6">{value}</pre>
    </section>
  );
}

function EvidenceFact({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="rounded-lg bg-card p-3 ring-1 ring-border"><dt className="text-xs text-muted-foreground">{label}</dt><dd className="mt-2">{children}</dd></div>;
}

function TestCaseRow({ item, onDelete, deleting }: { item: TestCase; onDelete: () => void; deleting: boolean }) {
  const { t } = useTranslation();
  return (
    <article className="grid gap-3 p-4 md:grid-cols-[minmax(0,1fr)_130px_120px_44px] md:items-center">
      <div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><strong className="text-sm font-medium">{item.name}</strong><span className="rounded-md border bg-muted/50 px-1.5 py-0.5 text-[10px] text-muted-foreground">{item.origin}</span></div><p className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">{item.content}</p></div>
      <div className="text-xs"><p>{riskLabel(item.risk, t)}</p><p className="mt-1 text-muted-foreground capitalize">{t(item.phase === "input" ? "profiles.input" : "profiles.output")}{item.risk === "prompt_injection" || item.risk === "jailbreak" ? ` · ${targetSourceLabel(item.target_source, t)}` : ""}</p></div>
      <StateBadge state={item.expected_decision === "intervene" ? "intervene" : item.expected_decision} />
      <Button type="button" size="icon" variant="ghost" aria-label={`Delete ${item.name}`} disabled={deleting} onClick={onDelete}><Trash2 /></Button>
    </article>
  );
}

function RiskRow({ risk, definition, template }: { risk: SafeProtection; definition?: ProtectionDefinition; template?: SafeTemplate }) {
  const { t } = useTranslation();
  const phases: Record<string, string> = { secrets: t("profiles.inputOutput"), pii: t("profiles.inputOutput"), prompt_injection: t("profiles.input"), jailbreak: t("profiles.input"), content_safety: t("profiles.inputOutput"), topic_control: t("profiles.inputOutput"), company_policy: t("profiles.inputOutput"), builtin_content_filter: t("profiles.perLocalControl") };
  return <div className="grid min-h-16 grid-cols-[minmax(0,1fr)_140px_150px] items-center px-4 text-xs"><div><strong className="font-medium">{risk.risk === "builtin_content_filter" && template ? template.name : definition?.display_name ?? riskLabel(risk.risk, t)}</strong>{definition ? <p className="mt-1 line-clamp-1 text-muted-foreground">{definition.description}</p> : null}</div><span>{phases[risk.risk] ?? t("profiles.modelIo")}</span><span>{actionLabel(risk.action, t)}</span></div>;
}

function SourceChoice({ active, icon: Icon, title, description, onClick }: { active: boolean; icon: typeof Library; title: string; description: string; onClick: () => void }) {
  return <button type="button" aria-pressed={active} onClick={onClick} className={cn("min-h-32 rounded-lg border bg-card p-4 text-left transition-colors hover:border-primary/60 focus-visible:outline-2 focus-visible:outline-ring", active && "border-primary/40 bg-accent")}><span className="flex items-center justify-between"><Icon className="size-5 text-primary" />{active ? <Check className="size-4 text-primary" /> : null}</span><strong className="mt-4 block text-sm font-medium">{title}</strong><span className="mt-1 block text-xs leading-5 text-muted-foreground">{description}</span></button>;
}

function TopicPanel({ title, items, empty, danger = false }: { title: string; items: string[]; empty: string; danger?: boolean }) {
  return <section className="overflow-hidden rounded-lg border bg-card"><div className="border-b bg-muted/40 px-4 py-3"><h3 className="text-lg">{title}</h3></div><div className="min-h-36 p-4">{items.length ? <ul className="space-y-2">{items.map((item) => <li key={item} className="flex items-start gap-2 text-sm"><span className={cn("mt-2 size-1.5 shrink-0 rounded-full bg-primary", danger && "bg-destructive")} />{item}</li>)}</ul> : <p className="text-sm text-muted-foreground">{empty}</p>}</div></section>;
}

function Fact({ label, value }: { label: string; value: string }) { return <div className="rounded-lg bg-muted/60 p-3"><p className="text-xs font-medium text-muted-foreground">{label}</p><p className="mt-2 text-sm">{value}</p></div>; }
function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) { return <label className="grid gap-2 text-sm font-medium">{label}{children}{hint ? <span className="text-xs font-normal leading-5 text-muted-foreground">{hint}</span> : null}</label>; }
function lines(value: string) { return value.split("\n").map((item) => item.trim()).filter(Boolean); }
function deliveryLabel(value: string, t: TFunction) { return value === "interruptible" ? t("profiles.outputRealtime") : value === "full_buffered" ? t("profiles.outputFull") : t("profiles.outputWindow"); }
function riskLabel(value: string, t: TFunction) { return ({ builtin_content_filter: t("profiles.riskBuiltin"), topic_control: t("profiles.riskTopic"), pii: t("profiles.riskPii"), secrets: t("profiles.riskSecrets"), prompt_injection: t("profiles.riskInjection"), jailbreak: t("profiles.riskJailbreak"), content_safety: t("profiles.riskUnsafe"), company_policy: t("profiles.riskCompany") } as Record<string, string>)[value] ?? value.replaceAll("_", " "); }
function actionLabel(value: string, t: TFunction) { return ({ reject: t("profiles.actionReject"), redact: t("profiles.actionRedact"), rewrite: t("profiles.actionRewrite"), regenerate: t("profiles.actionRegenerate"), redirect: t("profiles.actionRedirect"), pass: t("profiles.actionPass"), fallback: t("profiles.actionFallback") } as Record<string, string>)[value] ?? value; }
function stageLabel(value: string, t: TFunction) { return ({ deterministic: t("playground.stages.deterministic"), fast_semantic: t("playground.stages.fast_semantic"), deep_judge: t("playground.stages.deep_judge"), none: t("states.not evaluated") } as Record<string, string>)[value.toLowerCase().replaceAll(" ", "_")] ?? value; }
function targetSourceLabel(value: string, t: TFunction) { return ({ user_input: t("profiles.sourceUserInput"), retrieved_content: t("profiles.sourceRetrieved"), tool_output: t("profiles.sourceToolOutput") } as Record<string, string>)[value] ?? value; }
function notifyError(error: unknown, fallback: string) { toast.error(error instanceof Error ? error.message : fallback); }
