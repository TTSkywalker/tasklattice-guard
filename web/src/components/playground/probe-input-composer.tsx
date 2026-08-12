import type { KeyboardEvent } from "react";
import { LoaderCircle, Send } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import type { ProbePhase } from "@/components/playground/types";

export function ProbeInputComposer({
  phase,
  content,
  pending,
  onPhaseChange,
  onContentChange,
  onSubmit,
}: {
  phase: ProbePhase;
  content: string;
  pending: boolean;
  onPhaseChange: (phase: ProbePhase) => void;
  onContentChange: (content: string) => void;
  onSubmit: () => void;
}) {
  const { t } = useTranslation();
  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) return;
    event.preventDefault();
    onSubmit();
  };
  return (
    <div className="border-t bg-card p-4 sm:p-5">
      <Tabs value={phase} onValueChange={(value) => onPhaseChange(value as ProbePhase)}>
        <TabsList className="mb-3 h-9" aria-label={t("playground.probeSurface")}>
          <TabsTrigger value="input" className="px-3">{t("playground.modelInput")}</TabsTrigger>
          <TabsTrigger value="output" className="px-3">{t("playground.modelOutput")}</TabsTrigger>
        </TabsList>
      </Tabs>
      <div className="flex items-end gap-2 rounded-xl border bg-background p-2 transition-shadow focus-within:ring-2 focus-within:ring-ring/40">
        <Textarea
          value={content}
          onChange={(event) => onContentChange(event.target.value)}
          onKeyDown={handleKeyDown}
          className="min-h-24 flex-1 resize-y border-0 bg-transparent shadow-none focus-visible:ring-0"
          placeholder={t(phase === "input" ? "playground.inputPlaceholder" : "playground.outputPlaceholder")}
          maxLength={8_000}
          aria-label={t(phase === "input" ? "playground.modelInput" : "playground.modelOutput")}
        />
        <Button type="button" size="icon" className="size-11 shrink-0" onClick={onSubmit} disabled={!content.trim() || pending} aria-label={t("playground.runProbe")}>
          {pending ? <LoaderCircle className="animate-spin" /> : <Send />}
        </Button>
      </div>
      <p className="mt-2 text-[11px] text-muted-foreground">{t("playground.keyboardHelp")}</p>
    </div>
  );
}
