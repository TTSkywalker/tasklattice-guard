import { Fragment, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Braces,
  ChevronDown,
  ChevronRight,
  ListTree,
  PackageOpen,
  Plus,
  RotateCcw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Workflow,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import { ControlDetailSheet, ControlStudioSheet } from "@/components/native-control-studio";
import { EntitySheet } from "@/components/entity-sheet";
import { ErrorNotice, PageHeader } from "@/components/product-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { queryKeys } from "@/features/query-keys";
import {
  getControlTemplates,
  getNativeControls,
  type ControlTemplate,
  type ControlTemplateRule,
  type NativeControl,
  type NativeRailType,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const EMPTY_TEMPLATES: ControlTemplate[] = [];
const EMPTY_CONTROLS: NativeControl[] = [];
const RAILS: NativeRailType[] = ["input", "output", "retrieval", "dialog", "execution"];
const IMPLEMENTATIONS = ["colang", "regex", "keyword", "category"] as const;

type CatalogSource = "custom" | "built-in" | "template";
type CatalogImplementation = typeof IMPLEMENTATIONS[number];
type CatalogItem = {
  key: string;
  id: string;
  source: CatalogSource;
  name: string;
  description: string;
  rails: NativeRailType[];
  implementations: CatalogImplementation[];
  packs: Array<{ id: string; name: string }>;
  searchText: string;
  native?: NativeControl;
  template?: ControlTemplate;
};

export function ControlLibraryPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const nativeQuery = useQuery({ queryKey: queryKeys.nativeControls, queryFn: getNativeControls });
  const templateQuery = useQuery({ queryKey: queryKeys.controlTemplates, queryFn: getControlTemplates });
  const nativeControls = nativeQuery.data?.items ?? EMPTY_CONTROLS;
  const templates = templateQuery.data?.items ?? EMPTY_TEMPLATES;
  const [search, setSearch] = useState("");
  const [sources, setSources] = useState<Set<CatalogSource>>(new Set());
  const [rails, setRails] = useState<Set<NativeRailType>>(new Set());
  const [implementations, setImplementations] = useState<Set<CatalogImplementation>>(new Set());
  const [packs, setPacks] = useState<Set<string>>(new Set());
  const [selectedNativeId, setSelectedNativeId] = useState<string | null>(null);
  const [selectedTemplate, setSelectedTemplate] = useState<ControlTemplate | null>(null);
  const [studioControl, setStudioControl] = useState<NativeControl | null | undefined>(undefined);

  const items = useMemo(() => catalogItems(nativeControls, templates), [nativeControls, templates]);
  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    return items.filter((item) => {
      if (sources.size && !sources.has(item.source)) return false;
      if (rails.size && !item.rails.some((rail) => rails.has(rail))) return false;
      if (implementations.size && !item.implementations.some((implementation) => implementations.has(implementation))) return false;
      if (packs.size && !item.packs.some((pack) => packs.has(pack.id))) return false;
      return !query || item.searchText.includes(query);
    });
  }, [implementations, items, packs, rails, search, sources]);

  const activeFilterCount = sources.size + rails.size + implementations.size + packs.size;
  const loading = nativeQuery.isLoading || templateQuery.isLoading;

  function clearFilters() {
    setSources(new Set());
    setRails(new Set());
    setImplementations(new Set());
    setPacks(new Set());
  }

  async function refresh(controlId?: string) {
    await queryClient.invalidateQueries({ queryKey: queryKeys.nativeControls });
    if (controlId) await queryClient.invalidateQueries({ queryKey: queryKeys.nativeControl(controlId) });
  }

  const filterProps = {
    items,
    sources,
    rails,
    implementations,
    packs,
    activeFilterCount,
    onToggleSource: (value: CatalogSource) => setSources((current) => toggled(current, value)),
    onToggleRail: (value: NativeRailType) => setRails((current) => toggled(current, value)),
    onToggleImplementation: (value: CatalogImplementation) => setImplementations((current) => toggled(current, value)),
    onTogglePack: (value: string) => setPacks((current) => toggled(current, value)),
    onClear: clearFilters,
  };

  return (
    <section className="py-6 sm:py-8">
      <PageHeader
        title={t("pages.controlLibrary.title")}
        description={t("pages.controlLibrary.description")}
        action={<Button size="lg" onClick={() => setStudioControl(null)}><Plus />{t("controlStudio.newControl")}</Button>}
      />

      <div className="mt-6 flex flex-col gap-3 border-y py-4 sm:flex-row sm:items-center sm:justify-between">
        <label className="relative block w-full sm:max-w-xl">
          <span className="sr-only">{t("controlLibrary.searchCatalog")}</span>
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input className="min-h-11 bg-card pl-9" value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t("controlLibrary.catalogSearchPlaceholder")} />
        </label>
        <p className="shrink-0 text-xs text-muted-foreground" aria-live="polite">
          {t("controlLibrary.catalogResults", { shown: filtered.length, total: items.length })}
        </p>
      </div>

      {nativeQuery.error ? <div className="mt-5"><ErrorNotice error={nativeQuery.error} /></div> : null}
      {templateQuery.error ? <div className="mt-5"><ErrorNotice error={templateQuery.error} /></div> : null}

      {loading ? <CatalogSkeleton /> : (
        <div className="mt-5 grid min-w-0 gap-5 lg:grid-cols-[19rem_minmax(0,1fr)] lg:items-start">
          <aside className="sticky top-20 hidden max-h-[calc(100dvh-6rem)] overflow-y-auto border-r pr-5 lg:block" aria-label={t("controlLibrary.filters")}>
            <FacetFilters {...filterProps} />
          </aside>

          <div className="min-w-0">
            <details className="mb-4 overflow-hidden rounded-xl border bg-card lg:hidden">
              <summary className="flex min-h-12 cursor-pointer list-none items-center gap-2 px-4 text-sm font-medium outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring [&::-webkit-details-marker]:hidden">
                <SlidersHorizontal className="size-4 text-primary" />
                <span>{t("controlLibrary.filters")}</span>
                {activeFilterCount ? <Badge className="ml-auto">{activeFilterCount}</Badge> : <span className="ml-auto text-xs font-normal text-muted-foreground">{t("controlLibrary.optional")}</span>}
                <ChevronDown className="size-4 text-muted-foreground" />
              </summary>
              <div className="border-t"><FacetFilters {...filterProps} compact /></div>
            </details>

            {filtered.length ? (
              <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3" aria-label={t("controlLibrary.catalogLabel")}>
                {filtered.map((item) => (
                  <ControlCatalogCard
                    key={item.key}
                    item={item}
                    onOpen={() => item.native ? setSelectedNativeId(item.native.id) : setSelectedTemplate(item.template ?? null)}
                  />
                ))}
              </div>
            ) : (
              <div className="flex min-h-80 flex-col items-center justify-center rounded-xl border border-dashed bg-card px-6 text-center">
                <Workflow className="size-8 text-muted-foreground" />
                <h2 className="mt-3 text-sm font-semibold">{t("controlLibrary.noCatalogResults")}</h2>
                <p className="mt-1 max-w-md text-xs leading-5 text-muted-foreground">{t("controlLibrary.noCatalogResultsDescription")}</p>
                <Button className="mt-4" variant="outline" onClick={() => { setSearch(""); clearFilters(); }}><RotateCcw />{t("controlLibrary.resetCatalog")}</Button>
              </div>
            )}
          </div>
        </div>
      )}

      <ControlDetailSheet
        controlId={selectedNativeId}
        onClose={() => setSelectedNativeId(null)}
        onEdit={(control) => { setSelectedNativeId(null); setStudioControl(control); }}
      />
      <ControlTemplateDetail template={selectedTemplate} onClose={() => setSelectedTemplate(null)} />
      <ControlStudioSheet
        control={studioControl}
        open={studioControl !== undefined}
        onOpenChange={(open) => { if (!open) setStudioControl(undefined); }}
        onSaved={async (controlId) => { await refresh(controlId); setStudioControl(undefined); setSelectedNativeId(controlId); }}
      />
    </section>
  );
}

