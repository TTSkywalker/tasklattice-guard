import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearch } from "@tanstack/react-router";
import {
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  FlaskConical,
  Plus,
  RotateCcw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Workflow,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import { PolicyStudioSheet } from "@/components/policy-studio";
import { EntitySheet } from "@/components/entity-sheet";
import { ErrorNotice, PageHeader } from "@/components/product-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { queryKeys } from "@/features/query-keys";
import { compactActionName } from "@/lib/action-name";
import { getPolicies, getPolicy, type ProgrammablePolicy, type Policy, type PolicyRule, type PolicyTag } from "@/lib/api";
import { cn } from "@/lib/utils";

const EMPTY_POLICIES: Policy[] = [];
const HIDDEN_POLICY_TAG_NAMESPACES = new Set(["engine"]);

export function PolicyLibraryPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const searchParams = useSearch({ strict: false }) as { policy?: string };
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: queryKeys.policies, queryFn: getPolicies });
  const policies = query.data?.items ?? EMPTY_POLICIES;
  const [search, setSearch] = useState("");
  const [selectedTags, setSelectedTags] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<Policy | null>(null);
  const [studioPolicy, setStudioPolicy] = useState<ProgrammablePolicy | null | undefined>(undefined);

  useEffect(() => {
    if (!searchParams.policy) {
      setSelected(null);
      return;
    }
    const policy = policies.find((item) => item.id === searchParams.policy);
    if (policy) setSelected(policy);
  }, [policies, searchParams.policy]);

  function openPolicy(policy: Policy) {
    setSelected(policy);
    navigate({ to: "/policy-library", search: { policy: policy.id }, replace: true });
  }

  function closePolicy() {
    setSelected(null);
    navigate({ to: "/policy-library", search: { policy: undefined }, replace: true });
  }

  const facets = useMemo(() => tagFacets(policies), [policies]);
  const filtered = useMemo(() => {
    const words = search.trim().toLocaleLowerCase();
    return policies.filter((policy) => {
      const ids = new Set(policy.tags.map((tag) => tag.id));
      if ([...selectedTags].some((tag) => !ids.has(tag))) return false;
      if (!words) return true;
      return policySearchText(policy).includes(words);
    });
  }, [policies, search, selectedTags]);

  async function refresh(policyId?: string) {
    await queryClient.invalidateQueries({ queryKey: queryKeys.policies });
    if (policyId) await queryClient.invalidateQueries({ queryKey: queryKeys.policy(policyId) });
  }

  return (
    <section className="py-6 sm:py-8">
      <PageHeader
        title={t("pages.policyLibrary.title")}
        description={t("pages.policyLibrary.description")}
        action={<Button size="lg" onClick={() => setStudioPolicy(null)}><Plus />{t("policyLibrary.newPolicy")}</Button>}
      />

      <div className="mt-6 flex flex-col gap-3 border-y py-4 sm:flex-row sm:items-center sm:justify-between">
        <label className="relative block w-full sm:max-w-xl">
          <span className="sr-only">{t("policyLibrary.searchCatalog")}</span>
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            className="min-h-11 bg-card pl-9"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder={t("policyLibrary.catalogSearchPlaceholder")}
          />
        </label>
        <p className="shrink-0 text-xs text-muted-foreground" aria-live="polite">
          {t("policyLibrary.catalogResults", { shown: filtered.length, total: policies.length })}
        </p>
      </div>

      {query.error ? <div className="mt-5"><ErrorNotice error={query.error} /></div> : null}
      {query.isLoading ? <CatalogSkeleton /> : (
        <div className="mt-5 grid min-w-0 gap-5 lg:grid-cols-[19rem_minmax(0,1fr)] lg:items-start">
          <aside className="sticky top-20 hidden max-h-[calc(100dvh-6rem)] overflow-y-auto border-r pr-5 lg:block" aria-label={t("policyLibrary.filters")}>
            <TagFilters facets={facets} selected={selectedTags} onChange={setSelectedTags} />
          </aside>

          <div className="min-w-0">
            <details className="mb-4 overflow-hidden rounded-xl border bg-card lg:hidden">
              <summary className="flex min-h-12 cursor-pointer list-none items-center gap-2 px-4 text-sm font-medium outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring [&::-webkit-details-marker]:hidden">
                <SlidersHorizontal className="size-4 text-primary" />
                <span>{t("policyLibrary.filters")}</span>
                {selectedTags.size ? <Badge className="ml-auto">{selectedTags.size}</Badge> : <span className="ml-auto text-xs font-normal text-muted-foreground">{t("policyLibrary.optional")}</span>}
                <ChevronDown className="size-4 text-muted-foreground" />
              </summary>
              <div className="border-t p-4"><TagFilters facets={facets} selected={selectedTags} onChange={setSelectedTags} /></div>
            </details>

            {filtered.length ? (
              <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3" aria-label={t("policyLibrary.catalogLabel")}>
                {filtered.map((policy) => <PolicyCard key={policy.id} policy={policy} onOpen={() => openPolicy(policy)} />)}
              </div>
            ) : (
              <div className="flex min-h-80 flex-col items-center justify-center rounded-xl border border-dashed bg-card px-6 text-center">
                <Workflow className="size-8 text-muted-foreground" />
                <h2 className="mt-3 text-sm font-semibold">{t("policyLibrary.noCatalogResults")}</h2>
                <p className="mt-1 max-w-md text-xs leading-5 text-muted-foreground">{t("policyLibrary.noCatalogResultsDescription")}</p>
                <Button className="mt-4" variant="outline" onClick={() => { setSearch(""); setSelectedTags(new Set()); }}><RotateCcw />{t("policyLibrary.resetCatalog")}</Button>
              </div>
            )}
          </div>
        </div>
      )}

      <PolicyDetail
        policy={selected}
        onClose={closePolicy}
        onEdit={(policy) => {
          closePolicy();
          setStudioPolicy(policy.implementation_detail);
        }}
      />
      <PolicyStudioSheet
        policy={studioPolicy}
        open={studioPolicy !== undefined}
        onOpenChange={(open) => { if (!open) setStudioPolicy(undefined); }}
        onSaved={async (policyId) => {
          await refresh(policyId);
          setStudioPolicy(undefined);
          const next = await queryClient.fetchQuery({ queryKey: queryKeys.policy(policyId), queryFn: () => getPolicy(policyId) });
          setSelected(next);
          navigate({ to: "/policy-library", search: { policy: policyId }, replace: true });
        }}
      />
    </section>
  );
}

