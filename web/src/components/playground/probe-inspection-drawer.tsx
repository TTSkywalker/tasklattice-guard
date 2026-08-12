import { Link } from "@tanstack/react-router";
import { ChevronDown, ExternalLink } from "lucide-react";
import { useTranslation } from "react-i18next";

import { ExecutionTracePanel, FindingsPanel, TriggeredControlsPanel } from "@/components/playground/probe-insights";
import { StateBadge } from "@/components/product-shell";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import type { PlaygroundProbeResult } from "@/lib/api";

export function ProbeInspectionDrawer({ result, open, onOpenChange }: { result: PlaygroundProbeResult | null; open: boolean; onOpenChange: (open: boolean) => void }) {
  const { t } = useTranslation();
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-[min(44rem,calc(100vw-1rem))]! max-w-none! gap-0 overflow-y-auto sm:max-w-none!">
        <SheetHeader className="border-b p-5 pr-14">
          <SheetTitle>{t("playground.inspectionTitle")}</SheetTitle>
          <SheetDescription>{t("playground.inspectionDescription")}</SheetDescription>
        </SheetHeader>
        {result ? <div className="space-y-4 p-5">
          <section className="overflow-hidden rounded-xl border bg-card">
            <header className="flex items-center justify-between gap-3 border-b bg-muted/20 px-4 py-3"><div><p className="text-[11px] font-medium text-muted-foreground">{t("playground.guardrailResult")}</p><p className="mt-1 text-sm font-semibold">{t(`playground.decisions.${result.decision}`)}</p></div><StateBadge state={result.decision} /></header>
            <dl className="grid sm:grid-cols-2"><InspectionFact label={t("playground.triggeredControl")} value={result.triggered_control?.name ?? t("playground.noneMatched")} /><InspectionFact label={t("playground.triggeredRule")} value={result.triggered_rule?.name ?? (result.triggered_control ? t("playground.ruleUnavailable") : t("playground.noneTriggered"))} /><InspectionFact label={t("playground.latency")} value={`${result.latency_ms} ms`} mono /><InspectionFact label={t("playground.surface")} value={t(result.phase === "input" ? "playground.modelInput" : "playground.modelOutput")} /></dl>
            <p className="border-t px-4 py-3 text-sm leading-6 text-muted-foreground">{result.reason || t("playground.noDecisionReason")}</p>
          </section>

          <TriggeredControlsPanel result={result} />
          <FindingsPanel result={result} />
          <ExecutionTracePanel result={result} />

          <details className="group overflow-hidden rounded-xl border bg-card">
            <summary className="flex min-h-12 cursor-pointer list-none items-center gap-3 px-4 text-sm font-medium focus-visible:outline-2 focus-visible:outline-ring [&::-webkit-details-marker]:hidden">{t("playground.runMetadata")}<ChevronDown className="ml-auto size-4 text-muted-foreground transition-transform group-open:rotate-180" /></summary>
            <div className="border-t"><dl className="divide-y"><DrawerFact label={t("playground.runtime")} value={result.runtime} /><DrawerFact label={t("playground.traceId")} value={result.trace_id} mono /><DrawerFact label={t("playground.guardrailVersion")} value={t("playground.draftVersion", { version: result.guardrail.draft_version })} /><DrawerFact label={t("playground.runtimeVersion")} value={result.guardrail.compiler_version} mono /><DrawerFact label={t("playground.evidence")} value={result.evidence_id ?? t("playground.noEvidenceCreated")} /></dl><div className="border-t p-3"><Button asChild variant="ghost" size="sm"><Link to="/guardrails/$guardrailId" params={{ guardrailId: result.guardrail.id }}>{result.guardrail.name}<ExternalLink /></Link></Button></div></div>
          </details>
        </div> : null}
      </SheetContent>
    </Sheet>
  );
}

function InspectionFact({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return <div className="border-b px-4 py-3 odd:sm:border-r"><dt className="text-[11px] font-medium text-muted-foreground">{label}</dt><dd className={`mt-1 text-sm font-medium ${mono ? "font-mono" : ""}`}>{value}</dd></div>;
}

function DrawerFact({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return <div className="grid grid-cols-[9rem_minmax(0,1fr)] gap-4 px-4 py-3"><dt className="text-xs text-muted-foreground">{label}</dt><dd className={`break-all text-right text-xs font-medium ${mono ? "font-mono" : ""}`}>{value}</dd></div>;
}
