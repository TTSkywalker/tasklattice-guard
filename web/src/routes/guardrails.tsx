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
  FlaskConical,
  History,
  LoaderCircle,
  Play,
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
  analyzeGuardrailIntent,
  createGuardrail,
  createTestCase,
  getGuardrail,
  getGuardrailVersions,
  getGuardrails,
  getIntentAnalysisStatus,
  getControlDefinitions,
  getGuardrailTemplates,
  getAssignments,
  rollbackGuardrail,
  updateGuardrail,
  type GuardrailControl,
  type GuardrailControlConfig,
  type EvaluationCaseResult,
  type IntentAnalysis,
  type TestCase,
  type ControlDefinition,
  type Guardrail,
  type GuardrailTemplate,
  type GuardrailVersion,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { CreateAssignmentSheet } from "@/routes/assignments";
import { CreateGuardrailWizard } from "@/routes/create-guardrail-wizard";

const defaultControls: GuardrailControl[] = [
  { risk: "topic_control", action: "redirect" },
  { risk: "secrets", action: "reject" },
  { risk: "pii", action: "redact" },
];

export function GuardrailsPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const guardrailsQuery = useQuery({ queryKey: queryKeys.guardrails, queryFn: getGuardrails });
  const [createOpen, setCreateOpen] = useState(false);
  const guardrails = [...(guardrailsQuery.data?.items ?? [])].sort(
    (left, right) => Number(right.is_default) - Number(left.is_default),
  );

  return (
    <section className="py-6 sm:py-8">
      <PageHeader
        title={t("pages.guardrails.title")}
        description={t("guardrails.description")}
        action={<Button className="min-h-11 self-start" onClick={() => setCreateOpen(true)}><Plus />{t("guardrails.create")}</Button>}
      />

      {guardrailsQuery.error ? <div className="mt-5"><ErrorNotice error={guardrailsQuery.error} /></div> : null}
      {guardrailsQuery.isLoading ? <Skeleton className="mt-5 h-80 rounded-xl" /> : null}
      {!guardrailsQuery.isLoading && !guardrails.length ? (
        <div className="mt-5">
          <EmptyState
            title={t("guardrails.emptyTitle")}
            description={t("guardrails.emptyDescription")}
            action={<Button onClick={() => setCreateOpen(true)}><Plus />{t("guardrails.createFirst")}</Button>}
          />
        </div>
      ) : null}

      {guardrails.length ? (
        <section className="mt-5 overflow-hidden rounded-xl border bg-card shadow-xs">
          <div className="flex items-center justify-between gap-3 border-b bg-muted/30 px-5 py-3">
            <p className="text-xs font-medium text-muted-foreground">{t("guardrails.registry", { count: guardrails.length })}</p>
            <p className="hidden text-xs text-muted-foreground sm:block">{t("guardrails.openGuardrailHint")}</p>
          </div>
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="min-w-64 px-5">{t("guardrails.guardrail")}</TableHead>
                <TableHead>{t("common.status")}</TableHead>
                <TableHead className="hidden lg:table-cell">{t("guardrails.controls")}</TableHead>
                <TableHead>{t("guardrails.testEvidence")}</TableHead>
                <TableHead className="hidden xl:table-cell">{t("guardrails.assignments")}</TableHead>
                <TableHead className="hidden xl:table-cell">{t("guardrails.lastUpdated")}</TableHead>
                <TableHead className="w-12"><span className="sr-only">{t("guardrails.openDetails")}</span></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {guardrails.map((guardrail) => (
                <TableRow key={guardrail.id} className="group">
                  <TableCell className="px-5 py-4 whitespace-normal">
                    <Link
                      to="/guardrails/$guardrailId"
                      params={{ guardrailId: guardrail.id }}
                      className="block rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      <span className="flex items-center gap-2"><strong className="text-sm font-medium text-foreground group-hover:text-primary">{guardrailDisplayName(guardrail, t)}</strong>{guardrail.is_default ? <span className="rounded-md border bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">{t("guardrails.builtinBadge")}</span> : null}</span>
                      <span className="mt-1 block max-w-xl line-clamp-2 text-xs leading-5 text-muted-foreground">{guardrailDisplayPurpose(guardrail, t)}</span>
                    </Link>
                  </TableCell>
                  <TableCell><StateBadge state={guardrail.status} /></TableCell>
                  <TableCell className="hidden tabular-nums lg:table-cell">{guardrail.control_configurations.length || guardrail.controls.length}</TableCell>
                  <TableCell>
                    <p className="text-sm tabular-nums">{guardrail.system_managed ? t("guardrails.builtinVerified") : t("guardrails.testCount", { count: guardrail.test_case_count })}</p>
                    <p className="mt-1 text-xs text-muted-foreground">{guardrail.local_only ? t("guardrails.localOnly") : guardrail.latest_test_run ? t("guardrails.compliance", { rate: guardrail.latest_test_run.metrics.compliance_rate }) : t("guardrails.noEvidence")}</p>
                  </TableCell>
                  <TableCell className="hidden tabular-nums xl:table-cell">{guardrail.assignment_count}</TableCell>
                  <TableCell className="hidden text-xs text-muted-foreground xl:table-cell">{new Date(guardrail.updated_at).toLocaleDateString(i18n.language)}</TableCell>
                  <TableCell className="pr-4">
                    <Button asChild size="icon" variant="ghost" aria-label={t("guardrails.openNamedGuardrail", { name: guardrailDisplayName(guardrail, t) })}>
                      <Link to="/guardrails/$guardrailId" params={{ guardrailId: guardrail.id }}><ChevronRight /></Link>
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </section>
      ) : null}

      <CreateGuardrailWizard
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={async (id) => {
          setCreateOpen(false);
          await queryClient.invalidateQueries({ queryKey: queryKeys.guardrails });
          await navigate({ to: "/guardrails/$guardrailId", params: { guardrailId: id } });
        }}
      />
    </section>
  );
}

export function GuardrailDetailPage() {
  const { guardrailId } = useParams({ from: "/guardrails/$guardrailId" });
  const queryClient = useQueryClient();
  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.guardrails }),
      queryClient.invalidateQueries({ queryKey: queryKeys.guardrail(guardrailId) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.guardrailVersions(guardrailId) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.testCases(guardrailId) }),
    ]);
  };
  return <GuardrailDetail guardrailId={guardrailId} onRefresh={refresh} />;
}