function TagFilters({ facets, selected, onChange }: { facets: Map<string, PolicyTag[]>; selected: Set<string>; onChange: (next: Set<string>) => void }) {
  const { t } = useTranslation();
  const toggle = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onChange(next);
  };
  return (
    <div className="pb-4">
      <div className="flex min-h-11 items-center justify-between gap-3">
        <h2 className="text-base font-semibold">{t("policyLibrary.filters")}</h2>
        <Button size="sm" variant="ghost" className="min-h-11 px-2 text-muted-foreground shadow-none" disabled={!selected.size} onClick={() => onChange(new Set())}>{t("policyLibrary.clearFilters")}</Button>
      </div>
      {[...facets].map(([namespace, tags]) => (
        <details key={namespace} open className="group mt-5 border-t pt-4 first-of-type:mt-3 first-of-type:border-t-0 first-of-type:pt-1">
          <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-2 text-xs font-semibold outline-none focus-visible:ring-2 focus-visible:ring-ring [&::-webkit-details-marker]:hidden">
            {t(`policyLibrary.tagNamespaces.${namespace}`, { defaultValue: namespace })}<ChevronDown className="size-4 text-muted-foreground transition-transform group-open:rotate-180" />
          </summary>
          <div className="flex flex-wrap gap-2 pb-1">
            {tags.map((tag) => (
              <button
                key={tag.id}
                type="button"
                className={cn("inline-flex min-h-11 min-w-11 items-center rounded-lg bg-secondary px-3 text-left text-xs text-secondary-foreground outline-none hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring", selected.has(tag.id) && "bg-primary/10 text-primary ring-1 ring-primary/25")}
                aria-pressed={selected.has(tag.id)}
                onClick={() => toggle(tag.id)}
              >
                <span className="max-w-52 truncate">{tag.label}</span>
              </button>
            ))}
          </div>
        </details>
      ))}
    </div>
  );
}

