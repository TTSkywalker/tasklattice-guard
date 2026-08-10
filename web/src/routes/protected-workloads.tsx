import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ListFilter, Plus, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";

import { EntitySheet } from "@/components/entity-sheet";
import { EmptyState, ErrorNotice, InfoNotice, PageHeader, StateBadge } from "@/components/product-shell";
import {
  countTrafficRules,
  createTrafficFilterQuery,
  isTrafficFilterValid,
  toWorkloadFilterExpression,
  TrafficFilterBuilder,
  type TrafficFilterQuery,
} from "@/components/traffic-filter";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { queryKeys } from "@/features/query-keys";
import {
  createWorkload,
  getSafes,
  getWorkloadFilterFields,
  getWorkloads,
  setWorkloadEnabled,
  type Safe,
  type Workload,
  type WorkloadFilterExpression,
  type WorkloadFilterRule,
} from "@/lib/api";

export function ProtectedWorkloadsPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const workloadsQuery = useQuery({ queryKey: queryKeys.workloads, queryFn: getWorkloads });
  const safesQuery = useQuery({ queryKey: queryKeys.safes, queryFn: getSafes });
  const [createOpen, setCreateOpen] = useState(false);
  const workloads = workloadsQuery.data?.items ?? [];
  const safes = safesQuery.data?.items ?? [];
  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.workloads }),
      queryClient.invalidateQueries({ queryKey: queryKeys.safes }),
      queryClient.invalidateQueries({ queryKey: queryKeys.metrics }),
    ]);
  };
  const toggle = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) => setWorkloadEnabled(id, enabled),
    onSuccess: refresh,
    onError: (error) => notifyError(error, t("workloads.operationFailed")),
  });

  return (
    <section className="py-6 sm:py-8">
      <PageHeader
        eyebrow={t("pages.workloads.eyebrow")}
        title={t("pages.workloads.title")}
        description={t("pages.workloads.description")}
        action={<Button className="min-h-11 self-start" onClick={() => setCreateOpen(true)}><Plus />{t("pages.workloads.add")}</Button>}
      />

      {workloadsQuery.error ? <div className="mt-5"><ErrorNotice error={workloadsQuery.error} /></div> : null}
      {workloadsQuery.isLoading ? <Skeleton className="mt-5 h-52 rounded-lg" /> : null}

      {workloads.length ? (
        <>
          <div className="mt-5 flex min-h-14 items-center gap-3 rounded-lg border bg-card px-4 py-3">
            <ListFilter className="size-4 text-primary" />
            <div><p className="text-sm font-medium">{t("workloads.filterRule")}</p><p className="mt-0.5 text-xs text-muted-foreground">{t("workloads.filterRuleDescription")}</p></div>
          </div>
          <section className="mt-4 surface">
            <div className="hidden grid-cols-[minmax(210px,1.1fr)_minmax(320px,1.8fr)_minmax(155px,.8fr)_132px] border-b bg-muted/40 px-5 py-3 text-xs font-medium text-muted-foreground lg:grid">
              <span>{t("workloads.workload")}</span><span>{t("workloads.trafficFilter")}</span><span>{t("workloads.profile")}</span><span>{t("common.status")}</span>
            </div>
            <div className="divide-y divide-border">
              {workloads.map((workload) => (
                <WorkloadRow
                  key={workload.id}
                  workload={workload}
                  safe={safes.find((item) => item.id === workload.safe_id)}
                  onToggle={(enabled) => toggle.mutate({ id: workload.id, enabled })}
                />
              ))}
            </div>
          </section>
        </>
      ) : !workloadsQuery.isLoading ? (
        <div className="mt-5">
          <EmptyState
            title={t("workloads.emptyTitle")}
            description={t("workloads.emptyDescription")}
            action={<Button onClick={() => setCreateOpen(true)}><ShieldCheck />{t("workloads.protectFirst")}</Button>}
          />
        </div>
      ) : null}

      <CreateWorkloadSheet
        open={createOpen}
        onOpenChange={setCreateOpen}
        safes={safes}
        onCreated={async () => { setCreateOpen(false); await refresh(); }}
      />
    </section>
  );
}

