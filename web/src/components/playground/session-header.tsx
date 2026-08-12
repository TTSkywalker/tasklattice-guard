import { Link } from "@tanstack/react-router";
import { Eraser, ExternalLink, FlaskConical } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { Guardrail } from "@/lib/api";

export function PlaygroundSessionHeader({
  guardrail,
  guardrails,
  value,
  hasTurns,
  onChange,
  onClear,
}: {
  guardrail: Guardrail;
  guardrails: Guardrail[];
  value: string;
  hasTurns: boolean;
  onChange: (value: string) => void;
  onClear: () => void;
}) {
  const { t } = useTranslation();
  return (
    <section className="mt-5 rounded-xl border bg-card p-4 shadow-xs sm:p-5">
      <div className="flex flex-col gap-5 xl:flex-row xl:items-center xl:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="grid size-8 place-items-center rounded-lg bg-primary/[0.07] text-primary"><FlaskConical className="size-4" /></span>
            <h2 className="text-sm font-semibold">{t("playground.sessionTitle")}</h2>
            <Badge variant="outline" className="border-emerald-200 bg-emerald-50 text-emerald-700"><span className="size-1.5 rounded-full bg-emerald-500" />{t("playground.active")}</Badge>
          </div>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">{t("playground.sessionDescription")}</p>
        </div>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div className="min-w-0 sm:w-80">
            <label className="mb-1.5 block text-[11px] font-medium text-muted-foreground">{t("playground.selectedGuardrail")}</label>
            <div className="flex items-center gap-1">
              <Select value={value} onValueChange={onChange}>
                <SelectTrigger className="min-h-11 min-w-0 flex-1 bg-card" aria-label={t("playground.selectedGuardrail")}><SelectValue /></SelectTrigger>
                <SelectContent>{guardrails.map((item) => <SelectItem key={item.id} value={item.id}>{item.name}</SelectItem>)}</SelectContent>
              </Select>
              <Button asChild size="icon" variant="ghost" className="size-10 shrink-0 text-muted-foreground" title={t("playground.openGuardrailDefinition")}>
                <Link to="/guardrails/$guardrailId" params={{ guardrailId: guardrail.id }} aria-label={t("playground.openGuardrailDefinition")}><ExternalLink className="size-4" /></Link>
              </Button>
            </div>
          </div>
          <Button type="button" variant="ghost" className="min-h-11 justify-center text-muted-foreground" disabled={!hasTurns} onClick={onClear}><Eraser />{t("playground.clearSession")}</Button>
        </div>
      </div>
    </section>
  );
}