function FacetFilters({
  items,
  sources,
  rails,
  implementations,
  packs,
  activeFilterCount,
  onToggleSource,
  onToggleRail,
  onToggleImplementation,
  onTogglePack,
  onClear,
  compact = false,
}: {
  items: CatalogItem[];
  sources: Set<CatalogSource>;
  rails: Set<NativeRailType>;
  implementations: Set<CatalogImplementation>;
  packs: Set<string>;
  activeFilterCount: number;
  onToggleSource: (value: CatalogSource) => void;
  onToggleRail: (value: NativeRailType) => void;
  onToggleImplementation: (value: CatalogImplementation) => void;
  onTogglePack: (value: string) => void;
  onClear: () => void;
  compact?: boolean;
}) {
  const { t } = useTranslation();
  const packOptions = useMemo(() => {
    const values = new Map<string, string>();
    for (const item of items) for (const pack of item.packs) values.set(pack.id, pack.name);
    return [...values].sort((left, right) => left[1].localeCompare(right[1]));
  }, [items]);

  return (
    <div className={cn(!compact && "pb-4", compact && "p-4")}>
      <div className="flex min-h-11 items-center justify-between gap-3">
        <h2 className="text-base font-semibold">{t("controlLibrary.filters")}</h2>
        <Button size="sm" variant="ghost" className="px-2 text-muted-foreground shadow-none" disabled={!activeFilterCount} onClick={onClear}>{t("controlLibrary.clearFilters")}</Button>
      </div>

      <FilterGroup title={t("controlLibrary.filterGroups.source")}>
        {(["custom", "built-in", "template"] as const).map((source) => (
          <FilterOption
            key={source}
            label={t(`controlLibrary.sourceLabels.${source}`)}
            count={items.filter((item) => item.source === source).length}
            selected={sources.has(source)}
            onClick={() => onToggleSource(source)}
          />
        ))}
      </FilterGroup>

      <FilterGroup title={t("controlLibrary.filterGroups.rail")}>
        {RAILS.map((rail) => (
          <FilterOption
            key={rail}
            label={t(`controlStudio.railNames.${rail}`)}
            count={items.filter((item) => item.rails.includes(rail)).length}
            selected={rails.has(rail)}
            onClick={() => onToggleRail(rail)}
          />
        ))}
      </FilterGroup>

      <FilterGroup title={t("controlLibrary.filterGroups.implementation")}>
        {IMPLEMENTATIONS.map((implementation) => (
          <FilterOption
            key={implementation}
            label={t(`controlLibrary.implementations.${implementation}`)}
            count={items.filter((item) => item.implementations.includes(implementation)).length}
            selected={implementations.has(implementation)}
            onClick={() => onToggleImplementation(implementation)}
          />
        ))}
      </FilterGroup>

      {packOptions.length ? (
        <FilterGroup title={t("controlLibrary.filterGroups.pack")}>
          {packOptions.map(([id, name]) => (
            <FilterOption
              key={id}
              label={name}
              count={items.filter((item) => item.packs.some((pack) => pack.id === id)).length}
              selected={packs.has(id)}
              onClick={() => onTogglePack(id)}
            />
          ))}
        </FilterGroup>
      ) : null}
    </div>
  );
}

