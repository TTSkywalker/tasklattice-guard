import { useEffect, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "@tanstack/react-router";
import { Activity, ArrowLeft, ArrowUpRight, Check, ChevronDown, Circle, FileCode2, FlaskConical, History, LoaderCircle, LockKeyhole, Pencil, Plus, Rocket, Save, ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { RuntimeHealthAlert } from "@/components/dashboard/runtime-health-alert";
import { RuntimeMetricChart } from "@/components/dashboard/runtime-metric-chart";
import { EntitySheet } from "@/components/entity-sheet";
import { PolicyBindingEditor } from "@/components/policy-binding-editor";
import { EmptyState, ErrorNotice, InfoNotice, PageHeader, StateBadge } from "@/components/product-shell";
import { RuntimePostureFields } from "@/components/runtime-posture-fields";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { queryKeys } from "@/features/query-keys";
import {
  createTestCase,
  getDeployments,
  getGuardrail,
  getGuardrailVersion,
  getGuardrails,
  getGuardrailVersions,
  getMetrics,
  getPolicies,
  getTestCases,
  getValidationRuns,
  rollbackGuardrail,
  updateGuardrail,
  type Guardrail,
  type GuardrailPolicyBinding,
  type GuardrailVersion,
  type GuardrailVersionDetail,
  type MetricWindow,
  type Metrics,
  type Policy,
  type TestCase,
} from "@/lib/api";
import { CreateGuardrailWizard } from "@/routes/create-guardrail-wizard";
import { CreateDeploymentSheet, TrafficScopeBadges } from "@/routes/deployments";

const EMPTY_POLICIES: Policy[] = [];

export function GuardrailsPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: queryKeys.guardrails, queryFn: getGuardrails });
  const [createOpen, setCreateOpen] = useState(false);
  const guardrails = [...(query.data?.items ?? [])].sort((left, right) => Number(right.is_default) - Number(left.is_default));

  return (
    <section className="py-6 sm:py-8">
      <PageHeader title={t("pages.guardrails.title")} description={t("guardrails.description")} action={<Button className="min-h-11" onClick={() => setCreateOpen(true)}><Plus />{t("guardrails.create")}</Button>} />
      {query.error ? <div className="mt-5"><ErrorNotice error={query.error} /></div> : null}
      {query.isLoading ? <Skeleton className="mt-5 h-80 rounded-xl" /> : null}
      {!query.isLoading && !guardrails.length ? <div className="mt-5"><EmptyState title={t("guardrails.emptyTitle")} description={t("guardrails.emptyDescription")} action={<Button onClick={() => setCreateOpen(true)}><Plus />{t("guardrails.createFirst")}</Button>} /></div> : null}
      {guardrails.length ? (
        <section className="mt-5 overflow-hidden rounded-xl border bg-card shadow-xs">
          <header className="border-b bg-muted/25 px-5 py-3"><p className="text-xs font-medium text-muted-foreground">{t("guardrails.registry", { count: guardrails.length })}</p></header>
          <Table>
            <TableHeader><TableRow className="hover:bg-transparent"><TableHead className="min-w-64 px-5">{t("guardrails.guardrail")}</TableHead><TableHead>{t("common.status")}</TableHead><TableHead className="hidden md:table-cell">{t("guardrails.policies")}</TableHead><TableHead className="hidden lg:table-cell">{t("guardrails.validation")}</TableHead><TableHead className="hidden xl:table-cell">{t("guardrails.updated")}</TableHead></TableRow></TableHeader>
            <TableBody>{guardrails.map((guardrail) => (
              <TableRow key={guardrail.id} tabIndex={0} className="cursor-pointer focus-visible:outline-2 focus-visible:outline-ring" onClick={() => navigate({ to: "/guardrails/$guardrailId", params: { guardrailId: guardrail.id } })} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") navigate({ to: "/guardrails/$guardrailId", params: { guardrailId: guardrail.id } }); }}>
                <TableCell className="px-5"><span className="flex items-start gap-3"><span className="grid size-9 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary"><ShieldCheck className="size-4" /></span><span className="min-w-0"><strong className="block truncate text-sm">{guardrail.name}</strong><span className="mt-1 line-clamp-1 text-xs text-muted-foreground">{guardrail.purpose}</span></span></span></TableCell>
                <TableCell><StateBadge state={guardrail.status} /></TableCell>
                <TableCell className="hidden font-mono text-xs md:table-cell">{guardrail.policy_bindings.length}</TableCell>
                <TableCell className="hidden lg:table-cell">{guardrail.latest_validation_run ? <span className="flex items-center gap-2"><StateBadge state={guardrail.latest_validation_run.status} /><span className="font-mono text-xs text-muted-foreground">{guardrail.latest_validation_run.metrics.compliance_rate}%</span></span> : <span className="text-xs text-muted-foreground">{t("guardrails.notRun")}</span>}</TableCell>
                <TableCell className="hidden text-xs text-muted-foreground xl:table-cell">{new Date(guardrail.updated_at).toLocaleString(i18n.language)}</TableCell>
              </TableRow>
            ))}</TableBody>
          </Table>
        </section>
      ) : null}
      <CreateGuardrailWizard open={createOpen} onOpenChange={setCreateOpen} onCreated={async (id) => { setCreateOpen(false); await queryClient.invalidateQueries({ queryKey: queryKeys.guardrails }); navigate({ to: "/guardrails/$guardrailId", params: { guardrailId: id } }); }} />
    </section>
  );
}

