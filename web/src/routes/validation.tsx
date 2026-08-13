import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, LoaderCircle, Play, Plus, Search, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { EntitySheet } from "@/components/entity-sheet";
import { EmptyState, ErrorNotice, InfoNotice, PageHeader, StateBadge } from "@/components/product-shell";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { queryKeys } from "@/features/query-keys";
import {
  createTestRun,
  deleteTestCase,
  getGuardrails,
  getTestCases,
  getTestRuns,
  type EvaluationCaseResult,
  type Guardrail,
  type TestRun,
} from "@/lib/api";
import { AddTestCaseSheet } from "@/routes/guardrails";

export function EvaluationsPage() {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const requestedGuardrail = typeof window === "undefined" ? "" : new URLSearchParams(window.location.search).get("guardrail") ?? "";
  const guardrailsQuery = useQuery({ queryKey: queryKeys.guardrails, queryFn: getGuardrails });
  const runsQuery = useQuery({ queryKey: queryKeys.allTestRuns, queryFn: () => getTestRuns() });
  const guardrails = (guardrailsQuery.data?.items ?? []).filter((item) => !item.system_managed);
  const runs = runsQuery.data?.items ?? [];
  const [createOpen, setCreateOpen] = useState(Boolean(requestedGuardrail));
  const [selected, setSelected] = useState<TestRun | null>(null);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const guardrailNames = useMemo(() => new Map(guardrails.map((item) => [item.id, item.name])), [guardrails]);
  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    return runs.filter((run) => (status === "all" || run.status === status) && (!query || `${run.id} ${guardrailNames.get(run.guardrail_id) ?? run.guardrail_id}`.toLowerCase().includes(query)));
  }, [guardrailNames, runs, search, status]);
  const refresh = async () => { await Promise.all([queryClient.invalidateQueries({ queryKey: queryKeys.allTestRuns }), queryClient.invalidateQueries({ queryKey: queryKeys.guardrails })]); };
  const rerun = useMutation({ mutationFn: (guardrailId: string) => createTestRun(guardrailId), onSuccess: async (run) => { await refresh(); setSelected(run); toast[run.status === "passed" ? "success" : "error"](t(run.status === "passed" ? "guardrails.testsPassed" : "guardrails.testsFailed", { rate: run.metrics.compliance_rate })); }, onError: (error) => notifyError(error, t("guardrails.operationFailed")) });

  return (
    <section className="py-6 sm:py-8">
      <PageHeader title={t("pages.evaluations.title")} description={t("pages.evaluations.description")} action={<Button className="min-h-11" disabled={!guardrails.length} onClick={() => setCreateOpen(true)}><Plus />{t("validation.createEvaluation")}</Button>} />
      {guardrailsQuery.error || runsQuery.error ? <div className="mt-5"><ErrorNotice error={guardrailsQuery.error || runsQuery.error} /></div> : null}
      {guardrailsQuery.isLoading || runsQuery.isLoading ? <Skeleton className="mt-5 h-[34rem] rounded-xl" /> : null}
      {!guardrailsQuery.isLoading && !guardrails.length ? <div className="mt-5"><EmptyState title={t("validation.noGuardrails")} description={t("validation.noGuardrailsDescription")} /></div> : null}
      {!runsQuery.isLoading && guardrails.length ? (
        <>
          <EvaluationSummary runs={runs} />
          <section className="mt-5 overflow-hidden rounded-xl border bg-card shadow-xs">
            <div className="grid gap-3 border-b bg-muted/20 p-4 sm:grid-cols-[minmax(16rem,1fr)_14rem_auto] sm:items-center"><label className="relative"><span className="sr-only">{t("validation.searchEvaluations")}</span><Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" /><Input className="min-h-11 bg-card pl-9" value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t("validation.searchEvaluations")} /></label><Select value={status} onValueChange={setStatus}><SelectTrigger className="min-h-11 bg-card" aria-label={t("validation.filterStatus")}><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">{t("validation.allStatuses")}</SelectItem><SelectItem value="passed">{t("states.passed")}</SelectItem><SelectItem value="failed">{t("states.failed")}</SelectItem><SelectItem value="incomplete">{t("states.incomplete")}</SelectItem></SelectContent></Select><p className="text-xs text-muted-foreground sm:text-right">{t("validation.evaluationCount", { count: filtered.length })}</p></div>
            {filtered.length ? <Table><TableHeader><TableRow className="hover:bg-transparent"><TableHead className="pl-4">{t("validation.evaluationColumn")}</TableHead><TableHead>{t("validation.guardrailColumn")}</TableHead><TableHead>{t("validation.targetColumn")}</TableHead><TableHead>{t("validation.casesColumn")}</TableHead><TableHead>{t("validation.statusColumn")}</TableHead><TableHead>{t("validation.passRateColumn")}</TableHead><TableHead>{t("validation.durationColumn")}</TableHead><TableHead>{t("validation.runAtColumn")}</TableHead><TableHead className="w-12"><span className="sr-only">{t("validation.openEvaluation")}</span></TableHead></TableRow></TableHeader><TableBody>{filtered.map((run) => <EvaluationRow key={run.id} run={run} guardrailName={guardrailNames.get(run.guardrail_id) ?? run.guardrail_id} locale={i18n.language} onOpen={() => setSelected(run)} />)}</TableBody></Table> : <EmptyState title={runs.length ? t("validation.noMatchingEvaluations") : t("validation.noEvaluations")} description={runs.length ? t("validation.noMatchingEvaluationsDescription") : t("validation.noEvaluationsDescription")} action={!runs.length ? <Button onClick={() => setCreateOpen(true)}><Plus />{t("validation.createEvaluation")}</Button> : undefined} />}
          </section>
        </>
      ) : null}
      <CreateEvaluationSheet open={createOpen} onOpenChange={setCreateOpen} guardrails={guardrails} initialGuardrailId={requestedGuardrail} onCreated={async (run) => { setCreateOpen(false); await refresh(); setSelected(run); }} />
      <EvaluationDetailSheet run={selected} guardrail={selected ? guardrails.find((item) => item.id === selected.guardrail_id) : undefined} running={rerun.isPending} onRunAgain={(guardrailId) => rerun.mutate(guardrailId)} onClose={() => setSelected(null)} />
    </section>
  );
}

