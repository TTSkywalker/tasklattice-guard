import { Fragment, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Braces,
  ChevronDown,
  ChevronRight,
  FlaskConical,
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { queryKeys } from "@/features/query-keys";
import {
  getControls,
  type Control,
  type ControlRule,
  type NativeControl,
  type NativeRailType,
  type RulesControl,
  type RulesControlTestCase,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const EMPTY_CONTROLS: Control[] = [];
const RAILS: NativeRailType[] = ["input", "output", "retrieval", "dialog", "execution"];
const IMPLEMENTATIONS = ["colang", "regex", "keyword", "category"] as const;

type CatalogSource = "custom" | "built_in";
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
  rulesControl?: RulesControl;
};

export function ControlLibraryPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const controlsQuery = useQuery({ queryKey: queryKeys.controls, queryFn: getControls });
  const controls = controlsQuery.data?.items ?? EMPTY_CONTROLS;
  const [search, setSearch] = useState("");
  const [sources, setSources] = useState<Set<CatalogSource>>(new Set());
  const [rails, setRails] = useState<Set<NativeRailType>>(new Set());
  const [implementations, setImplementations] = useState<Set<CatalogImplementation>>(new Set());
  const [packs, setPacks] = useState<Set<string>>(new Set());
  const [selectedNativeId, setSelectedNativeId] = useState<string | null>(null);
  const [selectedRulesControl, setSelectedRulesControl] = useState<RulesControl | null>(null);
  const [studioControl, setStudioControl] = useState<NativeControl | null | undefined>(undefined);

  const items = useMemo(() => catalogItems(controls), [controls]);
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
  const loading = controlsQuery.isLoading;

  function clearFilters() {
    setSources(new Set());
    setRails(new Set());
    setImplementations(new Set());
    setPacks(new Set());
  }

  async function refresh(controlId?: string) {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.controls }),
      queryClient.invalidateQueries({ queryKey: queryKeys.nativeControls }),
    ]);
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

      {controlsQuery.error ? <div className="mt-5"><ErrorNotice error={controlsQuery.error} /></div> : null}

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
                    onOpen={() => item.native ? setSelectedNativeId(item.native.id) : setSelectedRulesControl(item.rulesControl ?? null)}
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
      <RulesControlDetail control={selectedRulesControl} onClose={() => setSelectedRulesControl(null)} />
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
        {(["custom", "built_in"] as const).map((source) => (
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
  const rulesControl = item.rulesControl;
  const Icon = item.source === "custom" ? Braces : native ? ShieldCheck : ListTree;

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
        {rulesControl ? (
          <>
            <div className="flex items-center justify-between gap-3 text-xs">
              <span className="font-medium">{t("controlLibrary.rulesCount", { count: rulesControl.rules.length })}</span>
              <span className="text-muted-foreground">{t("controlLibrary.testsCount", { count: rulesControl.test_count })}</span>
            </div>
            <RuleTeeth count={rulesControl.rules.length} />
            <p className="mt-2 font-mono text-[10px] text-muted-foreground">v{rulesControl.version}</p>
          </>
        ) : native ? (
          <div className="grid grid-cols-2 gap-2 rounded-lg bg-muted/35 p-3 text-xs">
            <div><span className="block text-[10px] text-muted-foreground">{t("controlLibrary.railBindings")}</span><strong className="mt-0.5 block font-mono font-medium">{native.draft.rail_bindings.length}</strong></div>
            <div><span className="block text-[10px] text-muted-foreground">{t("controlLibrary.revisionLabel")}</span><strong className="mt-0.5 block font-mono font-medium">r{native.draft_revision}</strong></div>
          </div>
        ) : null}

        <div className="mt-3 flex min-h-11 items-center justify-between gap-3 border-t pt-3">
          <span className="min-w-0 truncate text-[11px] text-muted-foreground">{rulesControl?.packs[0]?.name ?? native?.owner ?? t("controlLibrary.noPack")}</span>
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

function catalogItems(controls: Control[]): CatalogItem[] {
  const items = controls.map((control): CatalogItem => {
    if (control.implementation === "nemo_native") {
      const rails = [...new Set(control.draft.rail_bindings.map((binding) => binding.rail_type))];
      return {
        key: `nemo-native:${control.id}`,
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
    }
    return {
      key: `rules:${control.id}`,
      id: control.id,
      source: control.source,
      name: control.name,
      description: control.description,
      rails: control.phases,
      implementations: control.detector_types,
      packs: control.packs,
      searchText: [
        control.id,
        control.name,
        control.description,
        ...control.detector_types,
        ...control.packs.map((pack) => pack.name),
        ...control.rules.flatMap((rule) => [
          rule.id,
          rule.name,
          rule.description,
          ...rule.keywords.map((keyword) => keyword.value),
          ...rule.always_block.map((keyword) => keyword.value),
        ]),
        ...control.test_suites.flatMap((suite) => [
          suite.id,
          suite.name,
          suite.description,
          ...suite.cases.flatMap((testCase) => [testCase.id, testCase.name, testCase.description, testCase.content]),
        ]),
      ].join(" ").toLowerCase(),
      rulesControl: control,
    };
  });
  return items.sort((left, right) => {
    const sourceOrder: Record<CatalogSource, number> = { custom: 0, built_in: 1 };
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

export function RulesControlDetail({ control, onClose }: { control: RulesControl | null; onClose: () => void }) {
  const { t } = useTranslation();
  const [expandedRule, setExpandedRule] = useState<string | null>(null);

  useEffect(() => setExpandedRule(null), [control?.id]);

  return (
    <EntitySheet
      open={Boolean(control)}
      onOpenChange={(open) => { if (!open) onClose(); }}
      eyebrow={t("controlLibrary.auditEyebrow")}
      title={control?.name ?? t("controlLibrary.control")}
      description={control?.description ?? ""}
      width="xl"
      footer={<Button type="button" variant="outline" onClick={onClose}>{t("common.close")}</Button>}
    >
      {control ? (
        <div className="space-y-5">
          <section className="overflow-hidden rounded-xl border bg-card">
            <div className="flex flex-col gap-3 border-b px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0"><p className="text-xs font-medium text-muted-foreground">{t("controlLibrary.controlId")}</p><code className="mt-1 block truncate text-xs">{control.id}</code></div>
              <div className="flex flex-wrap gap-1.5"><Badge variant="outline">{t("controlLibrary.builtIn")}</Badge><Badge variant="outline" className="font-mono">v{control.version}</Badge></div>
            </div>
            <dl className="grid grid-cols-2 sm:grid-cols-4">
              <DetailFact label={t("controlLibrary.detector")} value={control.detector_types.map((item) => t(`controlLibrary.detectors.${item}`)).join(", ")} />
              <DetailFact label={t("controlLibrary.phase")} value={control.phases.map((item) => t(`controlLibrary.phases.${item}`)).join(", ")} />
              <DetailFact label={t("controlLibrary.defaultAction")} value={actionLabel(control.default_action, t)} />
              <DetailFact label={t("controlLibrary.ruleCount")} value={String(control.rules.length)} mono />
            </dl>
            <p className="border-t px-4 py-2.5 text-xs text-muted-foreground"><span className="font-medium text-foreground">{t("controlLibrary.source")}:</span> {t("controlLibrary.builtIn")}</p>
          </section>

          {control.packs.length ? (
            <section className="rounded-xl border bg-card p-4">
              <h3 className="text-sm font-medium">{t("controlLibrary.includedIn")}</h3>
              <div className="mt-3 flex flex-wrap gap-2">
                {control.packs.map((item) => <Badge key={item.id} variant="outline" className="h-auto whitespace-normal py-1"><PackageOpen />{item.name}</Badge>)}
              </div>
            </section>
          ) : null}

          <Tabs key={control.id} defaultValue="rules" className="gap-0 overflow-hidden rounded-xl border bg-card">
            <TabsList className="grid h-auto! w-full grid-cols-2 rounded-none border-b bg-muted/30 p-1" aria-label={t("controlLibrary.contractViews")}>
              <TabsTrigger value="rules" className="min-h-11 gap-2 px-3">
                <ListTree aria-hidden="true" />
                {t("controlLibrary.rulesCount", { count: control.rules.length })}
              </TabsTrigger>
              <TabsTrigger value="tests" className="min-h-11 gap-2 px-3">
                <FlaskConical aria-hidden="true" />
                {t("controlLibrary.testsCount", { count: control.test_count })}
              </TabsTrigger>
            </TabsList>

            <TabsContent value="rules" className="m-0">
              <div className="border-b bg-muted/15 px-4 py-3">
                <p className="text-xs leading-5 text-muted-foreground">{t("controlLibrary.rulesDescription")}</p>
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
                  {control.rules.map((rule) => {
                    const expanded = expandedRule === rule.id;
                    const acceptanceCases = control.test_suites.flatMap((suite) => suite.cases).filter((testCase) => testCase.covered_rule_ids.includes(rule.id));
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
                            <TableCell colSpan={4} className="max-w-0 min-w-0 bg-muted/20 p-4 whitespace-normal"><RuleImplementation rule={rule} tests={acceptanceCases} /></TableCell>
                          </TableRow>
                        ) : null}
                      </Fragment>
                    );
                  })}
                </TableBody>
              </Table>
            </TabsContent>

            <TabsContent value="tests" className="m-0">
              <ControlTestSuites control={control} />
            </TabsContent>
          </Tabs>

        </div>
      ) : null}
    </EntitySheet>
  );
}

function RuleImplementation({ rule, tests }: { rule: ControlRule; tests: RulesControlTestCase[] }) {
  const { t } = useTranslation();
  const acceptanceTests = tests.filter((testCase) => testCase.kind === "rule_acceptance");
  const scenarioCount = tests.length - acceptanceTests.length;
  const textLists = [
    ["identifiers", rule.identifiers],
    ["conditions", rule.conditions],
    ["exceptions", rule.exceptions],
    ["phrasePatterns", rule.phrase_patterns],
  ] as const;
  const keywordLists = [
    ["keywords", rule.keywords],
    ["alwaysBlock", rule.always_block],
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
      {textLists.some(([, values]) => values.length) || keywordLists.some(([, values]) => values.length) ? (
        <div className="grid gap-4 sm:grid-cols-2">
          {textLists.map(([key, values]) => values.length ? (
            <div key={key}>
              <p className="text-xs font-medium text-muted-foreground">{t(`controlLibrary.${key}`)}</p>
              <div className="mt-2 flex flex-wrap gap-1.5">{values.map((value) => <Badge key={value} variant="secondary" className="h-auto max-w-full whitespace-normal py-1 font-normal">{value}</Badge>)}</div>
            </div>
          ) : null)}
          {keywordLists.map(([key, values]) => values.length ? (
            <div key={key}>
              <p className="text-xs font-medium text-muted-foreground">{t(`controlLibrary.${key}`)}</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {values.map((keyword) => (
                  <Badge key={`${keyword.value}:${keyword.severity}`} variant="secondary" className="h-auto max-w-full gap-1.5 whitespace-normal py-1 font-normal">
                    <span>{keyword.value}</span>
                    <span className="font-mono text-[9px] uppercase text-muted-foreground">{keyword.severity}</span>
                  </Badge>
                ))}
              </div>
            </div>
          ) : null)}
        </div>
      ) : null}
      <div className="border-t pt-4">
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs font-medium text-muted-foreground">{t("controlLibrary.ruleAcceptance")}</p>
          <Badge variant="outline">{acceptanceTests.length}</Badge>
        </div>
        <div className="mt-3 grid gap-2">
          {acceptanceTests.map((testCase) => <TestCaseContract key={testCase.id} testCase={testCase} compact />)}
        </div>
        {scenarioCount ? <p className="mt-3 text-xs leading-5 text-muted-foreground">{t("controlLibrary.scenariosAlsoCover", { count: scenarioCount })}</p> : null}
      </div>
    </div>
  );
}

function ControlTestSuites({ control }: { control: RulesControl }) {
  const { t } = useTranslation();
  return (
    <div>
      <div className="border-b bg-muted/15 px-4 py-3">
        <h3 className="text-sm font-medium">{t("controlLibrary.acceptanceContract")}</h3>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">{t("controlLibrary.testsDescription")}</p>
      </div>
      <div className="border-b bg-primary/5 px-4 py-3 text-xs leading-5 text-muted-foreground">
        <span className="font-medium text-foreground">{t("controlLibrary.evaluationHandoffTitle")}</span>{" "}{t("controlLibrary.evaluationHandoff")}
      </div>
      <div className="divide-y">
        {control.test_suites.map((suite, index) => (
          <details key={suite.id} className="group" open={index === 0}>
            <summary className="flex min-h-14 cursor-pointer list-none items-center gap-3 px-4 py-3 focus-visible:outline-2 focus-visible:outline-ring [&::-webkit-details-marker]:hidden">
              <ChevronRight className="size-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-90" aria-hidden="true" />
              <span className="min-w-0 flex-1">
                <strong className="block text-sm font-medium">{suite.name}</strong>
                <span className="mt-0.5 block text-xs leading-5 text-muted-foreground">{suite.description}</span>
              </span>
              <Badge variant="secondary" className="shrink-0">{suite.cases.length}</Badge>
            </summary>
            <div className="grid gap-3 border-t bg-muted/15 p-3 sm:p-4">
              {suite.cases.map((testCase) => <TestCaseContract key={testCase.id} testCase={testCase} />)}
            </div>
          </details>
        ))}
      </div>
    </div>
  );
}

function TestCaseContract({ testCase, compact = false }: { testCase: RulesControlTestCase; compact?: boolean }) {
  const { t } = useTranslation();
  return (
    <article className="min-w-0 rounded-lg border bg-card p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <strong className="block text-sm font-medium">{testCase.name}</strong>
          <span className="mt-1 block font-mono text-[10px] text-muted-foreground">{testCase.id}</span>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <ExpectedDecisionBadge decision={testCase.expected_decision} />
          <Badge variant="outline" className="font-normal">{t(`controlLibrary.phases.${testCase.phase}`)}</Badge>
        </div>
      </div>
      {!compact ? <p className="mt-2 text-xs leading-5 text-muted-foreground">{testCase.description}</p> : null}
      <blockquote className="mt-3 break-words rounded-md border-l-2 border-primary/50 bg-muted/35 px-3 py-2 text-xs leading-5 text-foreground">{testCase.content}</blockquote>
      <dl className="mt-3 grid gap-2 text-xs sm:grid-cols-2">
        <div><dt className="text-muted-foreground">{t("controlLibrary.testKind")}</dt><dd className="mt-1 font-medium">{t(`controlLibrary.testKinds.${testCase.kind}`)}</dd></div>
        <div><dt className="text-muted-foreground">{t("controlLibrary.coveredRules")}</dt><dd className="mt-1 flex flex-wrap gap-1">{testCase.covered_rule_ids.map((ruleId) => <code key={ruleId} className="rounded bg-muted px-1.5 py-0.5 text-[10px]">{ruleId}</code>)}</dd></div>
      </dl>
      {testCase.parameter_names.length ? <p className="mt-3 text-[11px] leading-5 text-muted-foreground">{t("controlLibrary.parameterizedCase", { parameters: testCase.parameter_names.join(", ") })}</p> : null}
    </article>
  );
}

function ExpectedDecisionBadge({ decision }: { decision: RulesControlTestCase["expected_decision"] }) {
  const { t } = useTranslation();
  return (
    <Badge variant="outline" className={cn(
      "font-normal",
      decision === "allow" && "border-emerald-200 bg-emerald-50 text-emerald-700",
      decision === "block" && "border-red-200 bg-red-50 text-red-700",
      (decision === "transform" || decision === "intervene") && "border-amber-200 bg-amber-50 text-amber-700",
    )}>
      {t(`controlLibrary.expectedDecisions.${decision}`)}
    </Badge>
  );
}

function DetailFact({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return <div className="min-w-0 border-r border-b p-3 even:border-r-0 sm:border-b-0 sm:even:border-r sm:last:border-r-0"><dt className="text-xs font-medium text-muted-foreground">{label}</dt><dd className={cn("mt-1.5 break-words text-sm", mono && "font-mono text-xs")}>{value || "—"}</dd></div>;
}

function CodeValue({ label, value }: { label: string; value: string }) {
  return <div className="min-w-0"><p className="text-xs font-medium text-muted-foreground">{label}</p><code className="mt-1.5 block w-full max-w-full overflow-x-auto rounded-lg border bg-background p-3 text-[11px] leading-5 text-foreground">{value}</code></div>;
}

function DetectorBadges({ detectors }: { detectors: ControlRule["detector"][] }) {
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
