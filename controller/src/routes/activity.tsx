import { useQuery } from "@tanstack/react-query";
import { Activity, ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";

import { EmptyState, ErrorNotice, PageHeader, StateBadge } from "@/components/product-shell";
import { Card } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { listAuditEvents, listRuntimeEvents } from "@/lib/controller-api";

export function ActivityPage() {
  const { t, i18n } = useTranslation();
  const runtime = useQuery({ queryKey: ["controller", "runtime-events"], queryFn: () => listRuntimeEvents(), refetchInterval: 15_000 });
  const audit = useQuery({ queryKey: ["controller", "audit-events"], queryFn: () => listAuditEvents(), refetchInterval: 30_000 });

  return (
    <section className="py-6 sm:py-8">
      <PageHeader
        title={t("activity.title")}
        description={t("activity.description")}
      />
      <Tabs defaultValue="runtime" className="mt-6">
        <TabsList>
          <TabsTrigger value="runtime"><Activity />{t("activity.runtimeEvents")}</TabsTrigger>
          <TabsTrigger value="audit"><ShieldCheck />{t("activity.auditEvents")}</TabsTrigger>
        </TabsList>
        <TabsContent value="runtime" className="mt-5">
          {runtime.isLoading ? <Skeleton className="h-64 rounded-xl" /> : runtime.error ? <ErrorNotice error={runtime.error} /> : !runtime.data?.items.length ? <EmptyState title={t("activity.noRuntimeTitle")} description={t("activity.noRuntimeDescription")} /> : <Card><Table><TableHeader><TableRow><TableHead>{t("activity.columns.time")}</TableHead><TableHead>Runner</TableHead><TableHead>{t("activity.columns.direction")}</TableHead><TableHead>{t("activity.columns.decision")}</TableHead><TableHead>{t("activity.columns.duration")}</TableHead><TableHead>Request ID</TableHead></TableRow></TableHeader><TableBody>
            {(runtime.data?.items ?? []).map((event) => <TableRow key={event.id}><TableCell className="text-xs text-muted-foreground">{formatDate(event.occurredAt, i18n.language)}</TableCell><TableCell><code className="text-xs">{event.runnerId}</code></TableCell><TableCell>{event.direction}</TableCell><TableCell><StateBadge state={event.decision} /></TableCell><TableCell>{event.durationMs} ms</TableCell><TableCell><code className="text-xs">{event.requestId}</code></TableCell></TableRow>)}
          </TableBody></Table></Card>}
        </TabsContent>
        <TabsContent value="audit" className="mt-5">
          {audit.isLoading ? <Skeleton className="h-64 rounded-xl" /> : audit.error ? <ErrorNotice error={audit.error} /> : !audit.data?.items.length ? <EmptyState title={t("activity.noAuditTitle")} description={t("activity.noAuditDescription")} /> : <Card><Table><TableHeader><TableRow><TableHead>{t("activity.columns.time")}</TableHead><TableHead>{t("activity.columns.event")}</TableHead><TableHead>{t("activity.columns.resource")}</TableHead><TableHead>{t("activity.columns.actor")}</TableHead></TableRow></TableHeader><TableBody>
            {(audit.data?.items ?? []).map((event) => <TableRow key={event.id}><TableCell className="text-xs text-muted-foreground">{formatDate(event.occurredAt, i18n.language)}</TableCell><TableCell><code className="text-xs">{event.kind}</code></TableCell><TableCell>{event.resourceType} · <code className="text-xs">{event.resourceId}</code></TableCell><TableCell><code className="text-xs">{event.actorId ?? "system"}</code></TableCell></TableRow>)}
          </TableBody></Table></Card>}
        </TabsContent>
      </Tabs>
    </section>
  );
}

function formatDate(value: string | null, locale: string) {
  return value ? new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "—";
}