function FilterGroup({ title, children }: { title: string; children: ReactNode }) {
  return (
    <details open className="group mt-5 border-t pt-4 first-of-type:mt-3 first-of-type:border-t-0 first-of-type:pt-1">
      <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-2 text-xs font-semibold outline-none focus-visible:ring-2 focus-visible:ring-ring [&::-webkit-details-marker]:hidden">
        {title}<ChevronDown className="size-4 text-muted-foreground transition-transform group-open:rotate-180" />
      </summary>
      <div className="flex flex-wrap gap-2 pb-1">{children}</div>
    </details>
  );
}

function FilterOption({ label, count, selected, onClick }: { label: string; count: number; selected: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      className={cn(
        "inline-flex min-h-11 min-w-0 flex-none items-center gap-2 rounded-lg bg-secondary px-3 text-left text-xs text-secondary-foreground outline-none transition-colors hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring",
        selected && "bg-primary/10 text-primary ring-1 ring-primary/25",
      )}
      aria-pressed={selected}
      onClick={onClick}
    >
      <span className="min-w-0 max-w-52 truncate">{label}</span>
      <span className="font-mono text-[10px] text-muted-foreground tabular-nums">{count}</span>
    </button>
  );
}

function ControlCatalogCard({ item, onOpen }: { item: CatalogItem; onOpen: () => void }) {
  const { t } = useTranslation();
  const native = item.native;
  const template = item.template;
  const Icon = item.source === "custom" ? Braces : item.source === "built-in" ? ShieldCheck : ListTree;

  return (
    <article className="group flex min-h-64 min-w-0 flex-col rounded-xl border bg-card p-4 shadow-xs transition-[border-color,box-shadow] hover:border-primary/30 hover:shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-lg border bg-muted/40 text-primary"><Icon className="size-4" /></span>
        <Badge variant="outline" className="max-w-[10rem] truncate">{t(`controlLibrary.sourceLabels.${item.source}`)}</Badge>
      </div>

      <div className="mt-4 min-w-0">
        <h3 className="truncate text-sm font-semibold">{item.name}</h3>
        <p className="mt-1 line-clamp-2 min-h-10 text-xs leading-5 text-muted-foreground">{item.description || t("controlStudio.noDescription")}</p>
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5">
        {item.rails.slice(0, 3).map((rail) => <Badge key={rail} variant="secondary" className="font-normal">{t(`controlStudio.railNames.${rail}`)}</Badge>)}
        {item.rails.length > 3 ? <Badge variant="secondary" className="font-normal">+{item.rails.length - 3}</Badge> : null}
        {item.implementations.slice(0, 2).map((implementation) => <Badge key={implementation} variant="outline" className="font-normal">{t(`controlLibrary.implementations.${implementation}`)}</Badge>)}
      </div>

      <div className="mt-auto pt-5">
        {template ? (
          <>
            <div className="flex items-center justify-between gap-3 text-xs">
              <span className="font-medium">{t("controlLibrary.rulesCount", { count: template.rules.length })}</span>
              <span className="font-mono text-[11px] text-muted-foreground">v{template.version}</span>
            </div>
            <RuleTeeth count={template.rules.length} />
          </>
        ) : native ? (
          <div className="grid grid-cols-2 gap-2 rounded-lg bg-muted/35 p-3 text-xs">
            <div><span className="block text-[10px] text-muted-foreground">{t("controlLibrary.railBindings")}</span><strong className="mt-0.5 block font-mono font-medium">{native.draft.rail_bindings.length}</strong></div>
            <div><span className="block text-[10px] text-muted-foreground">{t("controlLibrary.revisionLabel")}</span><strong className="mt-0.5 block font-mono font-medium">r{native.draft_revision}</strong></div>
          </div>
        ) : null}

        <div className="mt-3 flex min-h-11 items-center justify-between gap-3 border-t pt-3">
          <span className="min-w-0 truncate text-[11px] text-muted-foreground">{template?.packs[0]?.name ?? native?.owner ?? t("controlLibrary.noPack")}</span>
          <Button size="sm" variant="ghost" onClick={onOpen}>{t("controlLibrary.details")}<ChevronRight /></Button>
        </div>
      </div>
    </article>
  );
}