function PolicyCard({ policy, onOpen }: { policy: Policy; onOpen: () => void }) {
  const { t } = useTranslation();
  return (
    <article className="group flex min-h-64 min-w-0 flex-col rounded-xl border bg-card p-4 shadow-xs transition-[border-color,box-shadow] hover:border-primary/30 hover:shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-lg border bg-muted/40 text-primary"><ShieldCheck className="size-4" /></span>
        <Badge variant="outline">{t(`policyLibrary.sourceLabels.${policy.source}`)}</Badge>
      </div>
      <div className="mt-4 min-w-0">
        <h3 className="truncate text-sm font-semibold">{policy.name}</h3>
        <p className="mt-1 line-clamp-2 min-h-10 text-xs leading-5 text-muted-foreground">{policy.description}</p>
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {visiblePolicyTags(policy.tags).filter((tag) => !["implementation", "stage"].includes(tag.namespace)).slice(0, 3).map((tag) => <Badge key={tag.id} variant="secondary" className="font-normal">{tag.label}</Badge>)}
      </div>
      <div className="mt-auto pt-5">
        <div className="grid grid-cols-2 gap-2 rounded-lg bg-muted/35 p-3 text-xs">
          <Metric label={t("policyLibrary.rules")} value={policy.rules.length} />
          <Metric label={t("policyLibrary.testCases")} value={policy.test_count} />
        </div>
        <div className="mt-3 flex min-h-11 items-center justify-between gap-3 border-t pt-3">
          <span className="font-mono text-xs text-muted-foreground">v{policy.version}</span>
          <Button size="sm" variant="ghost" className="min-h-11" onClick={onOpen}>{t("policyLibrary.inspectPolicy")}<ChevronRight /></Button>
        </div>
      </div>
    </article>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return <div><span className="block text-[10px] text-muted-foreground">{label}</span><strong className="mt-0.5 block font-mono font-medium">{value}</strong></div>;
}

export function PolicyDetail({ policy, onClose, onEdit }: { policy: Policy | null; onClose: () => void; onEdit: (policy: Policy) => void }) {
  const { t } = useTranslation();
  if (!policy) return null;
  return (
    <EntitySheet
      open
      onOpenChange={(open) => { if (!open) onClose(); }}
      eyebrow={t("policyLibrary.detailEyebrow")}
      title={policy.name}
      description={policy.description}
      width="xl"
      footer={policy.implementation === "nemo_native" ? <Button onClick={() => onEdit(policy)}>{t("policyLibrary.editPolicy")}</Button> : <Button variant="outline" onClick={onClose}>{t("common.close")}</Button>}
    >
      <div className="flex flex-wrap gap-2">
        {visiblePolicyTags(policy.tags).map((tag) => <Badge key={tag.id} variant={tag.source === "derived" ? "outline" : "secondary"}>{tag.label}</Badge>)}
      </div>
      <Tabs key={policy.id} defaultValue="policy" className="mt-5">
        <div className="overflow-x-auto">
          <TabsList aria-label={t("policyLibrary.detailViews")} className="min-w-max">
            <TabsTrigger value="policy">{t("policyLibrary.tabs.policy")}</TabsTrigger>
            <TabsTrigger value="validation">{t("policyLibrary.tabs.testCases")}</TabsTrigger>
            <TabsTrigger aria-label={t("policyLibrary.tabs.implementation")} value="implementation"><span aria-hidden className="sm:hidden">{t("policyLibrary.tabs.implementationShort")}</span><span aria-hidden className="hidden sm:inline">{t("policyLibrary.tabs.implementation")}</span></TabsTrigger>
          </TabsList>
        </div>
        <TabsContent value="policy" className="pt-3 sm:pt-4"><RuleList policy={policy} /></TabsContent>
        <TabsContent value="validation" className="pt-3 sm:pt-4"><PolicyTestCases policy={policy} /></TabsContent>
        <TabsContent value="implementation" className="pt-3 sm:pt-4"><Implementation policy={policy} /></TabsContent>
      </Tabs>
    </EntitySheet>
  );
}

function RuleList({ policy }: { policy: Policy }) {
  const { t } = useTranslation();
  return (
    <section>
      <h3 className="text-sm font-semibold">{t("policyLibrary.ruleListTitle", { count: policy.rules.length })}</h3>
      <p className="mt-1 text-xs leading-5 text-muted-foreground">{t("policyLibrary.ruleListDescription")}</p>
      <div className="mt-4 divide-y overflow-hidden rounded-lg border">
        {policy.rules.map((rule) => <RuleRow key={rule.id} rule={rule} />)}
      </div>
    </section>
  );
}

function RuleRow({ rule }: { rule: PolicyRule }) {
  const { t } = useTranslation();
  return (
    <details className="group bg-card">
      <summary className="flex min-h-14 cursor-pointer list-none items-center gap-3 px-4 py-3 outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring [&::-webkit-details-marker]:hidden">
        <CheckCircle2 className="size-4 shrink-0 text-primary" />
        <span className="min-w-0 flex-1"><strong className="block truncate text-sm font-medium">{rule.name}</strong><span className="mt-1 block truncate font-mono text-xs text-muted-foreground">{rule.id}</span></span>
        <Badge variant="outline">{t(`policyLibrary.effects.${rule.effect}`, { defaultValue: rule.effect })}</Badge>
        <ChevronDown className="size-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180" />
      </summary>
      <div className="border-t bg-muted/15 px-4 py-4 text-xs">
        <p className="leading-5 text-muted-foreground">{rule.description || t("policyLibrary.noRuleDescription")}</p>
        <dl className="mt-3 grid gap-3 sm:grid-cols-3">
          <Fact label={t("policyLibrary.ruleForm")} value={t(`policyLibrary.forms.${rule.form}`)} />
          <Fact label={t("policyLibrary.stagesLabel")} value={rule.stages.map((stage) => t(`policyLibrary.stages.${stage}`)).join(", ")} />
          <Fact label={t("policyLibrary.effectLabel")} value={t(`policyLibrary.effects.${rule.effect}`, { defaultValue: rule.effect })} />
        </dl>
      </div>
    </details>
  );
}

function PolicyTestCases({ policy }: { policy: Policy }) {
  const { t } = useTranslation();
  const ruleNames = new Map(policy.rules.map((rule) => [rule.id, rule.name]));
  const groups = Array.from(new Set(policy.test_cases.map((testCase) => testCase.group)));
  return (
    <section>
      <h3 className="text-sm font-semibold">{t("policyLibrary.testCasesTitle", { count: policy.test_count })}</h3>
      <p className="mt-1 text-xs leading-5 text-muted-foreground">{t("policyLibrary.testCasesDescription")}</p>
      <div className="mt-4 space-y-4">
        {groups.map((group) => (
          <section key={group} className="overflow-hidden rounded-lg border">
            <div className="border-b bg-muted/20 px-4 py-3"><h4 className="text-sm font-medium">{group}</h4></div>
            <div className="divide-y">
              {policy.test_cases.filter((testCase) => testCase.group === group).map((testCase) => (
                <details key={testCase.id} className="group bg-card">
                  <summary className="flex min-h-14 cursor-pointer list-none items-center gap-3 px-4 py-3 outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring [&::-webkit-details-marker]:hidden">
                    <FlaskConical className="size-4 shrink-0 text-primary" />
                    <span className="min-w-0 flex-1"><strong className="block truncate text-sm font-medium">{testCase.name}</strong><span className="mt-1 block text-[10px] text-muted-foreground">{t(`policyLibrary.testKinds.${testCase.kind}`)}</span></span>
                    <Badge variant="secondary">{t(`policyLibrary.expectedDecisions.${testCase.expected_decision}`)}</Badge>
                    <ChevronDown className="size-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180" />
                  </summary>
                  <div className="border-t bg-muted/15 px-4 py-4">
                    <pre className="whitespace-pre-wrap rounded-md border bg-background p-3 font-mono text-xs leading-5">{testCase.content}</pre>
                    <p className="mt-3 text-xs text-muted-foreground">{t("policyLibrary.coveredRules")}: {testCase.covered_rule_ids.map((id) => ruleNames.get(id) ?? id).join(", ")}</p>
                  </div>
                </details>
              ))}
            </div>
          </section>
        ))}
      </div>
    </section>
  );
}

function Implementation({ policy }: { policy: Policy }) {
  const { t } = useTranslation();
  return (
    <section>
      <h3 className="text-sm font-semibold">{t("policyLibrary.implementationTitle")}</h3>
      <p className="mt-1 text-xs leading-5 text-muted-foreground">{t("policyLibrary.implementationDescription")}</p>
      <dl className="mt-4 grid gap-3 rounded-lg border bg-muted/15 p-4 sm:grid-cols-2">
        <Fact label={t("policyLibrary.stagesLabel")} value={policy.stages.map((stage) => t(`policyLibrary.stages.${stage}`)).join(", ")} />
        <Fact label={t("policyLibrary.ruleForms")} value={policy.forms.map((form) => t(`policyLibrary.forms.${form}`)).join(", ")} />
      </dl>
      <div className="mt-4 divide-y overflow-hidden rounded-lg border">
        {policy.rules.map((rule) => (
          <div key={rule.id} className="grid gap-2 px-4 py-3 text-xs sm:grid-cols-[minmax(0,1fr)_10rem_12rem]">
            <div className="min-w-0"><strong className="block truncate font-medium">{rule.name}</strong><span className="mt-1 block truncate font-mono text-xs text-muted-foreground">{rule.implementation.binding_id}</span></div>
            <span className="font-mono text-muted-foreground">{rule.implementation.flow_name ?? rule.implementation.detector ?? rule.form}</span>
            {rule.implementation.action_name ? (
              <code className="truncate text-muted-foreground" title={rule.implementation.action_name}>{compactActionName(rule.implementation.action_name)}</code>
            ) : (
              <span className="truncate text-muted-foreground">{t("policyLibrary.runtimeManaged")}</span>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return <div><dt className="text-[10px] text-muted-foreground">{label}</dt><dd className="mt-1 text-xs font-medium">{value}</dd></div>;
}

function CatalogSkeleton() {
  return <div className="mt-5 grid gap-5 lg:grid-cols-[19rem_minmax(0,1fr)]"><Skeleton className="hidden h-[36rem] rounded-xl lg:block" /><div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">{Array.from({ length: 6 }, (_, index) => <Skeleton key={index} className="h-64 rounded-xl" />)}</div></div>;
}

function tagFacets(policies: Policy[]) {
  const facets = new Map<string, Map<string, PolicyTag>>();
  for (const policy of policies) {
    for (const tag of visiblePolicyTags(policy.tags)) {
      const values = facets.get(tag.namespace) ?? new Map<string, PolicyTag>();
      values.set(tag.id, tag);
      facets.set(tag.namespace, values);
    }
  }
  return new Map(
    [...facets]
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([namespace, values]) => [namespace, [...values.values()].sort((left, right) => left.label.localeCompare(right.label))]),
  );
}

function visiblePolicyTags(tags: PolicyTag[]) {
  return tags.filter((tag) => !HIDDEN_POLICY_TAG_NAMESPACES.has(tag.namespace));
}

function policySearchText(policy: Policy) {
  return [
    policy.id,
    policy.name,
    policy.description,
    ...visiblePolicyTags(policy.tags).flatMap((tag) => [tag.id, tag.label]),
    ...policy.rules.flatMap((rule) => [rule.id, rule.name, rule.description]),
    ...policy.test_cases.flatMap((testCase) => [testCase.group, testCase.name, testCase.content]),
  ].join(" ").toLocaleLowerCase();
}
