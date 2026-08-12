import { Clock3, Search } from "lucide-react";
import { useTranslation } from "react-i18next";

import { StateBadge } from "@/components/product-shell";
import { Button } from "@/components/ui/button";
import type { PlaygroundProbeResult } from "@/lib/api";

export function GuardrailResultCard({ result, onViewDetails }: { result: PlaygroundProbeResult; onViewDetails: () => void }) {
  const { t } = useTranslation();
  return (
    <section className="flex flex-col gap-3 rounded-xl border bg-card px-3.5 py-3 shadow-xs sm:flex-row sm:items-center">
      <div className="flex shrink-0 items-center gap-2">
        <StateBadge state={result.decision} />
        <span className="text-xs font-medium text-muted-foreground">{t("playground.guardrailResult")}</span>
      </div>
      <p className="min-w-0 flex-1 truncate text-sm">
        <span className="font-medium">{result.triggered_control?.name ?? t("playground.noneMatched")}</span>
        <span className="mx-1.5 text-muted-foreground">·</span>
        <span className="text-muted-foreground">{result.triggered_rule?.name ?? (result.triggered_control ? t("playground.ruleUnavailable") : t("playground.noneTriggered"))}</span>
      </p>
      <span className="inline-flex shrink-0 items-center gap-1 font-mono text-xs text-muted-foreground"><Clock3 className="size-3.5" />{result.latency_ms} ms</span>
      <Button type="button" variant="outline" size="sm" className="shrink-0" onClick={onViewDetails}><Search />{t("playground.inspectRun")}</Button>
    </section>
  );
}
