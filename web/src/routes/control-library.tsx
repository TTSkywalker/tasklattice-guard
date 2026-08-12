import { Fragment, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  createColumnHelper,
  createPaginatedRowModel,
  createSortedRowModel,
  rowPaginationFeature,
  rowSortingFeature,
  sortFn_alphanumeric,
  sortFn_text,
  tableFeatures,
  useTable,
} from "@tanstack/react-table";
import {
  ArrowUpDown,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ListTree,
  PackageOpen,
  Search,
  ShieldCheck,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import { EntitySheet } from "@/components/entity-sheet";
import { NativeControlInventory } from "@/components/native-control-studio";
import { ErrorNotice, PageHeader } from "@/components/product-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { queryKeys } from "@/features/query-keys";
import {
  getControlTemplates,
  type ControlTemplate,
  type ControlTemplateRule,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const EMPTY_TEMPLATES: ControlTemplate[] = [];
const tableFeatureSet = tableFeatures({
  rowSortingFeature,
  sortedRowModel: createSortedRowModel(),
  sortFns: { alphanumeric: sortFn_alphanumeric, text: sortFn_text },
  rowPaginationFeature,
  paginatedRowModel: createPaginatedRowModel(),
});
const columnHelper = createColumnHelper<typeof tableFeatureSet, ControlTemplate>();

export function ControlLibraryPage() {
  const { t } = useTranslation();
  return (
    <section className="py-6 sm:py-8">
      <PageHeader
        eyebrow={t("pages.controlLibrary.eyebrow")}
        title={t("pages.controlLibrary.title")}
        description={t("pages.controlLibrary.description")}
      />
      <Tabs defaultValue="custom" className="mt-5">
        <TabsList className="h-11 w-full justify-start overflow-x-auto p-1 sm:w-fit" aria-label={t("controlStudio.libraryViews")}>
          <TabsTrigger className="min-h-9 px-3" value="custom">{t("controlStudio.customControls")}</TabsTrigger>
          <TabsTrigger className="min-h-9 px-3" value="built-in">{t("controlStudio.builtInControls")}</TabsTrigger>
          <TabsTrigger className="min-h-9 px-3" value="templates">{t("controlStudio.ruleTemplates")}</TabsTrigger>
        </TabsList>
        <TabsContent value="custom" className="pt-4"><NativeControlInventory source="custom" /></TabsContent>
        <TabsContent value="built-in" className="pt-4"><NativeControlInventory source="built-in" /></TabsContent>
        <TabsContent value="templates"><LegacyControlTemplatePage embedded /></TabsContent>
      </Tabs>
    </section>
  );
}

function LegacyControlTemplatePage({ embedded = false }: { embedded?: boolean }) {
  const { t } = useTranslation();
  const templatesQuery = useQuery({ queryKey: queryKeys.controlTemplates, queryFn: getControlTemplates });
  const templates = templatesQuery.data?.items ?? EMPTY_TEMPLATES;
  const [search, setSearch] = useState("");
  const [detector, setDetector] = useState("all");
  const [pack, setPack] = useState("all");
  const [selected, setSelected] = useState<ControlTemplate | null>(null);

  const packs = useMemo(() => {
    const values = new Map<string, string>();
    for (const template of templates) {
      for (const item of template.packs) values.set(item.id, item.name);
    }
    return [...values].sort((left, right) => left[1].localeCompare(right[1]));
  }, [templates]);

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    return templates.filter((template) => {
      if (detector !== "all" && !template.detector_types.includes(detector as ControlTemplateRule["detector"])) return false;
      if (pack !== "all" && !template.packs.some((item) => item.id === pack)) return false;
      if (!query) return true;
      const haystack = [
        template.name,
        template.id,
        template.description,
        ...template.tags,
        ...template.packs.flatMap((item) => [item.name, item.domain]),
        ...template.rules.flatMap((item) => [item.id, item.name, item.description]),
      ].join(" ").toLowerCase();
      return haystack.includes(query);
    });
  }, [detector, pack, search, templates]);

  const columns = useMemo(() => columnHelper.columns([
    columnHelper.accessor("name", {
      id: "name",
      header: ({ column }) => <SortableHeader label={t("controlLibrary.controlTemplate")} sorted={column.getIsSorted()} onClick={column.getToggleSortingHandler()} />,
      cell: ({ row }) => (
        <button
          type="button"
          className="block min-h-11 w-full rounded-md py-1 text-left outline-none focus-visible:ring-2 focus-visible:ring-ring"
          onClick={() => setSelected(row.original)}
        >
          <span className="block text-sm font-medium text-foreground group-hover:text-primary">{row.original.name}</span>
          <span className="mt-1 block font-mono text-[11px] text-muted-foreground">{row.original.id}</span>
        </button>
      ),
      sortFn: "text",
    }),
    columnHelper.accessor((row) => row.detector_types.join(","), {
      id: "detectors",
      header: t("controlLibrary.detector"),
      cell: ({ row }) => <DetectorBadges detectors={row.original.detector_types} />,
      sortFn: "text",
    }),
    columnHelper.accessor((row) => row.phases.join(","), {
      id: "phase",
      header: t("controlLibrary.phase"),
      cell: ({ row }) => <span className="text-xs text-muted-foreground">{row.original.phases.map((item) => t(`controlLibrary.phases.${item}`)).join(", ")}</span>,
      sortFn: "text",
    }),
    columnHelper.accessor("default_action", {
      id: "action",
      header: t("controlLibrary.defaultAction"),
      cell: ({ getValue }) => <ActionBadge action={getValue()} />,
      sortFn: "text",
    }),
    columnHelper.accessor((row) => row.rules.length, {
      id: "rules",
      header: ({ column }) => <SortableHeader label={t("controlLibrary.rules")} sorted={column.getIsSorted()} onClick={column.getToggleSortingHandler()} />,
      cell: ({ getValue }) => <span className="font-mono text-xs tabular-nums">{getValue()}</span>,
    }),
    columnHelper.accessor((row) => row.packs.map((item) => item.name).join(", "), {
      id: "packs",
      header: t("controlLibrary.controlPacks"),
      cell: ({ row }) => (
        <div className="max-w-60">
          <span className="block truncate text-xs">{row.original.packs[0]?.name ?? "—"}</span>
          {row.original.packs.length > 1 ? <span className="mt-1 block text-[11px] text-muted-foreground">{t("controlLibrary.morePacks", { count: row.original.packs.length - 1 })}</span> : null}
        </div>
      ),
      sortFn: "text",
    }),
    columnHelper.accessor("version", {
      id: "version",
      header: t("controlLibrary.version"),
      cell: ({ row }) => <div><span className="block font-mono text-xs">{row.original.version}</span><span className="mt-1 block text-[11px] text-muted-foreground">{t("controlLibrary.builtIn")}</span></div>,
      sortFn: "alphanumeric",
    }),
    columnHelper.display({
      id: "open",
      header: () => <span className="sr-only">{t("controlLibrary.openDetails")}</span>,
      cell: ({ row }) => (
        <Button type="button" size="icon" variant="ghost" aria-label={t("controlLibrary.openNamed", { name: row.original.name })} onClick={() => setSelected(row.original)}>
          <ChevronRight />
        </Button>
      ),
    }),
  ]), [t]);

  const table = useTable({
    features: tableFeatureSet,
    columns,
    data: filtered,
    getRowId: (row) => row.id,
    initialState: {
      sorting: [{ id: "name", desc: false }],
      pagination: { pageIndex: 0, pageSize: 20 },
    },
    enableSortingRemoval: false,
  });

  useEffect(() => {
    table.resetPageIndex(true);
  }, [detector, pack, search, table]);

  const pageStart = filtered.length ? table.state.pagination.pageIndex * table.state.pagination.pageSize + 1 : 0;
  const pageEnd = Math.min(filtered.length, pageStart + table.getRowModel().rows.length - 1);
  const ruleCount = templates.reduce((total, item) => total + item.rules.length, 0);

  return (
    <section className={cn(!embedded && "py-6 sm:py-8", embedded && "pt-4")}>
      {!embedded ? <PageHeader
        eyebrow={t("pages.controlLibrary.eyebrow")}
        title={t("pages.controlLibrary.title")}
        description={t("pages.controlLibrary.description")}
      /> : null}

      {templatesQuery.error ? <div className="mt-5"><ErrorNotice error={templatesQuery.error} /></div> : null}
      {templatesQuery.isLoading ? <Skeleton className="mt-5 h-[34rem] rounded-xl" /> : null}

      {!templatesQuery.isLoading && !templatesQuery.error ? (
        <>
          <section className="mt-5 grid overflow-hidden rounded-xl border bg-card shadow-xs sm:grid-cols-3" aria-label={t("controlLibrary.inventorySummary")}>
            <InventoryFact icon={ShieldCheck} label={t("controlLibrary.templatesAvailable")} value={templates.length} />
            <InventoryFact icon={ListTree} label={t("controlLibrary.executableRules")} value={ruleCount} />
            <InventoryFact icon={PackageOpen} label={t("controlLibrary.controlPacks")} value={packs.length} />
          </section>

          <section className="mt-5 overflow-hidden rounded-xl border bg-card shadow-xs">
            <div className="grid gap-3 border-b bg-muted/20 p-4 lg:grid-cols-[minmax(18rem,1fr)_13rem_18rem_auto] lg:items-center">
              <label className="relative block">
                <span className="sr-only">{t("controlLibrary.searchLabel")}</span>
                <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input className="min-h-11 bg-card pl-9" value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t("controlLibrary.searchPlaceholder")} />
              </label>
              <Select value={detector} onValueChange={setDetector}>
                <SelectTrigger className="min-h-11 bg-card" aria-label={t("controlLibrary.filterDetector")}><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">{t("controlLibrary.allDetectors")}</SelectItem>
                  <SelectItem value="regex">{t("controlLibrary.detectors.regex")}</SelectItem>
                  <SelectItem value="keyword">{t("controlLibrary.detectors.keyword")}</SelectItem>
                  <SelectItem value="category">{t("controlLibrary.detectors.category")}</SelectItem>
                </SelectContent>
              </Select>
              <Select value={pack} onValueChange={setPack}>
                <SelectTrigger className="min-h-11 bg-card" aria-label={t("controlLibrary.filterPack")}><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">{t("controlLibrary.allPacks")}</SelectItem>
                  {packs.map(([id, name]) => <SelectItem key={id} value={id}>{name}</SelectItem>)}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground lg:text-right" aria-live="polite">{t("controlLibrary.results", { count: filtered.length })}</p>
            </div>

            <Table>
              <TableHeader>
                {table.getHeaderGroups().map((group) => (
                  <TableRow key={group.id} className="hover:bg-transparent">
                    {group.headers.map((header) => (
                      <TableHead key={header.id} className={columnClass(header.column.id)}>
                        {header.isPlaceholder ? null : <table.FlexRender header={header} />}
                      </TableHead>
                    ))}
                  </TableRow>
                ))}
              </TableHeader>
              <TableBody>
                {table.getRowModel().rows.length ? table.getRowModel().rows.map((row) => (
                  <TableRow key={row.id} className="group">
                    {row.getAllCells().map((cell) => (
                      <TableCell key={cell.id} className={cn("py-3 whitespace-normal", columnClass(cell.column.id))}>
                        <table.FlexRender cell={cell} />
                      </TableCell>
                    ))}
                  </TableRow>
                )) : (
                  <TableRow className="hover:bg-transparent">
                    <TableCell colSpan={columns.length} className="h-48 text-center text-sm text-muted-foreground">
                      {t("controlLibrary.noResults")}
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>

            <div className="flex flex-col gap-3 border-t bg-muted/20 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-xs text-muted-foreground">{t("controlLibrary.range", { start: pageStart, end: pageEnd, total: filtered.length })}</p>
              <div className="flex items-center gap-2">
                <Button className="min-h-11" variant="outline" disabled={!table.getCanPreviousPage()} onClick={() => table.previousPage()}><ChevronLeft />{t("common.previous")}</Button>
                <span className="min-w-20 text-center font-mono text-xs text-muted-foreground">{t("controlLibrary.page", { current: table.state.pagination.pageIndex + 1, total: Math.max(1, table.getPageCount()) })}</span>
                <Button className="min-h-11" variant="outline" disabled={!table.getCanNextPage()} onClick={() => table.nextPage()}>{t("common.next")}<ChevronRight /></Button>
              </div>
            </div>
          </section>
        </>
      ) : null}

      <ControlTemplateDetail template={selected} onClose={() => setSelected(null)} />
    </section>
  );
}

function ControlTemplateDetail({ template, onClose }: { template: ControlTemplate | null; onClose: () => void }) {
  const { t } = useTranslation();
  const [expandedRule, setExpandedRule] = useState<string | null>(null);

  useEffect(() => setExpandedRule(null), [template?.id]);

  return (
    <EntitySheet
      open={Boolean(template)}
      onOpenChange={(open) => { if (!open) onClose(); }}
      eyebrow={t("controlLibrary.auditEyebrow")}
      title={template?.name ?? t("controlLibrary.controlTemplate")}
      description={template?.description ?? ""}
      width="xl"
      footer={<Button type="button" variant="outline" onClick={onClose}>{t("common.close")}</Button>}
    >
      {template ? (
        <div className="space-y-5">
          <section className="overflow-hidden rounded-xl border bg-card">
            <div className="flex flex-col gap-3 border-b px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0"><p className="text-xs font-medium text-muted-foreground">{t("controlLibrary.templateId")}</p><code className="mt-1 block truncate text-xs">{template.id}</code></div>
              <div className="flex flex-wrap gap-1.5"><Badge variant="outline">{t(`controlLibrary.statuses.${template.status}`)}</Badge><Badge variant="outline" className="font-mono">v{template.version}</Badge></div>
            </div>
            <dl className="grid grid-cols-2 sm:grid-cols-4">
              <DetailFact label={t("controlLibrary.detector")} value={template.detector_types.map((item) => t(`controlLibrary.detectors.${item}`)).join(", ")} />
              <DetailFact label={t("controlLibrary.phase")} value={template.phases.map((item) => t(`controlLibrary.phases.${item}`)).join(", ")} />
              <DetailFact label={t("controlLibrary.defaultAction")} value={actionLabel(template.default_action, t)} />
              <DetailFact label={t("controlLibrary.ruleCount")} value={String(template.rules.length)} mono />
            </dl>
            <p className="border-t px-4 py-2.5 text-xs text-muted-foreground"><span className="font-medium text-foreground">{t("controlLibrary.source")}:</span> {template.source}</p>
          </section>

          <section className="rounded-xl border bg-card p-4">
            <h3 className="text-sm font-medium">{t("controlLibrary.includedIn")}</h3>
            <div className="mt-3 flex flex-wrap gap-2">
              {template.packs.map((item) => <Badge key={item.id} variant="outline" className="h-auto whitespace-normal py-1"><PackageOpen />{item.name}</Badge>)}
            </div>
          </section>

          <section className="overflow-hidden rounded-xl border bg-card">
            <div className="border-b bg-muted/30 px-4 py-3">
              <h3 className="text-sm font-medium">{t("controlLibrary.rulesCount", { count: template.rules.length })}</h3>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">{t("controlLibrary.rulesDescription")}</p>
            </div>
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="min-w-56 pl-4">{t("controlLibrary.rule")}</TableHead>
                  <TableHead className="hidden sm:table-cell">{t("controlLibrary.detector")}</TableHead>
                  <TableHead className="hidden sm:table-cell">{t("controlLibrary.action")}</TableHead>
                  <TableHead className="w-12"><span className="sr-only">{t("controlLibrary.openDetails")}</span></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {template.rules.map((rule) => {
                  const expanded = expandedRule === rule.id;
                  return (
                    <Fragment key={rule.id}>
                      <TableRow className="group">
                        <TableCell className="py-3 pl-4 whitespace-normal"><strong className="block text-sm font-medium">{rule.name}</strong><span className="mt-1 block font-mono text-[11px] text-muted-foreground">{rule.id}</span><div className="mt-2 flex flex-wrap gap-1.5 sm:hidden"><DetectorBadges detectors={[rule.detector]} /><ActionBadge action={rule.action} /></div></TableCell>
                        <TableCell className="hidden sm:table-cell"><DetectorBadges detectors={[rule.detector]} /></TableCell>
                        <TableCell className="hidden sm:table-cell"><ActionBadge action={rule.action} /></TableCell>
                        <TableCell className="pr-3"><Button type="button" size="icon" variant="ghost" aria-expanded={expanded} aria-label={t("controlLibrary.toggleRule", { name: rule.name })} onClick={() => setExpandedRule(expanded ? null : rule.id)}><ChevronDown className={cn("transition-transform", expanded && "rotate-180")} /></Button></TableCell>
                      </TableRow>
                      {expanded ? (
                        <TableRow className="hover:bg-transparent">
                          <TableCell colSpan={4} className="max-w-0 min-w-0 bg-muted/20 p-4 whitespace-normal"><RuleImplementation rule={rule} /></TableCell>
                        </TableRow>
                      ) : null}
                    </Fragment>
                  );
                })}
              </TableBody>
            </Table>
          </section>

          {template.limitations.length ? (
            <section className="rounded-xl border border-amber-200 bg-amber-50/60 p-4">
              <h3 className="text-sm font-medium text-amber-900">{t("controlLibrary.limitations")}</h3>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-xs leading-5 text-amber-900/75">{template.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
            </section>
          ) : null}
        </div>
      ) : null}
    </EntitySheet>
  );
}

function RuleImplementation({ rule }: { rule: ControlTemplateRule }) {
  const { t } = useTranslation();
  const lists = [
    ["identifiers", rule.identifiers],
    ["conditions", rule.conditions],
    ["keywords", rule.keywords],
    ["alwaysBlock", rule.always_block],
    ["exceptions", rule.exceptions],
    ["phrasePatterns", rule.phrase_patterns],
  ] as const;
  return (
    <div className="grid min-w-0 gap-4">
      {rule.description ? <p className="text-xs leading-5 text-muted-foreground">{rule.description}</p> : null}
      <div className="grid min-w-0 gap-3 sm:grid-cols-2">
        {rule.expression ? <CodeValue label={t("controlLibrary.expression")} value={rule.expression} /> : null}
        {rule.context_expression ? <CodeValue label={t("controlLibrary.contextExpression")} value={rule.context_expression} /> : null}
        {rule.redaction ? <CodeValue label={t("controlLibrary.redactionFormat")} value={rule.redaction} /> : null}
        {rule.severity_threshold ? <CodeValue label={t("controlLibrary.severityThreshold")} value={rule.severity_threshold} /> : null}
      </div>
      {lists.some(([, values]) => values.length) ? (
        <div className="grid gap-4 sm:grid-cols-2">
          {lists.map(([key, values]) => values.length ? (
            <div key={key}>
              <p className="text-xs font-medium text-muted-foreground">{t(`controlLibrary.${key}`)}</p>
              <div className="mt-2 flex flex-wrap gap-1.5">{values.map((value) => <Badge key={value} variant="secondary" className="h-auto max-w-full whitespace-normal py-1 font-normal">{value}</Badge>)}</div>
            </div>
          ) : null)}
        </div>
      ) : null}
    </div>
  );
}

function InventoryFact({ icon: Icon, label, value }: { icon: typeof ShieldCheck; label: string; value: number }) {
  return <div className="flex min-h-20 items-center gap-3 border-b px-4 py-3 last:border-b-0 sm:border-r sm:border-b-0 sm:last:border-r-0"><span className="grid size-9 shrink-0 place-items-center rounded-lg bg-muted text-muted-foreground"><Icon className="size-4" /></span><div><p className="font-mono text-lg font-medium tabular-nums">{value}</p><p className="text-xs text-muted-foreground">{label}</p></div></div>;
}

function DetailFact({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return <div className="min-w-0 border-r border-b p-3 even:border-r-0 sm:border-b-0 sm:even:border-r sm:last:border-r-0"><dt className="text-xs font-medium text-muted-foreground">{label}</dt><dd className={cn("mt-1.5 break-words text-sm", mono && "font-mono text-xs")}>{value || "—"}</dd></div>;
}

function CodeValue({ label, value }: { label: string; value: string }) {
  return <div className="min-w-0"><p className="text-xs font-medium text-muted-foreground">{label}</p><code className="mt-1.5 block w-full max-w-full overflow-x-auto rounded-lg border bg-background p-3 text-[11px] leading-5 text-foreground">{value}</code></div>;
}

function DetectorBadges({ detectors }: { detectors: ControlTemplateRule["detector"][] }) {
  const { t } = useTranslation();
  return <div className="flex flex-wrap gap-1.5">{detectors.map((item) => <Badge key={item} variant="outline" className="font-normal">{t(`controlLibrary.detectors.${item}`)}</Badge>)}</div>;
}

function ActionBadge({ action }: { action: string }) {
  const { t } = useTranslation();
  const normalized = action.toUpperCase();
  return <Badge variant="outline" className={cn("font-normal", normalized === "MASK" && "border-amber-200 bg-amber-50 text-amber-700", normalized === "BLOCK" && "border-red-200 bg-red-50 text-red-700")}>{actionLabel(action, t)}</Badge>;
}

function SortableHeader({ label, sorted, onClick }: { label: string; sorted: false | "asc" | "desc"; onClick?: (event: unknown) => void }) {
  return <button type="button" className="-ml-2 inline-flex min-h-10 items-center gap-1 rounded-md px-2 text-left outline-none hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring" onClick={onClick}><span>{label}</span><ArrowUpDown className={cn("size-3.5 text-muted-foreground", sorted && "text-primary")} /></button>;
}

function columnClass(id: string) {
  if (id === "name") return "min-w-56 pl-4";
  if (id === "detectors") return "hidden md:table-cell";
  if (id === "phase") return "hidden xl:table-cell";
  if (id === "action" || id === "rules") return "hidden sm:table-cell";
  if (id === "packs") return "hidden lg:table-cell";
  if (id === "version") return "hidden 2xl:table-cell";
  if (id === "open") return "w-12 pr-3";
  return "";
}

function actionLabel(action: string, t: ReturnType<typeof useTranslation>["t"]) {
  const normalized = action.toUpperCase();
  if (normalized === "MASK") return t("controlLibrary.actions.mask");
  if (normalized === "BLOCK") return t("controlLibrary.actions.block");
  if (normalized === "POLICY") return t("controlLibrary.actions.policy");
  return action;
}
