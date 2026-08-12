import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { Activity, ArrowRight, Clock3, Gauge, ListFilter, ShieldAlert, ShieldCheck, SlidersHorizontal, TriangleAlert } from "lucide-react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useTranslation } from "react-i18next";

import { ErrorNotice, PageHeader, StateBadge } from "@/components/product-shell";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { queryKeys } from "@/features/query-keys";
import { getDecisions, getIntegrations, getMetrics, getGuardrails, getAssignments, type DecisionEvent, type Metrics, type RuntimeComponentMetric } from "@/lib/api";

export function OverviewPage() {
  const { t, i18n } = useTranslation();
  const [guardrailId, setGuardrailId] = useState("all");
  const [environment, setEnvironment] = useState("all");
  const [window, setWindow] = useState<"24h" | "7d" | "30d">("7d");
  const filters = {
    guardrailId: guardrailId === "all" ? undefined : guardrailId,
    environment: environment === "all" ? undefined : environment,
    window,
  };
  const metrics = useQuery({ queryKey: queryKeys.metricsScope(filters), queryFn: () => getMetrics(filters), refetchInterval: 15_000 });
  const decisions = useQuery({ queryKey: [...queryKeys.decisions, filters.guardrailId ?? "all"], queryFn: () => getDecisions({ limit: 8, guardrailId: filters.guardrailId }), refetchInterval: 15_000 });
  const guardrails = useQuery({ queryKey: queryKeys.guardrails, queryFn: getGuardrails });
  const assignments = useQuery({ queryKey: queryKeys.assignments, queryFn: getAssignments });
  const integrations = useQuery({ queryKey: queryKeys.integrations, queryFn: getIntegrations });
  const error = metrics.error || decisions.error || guardrails.error || assignments.error || integrations.error;

  return (
    <section className="py-6 sm:py-8">
      <PageHeader
        title={t("overview.title")}
        description={t("overview.description")}
        action={
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" asChild><Link to="/guardrails"><ShieldCheck />{t("overview.manageGuardrails")}</Link></Button>
            <Button asChild><Link to="/deployments"><ListFilter />{t("overview.manageAssignments")}</Link></Button>
          </div>
        }
      />

      <OverviewScope
        guardrailId={guardrailId}
        environment={environment}
        window={window}
        guardrails={guardrails.data?.items ?? []}
        environments={Array.from(new Set((integrations.data?.items ?? []).map((item) => item.environment))).sort()}
        onGuardrailChange={setGuardrailId}
        onEnvironmentChange={setEnvironment}
        onWindowChange={(value) => setWindow(value as typeof window)}
      />

      {error ? <div className="mt-6"><ErrorNotice error={error} /></div> : null}
      {metrics.isLoading ? <OverviewSkeleton /> : null}
      {metrics.data ? (
        <>
          <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Kpi icon={Activity} label={t("overview.evaluatedRequests")} value={metrics.data.total_decisions.toLocaleString(i18n.language)} detail={requestComparison(metrics.data, t)} />
            <Kpi icon={ShieldAlert} label={t("overview.interventionRate")} value={`${roundRate(metrics.data)}%`} detail={t("overview.outcomeBreakdown", { allowed: metrics.data.allowed, transformed: metrics.data.intervened, blocked: metrics.data.blocked, errors: metrics.data.errors })} tone={metrics.data.blocked + metrics.data.intervened > 0 ? "warning" : "default"} />
            <Kpi icon={Clock3} label={t("overview.runtimeP95")} value={metrics.data.total_decisions ? `${metrics.data.runtime_p95_ms} ms` : "—"} detail={metrics.data.total_decisions ? t("overview.runtimeSlo", { budget: metrics.data.latency_slo.p95_budget_ms, p99: metrics.data.runtime_p99_ms, breaches: metrics.data.slo_breach_count }) : t("overview.runtimeLatencyEmpty")} tone={metrics.data.latency_slo.p95_status === "breached" ? "warning" : "default"} />
            <Kpi icon={TriangleAlert} label={t("overview.runtimeFailures")} value={(metrics.data.errors + metrics.data.timeout_count + metrics.data.fail_closed_count).toLocaleString(i18n.language)} detail={t("overview.failureBreakdown", { errors: metrics.data.errors, timeouts: metrics.data.timeout_count, failClosed: metrics.data.fail_closed_count })} tone={metrics.data.errors + metrics.data.timeout_count + metrics.data.fail_closed_count ? "warning" : "default"} />
          </div>

          {guardrailId === "all" ? <GuardrailDistribution metrics={metrics.data} /> : null}

          {guardrailId !== "all" ? <>
            <div className="mt-4 grid gap-4 xl:grid-cols-2">
              <RuntimeComponents
                title={t("overview.railPerformance")}
                description={t("overview.railPerformanceDescription")}
                items={metrics.data.rail_metrics}
                window={metrics.data.window}
              />
              <RuntimeComponents
                title={t("overview.actionPerformance")}
                description={t("overview.actionPerformanceDescription")}
                items={metrics.data.action_metrics}
                window={metrics.data.window}
              />
            </div>

            <div className="mt-4 grid gap-4 xl:grid-cols-2">
              <ControlDistribution metrics={metrics.data} />
              <VersionDistribution metrics={metrics.data} />
            </div>
          </> : null}

          <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.55fr)_minmax(320px,0.75fr)]">
            <TrafficTrend metrics={metrics.data} />
            <Attention metrics={metrics.data} />
          </div>

          <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(300px,0.72fr)_minmax(0,1.58fr)]">
            <RiskDistribution metrics={metrics.data} />
            <RecentEvidence items={decisions.data?.items ?? []} />
          </div>

          {!metrics.data.total_guardrails || !metrics.data.total_assignments ? (
            <Card className="mt-4 border-dashed shadow-none">
              <CardHeader>
                <CardTitle>{t("overview.getStartedTitle")}</CardTitle>
                <CardDescription>{t("overview.getStartedDescription")}</CardDescription>
              </CardHeader>
              <CardContent className="flex flex-wrap gap-2">
                {!metrics.data.total_guardrails ? <Button asChild><Link to="/guardrails">{t("overview.createFirstGuardrail")}<ArrowRight /></Link></Button> : null}
                {!metrics.data.total_assignments && metrics.data.total_guardrails ? <Button variant="outline" asChild><Link to="/assignments">{t("overview.createFirstAssignment")}<ArrowRight /></Link></Button> : null}
              </CardContent>
            </Card>
          ) : null}
        </>
      ) : null}
    </section>
  );
}