function EvaluationSummary({ runs }: { runs: TestRun[] }) {
  const { t } = useTranslation();
  const passed = runs.filter((run) => run.status === "passed").length;
  const failed = runs.filter((run) => run.status === "failed").length;
  const latest = runs[0];
  return <dl className="mt-5 grid overflow-hidden rounded-xl border bg-card shadow-xs sm:grid-cols-3"><SummaryFact label={t("validation.totalEvaluations")} value={String(runs.length)} /><SummaryFact label={t("validation.passedFailed")} value={`${passed} / ${failed}`} /><SummaryFact label={t("validation.latestPassRate")} value={latest ? `${latest.metrics.compliance_rate}%` : "—"} /></dl>;
}

function SummaryFact({ label, value }: { label: string; value: string }) { return <div className="border-b p-4 last:border-b-0 sm:border-r sm:border-b-0 sm:last:border-r-0"><dt className="text-xs font-medium text-muted-foreground">{label}</dt><dd className="mt-1.5 text-xl font-semibold tabular-nums">{value}</dd></div>; }

function EvaluationRow({ run, guardrailName, locale, onOpen }: { run: TestRun; guardrailName: string; locale: string; onOpen: () => void }) {
  const { t } = useTranslation();
  return <TableRow role="button" tabIndex={0} className="cursor-pointer" onClick={onOpen} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onOpen(); } }}><TableCell className="pl-4"><strong className="block text-sm font-medium">{t("validation.evaluationNamed", { id: shortId(run.id) })}</strong><span className="mt-1 block font-mono text-[11px] text-muted-foreground">{run.id}</span></TableCell><TableCell className="text-sm">{guardrailName}</TableCell><TableCell className="text-xs">{targetLabel(run, t)}</TableCell><TableCell className="font-mono text-xs">{run.metrics.total}</TableCell><TableCell><StateBadge state={run.status} /></TableCell><TableCell className="font-mono text-xs">{run.metrics.compliance_rate}%</TableCell><TableCell className="font-mono text-xs">P95 {run.metrics.p95_latency_ms} ms</TableCell><TableCell className="whitespace-nowrap text-xs text-muted-foreground">{new Date(run.created_at).toLocaleString(locale)}</TableCell><TableCell><ChevronRight className="size-4 text-muted-foreground" /></TableCell></TableRow>;
}