export function GuardrailDetailPage() {
  const { t } = useTranslation();
  const { guardrailId } = useParams({ strict: false }) as { guardrailId: string };
  const queryClient = useQueryClient();
  const guardrailQuery = useQuery({ queryKey: queryKeys.guardrail(guardrailId), queryFn: () => getGuardrail(guardrailId) });
  const policiesQuery = useQuery({ queryKey: queryKeys.policies, queryFn: getPolicies });
  const versionsQuery = useQuery({ queryKey: queryKeys.guardrailVersions(guardrailId), queryFn: () => getGuardrailVersions(guardrailId) });
  const validationRunsQuery = useQuery({ queryKey: queryKeys.validationRuns(guardrailId), queryFn: () => getValidationRuns(guardrailId) });
  const testsQuery = useQuery({ queryKey: queryKeys.testCases(guardrailId), queryFn: () => getTestCases(guardrailId) });
  const deploymentsQuery = useQuery({ queryKey: queryKeys.deployments, queryFn: getDeployments });
  const [section, setSection] = useState("runtime");
  const [window, setWindow] = useState<MetricWindow>("24h");
  const [editOpen, setEditOpen] = useState(false);
  const [testOpen, setTestOpen] = useState(false);
  const [deploymentOpen, setDeploymentOpen] = useState(false);
  const activeVersion = versionsQuery.data?.items.find((item) => item.active);
  const activeVersionNumber = activeVersion?.version ?? 0;
  const activeValidation = validationRunsQuery.data?.items.find((run) => run.guardrail_version === activeVersionNumber && run.status === "passed") ?? null;
  const immutableQuery = useQuery({
    queryKey: queryKeys.guardrailVersion(guardrailId, activeVersionNumber),
    queryFn: () => getGuardrailVersion(guardrailId, activeVersionNumber),
    enabled: activeVersionNumber > 0,
  });
  const metricsQuery = useQuery({
    queryKey: queryKeys.metricsScope({ guardrailId, window }),
    queryFn: () => getMetrics({ guardrailId, window }),
  });

  async function refresh() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.guardrail(guardrailId) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.guardrails }),
      queryClient.invalidateQueries({ queryKey: queryKeys.guardrailVersions(guardrailId) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.metrics }),
      queryClient.invalidateQueries({ queryKey: queryKeys.testCases(guardrailId) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.allValidationRuns }),
    ]);
  }

  if (guardrailQuery.isLoading) return <Skeleton className="mt-8 h-[34rem] rounded-xl" />;
  if (guardrailQuery.error || !guardrailQuery.data) return <div className="py-8"><ErrorNotice error={guardrailQuery.error ?? new Error(t("guardrails.notFound"))} /></div>;
  const guardrail = guardrailQuery.data;
  const policies = policiesQuery.data?.items ?? EMPTY_POLICIES;
  const deployments = deploymentsQuery.data?.items.filter((item) => item.guardrail_id === guardrail.id) ?? [];
  const hasUnpublishedDraft = Boolean(activeVersion && !guardrail.tested_current);

  return (
    <section className="py-6 sm:py-8">
      <Link to="/guardrails" className="inline-flex min-h-11 items-center gap-2 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="size-4" />{t("guardrails.back")}</Link>
      <div className="mt-3 flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="font-display text-2xl font-semibold tracking-[-0.015em] sm:text-3xl">{guardrail.name}</h1>
            {activeVersion ? <Badge className="border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-50">{t("guardrails.activeVersion", { version: activeVersion.version })}</Badge> : <StateBadge state="needs_validation" />}
            {deployments.length ? <StateBadge state="protected" /> : activeVersion ? <StateBadge state="ready" /> : null}
            {guardrail.system_managed ? <Badge variant="outline">{t("guardrails.systemManaged")}</Badge> : null}
          </div>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">{guardrail.purpose}</p>
          {hasUnpublishedDraft ? <button type="button" className="mt-3 inline-flex min-h-9 items-center gap-2 rounded-md bg-amber-50 px-3 text-xs font-medium text-amber-800 hover:bg-amber-100 focus-visible:outline-2 focus-visible:outline-ring" onClick={() => setSection("draft")}><Circle className="size-2.5 fill-current" />{t("guardrails.unpublishedDraft")}</button> : null}
        </div>
        <div className="flex flex-wrap gap-2">
          {!guardrail.system_managed ? <Button variant="outline" onClick={() => setEditOpen(true)}><Pencil />{t("common.edit")}</Button> : null}
        </div>
      </div>

      <Tabs value={section} onValueChange={setSection} className="mt-7">
        <div className="overflow-x-auto">
          <TabsList className="min-w-max" aria-label={t("guardrails.detailViews")}>
            <TabsTrigger value="runtime">{t("guardrails.runtimeTab")}</TabsTrigger>
            <TabsTrigger value="immutable">{activeVersion ? t("guardrails.activeVersionTab", { version: activeVersion.version }) : t("guardrails.activeVersionTabEmpty")}</TabsTrigger>
            <TabsTrigger value="draft"><span className="flex items-center gap-2">{t("guardrails.draftReleaseTab")}{hasUnpublishedDraft ? <Circle className="size-2 fill-amber-500 text-amber-500" /> : null}</span></TabsTrigger>
          </TabsList>
        </div>
        <TabsContent value="runtime" className="pt-5">
          <GuardrailRuntimeView metrics={metricsQuery.data} loading={metricsQuery.isLoading} error={metricsQuery.error} deployments={deployments} window={window} onWindowChange={setWindow} />
        </TabsContent>
        <TabsContent value="immutable" className="pt-5">
          <ImmutableVersionView detail={immutableQuery.data} activeVersion={activeVersion} versions={versionsQuery.data?.items ?? []} loading={versionsQuery.isLoading || immutableQuery.isLoading || validationRunsQuery.isLoading} guardrailId={guardrail.id} validation={activeValidation} onChanged={refresh} onOpenDraft={() => setSection("draft")} />
        </TabsContent>
        <TabsContent value="draft" className="pt-5">
          <DraftReleaseView guardrail={guardrail} policies={policies} cases={testsQuery.data?.items ?? []} casesLoading={testsQuery.isLoading} activeVersion={activeVersion} deployments={deployments} onEdit={() => setEditOpen(true)} onAddCase={() => setTestOpen(true)} onCreateDeployment={() => setDeploymentOpen(true)} />
        </TabsContent>
      </Tabs>

      <EditGuardrailSheet guardrail={guardrail} policies={policies} open={editOpen} onOpenChange={setEditOpen} onSaved={async () => { setEditOpen(false); await refresh(); }} />
      <AddTestCaseSheet guardrail={guardrail} open={testOpen} onOpenChange={setTestOpen} onCreated={async () => { setTestOpen(false); await refresh(); }} />
      <CreateDeploymentSheet open={deploymentOpen} onOpenChange={setDeploymentOpen} guardrails={[guardrail]} onCreated={async () => { setDeploymentOpen(false); await refresh(); }} />
    </section>
  );
}

