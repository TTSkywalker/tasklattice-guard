import { useQuery } from "@tanstack/react-query";
import { Clock3, ListFilter } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";

import { EmptyState, InfoNotice, PageHeader, StateBadge } from "@/components/product-shell";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { queryKeys } from "@/features/query-keys";
import { getDecisions, getGuardrails, getAssignments, type DecisionEvent } from "@/lib/api";

export function EvidencePage() {
  const { t, i18n } = useTranslation();
  const query = useQuery({ queryKey: queryKeys.decisions, queryFn: () => getDecisions({ limit: 100 }), refetchInterval: 15_000 });
  const guardrails = useQuery({ queryKey: queryKeys.guardrails, queryFn: getGuardrails }).data?.items ?? [];
  const assignments = useQuery({ queryKey: queryKeys.assignments, queryFn: getAssignments }).data?.items ?? [];
  const evidence = query.data?.items ?? [];
  const context = (item: DecisionEvent) => ({
    assignment: assignments.find((candidate) => candidate.id === item.assignment_id)?.name ?? t("evidence.controlPlane"),
    guardrail: guardrails.find((candidate) => candidate.id === item.guardrail_id)?.name,
  });

  return (
    <section className="py-6 sm:py-8">
      <PageHeader
        title={t("pages.evidence.title")}
        description={t("evidence.description")}
      />

      {evidence.length ? (
        <>
          <div className="mt-5 space-y-3 md:hidden">
            {evidence.map((item) => {
              const names = context(item);
              return (
                <article key={item.id} className="overflow-hidden rounded-lg border bg-card">
                  <div className="flex items-start justify-between gap-3 border-b bg-muted/40 p-4">
                    <div>
                      <strong className="text-sm font-medium">{evidenceLabel(item.kind, t)}</strong>
                      <time className="mt-1 flex items-center gap-2 font-mono text-xs text-muted-foreground"><Clock3 className="size-3.5" />{new Date(item.created_at).toLocaleString(i18n.language)}</time>
                    </div>
                    <StateBadge state={item.outcome} />
                  </div>
                  <div className="p-4">
                    <p className="flex items-center gap-2 text-xs"><ListFilter className="size-3.5 text-primary" />{names.assignment}</p>
                    {names.guardrail ? <p className="mt-1 pl-5 text-xs text-muted-foreground">{names.guardrail}</p> : null}
                    <p className="mt-3 text-xs leading-5 text-muted-foreground">{item.detail}</p>
                  </div>
                </article>
              );
            })}
          </div>

          <div className="mt-5 hidden overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-surface)] md:block">
            <Table>
              <TableHeader className="bg-muted/40"><TableRow className="hover:bg-muted/40"><TableHead className="w-[190px] px-4 text-xs">{t("evidence.time")}</TableHead><TableHead className="w-[210px] px-4 text-xs">{t("evidence.event")}</TableHead><TableHead className="w-[220px] px-4 text-xs">{t("evidence.context")}</TableHead><TableHead className="w-[120px] px-4 text-xs">{t("evidence.outcome")}</TableHead><TableHead className="min-w-[280px] px-4 text-xs">{t("evidence.evidence")}</TableHead></TableRow></TableHeader>
              <TableBody>{evidence.map((item) => { const names = context(item); return <TableRow key={item.id}><TableCell className="px-4 py-4 align-top"><time className="flex items-center gap-2 font-mono text-xs text-muted-foreground"><Clock3 className="size-3.5" />{new Date(item.created_at).toLocaleString(i18n.language)}</time></TableCell><TableCell className="px-4 py-4 align-top"><strong className="text-xs font-medium">{evidenceLabel(item.kind, t)}</strong>{item.risk ? <p className="mt-1 text-xs capitalize text-muted-foreground">{item.risk.replaceAll("_", " ")}</p> : null}</TableCell><TableCell className="px-4 py-4 align-top text-xs"><p className="flex items-center gap-2"><ListFilter className="size-3.5 text-primary" />{names.assignment}</p>{names.guardrail ? <p className="mt-1 text-muted-foreground">{names.guardrail}</p> : null}</TableCell><TableCell className="px-4 py-4 align-top"><StateBadge state={item.outcome} /></TableCell><TableCell className="whitespace-normal px-4 py-4 align-top text-xs leading-5 text-muted-foreground">{item.detail}</TableCell></TableRow>; })}</TableBody>
            </Table>
          </div>
        </>
      ) : <div className="mt-5"><EmptyState title={t("evidence.emptyTitle")} description={t("evidence.emptyDescription")} /></div>}

      <div className="mt-5"><InfoNotice title={t("evidence.privacyTitle")}>{t("evidence.privacyDescription")}</InfoNotice></div>
    </section>
  );
}

function evidenceLabel(kind: string, t: TFunction) {
  const labels: Record<string, string> = {
    "guardrail.created": "evidence.kinds.guardrailCreated",
    "guardrail.default.created": "evidence.kinds.defaultGuardrailInstalled",
    "guardrail.updated": "evidence.kinds.guardrailUpdated",
    "guardrail.test_case.created": "evidence.kinds.testCaseCreated",
    "guardrail.test_case.deleted": "evidence.kinds.testCaseDeleted",
    "guardrail.test.completed": "evidence.kinds.guardrailTestCompleted",
    "guardrail.version.created": "evidence.kinds.guardrailVersionCreated",
    "assignment.created": "evidence.kinds.assignmentCreated",
    "assignment.default.created": "evidence.kinds.defaultAssignmentInstalled",
    "assignment.updated": "evidence.kinds.assignmentUpdated",
    "integration.registered": "evidence.kinds.integrationRegistered",
    "interaction.decision": "evidence.kinds.interactionDecision",
    "system.seeded": "evidence.kinds.systemSeeded",
  };
  return labels[kind] ? t(labels[kind]) : kind.replaceAll(".", " / ");
}