function CatalogSkeleton() {
  return (
    <div className="mt-5 grid gap-5 lg:grid-cols-[19rem_minmax(0,1fr)]">
      <Skeleton className="hidden h-[36rem] rounded-xl lg:block" />
      <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">{Array.from({ length: 6 }, (_, index) => <Skeleton key={index} className="h-64 rounded-xl" />)}</div>
    </div>
  );
}

function catalogItems(nativeControls: NativeControl[], templates: ControlTemplate[]): CatalogItem[] {
  const nativeItems = nativeControls.map((control): CatalogItem => {
    const rails = [...new Set(control.draft.rail_bindings.map((binding) => binding.rail_type))];
    return {
      key: `native:${control.id}`,
      id: control.id,
      source: control.source,
      name: control.name,
      description: control.description,
      rails,
      implementations: ["colang"],
      packs: [],
      searchText: [control.id, control.name, control.description, control.owner, ...rails, ...control.draft.action_references.map((action) => action.name)].join(" ").toLowerCase(),
      native: control,
    };
  });
  const templateItems = templates.map((template): CatalogItem => ({
    key: `template:${template.id}`,
    id: template.id,
    source: "template",
    name: template.name,
    description: template.description,
    rails: template.phases,
    implementations: template.detector_types,
    packs: template.packs.map(({ id, name }) => ({ id, name })),
    searchText: [template.id, template.name, template.description, ...template.tags, ...template.detector_types, ...template.packs.flatMap((pack) => [pack.name, pack.domain]), ...template.rules.flatMap((rule) => [rule.id, rule.name, rule.description])].join(" ").toLowerCase(),
    template,
  }));
  return [...nativeItems, ...templateItems].sort((left, right) => {
    const sourceOrder: Record<CatalogSource, number> = { custom: 0, "built-in": 1, template: 2 };
    return sourceOrder[left.source] - sourceOrder[right.source] || left.name.localeCompare(right.name);
  });
}

function toggled<T>(current: Set<T>, value: T) {
  const next = new Set(current);
  if (next.has(value)) next.delete(value);
  else next.add(value);
  return next;
}

function RuleTeeth({ count }: { count: number }) {
  const { t } = useTranslation();
  const visible = Math.min(count, 8);
  return (
    <div className="mt-2 flex items-center gap-1" aria-label={t("controlLibrary.rulesCount", { count })}>
      {Array.from({ length: visible }, (_, index) => <span key={index} className="h-2.5 flex-1 rounded-[2px] bg-primary/65" />)}
      {count > visible ? <span className="ml-1 shrink-0 font-mono text-[10px] text-muted-foreground">+{count - visible}</span> : null}
      {!count ? <span className="text-[11px] text-muted-foreground">0</span> : null}
    </div>
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

function actionLabel(action: string, t: ReturnType<typeof useTranslation>["t"]) {
  const normalized = action.toUpperCase();
  if (normalized === "MASK") return t("controlLibrary.actions.mask");
  if (normalized === "BLOCK") return t("controlLibrary.actions.block");
  if (normalized === "POLICY") return t("controlLibrary.actions.policy");
  return action;
}
