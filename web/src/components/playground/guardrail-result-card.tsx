import { Clock3, Search, ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import type { PlaygroundInteraction } from "@/lib/api";
import { cn } from "@/lib/utils";

export function GuardrailResultCard({ result, onViewDetails }: { result: PlaygroundInteraction; onViewDetails: () => void }) {
  const { t } = useTranslation();
  const totalLatency = result.input_check.latency_ms + (result.model.latency_ms ?? 0) + (result.output_check?.latency_ms ?? 0);
  const blocked = result.state !== "completed";
  const transformed = result.input_check.decision === "transform" || result.output_check?.decision === "transform";
  const summary = result.state === "input_blocked"
    ? t("playground.requestBlockedSummary")
    : result.state === "output_blocked"
      ? t("playground.responseBlockedSummary")
      : transformed
        ? t("playground.turnTransformedSummary")
        : t("playground.turnAllowedSummary");

  return (
    <section className={cn("flex flex-col gap-3 rounded-xl border bg-card px-3.5 py-3 shadow-xs sm:flex-row sm:items-center", blocked && "border-red-200/80 bg-red-50/30", transformed && !blocked && "border-amber-200/80 bg-amber-50/30")}>
      <div className={cn("grid size-7 shrink-0 place-items-center rounded-full bg-emerald-50 text-emerald-700", blocked && "bg-red-50 text-red-700", transformed && !blocked && "bg-amber-50 text-amber-700")}>
        <ShieldCheck className="size-4" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-xs font-semibold">{t("playground.guardrailReceipt")}</p>
        <p className="mt-0.5 truncate text-xs text-muted-foreground">{summary}</p>
      </div>
      <span className="inline-flex shrink-0 items-center gap-1 font-mono text-[11px] text-muted-foreground"><Clock3 className="size-3.5" />{totalLatency} ms</span>
      <Button type="button" variant="outline" size="sm" className="shrink-0" onClick={onViewDetails}><Search />{t("playground.inspect")}</Button>
    </section>
  );
}