function WorkloadRow({ workload, safe, onToggle }: { workload: Workload; safe?: Safe; onToggle: (enabled: boolean) => void }) {
  const { t } = useTranslation();
  return (
    <article className="grid gap-4 p-5 lg:grid-cols-[minmax(210px,1.1fr)_minmax(320px,1.8fr)_minmax(155px,.8fr)_132px] lg:items-center">
      <div>
        <div className="flex items-center gap-2"><ListFilter className="size-4 text-primary" /><strong className="text-sm font-medium">{workload.name}</strong></div>
        <p className="mt-2 text-xs text-muted-foreground">{countTrafficRules(workload.filter) ? t("workloads.conditionCount", { count: countTrafficRules(workload.filter) }) : t("workloads.allTraffic")}</p>
      </div>
      <WorkloadFilterBadges workload={workload} />
      <div><p className="text-xs font-medium">{safe?.name ?? workload.safe_id}</p><p className="mt-1 text-xs text-muted-foreground">{t(safe?.status === "needs_testing" ? "workloads.deployedVersion" : "workloads.currentVersion")}</p></div>
      <div className="flex items-center justify-between gap-3 lg:justify-start">
        <StateBadge state={workload.enabled ? "protected" : "paused"} />
        <Switch aria-label={`${t(workload.enabled ? "workloads.pause" : "workloads.enable")} ${workload.name}`} checked={workload.enabled} onCheckedChange={onToggle} />
      </div>
    </article>
  );
}

export function WorkloadFilterBadges({ workload }: { workload: Workload }) {
  const { t } = useTranslation();
  if (!workload.filter.rules.length) {
    return <span className="text-xs font-medium text-amber-700">{t("workloads.allTraffic")}</span>;
  }
  return (
    <FilterExpressionSummary expression={workload.filter} />
  );
}

function FilterExpressionSummary({ expression }: { expression: WorkloadFilterExpression }) {
  const { t } = useTranslation();
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-1.5">
      {expression.rules.map((item, index) => (
        <div key={isFilterGroup(item) ? `group-${index}` : `${item.field}:${item.key ?? ""}:${index}`} className="contents">
          {index ? <span className="text-[10px] font-semibold text-muted-foreground">{expression.combinator.toUpperCase()}</span> : null}
          {isFilterGroup(item) ? (
            <span className="inline-flex max-w-full items-center gap-1 rounded-md border bg-muted/20 p-1"><FilterExpressionSummary expression={item} /></span>
          ) : (
            <span className="max-w-full rounded-md border bg-muted/40 px-2 py-1 font-mono text-[11px] text-foreground">
              <span className="text-muted-foreground">{filterKeyLabel(t, item)} {operatorLabel(t, item.operator)} </span><span className="break-all">{item.value}</span>
            </span>
          )}
        </div>
      ))}
    </div>
  );
}

