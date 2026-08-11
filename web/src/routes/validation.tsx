import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import {
  columnFilteringFeature,
  createColumnHelper,
  createFilteredRowModel,
  createPaginatedRowModel,
  createSortedRowModel,
  filterFn_equalsString,
  filterFn_includesString,
  flexRender,
  globalFilteringFeature,
  rowPaginationFeature,
  rowSortingFeature,
  sortFn_text,
  tableFeatures,
  useTable,
  type PaginationState,
  type SortingState,
} from "@tanstack/react-table";
import { ArrowLeft, ArrowRight, ArrowUpDown, FlaskConical, ListChecks, Plus, Search, Trash2, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { toast } from "sonner";

import { EmptyState, ErrorNotice, InfoNotice, PageHeader, StateBadge } from "@/components/product-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { queryKeys } from "@/features/query-keys";
import { createTestRun, deleteTestCase, getGuardrails, getTestCases, type Guardrail, type TestCase } from "@/lib/api";
import { AddTestCaseSheet, QuickTestPanel, TestEvidence } from "@/routes/guardrails";
import { cn } from "@/lib/utils";

const regressionTableFeatures = tableFeatures({
  columnFilteringFeature,
  globalFilteringFeature,
  filteredRowModel: createFilteredRowModel(),
  filterFns: { equalsString: filterFn_equalsString, includesString: filterFn_includesString },
  rowSortingFeature,
  sortedRowModel: createSortedRowModel(),
  sortFns: { text: sortFn_text },
  rowPaginationFeature,
  paginatedRowModel: createPaginatedRowModel(),
});
const regressionCaseColumnHelper = createColumnHelper<typeof regressionTableFeatures, TestCase>();

export function PlaygroundPage() {
  const { t } = useTranslation();
  const guardrailsQuery = useQuery({ queryKey: queryKeys.guardrails, queryFn: getGuardrails });
  const guardrails = guardrailsQuery.data?.items ?? [];
  const [guardrailId, setGuardrailId] = useGuardrailSelection(guardrails);
  const selected = guardrails.find((item) => item.id === guardrailId);

  return (
    <section className="py-6 sm:py-8">
      <PageHeader eyebrow={t("pages.playground.eyebrow")} title={t("pages.playground.title")} description={t("pages.playground.description")} />
      {guardrailsQuery.error ? <div className="mt-5"><ErrorNotice error={guardrailsQuery.error} /></div> : null}
      {guardrailsQuery.isLoading ? <Skeleton className="mt-5 h-80 rounded-xl" /> : null}
      {!guardrailsQuery.isLoading && !guardrails.length ? <div className="mt-5"><EmptyState title={t("validation.noGuardrails")} description={t("validation.noGuardrailsDescription")} /></div> : null}
      {selected ? (
        <div className="mt-5 space-y-4">
          <GuardrailPicker guardrails={guardrails} value={guardrailId} onChange={setGuardrailId} />
          <SelectedGuardrail guardrail={selected} />
          <QuickTestPanel key={guardrailId} guardrailId={guardrailId} />
        </div>
      ) : null}
    </section>
  );
}

export function EvaluationsPage() {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const guardrailsQuery = useQuery({ queryKey: queryKeys.guardrails, queryFn: getGuardrails });
  const guardrails = guardrailsQuery.data?.items ?? [];
  const [guardrailId, setGuardrailId] = useGuardrailSelection(guardrails.filter((item) => !item.system_managed));
  const selected = guardrails.find((item) => item.id === guardrailId);
  const casesQuery = useQuery({ queryKey: queryKeys.testCases(guardrailId), queryFn: () => getTestCases(guardrailId), enabled: Boolean(guardrailId) });
  const [addOpen, setAddOpen] = useState(false);
  const testCases = casesQuery.data?.items ?? [];

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.guardrails }),
      queryClient.invalidateQueries({ queryKey: queryKeys.testCases(guardrailId) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.assignments }),
    ]);
  };
  const evaluation = useMutation({
    mutationFn: () => createTestRun(guardrailId),
    onSuccess: async (run) => {
      await refresh();
      toast[run.status === "passed" ? "success" : "error"](run.status === "passed" ? t("guardrails.testsPassed") : t("guardrails.testsFailed", { rate: run.metrics.compliance_rate }));
    },
    onError: (error) => notifyError(error, t("guardrails.operationFailed")),
  });
  const removeCase = useMutation({
    mutationFn: deleteTestCase,
    onSuccess: async () => { await refresh(); toast.success(t("guardrails.caseRemoved")); },
    onError: (error) => notifyError(error, t("guardrails.operationFailed")),
  });

  return (
    <section className="py-6 sm:py-8">
      <PageHeader eyebrow={t("pages.evaluations.eyebrow")} title={t("pages.evaluations.title")} description={t("pages.evaluations.description")} />
      {guardrailsQuery.error ? <div className="mt-5"><ErrorNotice error={guardrailsQuery.error} /></div> : null}
      {guardrailsQuery.isLoading ? <Skeleton className="mt-5 h-80 rounded-xl" /> : null}
      {!guardrailsQuery.isLoading && !guardrails.filter((item) => !item.system_managed).length ? <div className="mt-5"><EmptyState title={t("validation.noGuardrails")} description={t("validation.noGuardrailsDescription")} /></div> : null}
      {selected ? (
        <div className="mt-5 space-y-5">
          <EvaluationContext
            guardrails={guardrails.filter((item) => !item.system_managed)}
            guardrail={selected}
            value={guardrailId}
            onChange={setGuardrailId}
            caseCount={testCases.length}
            locale={i18n.language}
            running={evaluation.isPending}
            onRun={() => evaluation.mutate()}
          />
          {casesQuery.error ? <ErrorNotice error={casesQuery.error} /> : casesQuery.isLoading ? <Skeleton className="h-[560px] rounded-xl" /> : testCases.length ? (
            <RegressionCasesTable cases={testCases} deleting={removeCase.isPending} onDelete={(caseId) => removeCase.mutate(caseId)} onAdd={() => setAddOpen(true)} />
          ) : <EmptyState title={t("guardrails.noCases")} description={t("guardrails.noCasesDescription")} action={<Button onClick={() => setAddOpen(true)}><Plus />{t("guardrails.addTestCase")}</Button>} />}
          {selected.latest_test_run ? <TestEvidence guardrail={selected} /> : <InfoNotice title={t("validation.noRunTitle")}>{t("validation.noRunDescription")}</InfoNotice>}
          <AddTestCaseSheet guardrail={selected} open={addOpen} onOpenChange={setAddOpen} onCreated={async () => { setAddOpen(false); await refresh(); }} />
        </div>
      ) : null}
    </section>
  );
}