export function GuardrailRuntimeView({ metrics, loading, error, deployments, window, onWindowChange }: { metrics?: Metrics; loading: boolean; error: unknown; deployments: Awaited<ReturnType<typeof getDeployments>>["items"]; window: MetricWindow; onWindowChange: (window: MetricWindow) => void }) {
  const { t, i18n } = useTranslation();
  if (loading) return <Skeleton className="h-[38rem] rounded-xl" />;
  if (error || !metrics) return <ErrorNotice error={error ?? new Error(t("guardrails.runtimeUnavailable"))} />;
  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div><h2 className="text-base font-semibold">{t("guardrails.runtimeTitle")}</h2><p className="mt-0.5 text-xs text-muted-foreground">{t("guardrails.runtimeDescription")}</p></div>
        <Select value={window} onValueChange={(value) => onWindowChange(value as MetricWindow)}><SelectTrigger className="h-9 w-full bg-card sm:w-40" aria-label={t("dashboard.timeRangeFilter")}><SelectValue /></SelectTrigger><SelectContent>{(["1h", "24h", "7d", "15d", "30d"] as MetricWindow[]).map((value) => <SelectItem key={value} value={value}>{t(`dashboard.windows.${value}`)}</SelectItem>)}</SelectContent></Select>
      </div>
      <RuntimeHealthAlert metrics={metrics} />
      <dl className="grid overflow-hidden rounded-lg border border-border/65 bg-card sm:grid-cols-2 xl:grid-cols-4">
        <RuntimeStat label={t("dashboard.protectedTraffic")} value={metrics.total_decisions.toLocaleString(i18n.language)} detail={t("guardrails.callsInWindow")} />
        <RuntimeStat label={t("dashboard.interventionRate")} value={metrics.total_decisions ? `${metrics.intervention_rate}%` : "—"} detail={t("guardrails.blockedTransformed", { blocked: metrics.blocked, transformed: metrics.intervened })} />
        <RuntimeStat label={t("dashboard.p95Latency")} value={metrics.total_decisions ? `${metrics.runtime_p95_ms} ms` : "—"} detail={t("guardrails.runtimeLatencyDetail")} />
        <RuntimeStat label={t("dashboard.errorRate")} value={metrics.total_decisions ? `${metrics.error_rate}%` : "—"} detail={t("guardrails.errorsInWindow", { count: metrics.errors })} />
      </dl>
      <RuntimeMetricChart metrics={metrics} />
      <CallerDistribution metrics={metrics} deployments={deployments} />
    </div>
  );
}

function RuntimeStat({ label, value, detail }: { label: string; value: string; detail: string }) {
  return <div className="min-h-20 border-b px-4 py-3 last:border-b-0 sm:odd:border-r sm:[&:nth-child(3)]:border-b-0 xl:border-b-0 xl:border-r xl:odd:border-r xl:last:border-r-0"><dt className="text-xs font-medium text-muted-foreground">{label}</dt><dd className="mt-1 text-xl font-semibold tabular-nums">{value}</dd><p className="mt-1 text-xs text-muted-foreground">{detail}</p></div>;
}

function CallerDistribution({ metrics, deployments }: { metrics: Metrics; deployments: Awaited<ReturnType<typeof getDeployments>>["items"] }) {
  const { t, i18n } = useTranslation();
  return <Card size="sm" className="gap-0 overflow-hidden py-0 shadow-none"><CardHeader className="border-b px-4 py-3"><CardTitle className="text-sm">{t("guardrails.callersTitle")}</CardTitle><CardDescription className="text-xs leading-5">{t("guardrails.callersDescription")}</CardDescription></CardHeader>{metrics.caller_distribution.length ? <Table className="text-xs"><TableHeader><TableRow className="hover:bg-transparent"><TableHead className="h-9 pl-4">{t("guardrails.caller")}</TableHead><TableHead className="h-9">{t("guardrails.trafficScope")}</TableHead><TableHead className="h-9">{t("guardrails.volumeShare")}</TableHead><TableHead className="h-9">{t("guardrails.servedVersion")}</TableHead><TableHead className="h-9">{t("guardrails.outcome")}</TableHead><TableHead className="h-9">{t("dashboard.p95Latency")}</TableHead></TableRow></TableHeader><TableBody>{metrics.caller_distribution.map((item) => { const deployment = deployments.find((candidate) => candidate.id === item.deployment_id); return <TableRow key={`${item.integration_id}:${item.deployment_id}:${item.protocol}`}><TableCell className="py-2.5 pl-4 align-top"><strong className="text-sm font-medium">{item.integration_name}</strong><p className="mt-0.5 font-mono text-xs text-muted-foreground">{item.protocol}</p></TableCell><TableCell className="max-w-80 py-2.5 align-top"><p className="mb-1 text-xs font-medium">{item.deployment_name}</p>{deployment ? <TrafficScopeBadges deployment={deployment} /> : <span className="text-xs text-muted-foreground">{t("guardrails.unassignedTraffic")}</span>}</TableCell><TableCell className="py-2.5 align-top"><strong className="text-sm tabular-nums">{item.requests.toLocaleString(i18n.language)}</strong><div className="mt-1.5 flex items-center gap-2"><Progress className="h-1 w-16" value={item.share} /><span className="text-xs text-muted-foreground">{item.share}%</span></div></TableCell><TableCell className="py-2.5 align-top"><div className="flex flex-wrap gap-1">{item.guardrail_versions.map((version) => <Badge key={version} variant="outline" className="font-mono">v{version}</Badge>)}</div></TableCell><TableCell className="py-2.5 align-top"><p className="text-xs">{t("guardrails.interventionSummary", { rate: item.intervention_rate })}</p><p className="mt-0.5 text-xs text-muted-foreground">{t("guardrails.errorSummary", { rate: item.error_rate })}</p></TableCell><TableCell className="py-2.5 align-top font-mono text-xs">{item.p95_latency_ms} ms</TableCell></TableRow>; })}</TableBody></Table> : <div className="px-4 pb-4"><EmptyState title={t("guardrails.noRuntimeCalls")} description={t("guardrails.noRuntimeCallsDescription")} /></div>}</Card>;
}