export function CreateWorkloadSheet({
  open,
  onOpenChange,
  safes,
  onCreated,
  initialSafeId,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  safes: Safe[];
  onCreated: () => void;
  initialSafeId?: string;
}) {
  const { t } = useTranslation();
  const fieldQuery = useQuery({ queryKey: queryKeys.workloadFilterFields, queryFn: getWorkloadFilterFields, enabled: open });
  const definitions = fieldQuery.data?.items ?? [];
  const ready = useMemo(() => safes.filter((item) => item.tested_current), [safes]);
  const [name, setName] = useState("");
  const [safeId, setSafeId] = useState("");
  const [matchAll, setMatchAll] = useState(false);
  const [filterQuery, setFilterQuery] = useState<TrafficFilterQuery>({ combinator: "and", rules: [] });
  useEffect(() => {
    if (!open) return;
    setName("");
    setSafeId(ready.some((item) => item.id === initialSafeId) ? initialSafeId ?? "" : ready[0]?.id ?? "");
    setMatchAll(false);
    setFilterQuery(createTrafficFilterQuery(definitions));
  }, [definitions, initialSafeId, open, ready]);

  const payloadFilter = matchAll
    ? { combinator: "and" as const, rules: [] }
    : toWorkloadFilterExpression(filterQuery, definitions);
  const filterValid = isTrafficFilterValid(filterQuery, definitions, matchAll);
  const selectedSafe = ready.find((item) => item.id === safeId);
  const mutation = useMutation({
    mutationFn: () => createWorkload({ name, safe_id: safeId, filter: payloadFilter, enabled: true }),
    onSuccess: () => { toast.success(t("workloads.protected")); onCreated(); },
    onError: (error) => notifyError(error, t("workloads.operationFailed")),
  });

  return (
    <EntitySheet
      open={open}
      onOpenChange={onOpenChange}
      eyebrow={t("workloads.sheetEyebrow")}
      title={t("workloads.sheetTitle")}
      description={t("workloads.sheetDescription")}
      width="xl"
      footer={<><Button variant="outline" onClick={() => onOpenChange(false)}>{t("common.cancel")}</Button><Button disabled={!name.trim() || !safeId || !filterValid || mutation.isPending} onClick={() => mutation.mutate()}><ShieldCheck />{t(mutation.isPending ? "workloads.enabling" : "workloads.enableProtection")}</Button></>}
    >
      {!ready.length ? (
        <EmptyState title={t("workloads.noTestedTitle")} description={t("workloads.noTestedDescription")} />
      ) : (
        <div className="grid gap-7">
          <FormSection number="1" title={t("workloads.trafficCharacteristics")} description={t("workloads.trafficCharacteristicsDescription")}>
            <Field label={t("workloads.workloadName")} hint={t("workloads.workloadNameHint")}><Input autoFocus className="min-h-11 rounded-lg bg-card" value={name} onChange={(event) => setName(event.target.value)} placeholder="Finance Knowledge Agent" /></Field>
            {fieldQuery.isLoading ? <Skeleton className="h-72 rounded-lg" /> : null}
            {fieldQuery.error ? <ErrorNotice error={fieldQuery.error} /> : null}
            {definitions.length ? <TrafficFilterBuilder definitions={definitions} query={filterQuery} matchAll={matchAll} onQueryChange={setFilterQuery} onMatchAllChange={setMatchAll} /> : null}
            <InfoNotice title={t("workloads.filterTrustTitle")}>{t("workloads.filterTrustDescription")}</InfoNotice>
          </FormSection>

          <FormSection number="2" title={t("workloads.applySafe")} description={t("workloads.applySafeDescription")}>
            <Field label={t("workloads.profile")}>
              <Select disabled={Boolean(initialSafeId)} value={safeId} onValueChange={setSafeId}><SelectTrigger className="min-h-11 rounded-lg bg-card"><SelectValue /></SelectTrigger><SelectContent className="rounded-lg">{ready.map((item) => <SelectItem key={item.id} value={item.id}>{item.name}</SelectItem>)}</SelectContent></Select>
            </Field>
            {selectedSafe ? (
              <div className="grid gap-3 rounded-lg border bg-muted/25 p-4 sm:grid-cols-3">
                <SafeFact label={t("workloads.selectedSafe")} value={selectedSafe.name} />
                <SafeFact label={t("profiles.protections")} value={t("profiles.protectionCount", { count: selectedSafe.protections.length })} />
                <SafeFact label={t("profiles.testEvidence")} value={t("profiles.testCount", { count: selectedSafe.test_case_count })} />
              </div>
            ) : null}
          </FormSection>
        </div>
      )}
    </EntitySheet>
  );
}

function FormSection({ number, title, description, children }: { number: string; title: string; description: string; children: React.ReactNode }) {
  return (
    <section className="grid gap-4">
      <div className="flex items-start gap-3">
        <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">{number}</span>
        <div><h3 className="text-base font-semibold">{title}</h3><p className="mt-1 text-xs leading-5 text-muted-foreground">{description}</p></div>
      </div>
      <div className="grid gap-4 pl-0 sm:pl-10">{children}</div>
    </section>
  );
}

function SafeFact({ label, value }: { label: string; value: string }) {
  return <div><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 text-sm font-medium">{value}</p></div>;
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return <label className="grid gap-2 text-sm font-medium">{label}{children}{hint ? <span className="text-xs font-normal leading-5 text-muted-foreground">{hint}</span> : null}</label>;
}

function isFilterGroup(item: WorkloadFilterRule | WorkloadFilterExpression): item is WorkloadFilterExpression {
  return "rules" in item;
}

function filterKeyLabel(t: (key: string) => string, condition: WorkloadFilterRule) {
  const translated = t(`workloads.filterFields.${condition.field.replaceAll(".", "_")}`);
  return condition.key ? `${translated}:${condition.key}` : translated;
}

function operatorLabel(t: (key: string) => string, operator: WorkloadFilterRule["operator"]) {
  return t(`workloads.filterOperators.${operator}`);
}

function notifyError(error: unknown, fallback: string) { toast.error(error instanceof Error ? error.message : fallback); }