function EvaluationContext({
  guardrails,
  guardrail,
  value,
  onChange,
  caseCount,
  locale,
  running,
  onRun,
}: {
  guardrails: Guardrail[];
  guardrail: Guardrail;
  value: string;
  onChange: (value: string) => void;
  caseCount: number;
  locale: string;
  running: boolean;
  onRun: () => void;
}) {
  const { t } = useTranslation();
  return (
    <section className="overflow-hidden rounded-xl border bg-card shadow-xs">
      <div className="flex flex-col gap-4 border-b bg-muted/20 p-5 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium">{t("validation.chooseGuardrail")}</p>
          <p className="mt-1 text-xs text-muted-foreground">{t("validation.chooseGuardrailDescription")}</p>
          <Select value={value} onValueChange={onChange}>
            <SelectTrigger className="mt-3 min-h-11 w-full bg-card sm:max-w-md"><SelectValue /></SelectTrigger>
            <SelectContent>{guardrails.map((item) => <SelectItem key={item.id} value={item.id}>{item.name}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <Button asChild variant="outline" className="min-h-11 self-start lg:self-auto"><Link to="/guardrails/$guardrailId" params={{ guardrailId: guardrail.id }}>{t("validation.openDefinition")}</Link></Button>
      </div>
      <div className="p-5">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-3xl">
            <div className="flex flex-wrap items-center gap-2"><p className="text-xs font-semibold uppercase tracking-[0.12em] text-primary">{t("guardrails.releaseGate")}</p><StateBadge state={guardrail.tested_current ? "passed" : "needs_testing"} /></div>
            <h2 className="mt-2 text-lg font-semibold">{t("guardrails.releaseEvaluation")}</h2>
            <p className="mt-1 text-sm leading-6 text-muted-foreground">{t("guardrails.releaseEvaluationDescription")}</p>
          </div>
          <Button className="min-h-11 shrink-0" disabled={running || !caseCount} onClick={onRun}><ListChecks />{t(running ? "guardrails.runningEvaluation" : "guardrails.runEvaluation")}</Button>
        </div>
        <dl className="mt-5 grid overflow-hidden rounded-lg border sm:grid-cols-3">
          <EvaluationFact label={t("guardrails.regressionCases")} value={String(caseCount)} />
          <EvaluationFact label={t("guardrails.latestRun")} value={guardrail.latest_test_run ? new Date(guardrail.latest_test_run.created_at).toLocaleString(locale) : t("guardrails.neverRun")} />
          <EvaluationFact label={t("guardrails.releaseEligibility")} value={t(guardrail.tested_current ? "guardrails.versionReady" : "guardrails.blockedUntilPass")} />
        </dl>
      </div>
    </section>
  );
}

function RegressionCasesTable({ cases, deleting, onDelete, onAdd }: { cases: TestCase[]; deleting: boolean; onDelete: (caseId: string) => void; onAdd: () => void }) {
  const { t } = useTranslation();
  const [sorting, setSorting] = useState<SortingState>([]);
  const [globalFilter, setGlobalFilter] = useState("");
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 10 });
  const columns = useMemo(() => regressionCaseColumnHelper.columns([
    regressionCaseColumnHelper.accessor((item) => `${item.name} ${item.content}`, {
      id: "case",
      sortFn: "text",
      header: ({ column }) => <SortableHeader label={t("validation.caseColumn")} onClick={() => column.toggleSorting(column.getIsSorted() === "asc")} />,
      cell: ({ row }) => <div className="min-w-0 whitespace-normal"><strong className="block text-sm font-medium">{row.original.name}</strong><p className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">{row.original.content}</p><p className="mt-2 text-[11px] text-muted-foreground md:hidden">{caseRiskLabel(row.original.risk, t)} · {t(row.original.phase === "input" ? "guardrails.input" : "guardrails.output")}</p></div>,
    }),
    regressionCaseColumnHelper.accessor("risk", {
      filterFn: "equalsString",
      sortFn: "text",
      header: ({ column }) => <SortableHeader label={t("validation.controlColumn")} onClick={() => column.toggleSorting(column.getIsSorted() === "asc")} />,
      cell: ({ row }) => <span className="text-xs">{caseRiskLabel(row.original.risk, t)}</span>,
    }),
    regressionCaseColumnHelper.accessor("phase", {
      filterFn: "equalsString",
      sortFn: "text",
      header: ({ column }) => <SortableHeader label={t("validation.surfaceColumn")} onClick={() => column.toggleSorting(column.getIsSorted() === "asc")} />,
      cell: ({ row }) => <span className="text-xs">{t(row.original.phase === "input" ? "guardrails.input" : "guardrails.output")}</span>,
    }),
    regressionCaseColumnHelper.accessor("expected_decision", {
      filterFn: "equalsString",
      sortFn: "text",
      header: ({ column }) => <SortableHeader label={t("validation.expectedColumn")} onClick={() => column.toggleSorting(column.getIsSorted() === "asc")} />,
      cell: ({ row }) => <StateBadge state={row.original.expected_decision === "intervene" ? "intervene" : row.original.expected_decision} />,
    }),
    regressionCaseColumnHelper.display({
      id: "actions",
      enableSorting: false,
      enableGlobalFilter: false,
      enableColumnFilter: false,
      cell: ({ row }) => <Button type="button" size="icon" variant="ghost" className="size-11" aria-label={t("validation.deleteCase", { name: row.original.name })} disabled={deleting} onClick={() => onDelete(row.original.id)}><Trash2 /></Button>,
    }),
  ]), [deleting, onDelete, t]);
  const table = useTable({
    features: regressionTableFeatures,
    data: cases,
    columns,
    state: { sorting, globalFilter, pagination },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    onPaginationChange: setPagination,
    globalFilterFn: "includesString",
    getColumnCanGlobalFilter: (column) => column.id === "case",
    enableMultiSort: false,
    enableSortingRemoval: false,
    autoResetPageIndex: true,
    getRowId: (row) => row.id,
  });
  const controls = useMemo(() => Array.from(new Set(cases.map((item) => item.risk))).sort((left, right) => caseRiskLabel(left, t).localeCompare(caseRiskLabel(right, t))), [cases, t]);
  const filteredCount = table.getFilteredRowModel().rows.length;
  const start = filteredCount ? pagination.pageIndex * pagination.pageSize + 1 : 0;
  const end = Math.min(start + table.getRowModel().rows.length - 1, filteredCount);
  const filtersActive = Boolean(globalFilter || table.getColumn("risk")?.getFilterValue() || table.getColumn("expected_decision")?.getFilterValue());

  return (
    <section className="overflow-hidden rounded-xl border bg-card shadow-xs">
      <header className="flex flex-col gap-4 border-b p-5 sm:flex-row sm:items-start sm:justify-between">
        <div><div className="flex flex-wrap items-center gap-2"><h2 className="text-lg font-semibold">{t("guardrails.reviewedCases")}</h2><span className="rounded-md border bg-muted/40 px-2 py-0.5 text-xs font-medium text-muted-foreground">{filteredCount}</span></div><p className="mt-1 text-xs leading-5 text-muted-foreground">{t("guardrails.reviewedCasesDescription")}</p></div>
        <Button variant="outline" className="min-h-11 shrink-0" onClick={onAdd}><Plus />{t("guardrails.addCase")}</Button>
      </header>
      <div className="grid gap-3 border-b bg-muted/15 p-4 lg:grid-cols-[minmax(240px,1fr)_220px_180px_auto]">
        <label className="relative"><Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" /><Input value={globalFilter} onChange={(event) => setGlobalFilter(event.target.value)} className="min-h-11 bg-card pl-9" placeholder={t("validation.searchCases")} aria-label={t("validation.searchCases")} /></label>
        <Select value={String(table.getColumn("risk")?.getFilterValue() ?? "all")} onValueChange={(value) => table.getColumn("risk")?.setFilterValue(value === "all" ? undefined : value)}><SelectTrigger className="min-h-11 bg-card" aria-label={t("validation.filterControl")}><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">{t("validation.allControls")}</SelectItem>{controls.map((risk) => <SelectItem key={risk} value={risk}>{caseRiskLabel(risk, t)}</SelectItem>)}</SelectContent></Select>
        <Select value={String(table.getColumn("expected_decision")?.getFilterValue() ?? "all")} onValueChange={(value) => table.getColumn("expected_decision")?.setFilterValue(value === "all" ? undefined : value)}><SelectTrigger className="min-h-11 bg-card" aria-label={t("validation.filterExpected")}><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">{t("validation.allExpected")}</SelectItem>{["allow", "transform", "block", "intervene"].map((decision) => <SelectItem key={decision} value={decision}>{t(decision === "intervene" ? "guardrails.anyIntervention" : `states.${decision}`)}</SelectItem>)}</SelectContent></Select>
        <Button type="button" variant="ghost" className="min-h-11 justify-self-start px-3 lg:justify-self-end" disabled={!filtersActive} onClick={() => { setGlobalFilter(""); table.resetColumnFilters(); }}><X />{t("validation.clearFilters")}</Button>
      </div>
      <Table className="table-fixed">
        <TableHeader>
          {table.getHeaderGroups().map((headerGroup) => <TableRow key={headerGroup.id} className="hover:bg-transparent">{headerGroup.headers.map((header) => <TableHead key={header.id} className={columnClass(header.column.id)}>{header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}</TableHead>)}</TableRow>)}
        </TableHeader>
        <TableBody>
          {table.getRowModel().rows.length ? table.getRowModel().rows.map((row) => <TableRow key={row.id}>{row.getAllCells().map((cell) => <TableCell key={cell.id} className={cn("py-3", columnClass(cell.column.id))}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</TableCell>)}</TableRow>) : <TableRow><TableCell colSpan={columns.length} className="h-40 text-center whitespace-normal text-muted-foreground">{t("validation.noMatchingCases")}</TableCell></TableRow>}
        </TableBody>
      </Table>
      <footer className="flex flex-col gap-3 border-t bg-muted/15 px-4 py-3 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
        <p>{t("validation.showingCases", { start, end, total: filteredCount })}</p>
        <div className="flex flex-wrap items-center gap-2">
          <Select value={String(pagination.pageSize)} onValueChange={(value) => table.setPageSize(Number(value))}><SelectTrigger className="min-h-10 w-28 bg-card" aria-label={t("validation.rowsPerPage")}><SelectValue /></SelectTrigger><SelectContent>{[10, 20, 50].map((size) => <SelectItem key={size} value={String(size)}>{t("validation.rows", { count: size })}</SelectItem>)}</SelectContent></Select>
          <Button type="button" size="icon" variant="outline" className="size-10 bg-card" aria-label={t("validation.previousPage")} disabled={!table.getCanPreviousPage()} onClick={() => table.previousPage()}><ArrowLeft /></Button>
          <span className="min-w-16 text-center font-medium text-foreground">{t("validation.pageOf", { page: pagination.pageIndex + 1, pages: Math.max(table.getPageCount(), 1) })}</span>
          <Button type="button" size="icon" variant="outline" className="size-10 bg-card" aria-label={t("validation.nextPage")} disabled={!table.getCanNextPage()} onClick={() => table.nextPage()}><ArrowRight /></Button>
        </div>
      </footer>
    </section>
  );
}

