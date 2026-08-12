import { Link } from "@tanstack/react-router";
import { ArrowDown, CheckCircle2, ChevronDown, ExternalLink, ShieldCheck, SkipForward } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { ModelMark } from "@/components/playground/model-mark";
import { ExecutionTracePanel, FindingsPanel, TriggeredControlsPanel } from "@/components/playground/probe-insights";
import { StateBadge } from "@/components/product-shell";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { PlaygroundCheckResult, PlaygroundInteraction } from "@/lib/api";

export function ProbeInspectionDrawer({ result, open, onOpenChange }: { result: PlaygroundInteraction | null; open: boolean; onOpenChange: (open: boolean) => void }) {
  const { t } = useTranslation();
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-[min(46rem,calc(100vw-1rem))]! max-w-none! gap-0 overflow-y-auto sm:max-w-none!">
        <SheetHeader className="border-b p-5 pr-14">
          <SheetTitle>{t("playground.inspectionTitle")}</SheetTitle>
          <SheetDescription>{t("playground.inspectionDescription")}</SheetDescription>
        </SheetHeader>
        {result ? <div className="space-y-5 p-5">
          <InspectionFlow result={result} />
          <StageTabs result={result} />

          <details className="group overflow-hidden rounded-xl border bg-card">
            <summary className="flex min-h-12 cursor-pointer list-none items-center gap-3 px-4 text-sm font-medium focus-visible:outline-2 focus-visible:outline-ring [&::-webkit-details-marker]:hidden">{t("playground.runMetadata")}<ChevronDown className="ml-auto size-4 text-muted-foreground transition-transform group-open:rotate-180" /></summary>
            <div className="border-t"><dl className="divide-y"><DrawerFact label={t("playground.model")} value={`${result.model.provider} · ${result.model.name}`} /><DrawerFact label={t("playground.modelLatency")} value={result.model.latency_ms === null ? t("playground.notCalled") : `${result.model.latency_ms} ms`} mono /><DrawerFact label={t("playground.inputTraceId")} value={result.input_check.trace_id} mono /><DrawerFact label={t("playground.outputTraceId")} value={result.output_check?.trace_id ?? t("playground.notRun")} mono /><DrawerFact label={t("playground.guardrailVersion")} value={t("playground.draftVersion", { version: result.input_check.guardrail.draft_version })} /><DrawerFact label={t("playground.runtimeVersion")} value={result.input_check.guardrail.compiler_version} mono /><DrawerFact label={t("playground.evidence")} value={result.input_check.evidence_id ?? t("playground.noEvidenceCreated")} /></dl><div className="border-t p-3"><Button asChild variant="ghost" size="sm"><Link to="/guardrails/$guardrailId" params={{ guardrailId: result.input_check.guardrail.id }}>{result.input_check.guardrail.name}<ExternalLink /></Link></Button></div></div>
          </details>
        </div> : null}
      </SheetContent>
    </Sheet>
  );
}

function StageTabs({ result }: { result: PlaygroundInteraction }) {
  const { t } = useTranslation();
  return (
    <Tabs defaultValue={result.state === "output_blocked" ? "output" : "input"}>
      <TabsList className="grid h-auto w-full grid-cols-2 rounded-xl bg-muted/60 p-1.5">
        <TabsTrigger value="input" className="min-h-14 justify-start gap-3 px-3 data-active:bg-card">
          <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-primary/[0.07] text-primary"><ShieldCheck className="size-4" /></span>
          <span className="min-w-0 text-left"><span className="block text-sm font-semibold text-foreground">{t("playground.inputRail")}</span><span className="hidden text-[11px] font-normal text-muted-foreground sm:block">{t("playground.beforeModel")}</span></span>
          <span className="ml-auto hidden sm:block"><StateBadge state={result.input_check.decision} /></span>
        </TabsTrigger>
        <TabsTrigger value="output" className="min-h-14 justify-start gap-3 px-3 data-active:bg-card">
          <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-primary/[0.07] text-primary"><ShieldCheck className="size-4" /></span>
          <span className="min-w-0 text-left"><span className="block text-sm font-semibold text-foreground">{t("playground.outputRail")}</span><span className="hidden text-[11px] font-normal text-muted-foreground sm:block">{t("playground.afterModel")}</span></span>
          <span className="ml-auto hidden sm:block">{result.output_check ? <StateBadge state={result.output_check.decision} /> : <StateBadge state="not evaluated" />}</span>
        </TabsTrigger>
      </TabsList>
      <TabsContent value="input" className="mt-2">
        <CheckpointPanel title={t("playground.requestCheck")} description={t("playground.requestCheckDescription")} result={result.input_check} />
      </TabsContent>
      <TabsContent value="output" className="mt-2">
        {result.output_check ? (
          <CheckpointPanel title={t("playground.responseCheck")} description={t("playground.responseCheckDescription")} result={result.output_check} />
        ) : (
          <section className="rounded-xl border border-dashed bg-muted/20 p-6 text-center">
            <SkipForward className="mx-auto size-5 text-muted-foreground" />
            <h3 className="mt-2 text-sm font-semibold">{t("playground.responseCheckSkipped")}</h3>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">{t("playground.responseCheckSkippedDescription")}</p>
          </section>
        )}
      </TabsContent>
    </Tabs>
  );
}