function GuardrailDetail({ guardrailId, onRefresh }: { guardrailId: string; onRefresh: () => Promise<void> }) {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const guardrailQuery = useQuery({ queryKey: queryKeys.guardrail(guardrailId), queryFn: () => getGuardrail(guardrailId), enabled: Boolean(guardrailId) });
  const versionsQuery = useQuery({ queryKey: queryKeys.guardrailVersions(guardrailId), queryFn: () => getGuardrailVersions(guardrailId), enabled: Boolean(guardrailId) });
  const templatesQuery = useQuery({ queryKey: queryKeys.guardrailTemplates, queryFn: getGuardrailTemplates });
  const controlsQuery = useQuery({ queryKey: queryKeys.controlDefinitions, queryFn: getControlDefinitions });
  const assignmentsQuery = useQuery({ queryKey: queryKeys.assignments, queryFn: getAssignments });
  const [editOpen, setEditOpen] = useState(false);
  const [applyOpen, setApplyOpen] = useState(false);
  const [activeTab, setActiveTab] = useState("definition");

  const guardrail = guardrailQuery.data;
  if (guardrailQuery.error) return <section className="py-6 sm:py-8"><GuardrailBackLink /><div className="mt-4"><ErrorNotice error={guardrailQuery.error} /></div></section>;
  if (guardrailQuery.isLoading || !guardrail) return <section className="py-6 sm:py-8"><GuardrailBackLink /><Skeleton className="mt-4 h-[680px] rounded-xl" /></section>;

  const versions = versionsQuery.data?.items ?? [];
  const template = templatesQuery.data?.items.find((item) => item.id === guardrail.source_template_id);
  const definitions = controlsQuery.data?.items ?? [];
  const assignments = (assignmentsQuery.data?.items ?? []).filter((item) => item.guardrail_id === guardrail.id);

  return (
    <section className="min-w-0 py-6 sm:py-8">
      <GuardrailBackLink />
      <div className="mt-4">
        <PageHeader
          title={guardrailDisplayName(guardrail, t)}
          description={guardrailDisplayPurpose(guardrail, t)}
          action={<div className="flex flex-wrap gap-2">
            <Button asChild variant="outline" className="min-h-11"><Link to="/playground" search={{ guardrail: guardrail.id }}><Play />{t("guardrails.openInPlayground")}</Link></Button>
            {!guardrail.system_managed ? <Button variant="outline" className="min-h-11" onClick={() => setEditOpen(true)}><Save />{t("guardrails.editDefinition")}</Button> : null}
            {!guardrail.system_managed ? guardrail.tested_current ? <Button className="min-h-11" onClick={() => setApplyOpen(true)}><Building2 />{t("guardrails.createDeployment")}</Button> : <Button asChild className="min-h-11"><Link to="/evaluations" search={{ guardrail: guardrail.id }}><FlaskConical />{t("guardrails.openEvaluations")}</Link></Button> : null}
          </div>}
        />
      </div>

      {guardrail.is_default ? <div className="mt-5"><InfoNotice title={t("guardrails.defaultNoticeTitle")}>{t("guardrails.defaultNoticeDescription")}</InfoNotice></div> : null}

      <div className="mt-5 overflow-hidden rounded-xl border bg-card shadow-xs">
        <div className="flex items-center justify-between gap-3 border-b bg-muted/20 px-4 py-3 sm:px-5">
          <StateBadge state={guardrail.status} />
          <span className="text-xs text-muted-foreground">{t("guardrails.lastUpdatedValue", { date: new Date(guardrail.updated_at).toLocaleString(i18n.language) })}</span>
        </div>
        <WorkflowStatus guardrail={guardrail} testCaseCount={guardrail.test_case_count} onApply={() => setApplyOpen(true)} />

        <div className="grid grid-cols-2 gap-3 border-b p-4 sm:grid-cols-4">
          <Metric label={t("guardrails.controls")} value={guardrail.control_configurations.length || guardrail.controls.length} detail={t("guardrails.reviewedControls")} />
          <Metric label={t("guardrails.regressionCases")} value={guardrail.system_managed ? t("guardrails.builtin") : guardrail.test_case_count} detail={guardrail.system_managed ? t("guardrails.productManaged") : t("guardrails.visibleEditable")} />
          <Metric label={t("guardrails.releaseGate")} value={t(guardrail.system_managed ? "guardrails.builtinVerified" : guardrail.tested_current ? "guardrails.passed" : "guardrails.required")} detail={guardrail.local_only ? t("guardrails.localOnly") : guardrail.latest_test_run ? t("guardrails.compliance", { rate: guardrail.latest_test_run.metrics.compliance_rate }) : t("guardrails.noEvaluationEvidence")} />
          <Metric label={t("guardrails.deployments")} value={guardrail.assignment_count} detail={t("guardrails.trafficDeployments")} />
        </div>

        <Tabs value={activeTab} onValueChange={setActiveTab} className="p-5 sm:p-6">
        <TabsList className="h-auto min-h-11 w-full flex-wrap justify-start rounded-lg bg-muted p-1">
          <TabsTrigger value="definition" className="min-h-11 rounded-md px-3">{t("guardrails.definition")}</TabsTrigger>
          <TabsTrigger value="versions" className="min-h-11 rounded-md px-3">{t("guardrails.versions")}</TabsTrigger>
        </TabsList>

        <TabsContent value="definition" className="mt-5 space-y-5">
          <div className="grid gap-5 xl:grid-cols-2">
            <TopicPanel title={t("guardrails.allowedDomains")} items={guardrail.allowed_topics} empty={t(template ? "guardrails.templateDefined" : "guardrails.noAllowed")} />
            <TopicPanel title={t("guardrails.restrictedDomains")} items={guardrail.restricted_topics} empty={t(template ? "guardrails.templateDefined" : "guardrails.noRestricted")} danger />
          </div>
          <section className="rounded-lg border bg-card p-4">
            <h3 className="text-lg">{t("guardrails.decisionPosture")}</h3>
            <div className="mt-4 grid gap-3 sm:grid-cols-3">
              <Fact label={t("guardrails.evaluation")} value={guardrail.local_only ? t("guardrails.ruleChecksOnly") : t(guardrail.safety_level === "strict" ? "guardrails.strict" : "guardrails.balanced")} />
              <Fact label={t("guardrails.modelOutput")} value={deliveryLabel(guardrail.output_delivery, t)} />
              <Fact label={t("guardrails.ownership")} value={t(guardrail.system_managed ? "guardrails.productManagedBaseline" : "guardrails.organizationOwned")} />
            </div>
          </section>
          {template ? <TemplateControlSummary template={template} parameters={guardrail.template_parameters} /> : null}
          {guardrail.control_configurations.length ? <ConfiguredControlsSummary configurations={guardrail.control_configurations} /> : null}
          <DetectionPipeline definitions={definitions} controls={guardrail.controls} />
          <section className="overflow-hidden rounded-lg border bg-card">
            <div className="hidden grid-cols-[minmax(0,1fr)_150px_190px_140px] border-b bg-muted/40 px-4 py-3 text-xs font-medium text-muted-foreground md:grid"><span>{t("guardrails.control")}</span><span>{t("guardrails.modelBoundary")}</span><span>{t("guardrails.detectionRoute")}</span><span>{t("guardrails.whenDetected")}</span></div>
            <div className="divide-y divide-border">
              {guardrail.controls.map((risk) => <RiskRow key={risk.risk} risk={risk} definition={definitions.find((item) => item.id === risk.risk)} template={template} />)}
            </div>
          </section>
          <InfoNotice title={t("guardrails.runtimeBoundary")}>{t(guardrail.local_only ? "guardrails.defaultRuntimeBoundaryDescription" : "guardrails.runtimeBoundaryDescription")}</InfoNotice>
          <section className="flex flex-col gap-4 rounded-lg border bg-card p-4 sm:flex-row sm:items-center sm:justify-between"><div><h3 className="text-lg">{t("guardrails.deployments")}</h3><p className="mt-1 text-xs leading-5 text-muted-foreground">{assignments.length ? t("guardrails.deploymentCount", { count: assignments.length }) : t("guardrails.noDeploymentsDescription")}</p></div><Button asChild variant="outline"><Link to="/deployments">{t("guardrails.manageDeployments")}</Link></Button></section>
        </TabsContent>

        <TabsContent value="versions" className="mt-5">
          <GuardrailVersions guardrailId={guardrail.id} versions={versions} loading={versionsQuery.isLoading} onRolledBack={onRefresh} />
        </TabsContent>

        </Tabs>
      </div>

      {!guardrail.system_managed ? <><EditGuardrailSheet guardrail={guardrail} open={editOpen} onOpenChange={setEditOpen} onSaved={async () => { setEditOpen(false); await onRefresh(); }} />
      <CreateAssignmentSheet
        open={applyOpen}
        onOpenChange={setApplyOpen}
        guardrails={[guardrail]}
        initialGuardrailId={guardrail.id}
        onCreated={async () => {
          setApplyOpen(false);
          await Promise.all([onRefresh(), queryClient.invalidateQueries({ queryKey: queryKeys.assignments }), queryClient.invalidateQueries({ queryKey: queryKeys.metrics })]);
        }}
      /></> : null}
    </section>
  );
}

function GuardrailBackLink() {
  const { t } = useTranslation();
  return <Button asChild variant="ghost" className="-ml-3 min-h-10 px-3 text-muted-foreground"><Link to="/guardrails"><ArrowLeft />{t("guardrails.backToGuardrails")}</Link></Button>;
}