function SortableHeader({ label, onClick }: { label: string; onClick: () => void }) {
  return <button type="button" className="-ml-2 inline-flex min-h-10 items-center gap-1 rounded-md px-2 text-left hover:bg-muted focus-visible:outline-2 focus-visible:outline-ring" onClick={onClick}>{label}<ArrowUpDown className="size-3.5 text-muted-foreground" /></button>;
}

function columnClass(columnId: string) {
  return ({ case: "w-auto px-4", risk: "hidden w-52 md:table-cell", phase: "hidden w-28 lg:table-cell", expected_decision: "w-28 sm:w-36", actions: "w-14 pr-2 text-right" } as Record<string, string>)[columnId] ?? "";
}

function caseRiskLabel(value: string, t: TFunction) {
  return ({ builtin_content_filter: t("guardrails.riskBuiltin"), topic_control: t("guardrails.riskTopic"), pii: t("guardrails.riskPii"), secrets: t("guardrails.riskSecrets"), prompt_injection: t("guardrails.riskInjection"), jailbreak: t("guardrails.riskJailbreak"), content_safety: t("guardrails.riskUnsafe"), company_policy: t("guardrails.riskCompany"), contextual_grounding: t("guardrails.riskGrounding"), automated_reasoning: t("guardrails.riskReasoning") } as Record<string, string>)[value] ?? value.replaceAll("_", " ");
}