function OverviewScope({ guardrailId, environment, window, guardrails, environments, onGuardrailChange, onEnvironmentChange, onWindowChange }: {
  guardrailId: string;
  environment: string;
  window: "24h" | "7d" | "30d";
  guardrails: Array<{ id: string; name: string }>;
  environments: string[];
  onGuardrailChange: (value: string) => void;
  onEnvironmentChange: (value: string) => void;
  onWindowChange: (value: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <section className="mt-6 flex flex-col gap-3 rounded-xl border bg-card p-4 shadow-xs lg:flex-row lg:items-end" aria-label={t("overview.scopeTitle")}>
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-muted text-muted-foreground"><SlidersHorizontal className="size-4" /></span>
        <div><h2 className="text-sm font-semibold">{t("overview.scopeTitle")}</h2><p className="mt-0.5 text-xs text-muted-foreground">{t(guardrailId === "all" ? "overview.globalScopeDescription" : "overview.guardrailScopeDescription")}</p></div>
      </div>
      <label className="grid gap-1.5 text-xs font-medium text-muted-foreground">
        {t("overview.guardrailScope")}
        <Select value={guardrailId} onValueChange={onGuardrailChange}><SelectTrigger className="min-h-11 w-full bg-card sm:w-64"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">{t("overview.allGuardrails")}</SelectItem>{guardrails.map((item) => <SelectItem key={item.id} value={item.id}>{item.name}</SelectItem>)}</SelectContent></Select>
      </label>
      <label className="grid gap-1.5 text-xs font-medium text-muted-foreground">
        {t("overview.environmentScope")}
        <Select value={environment} onValueChange={onEnvironmentChange}><SelectTrigger className="min-h-11 w-full bg-card sm:w-44"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">{t("overview.allEnvironments")}</SelectItem>{environments.map((item) => <SelectItem key={item} value={item}>{item[0]?.toUpperCase()}{item.slice(1)}</SelectItem>)}</SelectContent></Select>
      </label>
      <label className="grid gap-1.5 text-xs font-medium text-muted-foreground">
        {t("overview.timeWindow")}
        <Select value={window} onValueChange={onWindowChange}><SelectTrigger className="min-h-11 w-full bg-card sm:w-36"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="24h">{t("overview.last24Hours")}</SelectItem><SelectItem value="7d">{t("overview.last7Days")}</SelectItem><SelectItem value="30d">{t("overview.last30Days")}</SelectItem></SelectContent></Select>
      </label>
    </section>
  );
}

function Kpi({ icon: Icon, label, value, detail, tone = "default" }: { icon: typeof Gauge; label: string; value: string; detail: string; tone?: "default" | "warning" }) {
  return (
    <Card className="gap-3 py-4">
      <CardHeader className="flex grid-cols-none flex-row items-center justify-between gap-3">
        <CardDescription className="text-xs font-medium">{label}</CardDescription>
        <span className={tone === "warning" ? "grid size-8 place-items-center rounded-lg bg-amber-50 text-amber-700" : "grid size-8 place-items-center rounded-lg bg-muted text-muted-foreground"}><Icon className="size-4" /></span>
      </CardHeader>
      <CardContent><p className="text-2xl font-semibold tracking-[-0.035em] tabular-nums">{value}</p><p className="mt-1 text-xs text-muted-foreground">{detail}</p></CardContent>
    </Card>
  );
}

function GuardrailDistribution({ metrics }: { metrics: Metrics }) {
  const { t, i18n } = useTranslation();
  return (
    <Card className="mt-4">
      <CardHeader>
        <CardTitle>{t("overview.guardrailDistribution")}</CardTitle>
        <CardDescription>{t("overview.guardrailDistributionDescription")}</CardDescription>
        <CardAction><span className="text-xs text-muted-foreground">{windowLabel(metrics.window, t)}</span></CardAction>
      </CardHeader>
      <CardContent className="px-0">
        <div className="hidden overflow-x-auto md:block">
          <Table className="min-w-[980px]">
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">{t("overview.guardrail")}</TableHead>
                <TableHead>{t("overview.requestShare")}</TableHead>
                <TableHead>{t("overview.nemoRuntime")}</TableHead>
                <TableHead>{t("overview.outcomeDistribution")}</TableHead>
                <TableHead>{t("overview.latencyDistribution")}</TableHead>
                <TableHead className="pr-4 text-right">{t("overview.timeouts")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {metrics.guardrail_distribution.map((item) => (
                <TableRow key={item.guardrail_id}>
                  <TableCell className="pl-4"><GuardrailIdentity item={item} /></TableCell>
                  <TableCell>
                    <p className="font-mono text-sm tabular-nums">{item.total.toLocaleString(i18n.language)}</p>
                    <p className="text-xs text-muted-foreground">{t("overview.trafficShare", { share: item.share })}</p>
                  </TableCell>
                  <TableCell><RuntimeExecution item={item} /></TableCell>
                  <TableCell className="min-w-56"><OutcomeDistribution item={item} /></TableCell>
                  <TableCell><LatencyDistribution item={item} /></TableCell>
                  <TableCell className="pr-4 text-right font-mono text-sm tabular-nums">
                    <span className={item.timeout_count ? "text-destructive" : "text-muted-foreground"}>{item.timeout_count}</span>
                    <p className="mt-1 font-sans text-[11px] text-muted-foreground">{t("overview.failClosed", { count: item.fail_closed_count })}</p>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
        <div className="divide-y md:hidden">
          {metrics.guardrail_distribution.map((item) => (
            <div key={item.guardrail_id} className="px-4 py-4">
              <div className="flex items-start justify-between gap-4">
                <GuardrailIdentity item={item} />
                <div className="shrink-0 text-right">
                  <p className="font-mono text-base tabular-nums">{item.total.toLocaleString(i18n.language)}</p>
                  <p className="text-xs text-muted-foreground">{t("overview.trafficShare", { share: item.share })}</p>
                </div>
              </div>
              <div className="mt-4"><OutcomeDistribution item={item} /></div>
              <div className="mt-4 border-y py-3"><RuntimeExecution item={item} /></div>
              <div className="mt-4 grid grid-cols-2 gap-3 rounded-lg bg-muted/50 p-3">
                <div>
                  <p className="text-xs text-muted-foreground">{t("overview.runtimeP95")}</p>
                  <p className="mt-1 font-mono text-sm tabular-nums">{item.total ? `${item.p95_latency_ms} ms` : "—"}</p>
                  {item.total ? <p className="mt-0.5 text-xs text-muted-foreground">{t("overview.runtimeLatencyBand", { p50: item.p50_latency_ms, p99: item.p99_latency_ms })}</p> : null}
                  {item.total ? <p className="mt-0.5 text-xs text-muted-foreground">{t("overview.queueP95", { value: item.queue_p95_ms })}</p> : null}
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">{t("overview.timeouts")}</p>
                  <p className={`mt-1 font-mono text-sm tabular-nums ${item.timeout_count || item.fail_closed_count ? "text-destructive" : ""}`}>{item.timeout_count}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">{t("overview.failClosed", { count: item.fail_closed_count })}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
        {metrics.unassigned_requests ? <p className="border-t px-4 py-3 text-xs text-amber-700">{t("overview.unassignedRequests", { count: metrics.unassigned_requests })}</p> : null}
      </CardContent>
    </Card>
  );
}

function RuntimeExecution({ item }: { item: GuardrailMetric }) {
  const { t } = useTranslation();
  if (!item.total) return <p className="text-xs text-muted-foreground">{t("overview.noRuntimeTraffic")}</p>;
  const runtime = item.runtime_engines.length ? item.runtime_engines.join(" + ") : "NeMo";
  const attempts = item.cache_hits + item.cache_misses;
  const cacheRate = attempts ? Math.round(item.cache_hits / attempts * 100) : 0;
  return (
    <div className="min-w-44 text-xs">
      <p className="font-medium">NeMo Guardrails · <span className="font-mono">{runtime}</span></p>
      <p className="mt-1 text-muted-foreground">{t("overview.runtimeCalls", { rails: item.rail_invocations, actions: item.action_invocations, models: item.model_invocations })}</p>
      <p className="mt-0.5 text-muted-foreground">{t("overview.cacheRate", { rate: cacheRate })}</p>
      <p className="mt-0.5 text-muted-foreground">{t("overview.concurrencyAndBreaches", { concurrency: item.peak_active_concurrency, breaches: item.slo_breach_count })}</p>
    </div>
  );
}

type GuardrailMetric = Metrics["guardrail_distribution"][number];

function GuardrailIdentity({ item }: { item: GuardrailMetric }) {
  const { t } = useTranslation();
  return (
    <div className="min-w-0">
      <Link to="/guardrails/$guardrailId" params={{ guardrailId: item.guardrail_id }} className="font-medium hover:underline focus-visible:outline-2 focus-visible:outline-ring">
        {item.name}
      </Link>
      <p className="mt-0.5 text-xs text-muted-foreground">
        {item.versions.length ? t("overview.observedVersions", { versions: item.versions.map((version) => `v${version}`).join(", ") }) : t("overview.noObservedVersion")}
      </p>
    </div>
  );
}

function OutcomeDistribution({ item }: { item: GuardrailMetric }) {
  const { t } = useTranslation();
  if (!item.total) return <p className="text-xs text-muted-foreground">{t("overview.noRuntimeTraffic")}</p>;
  const outcomes = [
    { count: item.allowed, className: "bg-emerald-500" },
    { count: item.intervened, className: "bg-amber-400" },
    { count: item.blocked, className: "bg-destructive" },
    { count: item.errors, className: "bg-foreground" },
  ];
  return (
    <>
      <div className="flex h-2 overflow-hidden rounded-full bg-muted" role="img" aria-label={t("overview.outcomeDistributionLabel", { allowed: item.allowed, intervened: item.intervened, blocked: item.blocked, errors: item.errors })}>
        {outcomes.map((outcome, index) => <span key={index} className={outcome.className} style={{ width: `${outcome.count / item.total * 100}%` }} />)}
      </div>
      <p className="mt-1.5 text-xs text-muted-foreground">{t("overview.outcomeSummary", { allowed: item.allowed, intervened: item.intervened, blocked: item.blocked, errors: item.errors })}</p>
    </>
  );
}

function LatencyDistribution({ item }: { item: GuardrailMetric }) {
  if (!item.total) return <span className="text-muted-foreground">—</span>;
  return (
    <div className="font-mono text-xs tabular-nums">
      <p><span className="text-muted-foreground">P50</span> {item.p50_latency_ms} ms <span className="ml-3 text-muted-foreground">P95</span> {item.p95_latency_ms} ms <span className="ml-3 text-muted-foreground">P99</span> {item.p99_latency_ms} ms</p>
      <p className="mt-1 text-muted-foreground">Queue P95 <span className="text-foreground">{item.queue_p95_ms} ms</span></p>
      <p className="mt-1 text-muted-foreground">Rail P95 <span className="text-foreground">{item.rail_p95_ms} ms</span> · Action P95 <span className="text-foreground">{item.action_p95_ms} ms</span></p>
      <p className="mt-1 text-muted-foreground">Provider P95 <span className="text-foreground">{item.provider_p95_ms} ms</span></p>
    </div>
  );
}

function RuntimeComponents({ title, description, items, window }: { title: string; description: string; items: RuntimeComponentMetric[]; window: Metrics["window"] }) {
  const { t, i18n } = useTranslation();
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
        <CardAction><span className="text-xs text-muted-foreground">{windowLabel(window, t)}</span></CardAction>
      </CardHeader>
      <CardContent className="px-0">
        {items.length ? (
          <div className="overflow-x-auto">
            <Table className="min-w-[560px]">
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-4">{t("overview.component")}</TableHead>
                  <TableHead>{t("overview.invocations")}</TableHead>
                  <TableHead>{t("overview.componentOutcomes")}</TableHead>
                  <TableHead className="pr-4 text-right">P50 / P95 / P99</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.slice(0, 8).map((item) => (
                  <TableRow key={`${item.name}:${item.risk ?? "none"}`}>
                    <TableCell className="max-w-64 pl-4">
                      <p className="break-words font-mono text-xs">{item.name}</p>
                      <p className="mt-0.5 text-xs text-muted-foreground">{item.risk ? riskLabel(item.risk, t) : t("overview.runtimeCore")}</p>
                      {item.parallel_group ? <p className="mt-0.5 text-[11px] text-muted-foreground">{t("overview.parallelGroup", { group: item.parallel_group })}</p> : null}
                    </TableCell>
                    <TableCell className="font-mono text-sm tabular-nums">{item.invocations.toLocaleString(i18n.language)}</TableCell>
                    <TableCell>
                      <p className="text-xs">{t("overview.componentOutcomeSummary", { passed: item.passed, intervened: item.intervened, errors: item.errors })}</p>
                      {item.uncertain || item.timeouts ? <p className="mt-0.5 text-xs text-amber-700">{t("overview.componentExceptions", { uncertain: item.uncertain, timeouts: item.timeouts })}</p> : null}
                    </TableCell>
                    <TableCell className="pr-4 text-right font-mono text-xs tabular-nums">{item.p50_latency_ms} / {item.p95_latency_ms} / {item.p99_latency_ms} ms</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ) : <p className="px-4 py-12 text-center text-sm text-muted-foreground">{t("overview.noComponentMetrics")}</p>}
      </CardContent>
    </Card>
  );
}

function ControlDistribution({ metrics }: { metrics: Metrics }) {
  const { t, i18n } = useTranslation();
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("overview.controlDistribution")}</CardTitle>
        <CardDescription>{t("overview.controlDistributionDescription")}</CardDescription>
        <CardAction><span className="text-xs text-muted-foreground">{windowLabel(metrics.window, t)}</span></CardAction>
      </CardHeader>
      <CardContent className="px-0">
        {metrics.control_distribution.length ? (
          <div className="overflow-x-auto">
            <Table className="min-w-[600px]">
              <TableHeader><TableRow>
                <TableHead className="pl-4">{t("overview.controlVersion")}</TableHead>
                <TableHead>{t("overview.invocations")}</TableHead>
                <TableHead>{t("overview.componentOutcomes")}</TableHead>
                <TableHead className="pr-4 text-right">P95</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {metrics.control_distribution.slice(0, 8).map((item) => (
                  <TableRow key={`${item.control_id}:${item.control_version ?? "draft"}`}>
                    <TableCell className="pl-4">
                      <Link to="/control-library" className="font-mono text-xs hover:underline">{item.control_id}</Link>
                      <p className="mt-0.5 text-[11px] text-muted-foreground">{item.control_version ? `v${item.control_version}` : t("overview.unversioned")} · {item.rail_types.join(" + ") || "—"}</p>
                    </TableCell>
                    <TableCell>
                      <p className="font-mono text-sm tabular-nums">{item.invocations.toLocaleString(i18n.language)}</p>
                      <p className="text-xs text-muted-foreground">{t("overview.controlHitShare", { share: item.hit_share, rate: item.hits_per_request })}</p>
                    </TableCell>
                    <TableCell>
                      <p className="text-xs">{t("overview.componentOutcomeSummary", { passed: item.passed, intervened: item.intervened, errors: item.errors })}</p>
                      {item.timeouts ? <p className="mt-0.5 text-xs text-amber-700">{t("overview.timeoutCount", { count: item.timeouts })}</p> : null}
                    </TableCell>
                    <TableCell className="pr-4 text-right font-mono text-xs tabular-nums">
                      <p>{item.p95_latency_ms} ms</p>
                      <p className="mt-0.5 text-muted-foreground">{t("overview.providerLatency", { value: item.provider_p95_ms })}</p>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ) : <p className="px-4 py-12 text-center text-sm text-muted-foreground">{t("overview.noControlMetrics")}</p>}
      </CardContent>
    </Card>
  );
}

function VersionDistribution({ metrics }: { metrics: Metrics }) {
  const { t, i18n } = useTranslation();
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("overview.versionDistribution")}</CardTitle>
        <CardDescription>{t("overview.versionDistributionDescription")}</CardDescription>
        <CardAction><span className="text-xs text-muted-foreground">{windowLabel(metrics.window, t)}</span></CardAction>
      </CardHeader>
      <CardContent className="px-0">
        {metrics.version_distribution.length ? (
          <div className="overflow-x-auto">
            <Table className="min-w-[520px]">
              <TableHeader><TableRow>
                <TableHead className="pl-4">{t("overview.guardrail")}</TableHead>
                <TableHead>{t("overview.requestShare")}</TableHead>
                <TableHead>{t("overview.sloBreaches")}</TableHead>
                <TableHead className="pr-4 text-right">P95</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {metrics.version_distribution.slice(0, 8).map((item) => (
                  <TableRow key={`${item.guardrail_id}:${item.guardrail_version}`}>
                    <TableCell className="pl-4">
                      <Link to="/guardrails/$guardrailId" params={{ guardrailId: item.guardrail_id }} className="font-medium hover:underline">{item.guardrail_name}</Link>
                      <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">v{item.guardrail_version}</p>
                    </TableCell>
                    <TableCell><p className="font-mono text-sm tabular-nums">{item.requests.toLocaleString(i18n.language)}</p><p className="text-xs text-muted-foreground">{item.share}%</p></TableCell>
                    <TableCell><span className={item.slo_breaches || item.errors ? "font-mono text-sm text-destructive" : "font-mono text-sm text-muted-foreground"}>{item.slo_breaches}</span><p className="text-xs text-muted-foreground">{t("overview.errorCount", { count: item.errors })}</p></TableCell>
                    <TableCell className="pr-4 text-right font-mono text-xs tabular-nums">{item.p95_latency_ms} ms</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ) : <p className="px-4 py-12 text-center text-sm text-muted-foreground">{t("overview.noVersionMetrics")}</p>}
      </CardContent>
    </Card>
  );
}

function TrafficTrend({ metrics }: { metrics: Metrics }) {
  const { t, i18n } = useTranslation();
  const data = metrics.trend.map((item) => ({ ...item, label: new Date(`${item.date}T00:00:00`).toLocaleDateString(i18n.language, { month: "short", day: "numeric" }) }));
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("overview.trafficTrend")}</CardTitle>
        <CardDescription>{t("overview.trafficTrendDescriptionWindow", { window: windowLabel(metrics.window, t) })}</CardDescription>
        <CardAction><StateBadge state={metrics.system_status} /></CardAction>
      </CardHeader>
      <CardContent className="h-64 pl-0 sm:h-72">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 8, right: 16, left: -16, bottom: 0 }}>
            <defs><linearGradient id="overviewTotal" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="var(--primary)" stopOpacity={0.18} /><stop offset="95%" stopColor="var(--primary)" stopOpacity={0} /></linearGradient></defs>
            <CartesianGrid vertical={false} stroke="var(--border)" strokeDasharray="3 3" />
            <XAxis dataKey="label" axisLine={false} tickLine={false} tick={{ fill: "var(--muted-foreground)", fontSize: 11 }} />
            <YAxis allowDecimals={false} axisLine={false} tickLine={false} tick={{ fill: "var(--muted-foreground)", fontSize: 11 }} />
            <Tooltip contentStyle={{ borderColor: "var(--border)", borderRadius: 10, background: "var(--card)", boxShadow: "var(--shadow-surface)" }} />
            <Area type="monotone" dataKey="total" name={t("overview.requests")} stroke="var(--primary)" strokeWidth={2} fill="url(#overviewTotal)" />
            <Area type="monotone" dataKey="blocked" name={t("overview.blocked")} stroke="var(--destructive)" fill="transparent" strokeWidth={1.5} />
          </AreaChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

function Attention({ metrics }: { metrics: Metrics }) {
  const { t } = useTranslation();
  const items = [
    metrics.guardrails_needing_test ? { label: t("overview.guardrailsNeedTest", { count: metrics.guardrails_needing_test }), to: "/guardrails" as const, state: "needs_testing" } : null,
    metrics.total_assignments === 0 ? { label: t("overview.noAssignments"), to: "/deployments" as const, state: "waiting" } : null,
    metrics.degraded_integrations ? { label: t("overview.integrationsDegraded", { count: metrics.degraded_integrations }), to: "/integrations" as const, state: "degraded" } : null,
    metrics.latency_slo.p95_status === "breached" || metrics.latency_slo.p99_status === "breached" ? { label: t("overview.latencyBudgetBreached", { p95: metrics.runtime_p95_ms, p99: metrics.runtime_p99_ms }), to: "/evidence" as const, state: "degraded" } : null,
    metrics.fail_closed_count ? { label: t("overview.failClosedAttention", { count: metrics.fail_closed_count }), to: "/evidence" as const, state: "degraded" } : null,
    metrics.comparison_count && metrics.decision_match_rate < 100 ? { label: t("overview.shadowMismatch", { rate: metrics.decision_match_rate, count: metrics.comparison_count }), to: "/evidence" as const, state: "needs_testing" } : null,
  ].filter(Boolean) as Array<{ label: string; to: "/guardrails" | "/assignments" | "/integrations" | "/evidence"; state: string }>;
  return (
    <Card>
      <CardHeader><CardTitle>{t("overview.attention")}</CardTitle><CardDescription>{t("overview.attentionDescription")}</CardDescription></CardHeader>
      <CardContent className="space-y-2">
        {items.length ? items.map((item) => (
          <Link key={item.label} to={item.to} className="flex min-h-14 items-center gap-3 rounded-lg border p-3 transition-colors hover:bg-muted/50 focus-visible:outline-2 focus-visible:outline-ring">
            <StateBadge state={item.state} /><span className="min-w-0 flex-1 text-sm">{item.label}</span><ArrowRight className="size-4 text-muted-foreground" />
          </Link>
        )) : <div className="flex min-h-40 flex-col items-center justify-center text-center"><ShieldCheck className="size-7 text-emerald-600" /><p className="mt-3 text-sm font-medium">{t("overview.noAttentionTitle")}</p><p className="mt-1 text-xs text-muted-foreground">{t("overview.noAttentionDescription")}</p></div>}
      </CardContent>
    </Card>
  );
}

function RiskDistribution({ metrics }: { metrics: Metrics }) {
  const { t } = useTranslation();
  const max = Math.max(1, ...metrics.risk_counts.map((item) => item.count));
  return (
    <Card>
      <CardHeader><CardTitle>{t("overview.riskDistribution")}</CardTitle><CardDescription>{t("overview.riskDistributionDescription")}</CardDescription></CardHeader>
      <CardContent className="space-y-4">
        {metrics.risk_counts.length ? metrics.risk_counts.slice(0, 6).map((item) => <div key={item.risk}><div className="mb-1.5 flex items-center justify-between gap-3 text-xs"><span>{riskLabel(item.risk, t)}</span><span className="font-mono text-muted-foreground">{item.count}</span></div><Progress value={item.count / max * 100} /></div>) : <p className="py-10 text-center text-sm text-muted-foreground">{t("overview.noRiskData")}</p>}
      </CardContent>
    </Card>
  );
}

function RecentEvidence({ items }: { items: DecisionEvent[] }) {
  const { t, i18n } = useTranslation();
  return (
    <Card>
      <CardHeader><CardTitle>{t("overview.recentEvidence")}</CardTitle><CardDescription>{t("overview.recentEvidenceDescription")}</CardDescription><CardAction><Button size="sm" variant="ghost" asChild><Link to="/evidence">{t("common.viewAll")}<ArrowRight /></Link></Button></CardAction></CardHeader>
      <CardContent className="px-0">
        {items.length ? <Table><TableHeader><TableRow><TableHead className="pl-4">{t("overview.time")}</TableHead><TableHead>{t("overview.event")}</TableHead><TableHead>{t("overview.risk")}</TableHead><TableHead className="pr-4 text-right">{t("overview.outcome")}</TableHead></TableRow></TableHeader><TableBody>{items.map((item) => <TableRow key={item.id}><TableCell className="pl-4 text-xs text-muted-foreground">{new Date(item.created_at).toLocaleString(i18n.language, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}</TableCell><TableCell className="max-w-[420px] truncate text-xs">{item.detail}</TableCell><TableCell className="text-xs text-muted-foreground">{item.risk ? riskLabel(item.risk, t) : "—"}</TableCell><TableCell className="pr-4 text-right"><StateBadge state={item.outcome} /></TableCell></TableRow>)}</TableBody></Table> : <div className="flex min-h-52 flex-col items-center justify-center px-6 text-center"><Activity className="size-6 text-muted-foreground" /><p className="mt-3 text-sm font-medium">{t("overview.noEvidenceTitle")}</p><p className="mt-1 text-xs text-muted-foreground">{t("overview.noEvidenceDescription")}</p></div>}
      </CardContent>
    </Card>
  );
}

function OverviewSkeleton() { return <div className="mt-6 space-y-4"><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{Array.from({ length: 4 }).map((_, index) => <Skeleton key={index} className="h-32 rounded-xl" />)}</div><div className="grid gap-4 xl:grid-cols-[minmax(0,1.55fr)_minmax(320px,0.75fr)]"><Skeleton className="h-96 rounded-xl" /><Skeleton className="h-96 rounded-xl" /></div></div>; }

function requestComparison(metrics: Metrics, t: ReturnType<typeof useTranslation>["t"]) {
  const delta = metrics.comparison.request_delta_pct;
  if (delta === null) return t("overview.noPreviousTraffic");
  return t(delta >= 0 ? "overview.requestIncrease" : "overview.requestDecrease", { value: Math.abs(delta) });
}

function roundRate(metrics: Metrics) {
  return metrics.total_decisions ? Math.round((metrics.blocked + metrics.intervened) / metrics.total_decisions * 1_000) / 10 : 0;
}

function windowLabel(window: Metrics["window"], t: ReturnType<typeof useTranslation>["t"]) {
  return t(window === "24h" ? "overview.last24Hours" : window === "30d" ? "overview.last30Days" : "overview.last7Days");
}

function riskLabel(risk: string, t: ReturnType<typeof useTranslation>["t"]) {
  const key = ({ topic_control: "guardrails.riskTopic", pii: "guardrails.riskPii", secrets: "guardrails.riskSecrets", prompt_injection: "guardrails.riskInjection", jailbreak: "guardrails.riskJailbreak", content_safety: "guardrails.riskUnsafe", company_policy: "guardrails.riskCompany", builtin_content_filter: "guardrails.riskBuiltin" } as Record<string, string>)[risk];
  return key ? t(key) : risk.replaceAll("_", " ");
}