export function ImmutableVersionView({ detail, activeVersion, versions, loading, guardrailId, validation, onChanged, onOpenDraft }: { detail?: GuardrailVersionDetail; activeVersion?: GuardrailVersion; versions: GuardrailVersion[]; loading: boolean; guardrailId: string; validation: Guardrail["latest_validation_run"]; onChanged: () => Promise<void>; onOpenDraft: () => void }) {
  const { t, i18n } = useTranslation();
  if (loading) return <Skeleton className="h-[34rem] rounded-xl" />;
  if (!activeVersion || !detail) return <EmptyState title={t("guardrails.noActiveVersion")} description={t("guardrails.noActiveVersionDescription")} action={<Button onClick={onOpenDraft}>{t("guardrails.openDraftRelease")}</Button>} />;
  return <div className="space-y-4">
    <Card className="shadow-none"><CardHeader className="border-b"><div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between"><div><div className="flex items-center gap-2"><LockKeyhole className="size-4 text-primary" /><CardTitle>{t("guardrails.immutableConfiguration", { version: detail.version })}</CardTitle></div><CardDescription className="mt-2">{t("guardrails.immutableDescription")}</CardDescription></div><Badge variant="outline" className="w-fit">{t("guardrails.readOnlyImmutable")}</Badge></div></CardHeader><CardContent className="space-y-6 pt-6">
      <dl className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"><VersionFact label={t("guardrails.runtimeEngine")} value={`${detail.runtime_engine} · ${detail.runtime_profile}`} /><VersionFact label={t("guardrails.compiledWith")} value={detail.compiler_version} mono /><VersionFact label={t("guardrails.createdAt")} value={new Date(detail.created_at).toLocaleString(i18n.language)} /><VersionFact label={t("guardrails.configIdentity")} value={detail.config_checksum} mono /></dl>
      <div className="grid gap-4 lg:grid-cols-2"><ImmutablePosture detail={detail} /><PinnedPolicies bindings={detail.policy_bindings} /></div>
      <div className="grid gap-4 lg:grid-cols-2"><CompiledRails detail={detail} /><CompiledDependencies detail={detail} /></div>
    </CardContent></Card>
    <GeneratedArtifacts artifacts={detail.artifacts} />
    <Card className="shadow-none"><CardHeader><CardTitle>{t("guardrails.validationEvidence")}</CardTitle><CardDescription>{t("guardrails.validationEvidenceDescription")}</CardDescription></CardHeader><CardContent>{validation ? <div className="flex flex-col gap-3 rounded-lg border bg-muted/20 p-4 sm:flex-row sm:items-center sm:justify-between"><div><div className="flex items-center gap-2"><StateBadge state={validation.status} /><span className="text-sm font-medium">{t("guardrails.compliance", { rate: validation.metrics.compliance_rate })}</span></div><p className="mt-2 text-xs text-muted-foreground">{new Date(validation.created_at).toLocaleString(i18n.language)}</p></div><Button variant="outline" asChild><Link to="/validation" search={{ guardrail: guardrailId }}><FlaskConical />{t("guardrails.openValidation")}</Link></Button></div> : <InfoNotice title={t("guardrails.noValidationEvidence")}>{t("guardrails.noEvidence")}</InfoNotice>}</CardContent></Card>
    <details className="group overflow-hidden rounded-xl border bg-card"><summary className="flex min-h-14 cursor-pointer list-none items-center justify-between px-5 text-sm font-semibold focus-visible:outline-2 focus-visible:outline-ring [&::-webkit-details-marker]:hidden">{t("guardrails.versionHistory")}<ChevronDown className="size-4 text-muted-foreground transition-transform group-open:rotate-180" /></summary><div className="border-t p-4"><VersionHistory guardrailId={guardrailId} versions={versions} loading={false} onChanged={onChanged} /></div></details>
  </div>;
}

