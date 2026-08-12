import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { ProbeInspectionDrawer } from "@/components/playground/probe-inspection-drawer";
import { ProbeConversationPanel } from "@/components/playground/probe-conversation-panel";
import { PlaygroundSessionHeader } from "@/components/playground/session-header";
import type { PlaygroundTurn, ProbePhase } from "@/components/playground/types";
import { EmptyState, ErrorNotice, PageHeader } from "@/components/product-shell";
import { Skeleton } from "@/components/ui/skeleton";
import { queryKeys } from "@/features/query-keys";
import { createPlaygroundProbe, getGuardrails, type Guardrail, type PlaygroundProbeResult } from "@/lib/api";

export function PlaygroundPage() {
  const { t } = useTranslation();
  const guardrailsQuery = useQuery({ queryKey: queryKeys.guardrails, queryFn: getGuardrails });
  const guardrails = guardrailsQuery.data?.items ?? [];
  const [guardrailId, setGuardrailId] = useGuardrailSelection(guardrails);
  const selected = guardrails.find((item) => item.id === guardrailId);
  return (
    <section className="py-6 sm:py-8">
      <div className="mx-auto max-w-5xl"><PageHeader title={t("pages.playground.title")} description={t("pages.playground.description")} /></div>
      {guardrailsQuery.error ? <div className="mt-5"><ErrorNotice error={guardrailsQuery.error} /></div> : null}
      {guardrailsQuery.isLoading ? <Skeleton className="mt-5 h-[48rem] rounded-xl" /> : null}
      {!guardrailsQuery.isLoading && !guardrails.length ? <div className="mt-5"><EmptyState title={t("validation.noGuardrails")} description={t("validation.noGuardrailsDescription")} /></div> : null}
      {selected ? <div className="mx-auto max-w-5xl"><PlaygroundWorkspace key={selected.id} guardrail={selected} guardrails={guardrails} value={selected.id} onChange={setGuardrailId} /></div> : null}
    </section>
  );
}

function PlaygroundWorkspace({ guardrail, guardrails, value, onChange }: { guardrail: Guardrail; guardrails: Guardrail[]; value: string; onChange: (value: string) => void }) {
  const { t } = useTranslation();
  const [phase, setPhase] = useState<ProbePhase>("input");
  const [content, setContent] = useState("");
  const [turns, setTurns] = useState<PlaygroundTurn[]>([]);
  const [details, setDetails] = useState<PlaygroundProbeResult | null>(null);
  const probe = useMutation({
    mutationFn: (input: { phase: ProbePhase; content: string; context_messages: { role: "user" | "assistant"; content: string }[] }) => createPlaygroundProbe(guardrail.id, input),
    onSuccess: (result, input) => {
      setTurns((current) => [...current, { id: result.probe_id, phase: input.phase, content: input.content, result }]);
      setContent("");
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : t("guardrails.operationFailed")),
  });
  const submit = () => {
    const trimmed = content.trim();
    if (!trimmed || probe.isPending) return;
    probe.mutate({
      phase,
      content: trimmed,
      context_messages: turns.map((turn) => ({ role: turn.phase === "input" ? "user" : "assistant", content: turn.content })),
    });
  };
  const clear = () => {
    setTurns([]);
    setContent("");
    setDetails(null);
    probe.reset();
  };
  return (
    <>
      <PlaygroundSessionHeader guardrail={guardrail} guardrails={guardrails} value={value} hasTurns={Boolean(turns.length)} onChange={onChange} onClear={clear} />
      <div className="mt-5 min-w-0"><ProbeConversationPanel turns={turns} phase={phase} content={content} pending={probe.isPending} onPhaseChange={setPhase} onContentChange={setContent} onSubmit={submit} onViewDetails={setDetails} /></div>
      <ProbeInspectionDrawer result={details} open={Boolean(details)} onOpenChange={(open) => { if (!open) setDetails(null); }} />
    </>
  );
}

function useGuardrailSelection(guardrails: Guardrail[]) {
  const initial = typeof window === "undefined" ? "" : new URLSearchParams(window.location.search).get("guardrail") ?? "";
  const [guardrailId, setGuardrailId] = useState(initial);
  useEffect(() => {
    if (guardrails.length && !guardrails.some((item) => item.id === guardrailId)) setGuardrailId(guardrails[0].id);
  }, [guardrailId, guardrails]);
  const select = (next: string) => {
    setGuardrailId(next);
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.searchParams.set("guardrail", next);
      window.history.replaceState(window.history.state, "", url);
    }
  };
  return [guardrailId, select] as const;
}
