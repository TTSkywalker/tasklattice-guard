import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { ProbeInspectionDrawer } from "@/components/playground/probe-inspection-drawer";
import { ProbeConversationPanel } from "@/components/playground/probe-conversation-panel";
import { usePlaygroundSession } from "@/components/playground/use-playground-session";
import type { PlaygroundTurn } from "@/components/playground/types";
import { EmptyState, ErrorNotice, PageHeader } from "@/components/product-shell";
import { Skeleton } from "@/components/ui/skeleton";
import { queryKeys } from "@/features/query-keys";
import { createPlaygroundInteraction, getGuardrails, getPlaygroundModels, type Guardrail, type PlaygroundInteraction, type PlaygroundModel } from "@/lib/api";

export function PlaygroundPage() {
  const { t } = useTranslation();
  const guardrailsQuery = useQuery({ queryKey: queryKeys.guardrails, queryFn: getGuardrails });
  const modelsQuery = useQuery({ queryKey: queryKeys.playgroundModels, queryFn: getPlaygroundModels });
  const guardrails = guardrailsQuery.data?.items ?? [];
  const models = modelsQuery.data?.items ?? [];
  const [guardrailId, setGuardrailId] = useGuardrailSelection(guardrails);
  const selected = guardrails.find((item) => item.id === guardrailId);
  const loading = guardrailsQuery.isLoading || modelsQuery.isLoading;
  return (
    <section className="py-6 sm:py-8">
      <PageHeader title={t("pages.playground.title")} description={t("pages.playground.description")} />
      {guardrailsQuery.error ? <div className="mt-5"><ErrorNotice error={guardrailsQuery.error} /></div> : null}
      {modelsQuery.error ? <div className="mt-5"><ErrorNotice error={modelsQuery.error} /></div> : null}
      {loading ? <Skeleton className="mt-5 h-[calc(100dvh-14rem)] min-h-[34rem] rounded-2xl" /> : null}
      {!loading && !guardrails.length ? <div className="mt-5"><EmptyState title={t("validation.noGuardrails")} description={t("validation.noGuardrailsDescription")} /></div> : null}
      {!loading && selected ? <PlaygroundWorkspace key={selected.id} guardrail={selected} guardrails={guardrails} models={models} value={selected.id} onChange={setGuardrailId} /> : null}
    </section>
  );
}

function PlaygroundWorkspace({ guardrail, guardrails, models, value, onChange }: { guardrail: Guardrail; guardrails: Guardrail[]; models: PlaygroundModel[]; value: string; onChange: (value: string) => void }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [modelId, setModelId] = useState("");
  const { turns, appendTurn, clearTurns } = usePlaygroundSession(guardrail.id);
  const [details, setDetails] = useState<PlaygroundInteraction | null>(null);

  useEffect(() => {
    if (models.length && !models.some((model) => model.id === modelId)) setModelId(models[0].id);
  }, [modelId, models]);

  const interaction = useMutation({
    mutationFn: (input: { model_id: string; message: string; history: { role: "user" | "assistant"; content: string }[] }) => createPlaygroundInteraction(guardrail.id, input),
    onSuccess: (result) => {
      appendTurn(result);
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.metrics }),
        queryClient.invalidateQueries({ queryKey: queryKeys.decisions }),
      ]);
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : t("guardrails.operationFailed")),
  });
  const submit = async (message: string) => {
    const trimmed = message.trim();
    if (!trimmed || interaction.isPending || !modelId) return;
    await interaction.mutateAsync({
      model_id: modelId,
      message: trimmed,
      history: conversationHistory(turns),
    });
  };
  const clear = () => {
    clearTurns();
    setDetails(null);
    interaction.reset();
  };
  return (
    <>
      <div className="mt-5 min-w-0">
        <ProbeConversationPanel
          guardrail={guardrail}
          guardrails={guardrails}
          guardrailId={value}
          turns={turns}
          models={models}
          modelId={modelId}
          pending={interaction.isPending}
          onGuardrailChange={onChange}
          onModelChange={setModelId}
          onSubmitMessage={submit}
          onClear={clear}
          onViewDetails={setDetails}
        />
      </div>
      <ProbeInspectionDrawer result={details} open={Boolean(details)} onOpenChange={(open) => { if (!open) setDetails(null); }} />
    </>
  );
}

function conversationHistory(turns: PlaygroundTurn[]): { role: "user" | "assistant"; content: string }[] {
  return turns.flatMap((turn) => {
    if (turn.state !== "completed" || !turn.effective_user_message || !turn.assistant_message) return [];
    return [
      { role: "user" as const, content: turn.effective_user_message },
      { role: "assistant" as const, content: turn.assistant_message },
    ];
  });
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
