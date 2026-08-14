import { ArrowRight, ShieldCheck } from "lucide-react";
import { Link } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";

import { formatEventTimestamp } from "@/components/dashboard/event-time";
import { StateBadge } from "@/components/product-shell";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { EvidenceRecord } from "@/lib/api";

type GuardrailReference = { id: string; name: string };

export function RuntimeEventStream({ items, loading, guardrails }: {
  items: EvidenceRecord[];
  loading: boolean;
  guardrails: GuardrailReference[];
}) {
  const { t, i18n } = useTranslation();
  const guardrailNames = new Map(guardrails.map((item) => [item.id, item.name]));

  return (
    <Card className="gap-0 overflow-hidden py-0 shadow-none">
      <header className="flex flex-col gap-2 border-b px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <h2 className="text-sm font-semibold">{t("dashboard.recentEvents")}</h2>
            <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-emerald-700">
              <span className="size-1.5 rounded-full bg-emerald-500" />
              {t("dashboard.live")}
            </span>
            <span className="text-[11px] text-muted-foreground">{t("dashboard.newestFirst")} · {t("dashboard.refreshCadence")}</span>
          </div>
          <p className="mt-0.5 truncate text-xs text-muted-foreground">{t("dashboard.recentEventsDescription")}</p>
        </div>
        <Button size="sm" variant="ghost" className="h-8 shrink-0 self-start px-2 text-xs sm:self-auto" asChild>
          <Link to="/evidence">{t("dashboard.viewAllEvents")}<ArrowRight /></Link>
        </Button>
      </header>

      {loading ? (
        <div className="space-y-px bg-border">
          {Array.from({ length: 7 }).map((_, index) => <Skeleton key={index} className="h-9 w-full rounded-none" />)}
        </div>
      ) : items.length ? (
        <div className="max-h-[22rem] overflow-auto [scrollbar-gutter:stable]">
          <table className="w-full min-w-[48rem] table-fixed text-left text-xs" aria-label={t("dashboard.eventStreamAria")}>
            <thead className="sticky top-0 z-10 border-b bg-muted/95 text-[11px] text-muted-foreground backdrop-blur-sm">
              <tr>
                <th scope="col" className="h-8 w-40 px-3 font-medium">{t("dashboard.lastSeen")}</th>
                <th scope="col" className="h-8 w-24 px-3 font-medium">{t("dashboard.outcome")}</th>
                <th scope="col" className="h-8 w-36 px-3 font-medium">{t("dashboard.guardrail")}</th>
                <th scope="col" className="h-8 px-3 font-medium">{t("dashboard.message")}</th>
                <th scope="col" className="h-8 w-24 px-3 text-right font-medium">{t("dashboard.eventId")}</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {items.map((item) => {
                const timestamp = formatEventTimestamp(item.created_at, i18n.language);
                const guardrailName = item.guardrail_id ? guardrailNames.get(item.guardrail_id) ?? item.guardrail_id : t("dashboard.unassigned");
                return (
                  <tr key={item.id} className="h-10 transition-colors hover:bg-muted/40">
                    <td className="px-3 font-mono text-[11px] whitespace-nowrap tabular-nums" title={new Date(item.created_at).toLocaleString(i18n.language)}>
                      <span className="text-muted-foreground">{timestamp.date}</span> {timestamp.time}
                    </td>
                    <td className="px-3"><StateBadge state={item.outcome} /></td>
                    <td className="truncate px-3 text-[11px] text-muted-foreground" title={guardrailName}>{guardrailName}</td>
                    <td className="truncate px-3 text-xs" title={item.detail}>{item.detail}</td>
                    <td className="px-3 text-right"><code className="text-[10px] text-muted-foreground" title={item.id}>#{shortEventId(item.id)}</code></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="flex min-h-36 flex-col items-center justify-center px-6 text-center">
          <ShieldCheck className="size-5 text-muted-foreground" />
          <p className="mt-2 text-sm font-medium">{t("dashboard.noEventsTitle")}</p>
          <p className="mt-1 max-w-md text-xs leading-5 text-muted-foreground">{t("dashboard.noEventsDescription")}</p>
        </div>
      )}
    </Card>
  );
}

export function shortEventId(id: string) {
  return id.replace(/^evidence-/, "").slice(-8);
}