function GuardrailPicker({ guardrails, value, onChange }: { guardrails: Guardrail[]; value: string; onChange: (value: string) => void }) {
  const { t } = useTranslation();
  return <div className="flex flex-col gap-2 rounded-xl border bg-card p-4 sm:flex-row sm:items-center sm:justify-between"><div><p className="text-sm font-medium">{t("validation.chooseGuardrail")}</p><p className="mt-1 text-xs text-muted-foreground">{t("validation.chooseGuardrailDescription")}</p></div><Select value={value} onValueChange={onChange}><SelectTrigger className="min-h-11 w-full bg-card sm:w-80"><SelectValue /></SelectTrigger><SelectContent>{guardrails.map((item) => <SelectItem key={item.id} value={item.id}>{item.name}</SelectItem>)}</SelectContent></Select></div>;
}

function SelectedGuardrail({ guardrail }: { guardrail: Guardrail }) {
  const { t } = useTranslation();
  return <div className="flex flex-col gap-3 rounded-xl border bg-muted/20 p-4 sm:flex-row sm:items-center sm:justify-between"><div><div className="flex items-center gap-2"><FlaskConical className="size-4 text-primary" /><strong className="text-sm font-medium">{guardrail.name}</strong><StateBadge state={guardrail.status} /></div><p className="mt-1.5 line-clamp-2 text-xs leading-5 text-muted-foreground">{guardrail.purpose}</p></div><Button asChild variant="ghost" className="self-start sm:self-auto"><Link to="/guardrails/$guardrailId" params={{ guardrailId: guardrail.id }}>{t("validation.openDefinition")}</Link></Button></div>;
}

function EvaluationFact({ label, value }: { label: string; value: string }) {
  return <div className="border-b p-4 last:border-b-0 sm:border-r sm:border-b-0 sm:last:border-r-0"><dt className="text-xs font-medium text-muted-foreground">{label}</dt><dd className="mt-1.5 text-sm font-medium">{value}</dd></div>;
}

function useGuardrailSelection(guardrails: Guardrail[]) {
  const initial = typeof window === "undefined" ? "" : new URLSearchParams(window.location.search).get("guardrail") ?? "";
  const [guardrailId, setGuardrailId] = useState(initial);
  useEffect(() => {
    if (!guardrails.length) return;
    if (!guardrails.some((item) => item.id === guardrailId)) setGuardrailId(guardrails[0].id);
  }, [guardrailId, guardrails]);
  return [guardrailId, setGuardrailId] as const;
}

function notifyError(error: unknown, fallback: string) { toast.error(error instanceof Error ? error.message : fallback); }