function VersionFact({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) { return <div className="min-w-0"><dt className="text-xs text-muted-foreground">{label}</dt><dd className={`${mono ? "font-mono text-xs" : "text-sm font-medium"} mt-1.5 truncate`} title={value}>{value}</dd></div>; }

function ImmutablePosture({ detail }: { detail: GuardrailVersionDetail }) { const { t } = useTranslation(); return <section className="rounded-lg border p-4"><h3 className="text-sm font-semibold">{t("guardrails.decisionPosture")}</h3><dl className="mt-4 grid gap-4 sm:grid-cols-2"><VersionFact label={t("guardrailWizard.safetyLevel")} value={t(`guardrailWizard.safetyLevelOptions.${detail.safety_level}`)} /><VersionFact label={t("guardrailWizard.outputDelivery")} value={t(`guardrailWizard.outputDeliveryOptions.${detail.output_delivery}`)} /><VersionFact label={t("guardrails.colangVersion")} value={detail.colang_version} /><VersionFact label={t("guardrails.criticalPath")} value={`${detail.estimated_critical_path_ms} ms`} /></dl></section>; }

function PinnedPolicies({ bindings }: { bindings: GuardrailVersionDetail["policy_bindings"] }) { const { t } = useTranslation(); return <section className="rounded-lg border p-4"><h3 className="text-sm font-semibold">{t("guardrails.pinnedPolicies")}</h3><div className="mt-3 divide-y">{bindings.map((binding) => <div key={`${binding.policy_id}@${binding.policy_version}`} className="py-3 first:pt-0 last:pb-0"><div className="flex flex-wrap items-center justify-between gap-2"><code className="text-xs">{binding.policy_id}@{binding.policy_version}</code><Badge variant="outline">{binding.action ?? t("guardrails.policyBehavior")}</Badge></div><p className="mt-2 text-xs text-muted-foreground">{t("guardrails.pinnedPolicyRules", { count: binding.enabled_rule_ids.length })}</p></div>)}</div></section>; }

function CompiledRails({ detail }: { detail: GuardrailVersionDetail }) { const { t } = useTranslation(); return <section className="rounded-lg border p-4"><h3 className="text-sm font-semibold">{t("guardrails.compiledRailsActions")}</h3><div className="mt-3 space-y-2">{detail.rails.map((rail, index) => <div key={`${rail.rail_type}:${rail.flow}:${index}`} className="flex items-center justify-between gap-3 rounded-md bg-muted/40 px-3 py-2 text-xs"><span className="min-w-0 truncate font-mono">{rail.flow}</span><Badge variant="outline" className="shrink-0 uppercase">{rail.rail_type}</Badge></div>)}{detail.actions.map((action) => <div key={`${action.name}:${action.flow}`} className="flex items-center justify-between gap-3 rounded-md bg-muted/40 px-3 py-2 text-xs"><span className="min-w-0 truncate font-mono">{action.name}{action.version ? `@${action.version}` : ""}</span><span className="shrink-0 text-muted-foreground">{action.timeout_ms} ms</span></div>)}</div></section>; }

function CompiledDependencies({ detail }: { detail: GuardrailVersionDetail }) { const { t } = useTranslation(); return <section className="rounded-lg border p-4"><h3 className="text-sm font-semibold">{t("guardrails.dependenciesModels")}</h3><div className="mt-3 flex flex-wrap gap-2">{detail.dependencies.map((item) => <Badge key={`${item.kind}:${item.name}:${item.version}`} variant="secondary" className="font-mono">{item.kind}:{item.name}@{item.version}</Badge>)}{detail.models.map((model) => <Badge key={model} variant="outline" className="font-mono">model:{model}</Badge>)}{!detail.dependencies.length && !detail.models.length ? <span className="text-xs text-muted-foreground">{t("guardrails.noExternalDependencies")}</span> : null}</div></section>; }

function GeneratedArtifacts({ artifacts }: { artifacts: GuardrailVersionDetail["artifacts"] }) { const { t } = useTranslation(); const [selected, setSelected] = useState(artifacts[0]?.path ?? ""); const artifact = artifacts.find((item) => item.path === selected) ?? artifacts[0]; return <details className="group overflow-hidden rounded-xl border bg-card"><summary className="flex min-h-14 cursor-pointer list-none items-center justify-between px-5 focus-visible:outline-2 focus-visible:outline-ring [&::-webkit-details-marker]:hidden"><span><span className="flex items-center gap-2 text-sm font-semibold"><FileCode2 className="size-4 text-primary" />{t("guardrails.generatedArtifacts")}</span><span className="mt-1 block text-xs font-normal text-muted-foreground">{t("guardrails.generatedArtifactsDescription")}</span></span><ChevronDown className="size-4 text-muted-foreground transition-transform group-open:rotate-180" /></summary>{artifact ? <div className="grid border-t lg:grid-cols-[14rem_minmax(0,1fr)]"><nav className="border-b p-2 lg:border-r lg:border-b-0" aria-label={t("guardrails.artifactFiles")}>{artifacts.map((item) => <button key={item.path} type="button" className={`flex min-h-10 w-full items-center gap-2 rounded-md px-3 text-left font-mono text-xs ${item.path === artifact.path ? "bg-primary/10 text-primary" : "text-muted-foreground hover:bg-muted hover:text-foreground"}`} onClick={(event) => { event.preventDefault(); setSelected(item.path); }}><FileCode2 className="size-3.5" />{item.path}</button>)}</nav><pre className="max-h-[32rem] overflow-auto bg-muted/25 p-4 text-xs leading-5"><code>{artifact.content}</code></pre></div> : null}</details>; }

export function DraftReleaseView({ guardrail, policies, cases, casesLoading, activeVersion, deployments, onEdit, onAddCase, onCreateDeployment }: { guardrail: Guardrail; policies: Policy[]; cases: TestCase[]; casesLoading: boolean; activeVersion?: GuardrailVersion; deployments: Awaited<ReturnType<typeof getDeployments>>["items"]; onEdit: () => void; onAddCase: () => void; onCreateDeployment: () => void }) { const { t } = useTranslation(); const checks = [{ label: t("guardrails.flowIntent"), complete: Boolean(guardrail.purpose), detail: t("guardrails.intentCheckDetail") }, { label: t("guardrails.flowPolicies"), complete: guardrail.policy_bindings.length > 0, detail: t("guardrails.policyCheckDetail", { count: guardrail.policy_bindings.length }) }, { label: guardrail.tested_current ? t("guardrails.flowValidationPassed") : t("guardrails.flowValidationRequired"), complete: guardrail.tested_current, detail: guardrail.latest_validation_run ? t("guardrails.compliance", { rate: guardrail.latest_validation_run.metrics.compliance_rate }) : t("guardrails.noValidationEvidence") }]; return <div className="space-y-4">{activeVersion && !guardrail.tested_current ? <div role="status" className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-amber-900"><p className="text-sm font-semibold">{t("guardrails.draftAheadTitle", { version: activeVersion.version })}</p><p className="mt-1 text-xs leading-5">{t("guardrails.draftAheadDescription", { version: activeVersion.version })}</p></div> : null}<Card className="shadow-none"><CardHeader><CardTitle>{t("guardrails.releaseReadiness")}</CardTitle><CardDescription>{t("guardrails.releaseReadinessDescription")}</CardDescription></CardHeader><CardContent><div className="grid gap-2 lg:grid-cols-3">{checks.map((check) => <div key={check.label} className="flex gap-3 rounded-lg border p-4"><span className={`grid size-6 shrink-0 place-items-center rounded-full ${check.complete ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>{check.complete ? <Check className="size-3.5" /> : <Circle className="size-3.5" />}</span><div><p className="text-sm font-medium">{check.label}</p><p className="mt-1 text-xs leading-5 text-muted-foreground">{check.detail}</p></div></div>)}</div><div className="mt-5 flex flex-wrap gap-2">{!guardrail.system_managed ? <Button variant="outline" onClick={onEdit}><Pencil />{t("common.edit")}</Button> : null}<Button variant="outline" asChild><Link to="/validation" search={{ guardrail: guardrail.id }}><FlaskConical />{t("guardrails.openValidation")}</Link></Button>{!guardrail.system_managed && guardrail.tested_current ? <Button onClick={onCreateDeployment}><Rocket />{t("guardrails.createDeployment")}</Button> : null}</div></CardContent></Card><section><div className="mb-3"><h2 className="text-base font-semibold">{t("guardrails.draftConfiguration")}</h2><p className="mt-1 text-sm text-muted-foreground">{t("guardrails.draftConfigurationDescription")}</p></div><PolicyBindings bindings={guardrail.policy_bindings} policies={policies} /></section><section><div className="mb-3 flex items-end justify-between gap-3"><div><h2 className="text-base font-semibold">{t("guardrails.validationInputs")}</h2><p className="mt-1 text-sm text-muted-foreground">{t("guardrails.validationInputsDescription")}</p></div></div><TestCases cases={cases} bindings={guardrail.policy_bindings} policies={policies} loading={casesLoading} onAdd={onAddCase} /></section>{deployments.length ? <Card className="shadow-none"><CardHeader><CardTitle>{t("guardrails.guardrailDeployments")}</CardTitle><CardDescription>{t("guardrails.guardrailDeploymentsDescription")}</CardDescription></CardHeader><CardContent className="space-y-3">{deployments.map((deployment) => <div key={deployment.id} className="rounded-lg border p-4"><div className="flex flex-wrap items-center justify-between gap-2"><strong className="text-sm font-medium">{deployment.name}</strong><Badge variant="outline">v{deployment.guardrail_version}</Badge></div><div className="mt-3"><TrafficScopeBadges deployment={deployment} /></div></div>)}</CardContent></Card> : null}</div>; }

function PolicyBindings({ bindings, policies }: { bindings: GuardrailPolicyBinding[]; policies: Policy[] }) {
  const { t } = useTranslation();
  return bindings.length ? <div className="grid gap-3 lg:grid-cols-2">{bindings.map((binding) => {
    const policy = policies.find((item) => item.id === binding.policy_id);
    const name = policy?.name ?? binding.policy_id;
    const enabledRuleCount = binding.enabled_rule_ids.length || policy?.rules.length || 0;
    return <Link
      key={`${binding.policy_id}@${binding.policy_version}`}
      to="/policy-library"
      search={{ policy: binding.policy_id }}
      aria-label={t("guardrails.inspectPolicyAria", { name })}
      className="group rounded-lg border bg-card p-4 shadow-xs outline-none transition-colors hover:border-primary/35 hover:bg-primary/[0.025] focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30"
    >
      <div className="flex items-start justify-between gap-3">
        <span className="min-w-0"><strong className="block truncate text-sm">{name}</strong><span className="mt-1 block font-mono text-xs text-muted-foreground">{binding.policy_id}@{binding.policy_version}</span></span>
        <span className="flex shrink-0 items-center gap-1 text-xs font-medium text-primary">{t("guardrails.inspectPolicy")}<ArrowUpRight className="size-3.5" /></span>
      </div>
      <p className="mt-3 line-clamp-2 text-xs leading-5 text-muted-foreground">{policy?.description}</p>
      <div className="mt-4 flex flex-wrap items-center gap-2"><Badge variant="secondary">{t("guardrails.ruleCount", { count: enabledRuleCount })}</Badge>{binding.enabled_rails.map((rail) => <Badge key={rail} variant="outline" className="font-mono uppercase">{rail}</Badge>)}<span className="ml-auto text-xs text-muted-foreground">{binding.action ?? t("guardrails.policyBehavior")}</span></div>
    </Link>;
  })}</div> : <EmptyState title={t("guardrails.noPolicies")} description={t("guardrails.noPoliciesDescription")} />;
}

type TestCaseSourceGroup = {
  id: string;
  kind: "policy" | "guardrail";
  label: string;
  sourceId: string | null;
  version: string | null;
  cases: TestCase[];
  coveredRules: number;
};

function groupTestCasesBySource(cases: TestCase[], bindings: GuardrailPolicyBinding[], policies: Policy[]): TestCaseSourceGroup[] {
  const boundPolicyIds = new Set(bindings.map((binding) => binding.policy_id));
  const policyGroups = bindings.map((binding) => {
    const items = cases.filter((item) => item.origin !== "custom" && item.source_policy_id === binding.policy_id);
    const policy = policies.find((item) => item.id === binding.policy_id);
    return {
      id: `policy:${binding.policy_id}`,
      kind: "policy" as const,
      label: policy?.name ?? binding.policy_id,
      sourceId: binding.policy_id,
      version: binding.policy_version,
      cases: items,
      coveredRules: new Set(items.flatMap((item) => item.covered_rule_ids)).size,
    };
  });
  const unboundSourceIds = Array.from(new Set(cases.flatMap((item) => item.origin !== "custom" && item.source_policy_id && !boundPolicyIds.has(item.source_policy_id) ? [item.source_policy_id] : [])));
  const unboundGroups = unboundSourceIds.map((sourceId) => {
    const items = cases.filter((item) => item.origin !== "custom" && item.source_policy_id === sourceId);
    const policy = policies.find((item) => item.id === sourceId);
    return {
      id: `policy:${sourceId}`,
      kind: "policy" as const,
      label: policy?.name ?? sourceId,
      sourceId,
      version: items[0]?.source_policy_version ?? null,
      cases: items,
      coveredRules: new Set(items.flatMap((item) => item.covered_rule_ids)).size,
    };
  });
  const guardrailCases = cases.filter((item) => item.origin === "custom" || !item.source_policy_id);
  return [...policyGroups, ...unboundGroups, {
    id: "guardrail:custom",
    kind: "guardrail",
    label: "",
    sourceId: null,
    version: null,
    cases: guardrailCases,
    coveredRules: new Set(guardrailCases.flatMap((item) => item.covered_rule_ids)).size,
  }];
}

export function TestCases({ cases, bindings, policies, loading, onAdd }: { cases: TestCase[]; bindings: GuardrailPolicyBinding[]; policies: Policy[]; loading: boolean; onAdd: () => void }) {
  const { t } = useTranslation();
  if (loading) return <Skeleton className="h-64 rounded-xl" />;
  const groups = groupTestCasesBySource(cases, bindings, policies);
  const inheritedCount = groups.filter((group) => group.kind === "policy").reduce((total, group) => total + group.cases.length, 0);
  const customCount = groups.find((group) => group.kind === "guardrail")?.cases.length ?? 0;
  return <section className="overflow-hidden rounded-lg border bg-card">
    <header className="flex flex-col gap-3 border-b bg-muted/20 p-4 sm:flex-row sm:items-center sm:justify-between">
      <div><h3 className="text-sm font-semibold">{t("guardrails.testCaseSources")}</h3><p className="mt-1 text-xs leading-5 text-muted-foreground">{t("guardrails.testCaseSourceSummary", { inherited: inheritedCount, policies: groups.filter((group) => group.kind === "policy").length, custom: customCount })}</p></div>
      <Button className="min-h-11 self-start sm:self-auto" variant="outline" onClick={onAdd}><Plus />{t("guardrails.addTestCase")}</Button>
    </header>
    <div className="divide-y">{groups.map((group) => {
      const label = group.kind === "policy" ? group.label : t("guardrails.guardrailCustomTests");
      const identity = group.kind === "policy" ? `${group.sourceId}@${group.version}` : t("guardrails.guardrailCustomTestsIdentity");
      return <details key={group.id} data-testid={`test-source-${group.id}`} className="group">
        <summary className="flex min-h-16 cursor-pointer list-none items-center gap-3 px-4 py-3 outline-none hover:bg-muted/25 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring [&::-webkit-details-marker]:hidden">
          <span className="grid size-8 shrink-0 place-items-center rounded-md border bg-muted/25 text-muted-foreground">{group.kind === "policy" ? <ShieldCheck className="size-4" /> : <FlaskConical className="size-4" />}</span>
          <span className="min-w-0 flex-1"><span className="flex flex-wrap items-center gap-2"><strong className="truncate text-sm font-medium">{label}</strong><Badge variant="outline" className="font-normal">{group.kind === "policy" ? t("guardrails.inheritedTests") : t("guardrails.customTests")}</Badge></span><span className="mt-1 block truncate font-mono text-xs text-muted-foreground">{identity}</span></span>
          <span className="hidden shrink-0 text-right text-xs text-muted-foreground sm:block">{t("guardrails.testCaseGroupSummary", { cases: group.cases.length, rules: group.coveredRules })}</span>
          <ChevronDown className="size-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180" />
        </summary>
        <div className="border-t bg-muted/10">
          {group.cases.length ? <div className="divide-y">{group.cases.map((item) => <article key={item.id} className="grid gap-2 px-4 py-3 pl-15 sm:grid-cols-[minmax(0,1fr)_7rem_8rem] sm:items-center">
            <span className="min-w-0"><strong className="block truncate text-sm font-medium">{item.name}</strong><span className="mt-1 block truncate font-mono text-xs text-muted-foreground">{item.source_case_id ?? item.id}</span></span>
            <Badge variant="outline" className="w-fit font-mono uppercase">{item.phase}</Badge>
            <StateBadge state={item.expected_decision} />
          </article>)}</div> : <div className="px-4 py-4 pl-15"><p className="text-xs leading-5 text-muted-foreground">{group.kind === "policy" ? t("guardrails.noInheritedTests") : t("guardrails.noCustomTests")}</p>{group.kind === "guardrail" ? <Button className="mt-3 min-h-11" size="sm" variant="outline" onClick={onAdd}><Plus />{t("guardrails.addTestCase")}</Button> : null}</div>}
        </div>
      </details>;
    })}</div>
  </section>;
}

function VersionHistory({ guardrailId, versions, loading, onChanged }: { guardrailId: string; versions: GuardrailVersion[]; loading: boolean; onChanged: () => Promise<void> }) {
  const { t, i18n } = useTranslation();
  const rollback = useMutation({ mutationFn: (version: number) => rollbackGuardrail(guardrailId, version), onSuccess: async () => { toast.success(t("guardrails.rollbackSucceeded")); await onChanged(); }, onError: (error) => notifyError(error, t("guardrails.operationFailed")) });
  if (loading) return <Skeleton className="h-48 rounded-xl" />;
  if (!versions.length) return <EmptyState title={t("guardrails.noVersions")} description={t("guardrails.noVersionsDescription")} />;
  return <section className="overflow-hidden rounded-xl border bg-card"><div className="divide-y">{versions.map((version) => <article key={version.version} className="grid gap-3 p-4 sm:grid-cols-[6rem_minmax(0,1fr)_11rem_9rem] sm:items-center"><span className="flex items-center gap-2"><History className="size-4 text-primary" /><strong className="font-mono text-sm">v{version.version}</strong></span><span className="min-w-0"><span className="block text-xs">{version.compiler_version} · {version.runtime_engine}</span><code className="mt-1 block truncate text-xs text-muted-foreground">{version.config_checksum || version.plan_checksum}</code></span><time className="text-xs text-muted-foreground">{new Date(version.created_at).toLocaleString(i18n.language)}</time><span>{version.active ? <StateBadge state="active" /> : <Button size="sm" variant="outline" disabled={rollback.isPending} onClick={() => rollback.mutate(version.version)}>{rollback.isPending && rollback.variables === version.version ? <LoaderCircle className="animate-spin" /> : <History />}{t("guardrails.rollback")}</Button>}</span></article>)}</div></section>;
}

function EditGuardrailSheet({ guardrail, policies, open, onOpenChange, onSaved }: { guardrail: Guardrail; policies: Policy[]; open: boolean; onOpenChange: (open: boolean) => void; onSaved: () => void }) {
  const { t } = useTranslation();
  const [name, setName] = useState(guardrail.name);
  const [purpose, setPurpose] = useState(guardrail.purpose);
  const [allowed, setAllowed] = useState(guardrail.allowed_topics.join("\n"));
  const [restricted, setRestricted] = useState(guardrail.restricted_topics.join("\n"));
  const [bindings, setBindings] = useState(guardrail.policy_bindings);
  const [level, setLevel] = useState(guardrail.safety_level);
  const [delivery, setDelivery] = useState(guardrail.output_delivery);
  useEffect(() => { if (open) { setName(guardrail.name); setPurpose(guardrail.purpose); setAllowed(guardrail.allowed_topics.join("\n")); setRestricted(guardrail.restricted_topics.join("\n")); setBindings(guardrail.policy_bindings); setLevel(guardrail.safety_level); setDelivery(guardrail.output_delivery); } }, [guardrail, open]);
  const mutation = useMutation({ mutationFn: () => updateGuardrail(guardrail.id, { name, purpose, allowed_topics: lines(allowed), restricted_topics: lines(restricted), policy_bindings: bindings, safety_level: level, output_delivery: delivery }), onSuccess: () => { toast.success(t("guardrails.updated")); onSaved(); }, onError: (error) => notifyError(error, t("guardrails.operationFailed")) });
  return <EntitySheet open={open} onOpenChange={onOpenChange} eyebrow={t("guardrails.editEyebrow")} title={t("guardrails.editTitle", { name: guardrail.name })} description={t("guardrails.editDescription")} width="xl" footer={<><Button variant="outline" onClick={() => onOpenChange(false)}>{t("common.cancel")}</Button><Button disabled={!name.trim() || !purpose.trim() || !bindings.length || mutation.isPending} onClick={() => mutation.mutate()}>{mutation.isPending ? <LoaderCircle className="animate-spin" /> : <Save />}{t(mutation.isPending ? "common.saving" : "common.save")}</Button></>}><div className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-5"><Field label={t("guardrails.guardrailName")}><Input className="min-h-11" value={name} onChange={(event) => setName(event.target.value)} /></Field><Field label={t("guardrails.businessPurpose")}><Textarea className="min-h-28" value={purpose} onChange={(event) => setPurpose(event.target.value)} /></Field><div className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-4 sm:grid-cols-2"><Field label={t("guardrails.allowedDomains")}><Textarea className="min-h-24" value={allowed} onChange={(event) => setAllowed(event.target.value)} /></Field><Field label={t("guardrails.restrictedDomains")}><Textarea className="min-h-24" value={restricted} onChange={(event) => setRestricted(event.target.value)} /></Field></div><RuntimePostureFields safetyLevel={level} outputDelivery={delivery} onSafetyLevelChange={setLevel} onOutputDeliveryChange={setDelivery} /><section className="min-w-0"><h3 className="mb-3 text-sm font-semibold">{t("guardrails.policyBindings")}</h3><PolicyBindingEditor policies={policies} value={bindings} onChange={setBindings} /></section></div></EntitySheet>;
}

export function AddTestCaseSheet({ guardrail, open, onOpenChange, onCreated }: { guardrail: Guardrail; open: boolean; onOpenChange: (open: boolean) => void; onCreated: () => void }) {
  const { t } = useTranslation();
  const [name, setName] = useState("");
  const [policyId, setPolicyId] = useState(guardrail.policy_bindings[0]?.policy_id ?? "");
  const [phase, setPhase] = useState<"input" | "output">("input");
  const [content, setContent] = useState("");
  const [expected, setExpected] = useState<TestCase["expected_decision"]>("block");
  useEffect(() => { if (open) { setName(""); setPolicyId(guardrail.policy_bindings[0]?.policy_id ?? ""); setPhase("input"); setContent(""); setExpected("block"); } }, [guardrail.policy_bindings, open]);
  const mutation = useMutation({ mutationFn: () => createTestCase(guardrail.id, { name, policy_id: policyId, phase, content, expected_decision: expected, trusted_instruction: "", target_source: phase === "input" ? "user_input" : "model_output", query: "", grounding_sources: [], expected_reasoning_result: null }), onSuccess: () => { toast.success(t("guardrails.caseCreated")); onCreated(); }, onError: (error) => notifyError(error, t("guardrails.operationFailed")) });
  return <EntitySheet open={open} onOpenChange={onOpenChange} eyebrow={t("guardrails.addCaseEyebrow")} title={t("guardrails.addCaseTitle")} description={t("guardrails.addCaseDescription")} footer={<><Button variant="outline" onClick={() => onOpenChange(false)}>{t("common.cancel")}</Button><Button disabled={!name.trim() || !policyId || !content.trim() || mutation.isPending} onClick={() => mutation.mutate()}>{mutation.isPending ? <LoaderCircle className="animate-spin" /> : <Plus />}{t("guardrails.addTestCase")}</Button></>}><div className="grid gap-5"><Field label={t("guardrails.caseName")}><Input autoFocus className="min-h-11" value={name} onChange={(event) => setName(event.target.value)} /></Field><Field label={t("guardrails.policy")}><Select value={policyId} onValueChange={setPolicyId}><SelectTrigger className="min-h-11"><SelectValue /></SelectTrigger><SelectContent>{guardrail.policy_bindings.map((binding) => <SelectItem key={binding.policy_id} value={binding.policy_id}>{binding.policy_id}</SelectItem>)}</SelectContent></Select></Field><div className="grid gap-4 sm:grid-cols-2"><Field label={t("guardrails.modelBoundary")}><Select value={phase} onValueChange={(next) => setPhase(next as typeof phase)}><SelectTrigger className="min-h-11"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="input">Input</SelectItem><SelectItem value="output">Output</SelectItem></SelectContent></Select></Field><Field label={t("guardrails.expectedDecision")}><Select value={expected} onValueChange={(next) => setExpected(next as typeof expected)}><SelectTrigger className="min-h-11"><SelectValue /></SelectTrigger><SelectContent>{["allow", "block", "transform", "intervene"].map((decision) => <SelectItem key={decision} value={decision}>{decision}</SelectItem>)}</SelectContent></Select></Field></div><Field label={t("guardrails.testContent")}><Textarea className="min-h-32" value={content} onChange={(event) => setContent(event.target.value)} /></Field></div></EntitySheet>;
}

function Field({ label, children }: { label: string; children: ReactNode }) { return <label className="grid gap-2"><Label>{label}</Label>{children}</label>; }
function lines(value: string) { return value.split("\n").map((item) => item.trim()).filter(Boolean); }
function notifyError(error: unknown, fallback: string) { toast.error(error instanceof Error ? error.message : fallback); }