function CreateEvaluationSheet({ open, onOpenChange, guardrails, initialGuardrailId, onCreated }: { open: boolean; onOpenChange: (open: boolean) => void; guardrails: Guardrail[]; initialGuardrailId: string; onCreated: (run: TestRun) => Promise<void> }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [guardrailId, setGuardrailId] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  useEffect(() => { if (open) setGuardrailId(guardrails.some((item) => item.id === initialGuardrailId) ? initialGuardrailId : guardrails[0]?.id ?? ""); }, [guardrails, initialGuardrailId, open]);
  const guardrail = guardrails.find((item) => item.id === guardrailId);
  const casesQuery = useQuery({ queryKey: queryKeys.testCases(guardrailId), queryFn: () => getTestCases(guardrailId), enabled: open && Boolean(guardrailId) });
  const cases = casesQuery.data?.items ?? [];
  const run = useMutation({ mutationFn: () => createTestRun(guardrailId), onSuccess: async (result) => { toast[result.status === "passed" ? "success" : "error"](t(result.status === "passed" ? "guardrails.testsPassed" : "guardrails.testsFailed", { rate: result.metrics.compliance_rate })); await onCreated(result); }, onError: (error) => notifyError(error, t("guardrails.operationFailed")) });
  const remove = useMutation({ mutationFn: deleteTestCase, onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: queryKeys.testCases(guardrailId) }); toast.success(t("guardrails.caseRemoved")); }, onError: (error) => notifyError(error, t("guardrails.operationFailed")) });
  return <><EntitySheet open={open} onOpenChange={onOpenChange} eyebrow={t("validation.createEyebrow")} title={t("validation.createEvaluation")} description={t("validation.createEvaluationDescription")} width="lg" footer={<><Button variant="outline" onClick={() => onOpenChange(false)}>{t("common.cancel")}</Button><Button disabled={!guardrailId || !cases.length || run.isPending} onClick={() => run.mutate()}>{run.isPending ? <LoaderCircle className="animate-spin" /> : <Play />}{t(run.isPending ? "guardrails.runningEvaluation" : "validation.runRegression")}</Button></>}>
    <div className="space-y-5"><label className="grid gap-2 text-sm font-medium">{t("validation.chooseGuardrail")}<Select value={guardrailId} onValueChange={setGuardrailId}><SelectTrigger className="min-h-11 bg-card"><SelectValue /></SelectTrigger><SelectContent>{guardrails.map((item) => <SelectItem key={item.id} value={item.id}>{item.name}</SelectItem>)}</SelectContent></Select></label>
      {guardrail ? <section className="rounded-xl border bg-muted/20 p-4"><div className="flex flex-wrap items-center gap-2"><strong className="text-sm">{guardrail.name}</strong><StateBadge state={guardrail.status} /></div><p className="mt-2 text-xs leading-5 text-muted-foreground">{guardrail.purpose}</p><p className="mt-3 text-xs font-medium">{t("validation.draftTarget", { revision: guardrail.tested_current ? guardrail.latest_test_run?.source_draft_version ?? "—" : "current" })}</p></section> : null}
      <section className="overflow-hidden rounded-xl border"><header className="flex items-center justify-between gap-3 border-b bg-muted/25 px-4 py-3"><div><h3 className="text-sm font-semibold">{t("validation.regressionSuite")}</h3><p className="mt-1 text-xs text-muted-foreground">{t("validation.caseCount", { count: cases.length })}</p></div><Button variant="outline" size="sm" onClick={() => setAddOpen(true)} disabled={!guardrail}><Plus />{t("guardrails.addTestCase")}</Button></header>{casesQuery.isLoading ? <div className="p-4"><Skeleton className="h-32" /></div> : cases.length ? <div className="max-h-72 divide-y overflow-y-auto">{cases.map((item) => <div key={item.id} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 px-4 py-3"><div className="min-w-0"><div className="flex min-w-0 flex-wrap items-center gap-2"><strong className="truncate text-sm font-medium">{item.name}</strong><Badge variant="outline" className="font-normal">{testCaseTypeLabel(item.case_type, t)}</Badge></div><span className="mt-1 block text-xs text-muted-foreground">{humanize(item.risk)} · {humanize(item.phase)} · {humanize(item.expected_decision)}</span>{item.source_control_id ? <span className="mt-1 block truncate font-mono text-[10px] text-muted-foreground">{item.source_control_id}@{item.source_control_version} · {item.source_suite_id}</span> : null}</div><Button size="icon" variant="ghost" className="size-10" aria-label={t("validation.deleteCase", { name: item.name })} disabled={remove.isPending} onClick={() => remove.mutate(item.id)}><Trash2 /></Button></div>)}</div> : <div className="p-4"><InfoNotice title={t("guardrails.noCases")}>{t("guardrails.noCasesDescription")}</InfoNotice></div>}</section>
      <InfoNotice title={t("validation.releaseSemantics")}>{t("validation.releaseSemanticsDescription")}</InfoNotice>
    </div>
  </EntitySheet>{guardrail ? <AddTestCaseSheet guardrail={guardrail} open={addOpen} onOpenChange={setAddOpen} onCreated={async () => { setAddOpen(false); await queryClient.invalidateQueries({ queryKey: queryKeys.testCases(guardrailId) }); }} /> : null}</>;
}

function EvaluationDetailSheet({ run, guardrail, running, onRunAgain, onClose }: { run: TestRun | null; guardrail?: Guardrail; running: boolean; onRunAgain: (guardrailId: string) => void; onClose: () => void }) {
  const { t, i18n } = useTranslation();
  if (!run) return null;
  const results = [...run.results].sort((left, right) => Number(left.passed) - Number(right.passed));
  return <EntitySheet open onOpenChange={(next) => { if (!next) onClose(); }} eyebrow={t("validation.detailEyebrow")} title={t("validation.evaluationNamed", { id: shortId(run.id) })} description={`${guardrail?.name ?? run.guardrail_id} · ${new Date(run.created_at).toLocaleString(i18n.language)}`} width="xl" footer={<><Button variant="outline" onClick={onClose}>{t("common.close")}</Button><Button disabled={running} onClick={() => onRunAgain(run.guardrail_id)}>{running ? <LoaderCircle className="animate-spin" /> : <Play />}{t("validation.runAgain")}</Button></>}>
    <div className="space-y-5"><div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border bg-muted/20 p-4"><div><p className="text-xs text-muted-foreground">{t("validation.targetColumn")}</p><p className="mt-1 text-sm font-medium">{targetLabel(run, t)}</p></div><StateBadge state={run.status} /></div>
      <dl className="grid grid-cols-2 overflow-hidden rounded-xl border sm:grid-cols-4"><DetailFact label={t("validation.casesColumn")} value={String(run.metrics.total)} /><DetailFact label={t("validation.passRateColumn")} value={`${run.metrics.compliance_rate}%`} /><DetailFact label={t("guardrails.falsePositive")} value={`${run.metrics.false_positive_rate}%`} /><DetailFact label={t("guardrails.latency")} value={`${run.metrics.p95_latency_ms} ms`} /></dl>
      <InfoNotice title={run.guardrail_version ? t("validation.versionCreated", { version: run.guardrail_version }) : t("validation.draftNotReleased")}>{run.guardrail_version ? t("validation.versionCreatedDescription") : t("validation.draftNotReleasedDescription")}</InfoNotice>
      <section className="overflow-hidden rounded-xl border"><header className="border-b bg-muted/25 px-4 py-3"><h3 className="text-sm font-semibold">{t("validation.caseResults")}</h3><p className="mt-1 text-xs text-muted-foreground">{t("validation.failuresFirst")}</p></header><div className="divide-y">{results.map((result) => <EvaluationResultRow key={result.case_id} result={result} />)}</div></section>
    </div>
  </EntitySheet>;
}

function DetailFact({ label, value }: { label: string; value: string }) { return <div className="border-b p-4 last:border-b-0 sm:border-r sm:border-b-0 sm:last:border-r-0"><dt className="text-xs text-muted-foreground">{label}</dt><dd className="mt-1 font-mono text-sm font-medium">{value}</dd></div>; }

export function EvaluationResultRow({ result }: { result: EvaluationCaseResult }) {
  const { t } = useTranslation();
  return <details open={!result.passed} className="group"><summary className="grid min-h-16 cursor-pointer list-none gap-3 px-4 py-3 focus-visible:outline-2 focus-visible:outline-ring sm:grid-cols-[minmax(0,1fr)_110px_90px_20px] sm:items-center [&::-webkit-details-marker]:hidden"><div><div className="flex flex-wrap items-center gap-2"><strong className="text-sm font-medium">{result.name}</strong><Badge variant="outline" className="font-normal">{testCaseTypeLabel(result.case_type, t)}</Badge></div><p className="mt-1 text-xs text-muted-foreground">{humanize(result.risk)} · {humanize(result.phase)}</p></div><StateBadge state={result.actual_decision} /><span className="font-mono text-xs text-muted-foreground">{result.latency_ms} ms</span><ChevronDown className="size-4 text-muted-foreground transition-transform group-open:rotate-180" /></summary><div className="border-t bg-muted/15 p-4">{result.source_control_id ? <section className="mb-3 rounded-lg border bg-card p-3"><h4 className="text-xs font-medium text-muted-foreground">{t("validation.acceptanceProvenance")}</h4><dl className="mt-3 grid gap-3 text-xs sm:grid-cols-2"><div><dt className="text-muted-foreground">{t("validation.sourceControl")}</dt><dd className="mt-1 break-all font-mono">{result.source_control_id}@{result.source_control_version}</dd></div><div><dt className="text-muted-foreground">{t("validation.sourceSuiteCase")}</dt><dd className="mt-1 break-all font-mono">{result.source_suite_id} / {result.source_case_id}</dd></div><div><dt className="text-muted-foreground">{t("validation.coveredRules")}</dt><dd className="mt-1 flex flex-wrap gap-1">{result.covered_rule_ids.map((id) => <code key={id} className="rounded bg-muted px-1.5 py-0.5 text-[10px]">{id}</code>)}</dd></div><div><dt className="text-muted-foreground">{t("validation.matchedRules")}</dt><dd className="mt-1 flex flex-wrap gap-1">{result.matched_rule_ids.length ? result.matched_rule_ids.map((id) => <code key={id} className="rounded bg-muted px-1.5 py-0.5 text-[10px]">{id}</code>) : <span>{t("validation.noRulesMatched")}</span>}</dd></div></dl></section> : null}<div className="grid gap-3 sm:grid-cols-2"><div className="rounded-lg border bg-card p-3"><p className="text-xs text-muted-foreground">{t("guardrails.expectedDecision")}</p><div className="mt-2"><StateBadge state={result.expected_decision} /></div></div><div className="rounded-lg border bg-card p-3"><p className="text-xs text-muted-foreground">{t("guardrails.actualDecision")}</p><div className="mt-2"><StateBadge state={result.actual_decision} /></div></div></div><p className="mt-3 text-sm leading-6">{result.reason}</p>{result.trace.length ? <div className="mt-3 space-y-2">{result.trace.map((step) => <div key={step.id} className="flex gap-3 rounded-lg border bg-card p-3 text-xs"><strong>{step.name}</strong><span className="min-w-0 flex-1 text-muted-foreground">{step.detail}</span><span className="font-mono text-muted-foreground">{step.duration_ms} ms</span></div>)}</div> : null}</div></details>;
}

function targetLabel(run: TestRun, t: ReturnType<typeof useTranslation>["t"]) { return run.guardrail_version ? t("validation.versionTarget", { version: run.guardrail_version }) : t("validation.draftRevisionTarget", { revision: run.source_draft_version }); }
function shortId(id: string) { return id.replace(/^evaluation-/, "").slice(0, 8).toUpperCase(); }
function humanize(value: string) { return value ? value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()) : "—"; }
function testCaseTypeLabel(value: string, t: ReturnType<typeof useTranslation>["t"]) { return value === "rule_acceptance" || value === "scenario" || value === "custom" || value === "unit" ? t(`validation.caseTypes.${value}`) : humanize(value); }
function notifyError(error: unknown, fallback: string) { toast.error(error instanceof Error ? error.message : fallback); }
