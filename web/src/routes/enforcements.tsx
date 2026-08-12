import { useQuery } from "@tanstack/react-query";
import { LockKeyhole, Route, ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";

import { ErrorNotice, InfoNotice, PageHeader, StateBadge } from "@/components/product-shell";
import { Skeleton } from "@/components/ui/skeleton";
import { queryKeys } from "@/features/query-keys";
import { getAssignments, getGuardrails } from "@/lib/api";

export function EnforcementsPage() {
  const { t } = useTranslation();
  const guardrailsQuery = useQuery({ queryKey: queryKeys.guardrails, queryFn: getGuardrails });
  const assignmentsQuery = useQuery({ queryKey: queryKeys.assignments, queryFn: getAssignments });
  const error = guardrailsQuery.error || assignmentsQuery.error;
  const defaultGuardrail = guardrailsQuery.data?.items.find((item) => item.is_default);
  const defaultAssignment = assignmentsQuery.data?.items.find((item) => item.is_default);

  return (
    <section className="py-6 sm:py-8">
      <PageHeader
        title={t("enforcements.title")}
        description={t("enforcements.description")}
      />

      {error ? <div className="mt-5"><ErrorNotice error={error} /></div> : null}
      {guardrailsQuery.isLoading || assignmentsQuery.isLoading ? <Skeleton className="mt-5 h-72 rounded-xl" /> : null}

      {defaultGuardrail && defaultAssignment ? (
        <div className="mt-5 overflow-hidden rounded-xl border bg-card shadow-xs">
          <div className="flex flex-col gap-4 border-b bg-muted/25 p-5 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex min-w-0 items-start gap-3">
              <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary"><LockKeyhole className="size-5" /></span>
              <div className="min-w-0">
                <h2 className="text-base font-semibold">{t("enforcements.defaultTitle")}</h2>
                <p className="mt-1 text-sm leading-6 text-muted-foreground">{t("enforcements.defaultDescription")}</p>
              </div>
            </div>
            <StateBadge state={defaultAssignment.enabled ? "protected" : "paused"} />
          </div>

          <dl className="grid sm:grid-cols-3">
            <EnforcementFact icon={ShieldCheck} label={t("enforcements.guardrail")} value={defaultGuardrail.name} detail={t("enforcements.version", { version: defaultAssignment.guardrail_version })} />
            <EnforcementFact icon={Route} label={t("enforcements.scope")} value={t("enforcements.unmatchedTraffic")} detail={t("enforcements.scopeDescription")} />
            <EnforcementFact icon={LockKeyhole} label={t("enforcements.mode")} value={t("enforcements.baselineMode")} detail={t("enforcements.modeDescription")} />
          </dl>
        </div>
      ) : null}

      {!guardrailsQuery.isLoading && !assignmentsQuery.isLoading ? (
        <div className="mt-5">
          <InfoNotice title={t("enforcements.boundaryTitle")}>{t("enforcements.boundaryDescription")}</InfoNotice>
        </div>
      ) : null}
    </section>
  );
}

function EnforcementFact({ icon: Icon, label, value, detail }: { icon: typeof ShieldCheck; label: string; value: string; detail: string }) {
  return (
    <div className="border-b p-5 last:border-b-0 sm:border-b-0 sm:border-r sm:last:border-r-0">
      <dt className="flex items-center gap-2 text-xs font-medium text-muted-foreground"><Icon className="size-4" />{label}</dt>
      <dd className="mt-3 text-sm font-semibold">{value}</dd>
      <dd className="mt-1 text-xs leading-5 text-muted-foreground">{detail}</dd>
    </div>
  );
}
