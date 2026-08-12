import { FlaskConical, LoaderCircle, MessagesSquare } from "lucide-react";
import { useTranslation } from "react-i18next";

import { GuardrailResultCard } from "@/components/playground/guardrail-result-card";
import { ProbeInputComposer } from "@/components/playground/probe-input-composer";
import type { PlaygroundTurn, ProbePhase } from "@/components/playground/types";
import type { PlaygroundProbeResult } from "@/lib/api";

export function ProbeConversationPanel({
  turns,
  phase,
  content,
  pending,
  onPhaseChange,
  onContentChange,
  onSubmit,
  onViewDetails,
}: {
  turns: PlaygroundTurn[];
  phase: ProbePhase;
  content: string;
  pending: boolean;
  onPhaseChange: (phase: ProbePhase) => void;
  onContentChange: (content: string) => void;
  onSubmit: () => void;
  onViewDetails: (result: PlaygroundProbeResult) => void;
}) {
  const { t } = useTranslation();
  return (
    <section className="flex min-h-[calc(100dvh-22rem)] min-w-0 flex-col overflow-hidden rounded-xl border bg-card shadow-xs">
      <header className="flex items-center gap-3 border-b bg-muted/20 px-4 py-3.5">
        <span className="grid size-8 place-items-center rounded-lg border bg-card text-muted-foreground"><MessagesSquare className="size-4" /></span>
        <div><h2 className="text-sm font-semibold">{t("playground.conversationTitle")}</h2><p className="mt-0.5 text-xs text-muted-foreground">{t("playground.conversationDescription")}</p></div>
      </header>
      <div className="min-h-[30rem] flex-1 overflow-y-auto bg-muted/[0.08] p-4 sm:p-5" aria-live="polite">
        {!turns.length && !pending ? <ConversationEmptyState /> : null}
        <div className="space-y-7">
          {turns.map((turn) => (
            <article key={turn.id} className="space-y-3">
              <div className="ml-auto max-w-[88%] rounded-2xl rounded-br-md bg-slate-800 px-4 py-3 text-white sm:max-w-[78%]">
                <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-white/65">{t(turn.phase === "input" ? "playground.modelInput" : "playground.modelOutput")}</p>
                <p className="whitespace-pre-wrap text-sm leading-6">{turn.content}</p>
              </div>
              <div className="mr-auto w-full max-w-[92%]"><GuardrailResultCard result={turn.result} onViewDetails={() => onViewDetails(turn.result)} /></div>
            </article>
          ))}
          {pending ? <div className="flex items-center gap-3 rounded-xl border bg-card p-4 text-sm text-muted-foreground"><LoaderCircle className="size-4 animate-spin text-primary" />{t("playground.evaluating")}</div> : null}
        </div>
      </div>
      <ProbeInputComposer phase={phase} content={content} pending={pending} onPhaseChange={onPhaseChange} onContentChange={onContentChange} onSubmit={onSubmit} />
    </section>
  );
}

function ConversationEmptyState() {
  const { t } = useTranslation();
  return (
    <div className="flex min-h-[28rem] items-center justify-center text-center">
      <div className="max-w-sm px-6">
        <span className="mx-auto grid size-11 place-items-center rounded-full border bg-card text-muted-foreground"><FlaskConical className="size-5" /></span>
        <h3 className="mt-4 text-base font-semibold">{t("playground.emptyTitle")}</h3>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">{t("playground.emptyDescription")}</p>
      </div>
    </div>
  );
}