function InspectionFlow({ result }: { result: PlaygroundInteraction }) {
  const { t } = useTranslation();
  return (
    <section className="rounded-2xl border bg-[linear-gradient(145deg,hsl(var(--muted)/0.55),hsl(var(--card)))] p-4">
      <div className="mb-4 flex items-center justify-between gap-3"><div><p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-primary">{t("playground.protectionPath")}</p><h2 className="mt-1 text-base font-semibold">{t("playground.turnJourney")}</h2></div><StateBadge state={result.state === "completed" ? "protected" : "blocked"} /></div>
      <div className="grid gap-2 sm:grid-cols-[1fr_auto_1fr_auto_1fr] sm:items-stretch">
        <FlowNode icon={<ShieldCheck />} title={t("playground.requestCheck")} detail={t(`playground.decisions.${result.input_check.decision}`)} latency={result.input_check.latency_ms} state={result.input_check.decision} />
        <ArrowDown className="mx-auto size-4 text-muted-foreground sm:mt-7 sm:-rotate-90" />
        <FlowNode icon={<ModelMark model={result.model} />} title={result.model.provider} detail={result.model.name} latency={result.model.latency_ms} state={result.model.latency_ms === null ? "skipped" : "allow"} />
        <ArrowDown className="mx-auto size-4 text-muted-foreground sm:mt-7 sm:-rotate-90" />
        <FlowNode icon={<ShieldCheck />} title={t("playground.responseCheck")} detail={result.output_check ? t(`playground.decisions.${result.output_check.decision}`) : t("playground.notRun")} latency={result.output_check?.latency_ms ?? null} state={result.output_check?.decision ?? "skipped"} />
      </div>
    </section>
  );
}

function FlowNode({ icon, title, detail, latency, state }: { icon: ReactNode; title: string; detail: string; latency: number | null; state: string }) {
  const safe = state === "allow";
  const blocked = state === "block";
  return (
    <div className="rounded-xl border bg-card p-3 shadow-xs">
      <div className="flex items-center gap-2"><span className="grid size-7 place-items-center rounded-lg bg-muted text-muted-foreground [&_svg]:size-4">{icon}</span><span className="text-xs font-semibold">{title}</span></div>
      <div className="mt-3 flex items-center justify-between gap-2"><span className={`inline-flex items-center gap-1 text-[11px] font-medium ${safe ? "text-emerald-700" : blocked ? "text-red-700" : "text-muted-foreground"}`}><CheckCircle2 className="size-3.5" />{detail}</span><span className="font-mono text-[10px] text-muted-foreground">{latency === null ? "—" : `${latency} ms`}</span></div>
    </div>
  );
}

function CheckpointPanel({ title, description, result }: { title: string; description: string; result: PlaygroundCheckResult }) {
  const { t } = useTranslation();
  return (
    <section className="overflow-hidden rounded-xl border bg-card">
      <header className="flex items-center gap-3 bg-muted/20 px-4 py-3.5">
        <div className="min-w-0 flex-1"><h2 className="text-sm font-semibold">{title}</h2><p className="mt-0.5 text-xs text-muted-foreground">{description}</p></div>
        <StateBadge state={result.decision} />
      </header>
      <div className="space-y-4 border-t p-4">
        <section className="overflow-hidden rounded-xl border bg-card">
          <dl className="grid sm:grid-cols-2"><InspectionFact label={t("playground.triggeredControl")} value={result.triggered_control?.name ?? t("playground.noneMatched")} /><InspectionFact label={t("playground.triggeredRule")} value={result.triggered_rule?.name ?? (result.triggered_control ? t("playground.ruleUnavailable") : t("playground.noneTriggered"))} /><InspectionFact label={t("playground.latency")} value={`${result.latency_ms} ms`} mono /><InspectionFact label={t("playground.runtime")} value={result.runtime} /></dl>
          <p className="border-t px-4 py-3 text-sm leading-6 text-muted-foreground">{result.reason || t("playground.noDecisionReason")}</p>
        </section>
        <TriggeredControlsPanel result={result} />
        <FindingsPanel result={result} />
        <ExecutionTracePanel result={result} />
      </div>
    </section>
  );
}

function InspectionFact({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return <div className="border-b px-4 py-3 odd:sm:border-r"><dt className="text-[11px] font-medium text-muted-foreground">{label}</dt><dd className={`mt-1 text-sm font-medium ${mono ? "font-mono" : ""}`}>{value}</dd></div>;
}

function DrawerFact({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return <div className="grid grid-cols-[9rem_minmax(0,1fr)] gap-4 px-4 py-3"><dt className="text-xs text-muted-foreground">{label}</dt><dd className={`break-all text-right text-xs font-medium ${mono ? "font-mono" : ""}`}>{value}</dd></div>;
}