function GuardrailVersions({ guardrailId, versions, loading, onRolledBack }: { guardrailId: string; versions: GuardrailVersion[]; loading: boolean; onRolledBack: () => Promise<void> }) {
  const { t, i18n } = useTranslation();
  const rollback = useMutation({
    mutationFn: (version: number) => rollbackGuardrail(guardrailId, version),
    onSuccess: async (version) => {
      toast.success(t("guardrails.rollbackSucceeded", { version: version.version }));
      await onRolledBack();
    },
    onError: (error) => notifyError(error, t("guardrails.operationFailed")),
  });
  if (loading) return <Skeleton className="h-48 rounded-lg" />;
  if (!versions.length) return <EmptyState title={t("guardrails.noVersions")} description={t("guardrails.noVersionsDescription")} />;
  return (
    <section className="overflow-hidden rounded-lg border bg-card">
      <div className="grid grid-cols-[minmax(0,1fr)_minmax(130px,.5fr)] border-b bg-muted/40 px-4 py-3 text-xs font-medium text-muted-foreground sm:grid-cols-[90px_minmax(0,1fr)_110px_170px_120px]">
        <span>{t("guardrails.version")}</span><span className="hidden sm:block">{t("guardrails.compiler")}</span><span className="hidden sm:block">{t("guardrails.runtimeEngine")}</span><span className="hidden sm:block">{t("guardrails.createdAt")}</span><span>{t("common.status")}</span>
      </div>
      <div className="divide-y divide-border">
        {versions.map((version) => (
          <article key={version.version} className="grid grid-cols-[minmax(0,1fr)_minmax(130px,.5fr)] items-center gap-3 px-4 py-4 sm:grid-cols-[90px_minmax(0,1fr)_110px_170px_120px]">
            <div className="flex items-center gap-2"><History className="size-4 text-primary" /><strong className="font-mono text-sm">v{version.version}</strong></div>
            <div className="hidden min-w-0 sm:block"><p className="truncate text-xs font-medium">{version.compiler_version}</p><p className="mt-1 truncate font-mono text-[10px] text-muted-foreground" title={version.config_checksum}>{version.config_checksum || version.plan_checksum}</p></div>
            <div className="hidden sm:block"><p className="font-mono text-xs">{version.runtime_engine}</p><p className="mt-1 text-[10px] text-muted-foreground">{version.execution_mode}</p></div>
            <time className="hidden text-xs text-muted-foreground sm:block">{new Date(version.created_at).toLocaleString(i18n.language)}</time>
            <div className="flex min-h-11 items-center justify-end sm:justify-start">
              {version.active ? <StateBadge state="active" /> : <Button size="sm" variant="outline" className="min-h-11" disabled={rollback.isPending} onClick={() => rollback.mutate(version.version)}>{rollback.isPending && rollback.variables === version.version ? <LoaderCircle className="animate-spin" /> : <History />}{t("guardrails.rollback")}</Button>}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function WorkflowStatus({ guardrail, testCaseCount, onApply }: { guardrail: Guardrail; testCaseCount: number; onApply: () => void }) {
  const { t } = useTranslation();
  const steps = guardrail.system_managed ? [
    { label: t("guardrails.flowProductDefault"), complete: true },
    { label: t("guardrails.flowLocalOnly"), complete: true },
    { label: t("guardrails.flowBuiltinVerified"), complete: true },
    { label: t("guardrails.flowDefaultAssignment"), complete: true },
  ] : [
    { label: t("guardrails.flowIntent"), complete: Boolean(guardrail.purpose) },
    { label: t("guardrails.flowControls"), complete: guardrail.controls.length > 0 },
    { label: t(guardrail.tested_current ? "guardrails.flowTestsPassed" : "guardrails.flowTestsRun", { count: testCaseCount }), complete: guardrail.tested_current },
    { label: guardrail.assignment_count ? t("guardrails.flowAssignments", { count: guardrail.assignment_count }) : t("guardrails.flowApply"), complete: guardrail.assignment_count > 0 },
  ];
  return (
    <section aria-label={t("guardrails.workflowLabel")} className="grid border-b bg-muted/20 sm:grid-cols-4">
      {steps.map((step, index) => (
        <div key={step.label} className="flex min-h-14 items-center gap-2 border-b px-4 py-3 last:border-b-0 sm:border-b-0 sm:border-r sm:last:border-r-0">
          <span className={cn("grid size-6 shrink-0 place-items-center rounded-full border bg-card font-mono text-[10px] text-muted-foreground", step.complete && "border-emerald-200 bg-emerald-50 text-emerald-700")}>
            {step.complete ? <Check className="size-3.5" /> : index + 1}
          </span>
          {index === 3 && guardrail.tested_current && !guardrail.assignment_count && !guardrail.system_managed ? <button type="button" className="text-left text-xs font-medium text-primary hover:underline" onClick={onApply}>{step.label}</button> : <span className="text-xs font-medium">{step.label}</span>}
        </div>
      ))}
    </section>
  );
}

function CreateGuardrailSheet({ open, onOpenChange, onCreated }: { open: boolean; onOpenChange: (open: boolean) => void; onCreated: (id: string) => void }) {
  const { t, i18n } = useTranslation();
  const { user } = useAuth();
  const templatesQuery = useQuery({ queryKey: queryKeys.guardrailTemplates, queryFn: getGuardrailTemplates });
  const controlsQuery = useQuery({ queryKey: queryKeys.controlDefinitions, queryFn: getControlDefinitions });
  const [step, setStep] = useState(0);
  const intentAnalysisStatusQuery = useQuery({
    queryKey: queryKeys.intentAnalysisStatus,
    queryFn: getIntentAnalysisStatus,
    enabled: open,
    retry: false,
  });
  const [templateId, setTemplateId] = useState("");
  const [search, setSearch] = useState("");
  const [name, setName] = useState("");
  const [purpose, setPurpose] = useState("");
  const [allowed, setAllowed] = useState("");
  const [restricted, setRestricted] = useState("");
  const [risks, setRisks] = useState<GuardrailControl[]>(defaultControls);
  const [parameters, setParameters] = useState<Record<string, string>>({});
  const [analysis, setAnalysis] = useState<IntentAnalysis | null>(null);
  const [analyzedPurpose, setAnalyzedPurpose] = useState("");
  const creationSteps = [
    { label: t("guardrails.stepStart"), description: t("guardrails.stepStartDescription") },
    { label: t("guardrails.stepIntent"), description: t("guardrails.stepIntentDescription") },
    { label: t("guardrails.stepControls"), description: t("guardrails.stepControlsDescription") },
  ];

  const templates = templatesQuery.data?.items ?? [];
  const selected = templates.find((item) => item.id === templateId);
  const visibleTemplates = templates.filter((item) => `${item.name} ${item.description} ${item.domain}`.toLowerCase().includes(search.toLowerCase()));
  const definitions = controlsQuery.data?.items.filter((item) => item.id !== "builtin_content_filter") ?? [];
  const missingParameter = selected?.parameters?.some((item) => item.required && !parameters[item.name]?.trim());
  const invalidCustomTopics = risks.some((item) => item.risk === "topic_control") && (!lines(allowed).length || !lines(restricted).length);
  const invalidReasoningPolicy = hasInvalidReasoningPolicy(risks);
  const canContinue = step === 0 ? true : step === 1 ? Boolean(name.trim()) && Boolean(purpose.trim()) && !missingParameter : true;
  const profileLanguage = user?.preferred_language ?? (i18n.language.toLowerCase().startsWith("zh") ? "zh-CN" : "en");
  const analysisStale = Boolean(analysis && purpose.trim() !== analyzedPurpose);

  const mutation = useMutation({
    mutationFn: createGuardrail,
    onSuccess: (guardrail) => { toast.success(t("guardrails.created", { name: guardrail.name })); onCreated(guardrail.id); },
    onError: (error) => notifyError(error, t("guardrails.operationFailed")),
  });

  const analyzeIntent = useMutation({
    mutationFn: () => analyzeGuardrailIntent({ purpose: purpose.trim(), language: profileLanguage }),
    onSuccess: (result) => {
      setAllowed(result.allowed_topics.join("\n"));
      setRestricted(result.restricted_topics.join("\n"));
      setAnalysis(result);
      setAnalyzedPurpose(purpose.trim());
      setRisks((current) => current.some((item) => item.risk === "topic_control") ? current : [...current, { risk: "topic_control", action: "redirect" }]);
      toast.success(t("guardrails.analysisSucceeded"));
    },
    onError: (error) => notifyError(error, t("guardrails.operationFailed")),
  });

  useEffect(() => {
    if (open) {
      setStep(0); setTemplateId(""); setSearch(""); setName(""); setPurpose(""); setAllowed(""); setRestricted(""); setRisks(defaultControls); setParameters({}); setAnalysis(null); setAnalyzedPurpose("");
    }
  }, [open]);

  const submit = () => mutation.mutate({
    name,
    purpose,
    ...(templateId ? { template_id: templateId, template_parameters: parameters } : {}),
    allowed_topics: lines(allowed),
    restricted_topics: lines(restricted),
    controls: templateId ? [{ risk: "builtin_content_filter", action: "reject" }, ...risks.filter((item) => item.risk !== "builtin_content_filter")] : risks,
    safety_level: "balanced",
    output_delivery: risks.some((item) => item.risk === "automated_reasoning") ? "full_buffered" : "window_buffered",
  });

  return (
    <EntitySheet
      open={open}
      onOpenChange={onOpenChange}
      eyebrow={t("guardrails.createEyebrow")}
      title={t("guardrails.create")}
      description={t("guardrails.createDescription")}
      width="xl"
      footer={
        <>
          <Button variant="outline" onClick={() => step ? setStep(step - 1) : onOpenChange(false)}>{step ? <><ArrowLeft />{t("guardrails.back")}</> : t("common.cancel")}</Button>
          {step < creationSteps.length - 1
            ? <Button disabled={!canContinue} onClick={() => setStep(step + 1)}>{t("guardrails.continue")}<ArrowRight /></Button>
            : <Button disabled={!name.trim() || !risks.length || invalidCustomTopics || invalidReasoningPolicy || mutation.isPending} onClick={submit}><ShieldCheck />{t(mutation.isPending ? "common.creating" : "guardrails.createShort")}</Button>}
        </>
      }
    >
      <CreationFlow currentStep={step} onStepChange={setStep} progressLabel={t("guardrails.create")} steps={creationSteps}>
        {step === 0 ? (
          <div className="space-y-5">
            <InfoNotice title={t("guardrails.composableTitle")}>{t("guardrails.composableDescription")}</InfoNotice>
            <section>
              <div className="flex flex-col gap-3 sm:flex-row sm:items-end"><label className="grid flex-1 gap-2 text-sm font-medium">{t("guardrails.findTemplate")}<Input className="min-h-11 rounded-lg bg-card" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="MAS, PDPA, PII, Topic Control…" /></label>{templateId ? <Button type="button" variant="outline" onClick={() => { setTemplateId(""); setParameters({}); }}>{t("guardrails.removeTemplate")}</Button> : null}</div>
              <div className="mt-3 grid max-h-[430px] gap-2 overflow-y-auto pr-1 sm:grid-cols-2">
                {visibleTemplates.map((item) => (
                  <button key={item.id} type="button" aria-pressed={templateId === item.id} onClick={() => { const next = templateId === item.id ? "" : item.id; setTemplateId(next); setParameters({}); if (next) { setName((current) => current || item.name); setPurpose(item.purpose); setAllowed(item.allowed_topics.join("\n")); setRestricted(item.restricted_topics.join("\n")); } }} className={cn("min-h-36 rounded-lg border bg-card p-4 text-left transition-colors hover:border-primary/60 focus-visible:outline-2 focus-visible:outline-ring", templateId === item.id && "border-primary/40 bg-accent")}>
                    <span className="flex items-start justify-between gap-3"><strong className="font-medium">{item.name}</strong>{templateId === item.id ? <Check className="size-4 text-primary" /> : null}</span>
                    <span className="mt-2 block text-xs leading-5 text-muted-foreground">{item.description}</span>
                    <span className="mt-3 block text-xs font-medium text-muted-foreground">{t("guardrails.includedChecks", { count: item.controls?.length ?? 0, version: item.version })}</span>
                  </button>
                ))}
              </div>
              {!templateId ? <p className="mt-3 text-xs leading-5 text-muted-foreground">{t("guardrails.templateOptional")}</p> : null}
            </section>
          </div>
        ) : null}

        {step === 1 ? (
          <div className="grid gap-5">
            <Field label={t("guardrails.guardrailName")}><Input autoFocus className="min-h-11 rounded-lg bg-card" value={name} onChange={(event) => setName(event.target.value)} placeholder="Finance Assistant Guardrail" /></Field>
            {selected ? <>
              <TemplateControlSummary template={selected} parameters={parameters} compact />
              {selected.parameters?.map((parameter) => <Field key={parameter.name} label={`${parameter.label}${parameter.required ? " *" : ""}`} hint={parameter.description}>{parameter.kind === "multiline" ? <Textarea className="min-h-28 rounded-lg bg-card" value={parameters[parameter.name] ?? ""} onChange={(event) => setParameters((current) => ({ ...current, [parameter.name]: event.target.value }))} placeholder={parameter.placeholder} /> : <Input className="min-h-11 rounded-lg bg-card" value={parameters[parameter.name] ?? ""} onChange={(event) => setParameters((current) => ({ ...current, [parameter.name]: event.target.value }))} placeholder={parameter.placeholder} />}</Field>)}
            </> : null}
                <Field label={t("guardrails.businessPurpose")} hint={t("guardrails.businessPurposeHint")}><Textarea className="min-h-32 rounded-lg bg-card" value={purpose} onChange={(event) => setPurpose(event.target.value)} placeholder="Finance employees use this assistant to analyze approved company and market data." /></Field>
                <section className="rounded-lg border bg-muted/30 p-4" aria-live="polite">
                  <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                    <div className="flex min-w-0 gap-3">
                      <span className="grid size-9 shrink-0 place-items-center rounded-lg border bg-card text-primary"><Sparkles className="size-4" /></span>
                      <div><h3 className="text-sm font-medium">{t("guardrails.analyzeTitle")}</h3><p className="mt-1 max-w-2xl text-xs leading-5 text-muted-foreground">{t("guardrails.analyzeDescription")}</p></div>
                    </div>
                    <Button
                      type="button"
                      variant="outline"
                      className="min-h-11 shrink-0 bg-card"
                      disabled={purpose.trim().length < 20 || intentAnalysisStatusQuery.isLoading || !intentAnalysisStatusQuery.data?.available || analyzeIntent.isPending}
                      onClick={() => analyzeIntent.mutate()}
                    >
                      {analyzeIntent.isPending ? <LoaderCircle className="animate-spin" /> : <Sparkles />}
                      {t(analyzeIntent.isPending ? "guardrails.analyzingIntent" : analysis ? "guardrails.reanalyzeAction" : "guardrails.analyzeAction")}
                    </Button>
                  </div>
                  {intentAnalysisStatusQuery.isLoading ? <p className="mt-3 text-xs text-muted-foreground">{t("guardrails.analysisChecking")}</p> : null}
                  {!intentAnalysisStatusQuery.isLoading && !intentAnalysisStatusQuery.data?.available ? <p className="mt-3 text-xs text-amber-700 dark:text-amber-300">{t("guardrails.analysisUnavailable")}</p> : null}
                  {analysisStale ? <p className="mt-3 text-xs text-amber-700 dark:text-amber-300">{t("guardrails.analysisStale")}</p> : null}
                </section>
                {analysis ? (
                  <section className="rounded-lg border border-emerald-200 bg-emerald-50/50 p-4 dark:border-emerald-900 dark:bg-emerald-950/20">
                    <div className="flex items-start gap-3"><CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-700 dark:text-emerald-400" /><div><h3 className="text-sm font-medium">{t("guardrails.analysisComplete")}</h3><p className="mt-1 text-xs leading-5 text-muted-foreground">{t("guardrails.analysisCompleteDescription")}</p></div></div>
                    <dl className="mt-4 grid gap-3 text-xs">
                      <div><dt className="font-medium text-muted-foreground">{t("guardrails.analysisSummary")}</dt><dd className="mt-1 leading-5">{analysis.summary}</dd></div>
                      {analysis.review_notes.length ? <div><dt className="font-medium text-muted-foreground">{t("guardrails.analysisReviewNotes")}</dt><dd className="mt-1"><ul className="list-disc space-y-1 pl-4 leading-5">{analysis.review_notes.map((note) => <li key={note}>{note}</li>)}</ul></dd></div> : null}
                    </dl>
                  </section>
                ) : null}
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label={t("guardrails.allowedDomains")} hint={t("guardrails.onePerLine")}><Textarea className="min-h-36 rounded-lg bg-card" value={allowed} onChange={(event) => setAllowed(event.target.value)} placeholder={"Financial data analysis\nAccounting and reporting\nSQL, Python, and statistics for finance"} /></Field>
                  <Field label={t("guardrails.restrictedDomains")} hint={t("guardrails.restrictedHint")}><Textarea className="min-h-36 rounded-lg bg-card" value={restricted} onChange={(event) => setRestricted(event.target.value)} placeholder={"Standalone physics questions\nBiomedical advice or research\nManufacturing process design\nChemical refining instructions"} /></Field>
                </div>
          </div>
        ) : null}

        {step === 2 ? (
          <div className="space-y-5">
            {selected ? <TemplateControlSummary template={selected} parameters={parameters} /> : null}
            <InfoNotice title={t("guardrails.reviewBefore")}>{t(selected ? "guardrails.reviewCombinedDescription" : "guardrails.reviewBeforeDescription")}</InfoNotice>
            <ControlEditor definitions={definitions} risks={risks} onChange={setRisks} />
            {invalidCustomTopics ? <p className="text-sm text-destructive">{t("guardrails.topicRequired")}</p> : null}
            <InfoNotice title={t("guardrails.nextTitle")}>{t("guardrails.nextDescription")}</InfoNotice>
          </div>
        ) : null}
      </CreationFlow>
    </EntitySheet>
  );
}

function EditGuardrailSheet({ guardrail, open, onOpenChange, onSaved }: { guardrail: Guardrail; open: boolean; onOpenChange: (open: boolean) => void; onSaved: () => void }) {
  const { t } = useTranslation();
  const controlsQuery = useQuery({ queryKey: queryKeys.controlDefinitions, queryFn: getControlDefinitions });
  const [name, setName] = useState(guardrail.name);
  const [purpose, setPurpose] = useState(guardrail.purpose);
  const [allowed, setAllowed] = useState(guardrail.allowed_topics.join("\n"));
  const [restricted, setRestricted] = useState(guardrail.restricted_topics.join("\n"));
  const [risks, setRisks] = useState(guardrail.controls);
  const [level, setLevel] = useState(guardrail.safety_level);
  const [delivery, setDelivery] = useState(guardrail.output_delivery);

  useEffect(() => {
    if (open) {
      setName(guardrail.name); setPurpose(guardrail.purpose); setAllowed(guardrail.allowed_topics.join("\n")); setRestricted(guardrail.restricted_topics.join("\n")); setRisks(guardrail.controls); setLevel(guardrail.safety_level); setDelivery(guardrail.output_delivery);
    }
  }, [open, guardrail]);

  const mutation = useMutation({
    mutationFn: () => updateGuardrail(guardrail.id, { name, purpose, allowed_topics: lines(allowed), restricted_topics: lines(restricted), controls: risks, safety_level: level, output_delivery: delivery }),
    onSuccess: () => { toast.success(t("guardrails.updated")); onSaved(); },
    onError: (error) => notifyError(error, t("guardrails.operationFailed")),
  });
  const definitions = controlsQuery.data?.items.filter((item) => item.id !== "builtin_content_filter") ?? [];
  const editableRisks = risks.filter((item) => item.risk !== "builtin_content_filter");
  const invalidReasoningPolicy = hasInvalidReasoningPolicy(risks);

  return (
    <EntitySheet open={open} onOpenChange={onOpenChange} eyebrow={t("guardrails.editEyebrow")} title={t("guardrails.editTitle", { name: guardrail.name })} description={t("guardrails.editDescription")} width="xl" footer={<><Button variant="outline" onClick={() => onOpenChange(false)}>{t("common.cancel")}</Button><Button disabled={!name.trim() || !purpose.trim() || !risks.length || invalidReasoningPolicy || mutation.isPending} onClick={() => mutation.mutate()}><Save />{t(mutation.isPending ? "common.saving" : "common.save")}</Button></>}>
      <div className="grid gap-5">
        <Field label={t("guardrails.guardrailName")}><Input className="min-h-11 rounded-lg bg-card" value={name} onChange={(event) => setName(event.target.value)} /></Field>
        <Field label={t("guardrails.businessPurpose")}><Textarea className="min-h-32 rounded-lg bg-card" value={purpose} onChange={(event) => setPurpose(event.target.value)} /></Field>
        <div className="grid gap-4 sm:grid-cols-2"><Field label={t("guardrails.allowedDomains")}><Textarea className="min-h-32 rounded-lg bg-card" value={allowed} onChange={(event) => setAllowed(event.target.value)} placeholder={t("guardrails.onePerLine")} /></Field><Field label={t("guardrails.restrictedDomains")}><Textarea className="min-h-32 rounded-lg bg-card" value={restricted} onChange={(event) => setRestricted(event.target.value)} placeholder={t("guardrails.onePerLine")} /></Field></div>
        <div className="grid gap-4 sm:grid-cols-2"><Field label={t("guardrails.evaluationMode")}><Select value={level} onValueChange={(value) => setLevel(value as typeof level)}><SelectTrigger className="min-h-11 rounded-lg bg-card"><SelectValue /></SelectTrigger><SelectContent className="rounded-lg"><SelectItem value="balanced">{t("guardrails.balanced")}</SelectItem><SelectItem value="strict">{t("guardrails.strict")}</SelectItem></SelectContent></Select></Field><Field label={t("guardrails.modelOutput")}><Select value={delivery} onValueChange={(value) => setDelivery(value as typeof delivery)}><SelectTrigger className="min-h-11 rounded-lg bg-card"><SelectValue /></SelectTrigger><SelectContent className="rounded-lg"><SelectItem value="interruptible">{t("guardrails.outputRealtime")}</SelectItem><SelectItem value="window_buffered">{t("guardrails.outputWindow")}</SelectItem><SelectItem value="full_buffered">{t("guardrails.outputFull")}</SelectItem></SelectContent></Select></Field></div>
        {guardrail.source_template_id ? <InfoNotice title={t("guardrails.builtinAttached")}>{t("guardrails.builtinAttachedDescription")}</InfoNotice> : null}
        <ControlEditor definitions={definitions} risks={editableRisks} onChange={(next) => { const combined = [...guardrail.controls.filter((item) => item.risk === "builtin_content_filter"), ...next]; setRisks(combined); if (combined.some((item) => item.risk === "automated_reasoning")) setDelivery("full_buffered"); }} />
      </div>
    </EntitySheet>
  );
}

export function AddTestCaseSheet({ guardrail, open, onOpenChange, onCreated }: { guardrail: Guardrail; open: boolean; onOpenChange: (open: boolean) => void; onCreated: () => void }) {
  const { t } = useTranslation();
  const [name, setName] = useState("");
  const [risk, setRisk] = useState(guardrail.controls[0]?.risk ?? "");
  const [phase, setPhase] = useState<"input" | "output">("input");
  const [content, setContent] = useState("");
  const [expected, setExpected] = useState<TestCase["expected_decision"]>("block");
  const [trustedInstruction, setTrustedInstruction] = useState("");
  const [targetSource, setTargetSource] = useState<TestCase["target_source"]>("user_input");
  const [query, setQuery] = useState("");
  const [groundingSources, setGroundingSources] = useState("");
  const [expectedReasoningResult, setExpectedReasoningResult] = useState<NonNullable<TestCase["expected_reasoning_result"]>>("invalid");
  const promptSecurity = risk === "prompt_injection" || risk === "jailbreak";
  const grounding = risk === "contextual_grounding";
  const reasoning = risk === "automated_reasoning";
  useEffect(() => { if (open) { const initialRisk = guardrail.controls[0]?.risk ?? ""; const initialPromptSecurity = initialRisk === "prompt_injection" || initialRisk === "jailbreak"; const initialResponseAssurance = initialRisk === "contextual_grounding" || initialRisk === "automated_reasoning"; setName(""); setRisk(initialRisk); setPhase(initialResponseAssurance ? "output" : "input"); setContent(""); setExpected(initialResponseAssurance ? "transform" : "block"); setExpectedReasoningResult("invalid"); setTrustedInstruction(initialPromptSecurity ? t("guardrails.defaultTrustedInstruction", { purpose: guardrail.purpose }) : ""); setTargetSource(initialResponseAssurance ? "model_output" : "user_input"); setQuery(""); setGroundingSources(""); } }, [open, guardrail.purpose, guardrail.controls, t]);
  const mutation = useMutation({ mutationFn: () => createTestCase(guardrail.id, { name, risk, phase, content, expected_decision: expected, expected_reasoning_result: reasoning ? expectedReasoningResult : null, trusted_instruction: trustedInstruction, target_source: targetSource, query, grounding_sources: lines(groundingSources) }), onSuccess: () => { toast.success(t("guardrails.customAdded")); onCreated(); }, onError: (error) => notifyError(error, t("guardrails.operationFailed")) });
  function changeRisk(value: string) {
    setRisk(value);
    if (value !== "contextual_grounding") {
      setGroundingSources("");
    }
    if (value !== "contextual_grounding" && value !== "automated_reasoning") setQuery("");
    if (value === "prompt_injection" || value === "jailbreak") {
      setPhase("input");
      setTargetSource("user_input");
      setTrustedInstruction((current) => current || t("guardrails.defaultTrustedInstruction", { purpose: guardrail.purpose }));
    } else if (value === "contextual_grounding") {
      setPhase("output");
      setTargetSource("model_output");
      setExpected("transform");
    } else if (value === "automated_reasoning") {
      setPhase("output");
      setTargetSource("model_output");
      setExpected("transform");
    } else {
      setTargetSource("user_input");
    }
  }
  return (
    <EntitySheet open={open} onOpenChange={onOpenChange} eyebrow={t("guardrails.testEyebrow")} title={t("guardrails.testTitle")} description={t("guardrails.testDescription")} width="md" footer={<><Button variant="outline" onClick={() => onOpenChange(false)}>{t("common.cancel")}</Button><Button disabled={!name.trim() || !risk || !content.trim() || (grounding && (!query.trim() || !lines(groundingSources).length)) || mutation.isPending} onClick={() => mutation.mutate()}><Plus />{t(mutation.isPending ? "guardrails.adding" : "guardrails.addCase")}</Button></>}>
      <div className="grid gap-5">
        <Field label={t("guardrails.caseName")}><Input autoFocus className="min-h-11 rounded-lg bg-card" value={name} onChange={(event) => setName(event.target.value)} placeholder="Allow finance analysis of chemical company" /></Field>
        <div className="grid gap-4 sm:grid-cols-2"><Field label={t("guardrails.control")}><Select value={risk} onValueChange={changeRisk}><SelectTrigger className="min-h-11 rounded-lg bg-card"><SelectValue /></SelectTrigger><SelectContent>{guardrail.controls.map((item) => <SelectItem key={item.risk} value={item.risk}>{riskLabel(item.risk, t)}</SelectItem>)}</SelectContent></Select></Field><Field label={t("guardrails.modelBoundary")}><Select disabled={promptSecurity || grounding || reasoning} value={phase} onValueChange={(value) => setPhase(value as typeof phase)}><SelectTrigger className="min-h-11 rounded-lg bg-card"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="input">{t("guardrails.input")}</SelectItem><SelectItem value="output">{t("guardrails.output")}</SelectItem></SelectContent></Select></Field></div>
        {promptSecurity ? (
          <section className="grid gap-4 rounded-lg border bg-muted/30 p-4">
            <div><h3 className="text-sm font-medium">{t("guardrails.promptTrustBoundary")}</h3><p className="mt-1 text-xs leading-5 text-muted-foreground">{t("guardrails.promptTrustBoundaryDescription")}</p></div>
            <Field label={t("guardrails.trustedInstruction")} hint={t("guardrails.trustedInstructionHint")}><Textarea className="min-h-32 rounded-lg bg-card" value={trustedInstruction} onChange={(event) => setTrustedInstruction(event.target.value)} /></Field>
            <Field label={t("guardrails.untrustedSource")}><Select value={targetSource} onValueChange={(value) => setTargetSource(value as typeof targetSource)}><SelectTrigger className="min-h-11 rounded-lg bg-card"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="user_input">{t("guardrails.sourceUserInput")}</SelectItem><SelectItem value="retrieved_content">{t("guardrails.sourceRetrieved")}</SelectItem><SelectItem value="tool_output">{t("guardrails.sourceToolOutput")}</SelectItem></SelectContent></Select></Field>
          </section>
        ) : null}
        {grounding ? (
          <section className="grid gap-4 rounded-lg border bg-muted/30 p-4">
            <div><h3 className="text-sm font-medium">{t("guardrails.groundingContext")}</h3><p className="mt-1 text-xs leading-5 text-muted-foreground">{t("guardrails.groundingContextDescription")}</p></div>
            <Field label={t("guardrails.groundingQuery")}><Textarea className="min-h-24 rounded-lg bg-card" value={query} onChange={(event) => setQuery(event.target.value)} /></Field>
            <Field label={t("guardrails.groundingSources")} hint={t("guardrails.groundingSourcesHint")}><Textarea className="min-h-32 rounded-lg bg-card" value={groundingSources} onChange={(event) => setGroundingSources(event.target.value)} /></Field>
          </section>
        ) : null}
        {reasoning ? <section className="grid gap-4 rounded-lg border bg-muted/30 p-4"><div><h3 className="text-sm font-medium">{t("guardrails.reasoningContext")}</h3><p className="mt-1 text-xs leading-5 text-muted-foreground">{t("guardrails.reasoningContextDescription")}</p></div><Field label={t("guardrails.reasoningQuery")} hint={t("guardrails.reasoningQueryHint")}><Textarea className="min-h-24 rounded-lg bg-card" value={query} onChange={(event) => setQuery(event.target.value)} /></Field></section> : null}
        <Field label={t(promptSecurity ? "guardrails.untrustedTarget" : grounding ? "guardrails.groundingResponse" : reasoning ? "guardrails.reasoningResponse" : "guardrails.modelContent")}><Textarea className="min-h-40 rounded-lg bg-card" value={content} onChange={(event) => setContent(event.target.value)} placeholder={promptSecurity ? t("guardrails.untrustedTargetPlaceholder") : grounding ? t("guardrails.groundingResponsePlaceholder") : reasoning ? t("guardrails.reasoningResponsePlaceholder") : "Analyze the quarterly revenue and margin of this chemical manufacturer."} /></Field>
        <Field label={t("guardrails.expectedDecision")}><Select value={expected} onValueChange={(value) => setExpected(value as typeof expected)}><SelectTrigger className="min-h-11 rounded-lg bg-card"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="allow">{t("states.allow")}</SelectItem><SelectItem value="block">{t("states.block")}</SelectItem><SelectItem value="transform">{t("guardrails.transform")}</SelectItem><SelectItem value="intervene">{t("guardrails.anyIntervention")}</SelectItem></SelectContent></Select></Field>
        {reasoning ? <Field label={t("guardrails.expectedReasoningResult")} hint={t("guardrails.expectedReasoningResultHint")}><Select value={expectedReasoningResult} onValueChange={(value) => setExpectedReasoningResult(value as typeof expectedReasoningResult)}><SelectTrigger className="min-h-11 rounded-lg bg-card"><SelectValue /></SelectTrigger><SelectContent>{["valid", "invalid", "satisfiable", "impossible", "translation_ambiguous", "too_complex", "no_translations"].map((result) => <SelectItem key={result} value={result}>{result.toUpperCase()}</SelectItem>)}</SelectContent></Select></Field> : null}
      </div>
    </EntitySheet>
  );
}

function ControlEditor({ definitions, risks, onChange }: { definitions: ControlDefinition[]; risks: GuardrailControl[]; onChange: (risks: GuardrailControl[]) => void }) {
  const { t } = useTranslation();
  return (
    <section>
      <h3 className="text-lg">{t("guardrails.enforceTitle")}</h3>
      <p className="mt-1 text-xs text-muted-foreground">{t("guardrails.enforceDescription")}</p>
      <div className="mt-3 divide-y divide-border overflow-hidden rounded-lg border bg-card">
        {definitions.map((definition) => {
          const configured = risks.find((item) => item.risk === definition.id);
          const enabled = Boolean(configured);
          return (
            <div key={definition.id} className="p-4">
              <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_150px_44px] sm:items-center">
                <div><strong className="text-sm font-medium">{definition.display_name}</strong><p className="mt-1 text-xs leading-5 text-muted-foreground">{definition.description}</p></div>
                <Select disabled={!enabled} value={configured?.action ?? definition.default_action} onValueChange={(action) => onChange(risks.map((item) => item.risk === definition.id ? { ...item, action } : item))}><SelectTrigger aria-label={`${definition.display_name} action`} className="min-h-11 rounded-lg bg-card"><SelectValue /></SelectTrigger><SelectContent className="rounded-lg">{definition.allowed_actions.map((action) => <SelectItem key={action} value={action}>{actionLabel(action, t)}</SelectItem>)}</SelectContent></Select>
                <Switch checked={enabled} aria-label={`Control ${definition.display_name}`} onCheckedChange={(checked) => onChange(checked ? [...risks, { risk: definition.id, action: definition.default_action, reasoning_policy: definition.id === "automated_reasoning" ? { policy_id: "", policy_version: "", confidence_threshold: 0.8 } : null }] : risks.filter((item) => item.risk !== definition.id))} />
              </div>
              {definition.id === "automated_reasoning" && configured ? <div className="mt-4 grid gap-4 rounded-lg border bg-muted/30 p-4 sm:grid-cols-[minmax(0,1fr)_160px_160px]"><Field label={t("guardrails.reasoningPolicyId")}><Input className="min-h-11 bg-card" value={configured.reasoning_policy?.policy_id ?? ""} onChange={(event) => onChange(updateReasoningPolicy(risks, definition.id, { policy_id: event.target.value }))} /></Field><Field label={t("guardrails.reasoningPolicyVersion")}><Input className="min-h-11 bg-card" value={configured.reasoning_policy?.policy_version ?? ""} onChange={(event) => onChange(updateReasoningPolicy(risks, definition.id, { policy_version: event.target.value }))} /></Field><Field label={t("guardrails.reasoningConfidence")}><Input type="number" min="0" max="1" step="0.05" className="min-h-11 bg-card" value={configured.reasoning_policy?.confidence_threshold ?? 0.8} onChange={(event) => onChange(updateReasoningPolicy(risks, definition.id, { confidence_threshold: Number(event.target.value) }))} /></Field></div> : null}
            </div>
          );
        })}
      </div>
    </section>
  );
}

function TemplateControlSummary({ template, parameters, compact = false }: { template: GuardrailTemplate; parameters: Record<string, string>; compact?: boolean }) {
  const { t } = useTranslation();
  return (
    <section className="overflow-hidden rounded-lg border bg-card">
      <div className="flex items-start justify-between gap-3 border-b bg-muted/40 p-4"><div><p className="text-xs font-medium text-primary">{t("guardrails.templateRulePack")}</p><h3 className="mt-1 text-lg">{template.name}</h3><p className="mt-1 text-xs leading-5 text-muted-foreground">{template.description}</p></div><StateBadge state="local" /></div>
      <div className="grid gap-4 p-4 sm:grid-cols-2"><Fact label={t("guardrails.version")} value={template.version ?? t("guardrails.builtIn")} /><Fact label={t("guardrails.includedChecksLabel")} value={String(template.controls?.length ?? 0)} /></div>
      {!compact ? <div className="border-t p-4"><p className="text-xs font-medium text-muted-foreground">{t("guardrails.includedControls")}</p><div className="mt-2 flex flex-wrap gap-2">{template.controls?.map((control) => <span key={control} className="rounded-md border bg-muted/40 px-2 py-1 font-mono text-[11px]">{control}</span>)}</div>{Object.keys(parameters).length ? <p className="mt-3 text-xs text-muted-foreground">{t("guardrails.reviewedParameters", { parameters: Object.keys(parameters).join(", ") })}</p> : null}</div> : null}
    </section>
  );
}

function ConfiguredControlsSummary({ configurations }: { configurations: GuardrailControlConfig[] }) {
  const { t } = useTranslation();
  return (
    <section className="overflow-hidden rounded-lg border bg-card">
      <header className="border-b bg-muted/30 p-4">
        <h3 className="text-lg">{t("guardrailWizard.controls")}</h3>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">{t("guardrailWizard.selectedControlsDescription")}</p>
      </header>
      <div className="divide-y">
        {configurations.map((configuration) => {
          const active = configuration.rules.filter((rule) => rule.enabled);
          return (
            <details key={configuration.id} className="group">
              <summary className="flex min-h-16 cursor-pointer list-none items-center gap-3 p-4 hover:bg-muted/20 [&::-webkit-details-marker]:hidden">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2"><strong className="text-sm font-medium">{configuration.name}</strong><span className="rounded-md border bg-muted/30 px-1.5 py-0.5 text-[10px] text-muted-foreground">{t(`guardrailWizard.kinds.${configuration.kind}`)}</span></div>
                  <p className="mt-1 font-mono text-[11px] text-muted-foreground">{configuration.template_id ? `${configuration.template_id} · ${configuration.template_version}` : configuration.id}</p>
                </div>
                <span className="text-xs text-muted-foreground">{t("guardrailWizard.activeRuleCount", { active: active.length, total: configuration.rules.length })}</span>
                <ChevronDown className="size-4 text-muted-foreground transition-transform group-open:rotate-180" />
              </summary>
              <div className="border-t bg-muted/15 px-4 py-3">
                <ul className="space-y-2">
                  {active.map((rule) => <li key={rule.id} className="grid gap-1 text-xs sm:grid-cols-[minmax(0,1fr)_8rem_8rem]"><span className="font-medium">{rule.name}</span><span className="text-muted-foreground">{t(`guardrailWizard.detectors.${rule.detector}`)}</span><span className="text-muted-foreground">{configuredRuleActionLabel(rule.action, t)}</span></li>)}
                </ul>
              </div>
            </details>
          );
        })}
      </div>
    </section>
  );
}

function configuredRuleActionLabel(value: string, t: TFunction) {
  const normalized = value.toLowerCase();
  if (["block", "reject"].includes(normalized)) return t("guardrailWizard.actions.block");
  if (["mask", "redact"].includes(normalized)) return t("guardrailWizard.actions.mask");
  if (normalized === "rewrite") return t("guardrailWizard.actions.rewrite");
  if (normalized === "redirect") return t("guardrailWizard.actions.redirect");
  if (normalized === "allow") return t("guardrailWizard.actions.allow");
  return value;
}

function DetectionPipeline({ definitions, controls }: { definitions: ControlDefinition[]; controls: GuardrailControl[] }) {
  const { t } = useTranslation();
  const stages = [
    { id: "deterministic", title: t("guardrails.stageDeterministic"), description: t("guardrails.stageDeterministicDescription") },
    { id: "fast_semantic", title: t("guardrails.stageFastSemantic"), description: t("guardrails.stageFastSemanticDescription") },
    { id: "deep_judge", title: t("guardrails.stageDeepJudge"), description: t("guardrails.stageDeepJudgeDescription") },
  ];
  return (
    <section className="overflow-hidden rounded-lg border bg-card">
      <header className="border-b bg-muted/30 p-4"><h3 className="text-lg">{t("guardrails.detectionPipeline")}</h3><p className="mt-1 text-xs leading-5 text-muted-foreground">{t("guardrails.detectionPipelineDescription")}</p></header>
      <div className="grid md:grid-cols-3">
        {stages.map((stage, index) => {
          const count = controls.filter((control) => control.risk === "builtin_content_filter" ? stage.id === "deterministic" : definitions.find((definition) => definition.id === control.risk)?.available_stages.includes(stage.id)).length;
          return <div key={stage.id} className="relative border-b p-4 last:border-b-0 md:border-r md:border-b-0 md:last:border-r-0"><div className="flex items-center justify-between gap-3"><span className="grid size-7 place-items-center rounded-full bg-primary/10 text-xs font-semibold text-primary">{index + 1}</span><span className="text-xs font-medium text-muted-foreground">{t("guardrails.routeCount", { count })}</span></div><h4 className="mt-4 text-sm font-semibold">{stage.title}</h4><p className="mt-1 text-xs leading-5 text-muted-foreground">{stage.description}</p></div>;
        })}
      </div>
    </section>
  );
}

export function TestEvidence({ guardrail }: { guardrail: Guardrail }) {
  const { t, i18n } = useTranslation();
  const latest = guardrail.latest_test_run;
  if (!latest) return null;
  return (
    <section className="overflow-hidden rounded-lg border bg-card">
      <div className="flex items-center justify-between gap-3 border-b bg-muted/40 p-4"><div><h3 className="text-lg">{t("guardrails.latestEvidence")}</h3><p className="mt-1 text-xs text-muted-foreground">{new Date(latest.created_at).toLocaleString(i18n.language)}</p></div><StateBadge state={latest.status} /></div>
      <div className="grid grid-cols-2 gap-3 p-4 sm:grid-cols-4"><Metric label={t("guardrails.complianceLabel")} value={`${latest.metrics.compliance_rate}%`} /><Metric label={t("guardrails.falsePositive")} value={`${latest.metrics.false_positive_rate}%`} /><Metric label={t("guardrails.deepEscalation")} value={`${latest.metrics.deep_escalation_rate}%`} /><Metric label={t("guardrails.latency")} value={`${latest.metrics.p95_latency_ms} ms`} /></div>
      {guardrail.coverage?.length ? <div className="border-t"><div className="divide-y divide-border">{guardrail.coverage.map((item) => <div key={item.risk} className="grid gap-3 p-4 sm:grid-cols-[190px_minmax(0,1fr)_90px] sm:items-center"><span className="text-sm">{riskLabel(item.risk, t)}</span><Progress value={item.score ?? 0} aria-label={`${item.risk} coverage ${item.score ?? 0}%`} /><span className="text-right font-mono text-xs">{item.score === null ? t("guardrails.noRiskEvidence") : `${item.score}%`}</span></div>)}</div></div> : null}
      <div className="divide-y border-t">
        {latest.results.map((result) => (
          <TestEvidenceRow
            key={result.case_id}
            result={result}
          />
        ))}
      </div>
    </section>
  );
}

function TestEvidenceRow({ result }: { result: EvaluationCaseResult }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(!result.passed);
  const input = result.input_content;
  const phase = result.phase;
  const output = result.output_content || (result.actual_decision === "allow" ? input : "");
  const trustedInstruction = result.trusted_instruction;
  const targetSource = result.target_source;
  const groundingQuery = result.query;
  const groundingSources = result.grounding_sources;

  return (
    <details open={open} onToggle={(event) => setOpen(event.currentTarget.open)} className="group">
      <summary className="grid min-h-16 cursor-pointer list-none gap-3 p-4 transition-colors hover:bg-muted/40 focus-visible:outline-2 focus-visible:outline-ring sm:grid-cols-[28px_minmax(0,1fr)_100px_90px_20px] sm:items-center [&::-webkit-details-marker]:hidden">
        {result.passed ? <CheckCircle2 className="size-4 text-emerald-600" /> : <XCircle className="size-4 text-destructive" />}
        <div className="min-w-0">
          <strong className="text-sm font-medium">{result.name}</strong>
          <p className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">
            {result.passed ? result.reason : t("guardrails.testMismatch", { expected: t(`states.${result.expected_decision}`), actual: t(`states.${result.actual_decision}`) })}
          </p>
        </div>
        <StateBadge state={result.actual_decision} />
        <span className="font-mono text-xs text-muted-foreground">{result.latency_ms} ms</span>
        <ChevronDown className="size-4 text-muted-foreground transition-transform group-open:rotate-180" />
      </summary>

      <div className="border-t bg-muted/20 p-4 sm:p-5">
        {trustedInstruction ? (
          <section className="mb-4 overflow-hidden rounded-lg border border-primary/20 bg-primary/[0.03]">
            <header className="flex items-center gap-2 border-b border-primary/15 px-4 py-3"><ShieldCheck className="size-4 text-primary" /><h4 className="text-sm font-medium">{t("guardrails.trustedInstruction")}</h4><span className="ml-auto text-xs text-muted-foreground">{t("guardrails.trusted")}</span></header>
            <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words p-4 font-sans text-sm leading-6">{trustedInstruction}</pre>
          </section>
        ) : null}
        {groundingQuery ? (
          <div className="mb-4 grid gap-4 xl:grid-cols-2">
            <EvidenceContent label={result.risk === "automated_reasoning" ? t("guardrails.reasoningQuery") : t("guardrails.groundingQuery")} meta="query" value={groundingQuery} />
            {groundingSources.length ? <EvidenceContent label={t("guardrails.groundingSources")} meta={`${groundingSources.length}`} value={groundingSources.join("\n\n")} /> : null}
          </div>
        ) : null}
        <div className="grid gap-4 xl:grid-cols-2">
          <EvidenceContent
            label={t("guardrails.testInput")}
            meta={`${t(phase === "output" ? "guardrails.output" : "guardrails.input")} · ${targetSourceLabel(targetSource, t)}`}
            value={input || t("guardrails.evidenceNotRecorded")}
          />
          <EvidenceContent
            label={t("guardrails.testOutput")}
            meta={result.action ? actionLabel(result.action, t) : t("guardrails.evidenceNotRecorded")}
            value={output || (result.actual_decision === "block" ? t("guardrails.blockedNoOutput") : t("guardrails.evidenceNotRecorded"))}
          />
        </div>

        <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <EvidenceFact label={t("guardrails.expectedDecision")}><StateBadge state={result.expected_decision} /></EvidenceFact>
          <EvidenceFact label={t("guardrails.actualDecision")}><StateBadge state={result.actual_decision} /></EvidenceFact>
          <EvidenceFact label={t("guardrails.actualAction")}><strong className="text-sm font-medium">{result.action ? actionLabel(result.action, t) : t("guardrails.evidenceNotRecorded")}</strong></EvidenceFact>
          <EvidenceFact label={t("guardrails.stageReached")}><strong className="text-sm font-medium">{stageLabel(result.stage_reached, t)}</strong></EvidenceFact>
        </dl>
        {result.expected_reasoning_result ? <dl className="mt-3 grid grid-cols-2 gap-3"><EvidenceFact label={t("guardrails.expectedReasoningResult")}><strong className="font-mono text-sm">{result.expected_reasoning_result.toUpperCase()}</strong></EvidenceFact><EvidenceFact label={t("guardrails.actualReasoningResult")}><strong className="font-mono text-sm">{result.actual_reasoning_result?.toUpperCase() ?? t("guardrails.evidenceNotRecorded")}</strong></EvidenceFact></dl> : null}

        <section className="mt-4 rounded-lg border bg-card p-4">
          <h4 className="text-xs font-medium text-muted-foreground">{t("guardrails.decisionReason")}</h4>
          <p className="mt-2 text-sm leading-6">{result.reason || t("guardrails.evidenceNotRecorded")}</p>
        </section>

        {result.findings.length ? (
          <section className="mt-4">
            <h4 className="text-sm font-medium">{t("guardrails.triggeredFindings")}</h4>
            <div className="mt-2 divide-y rounded-lg border bg-card">
              {result.findings.map((finding, index) => (
                <div key={`${finding.risk}-${index}`} className="grid gap-2 p-4 sm:grid-cols-[160px_minmax(0,1fr)_70px]">
                  <strong className="text-sm font-medium">{riskLabel(finding.risk, t)}</strong>
                  <div className="text-xs leading-5 text-muted-foreground">
                    <p>{finding.evidence}</p>
                    {finding.grounding?.length ? <div className="mt-2 flex flex-wrap gap-2">{finding.grounding.map((score) => <span key={score.type} className="rounded-md border px-2 py-1 font-mono text-[11px]">{score.type} {Math.round(score.score * 100)}% / {Math.round(score.threshold * 100)}%</span>)}</div> : null}
                    {finding.claims?.length ? <ul className="mt-2 space-y-1">{finding.claims.map((claim) => <li key={claim.id}><strong className="font-medium">{claim.support}</strong> · {claim.claim}{claim.source_block_ids.length ? ` · ${claim.source_block_ids.join(", ")}` : ""}</li>)}</ul> : null}
                    {finding.reasoning?.length ? <ul className="mt-2 space-y-2">{finding.reasoning.map((proof) => <li key={proof.id}><strong className="font-mono font-medium">{proof.result.toUpperCase()}</strong>{proof.message ? ` · ${proof.message}` : ""}{proof.supporting_rules.length ? <span className="block">{t("guardrails.supportingRules")}: {proof.supporting_rules.map((rule) => rule.id).join(", ")}</span> : null}{proof.contradicting_rules.length ? <span className="block">{t("guardrails.contradictingRules")}: {proof.contradicting_rules.map((rule) => rule.id).join(", ")}</span> : null}</li>)}</ul> : null}
                  </div>
                  <span className="text-right font-mono text-xs text-muted-foreground">{Math.round(finding.confidence * 100)}%</span>
                </div>
              ))}
            </div>
          </section>
        ) : null}

        {result.trace.length ? (
          <section className="mt-4">
            <h4 className="text-sm font-medium">{t("guardrails.executionTrace")}</h4>
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
        ) : null}
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

export function TestCaseRow({ item, onDelete, deleting }: { item: TestCase; onDelete: () => void; deleting: boolean }) {
  const { t } = useTranslation();
  return (
    <article className="grid gap-3 p-4 md:grid-cols-[minmax(0,1fr)_130px_120px_44px] md:items-center">
      <div className="min-w-0"><strong className="text-sm font-medium">{item.name}</strong><p className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">{item.content}</p></div>
      <div className="text-xs"><p>{riskLabel(item.risk, t)}</p><p className="mt-1 text-muted-foreground capitalize">{t(item.phase === "input" ? "guardrails.input" : "guardrails.output")}{item.risk === "prompt_injection" || item.risk === "jailbreak" ? ` · ${targetSourceLabel(item.target_source, t)}` : ""}</p></div>
      <StateBadge state={item.expected_decision === "intervene" ? "intervene" : item.expected_decision} />
      <Button type="button" size="icon" variant="ghost" aria-label={`Delete ${item.name}`} disabled={deleting} onClick={onDelete}><Trash2 /></Button>
    </article>
  );
}

function RiskRow({ risk, definition, template }: { risk: GuardrailControl; definition?: ControlDefinition; template?: GuardrailTemplate }) {
  const { t } = useTranslation();
  const phases: Record<string, string> = { secrets: t("guardrails.inputOutput"), pii: t("guardrails.inputOutput"), prompt_injection: t("guardrails.input"), jailbreak: t("guardrails.input"), content_safety: t("guardrails.inputOutput"), topic_control: t("guardrails.inputOutput"), company_policy: t("guardrails.inputOutput"), contextual_grounding: t("guardrails.output"), automated_reasoning: t("guardrails.output"), builtin_content_filter: t("guardrails.perLocalControl") };
  const route = risk.risk === "builtin_content_filter" ? ["deterministic"] : definition?.available_stages ?? [];
  return <div className="grid min-h-16 gap-3 px-4 py-4 text-xs md:grid-cols-[minmax(0,1fr)_150px_190px_140px] md:items-center"><div><strong className="font-medium">{risk.risk === "builtin_content_filter" && template ? template.name : definition?.display_name ?? riskLabel(risk.risk, t)}</strong>{definition ? <p className="mt-1 line-clamp-1 text-muted-foreground">{definition.description}</p> : null}{risk.reasoning_policy ? <p className="mt-1 font-mono text-[11px] text-muted-foreground">{t("guardrails.reasoningPolicyBinding", { id: risk.reasoning_policy.policy_id, version: risk.reasoning_policy.policy_version, threshold: risk.reasoning_policy.confidence_threshold })}</p> : null}</div><span><span className="mr-1 text-muted-foreground md:hidden">{t("guardrails.modelBoundary")}:</span>{phases[risk.risk] ?? t("guardrails.modelIo")}</span><span className="flex flex-wrap gap-1">{route.map((stage) => <span key={stage} className="rounded-md border bg-muted/40 px-1.5 py-1">{stageLabel(stage, t)}</span>)}</span><span><span className="mr-1 text-muted-foreground md:hidden">{t("guardrails.whenDetected")}:</span>{actionLabel(risk.action, t)}</span></div>;
}

function TopicPanel({ title, items, empty, danger = false }: { title: string; items: string[]; empty: string; danger?: boolean }) {
  return <section className="overflow-hidden rounded-lg border bg-card"><div className="border-b bg-muted/40 px-4 py-3"><h3 className="text-lg">{title}</h3></div><div className="min-h-36 p-4">{items.length ? <ul className="space-y-2">{items.map((item) => <li key={item} className="flex items-start gap-2 text-sm"><span className={cn("mt-2 size-1.5 shrink-0 rounded-full bg-primary", danger && "bg-destructive")} />{item}</li>)}</ul> : <p className="text-sm text-muted-foreground">{empty}</p>}</div></section>;
}

function Fact({ label, value }: { label: string; value: string }) { return <div className="rounded-lg bg-muted/60 p-3"><p className="text-xs font-medium text-muted-foreground">{label}</p><p className="mt-2 text-sm">{value}</p></div>; }
function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) { return <label className="grid gap-2 text-sm font-medium">{label}{children}{hint ? <span className="text-xs font-normal leading-5 text-muted-foreground">{hint}</span> : null}</label>; }
function lines(value: string) { return value.split("\n").map((item) => item.trim()).filter(Boolean); }
function updateReasoningPolicy(risks: GuardrailControl[], risk: string, patch: Partial<NonNullable<GuardrailControl["reasoning_policy"]>>) {
  return risks.map((item) => item.risk === risk ? { ...item, reasoning_policy: { policy_id: "", policy_version: "", confidence_threshold: 0.8, ...item.reasoning_policy, ...patch } } : item);
}
function hasInvalidReasoningPolicy(risks: GuardrailControl[]) {
  const configured = risks.find((item) => item.risk === "automated_reasoning");
  if (!configured) return false;
  const policy = configured.reasoning_policy;
  return !policy?.policy_id.trim() || !policy.policy_version.trim() || policy.confidence_threshold < 0 || policy.confidence_threshold > 1;
}
function guardrailDisplayName(guardrail: Guardrail, t: TFunction) { return guardrail.is_default ? t("guardrails.defaultGuardrailName") : guardrail.name; }
function guardrailDisplayPurpose(guardrail: Guardrail, t: TFunction) { return guardrail.is_default ? t("guardrails.defaultGuardrailPurpose") : guardrail.purpose; }
function deliveryLabel(value: string, t: TFunction) { return value === "interruptible" ? t("guardrails.outputRealtime") : value === "full_buffered" ? t("guardrails.outputFull") : t("guardrails.outputWindow"); }
function riskLabel(value: string, t: TFunction) { return ({ builtin_content_filter: t("guardrails.riskBuiltin"), topic_control: t("guardrails.riskTopic"), pii: t("guardrails.riskPii"), secrets: t("guardrails.riskSecrets"), prompt_injection: t("guardrails.riskInjection"), jailbreak: t("guardrails.riskJailbreak"), content_safety: t("guardrails.riskUnsafe"), company_policy: t("guardrails.riskCompany"), contextual_grounding: t("guardrails.riskGrounding"), automated_reasoning: t("guardrails.riskReasoning") } as Record<string, string>)[value] ?? value.replaceAll("_", " "); }
function actionLabel(value: string, t: TFunction) { return ({ reject: t("guardrails.actionReject"), redact: t("guardrails.actionRedact"), rewrite: t("guardrails.actionRewrite"), regenerate: t("guardrails.actionRegenerate"), redirect: t("guardrails.actionRedirect"), clarify: t("guardrails.actionClarify"), pass: t("guardrails.actionPass"), fallback: t("guardrails.actionFallback") } as Record<string, string>)[value] ?? value; }
function stageLabel(value: string, t: TFunction) { return ({ deterministic: t("guardrails.stageDeterministic"), fast_semantic: t("guardrails.stageFastSemantic"), deep_judge: t("guardrails.stageDeepJudge"), none: t("states.not evaluated") } as Record<string, string>)[value.toLowerCase().replaceAll(" ", "_")] ?? value; }
function targetSourceLabel(value: string, t: TFunction) { return ({ user_input: t("guardrails.sourceUserInput"), retrieved_content: t("guardrails.sourceRetrieved"), tool_output: t("guardrails.sourceToolOutput"), model_output: t("guardrails.sourceModelOutput") } as Record<string, string>)[value] ?? value; }
function notifyError(error: unknown, fallback: string) { toast.error(error instanceof Error ? error.message : fallback); }
