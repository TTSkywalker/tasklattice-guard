import { useQuery } from "@tanstack/react-query";
import { Building2, Clock3 } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";

import { EmptyState, InfoNotice, PageHeader, StateBadge } from "@/components/product-shell";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { queryKeys } from "@/features/query-keys";
import { getDecisions, getSafes, getWorkloads, type DecisionEvent } from "@/lib/api";

export function ActivityPage() {
  const { t, i18n } = useTranslation();
  const query = useQuery({ queryKey: queryKeys.decisions, queryFn: () => getDecisions({ limit: 100 }), refetchInterval: 15_000 });
  const profiles = useQuery({ queryKey: queryKeys.safes, queryFn: getSafes }).data?.items ?? [];
  const workloads = useQuery({ queryKey: queryKeys.workloads, queryFn: getWorkloads }).data?.items ?? [];
  const activity = query.data?.items ?? [];
  const context = (item: DecisionEvent) => ({
    workload: workloads.find((candidate) => candidate.id === item.workload_id)?.name ?? t("activity.controlPlane"),
    profile: profiles.find((candidate) => candidate.id === item.safe_id)?.name,
  });

  return (
    <section className="py-6 sm:py-8">
      <PageHeader
        eyebrow={t("activity.eyebrow")}
        title={t("pages.activity.title")}
        description={t("activity.description")}
      />

      {activity.length ? (
        <>
          <div className="mt-5 space-y-3 md:hidden">
            {activity.map((item) => {
              const names = context(item);
              return (
                <article key={item.id} className="overflow-hidden rounded-lg border bg-card">
                  <div className="flex items-start justify-between gap-3 border-b bg-muted/40 p-4">
                    <div>
                      <strong className="text-sm font-medium">{activityLabel(item.kind, t)}</strong>
                      <time className="mt-1 flex items-center gap-2 font-mono text-xs text-muted-foreground"><Clock3 className="size-3.5" />{new Date(item.created_at).toLocaleString(i18n.language)}</time>
                    </div>
                    <StateBadge state={item.outcome} />
                  </div>
                  <div className="p-4">
                    <p className="flex items-center gap-2 text-xs"><Building2 className="size-3.5 text-primary" />{names.workload}</p>
                    {names.profile ? <p className="mt-1 pl-5 text-xs text-muted-foreground">{names.profile}</p> : null}
                    <p className="mt-3 text-xs leading-5 text-muted-foreground">{item.detail}</p>
                  </div>
                </article>
              );
            })}
          </div>

          <div className="mt-5 hidden overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-surface)] md:block">
            <Table>
              <TableHeader className="bg-muted/40"><TableRow className="hover:bg-muted/40"><TableHead className="w-[190px] px-4 text-xs">{t("activity.time")}</TableHead><TableHead className="w-[210px] px-4 text-xs">{t("activity.activity")}</TableHead><TableHead className="w-[220px] px-4 text-xs">{t("activity.context")}</TableHead><TableHead className="w-[120px] px-4 text-xs">{t("activity.outcome")}</TableHead><TableHead className="min-w-[280px] px-4 text-xs">{t("activity.evidence")}</TableHead></TableRow></TableHeader>
              <TableBody>{activity.map((item) => { const names = context(item); return <TableRow key={item.id}><TableCell className="px-4 py-4 align-top"><time className="flex items-center gap-2 font-mono text-xs text-muted-foreground"><Clock3 className="size-3.5" />{new Date(item.created_at).toLocaleString(i18n.language)}</time></TableCell><TableCell className="px-4 py-4 align-top"><strong className="text-xs font-medium">{activityLabel(item.kind, t)}</strong>{item.risk ? <p className="mt-1 text-xs capitalize text-muted-foreground">{item.risk.replaceAll("_", " ")}</p> : null}</TableCell><TableCell className="px-4 py-4 align-top text-xs"><p className="flex items-center gap-2"><Building2 className="size-3.5 text-primary" />{names.workload}</p>{names.profile ? <p className="mt-1 text-muted-foreground">{names.profile}</p> : null}</TableCell><TableCell className="px-4 py-4 align-top"><StateBadge state={item.outcome} /></TableCell><TableCell className="whitespace-normal px-4 py-4 align-top text-xs leading-5 text-muted-foreground">{item.detail}</TableCell></TableRow>; })}</TableBody>
            </Table>
          </div>
        </>
      ) : <div className="mt-5"><EmptyState title={t("activity.emptyTitle")} description={t("activity.emptyDescription")} /></div>}

      <div className="mt-5"><InfoNotice title={t("activity.privacyTitle")}>{t("activity.privacyDescription")}</InfoNotice></div>
    </section>
  );
}

function activityLabel(kind: string, t: TFunction) {
  const labels: Record<string, string> = {
    "profile.created": "activity.kinds.profileCreated",
    "profile.updated": "activity.kinds.profileUpdated",
    "profile.test_case.created": "activity.kinds.testCaseCreated",
    "profile.test_case.deleted": "activity.kinds.testCaseDeleted",
    "profile.test.completed": "activity.kinds.profileTestCompleted",
    "profile.tested": "activity.kinds.profileTested",
    "workload.protected": "activity.kinds.workloadProtected",
    "workload.updated": "activity.kinds.workloadUpdated",
    "gateway.registered": "activity.kinds.gatewayRegistered",
    "interaction.decision": "activity.kinds.interactionDecision",
    "system.seeded": "activity.kinds.systemSeeded",
  };
  return labels[kind] ? t(labels[kind]) : kind.replaceAll(".", " / ");
}
