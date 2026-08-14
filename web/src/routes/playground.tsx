import { useCallback, useEffect, useMemo, useState } from "react";
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
import { createPlaygroundInteraction, getGuardrails, getGuardrailVersions, getPlaygroundModels, type Guardrail, type GuardrailVersion, type PlaygroundInteraction, type PlaygroundModel } from "@/lib/api";

export function PlaygroundPage() {
  const { t } = useTranslation();
  const guardrailsQuery = useQuery({ queryKey: queryKeys.guardrails, queryFn: getGuardrails });
  const modelsQuery = useQuery({ queryKey: queryKeys.playgroundModels, queryFn: getPlaygroundModels });
  const guardrails = guardrailsQuery.data?.items ?? [];
  const publishedGuardrails = useMemo(() => guardrails.filter(hasPublishedVersion), [guardrails]);
  const models = modelsQuery.data?.items ?? [];
  const { guardrailId, guardrailVersion, selectGuardrail, selectVersion } = usePlaygroundSelection(publishedGuardrails);
  const selected = publishedGuardrails.find((item) => item.id === guardrailId);
  const versionsQuery = useQuery({
    queryKey: queryKeys.guardrailVersions(guardrailId),
    queryFn: () => getGuardrailVersions(guardrailId),
    enabled: Boolean(guardrailId),
  });
  const versions = versionsQuery.data?.items ?? [];
  const selectedVersion = versions.find((item) => item.version === guardrailVersion);

  useEffect(() => {
    if (!versionsQuery.isSuccess) return;
    const resolved = resolvePublishedVersion(versions, guardrailVersion);
    if (resolved !== guardrailVersion) selectVersion(resolved);
  }, [guardrailVersion, selectVersion, versions, versionsQuery.isSuccess]);

  const loading = guardrailsQuery.isLoading || modelsQuery.isLoading;
  return (
    <section className="py-6 sm:py-8">
      <PageHeader title={t("pages.playground.title")} description={t("pages.playground.description")} />
      {guardrailsQuery.error ? <div className="mt-5"><ErrorNotice error={guardrailsQuery.error} /></div> : null}
      {modelsQuery.error ? <div className="mt-5"><ErrorNotice error={modelsQuery.error} /></div> : null}
      {versionsQuery.error ? <div className="mt-5"><ErrorNotice error={versionsQuery.error} /></div> : null}
      {loading ? <Skeleton className="mt-5 h-[calc(100dvh-14rem)] min-h-[34rem] rounded-2xl" /> : null}
      {!loading && !guardrails.length ? <div className="mt-5"><EmptyState title={t("validation.noGuardrails")} description={t("validation.noGuardrailsDescription")} /></div> : null}
      {!loading && guardrails.length > 0 && !publishedGuardrails.length ? <div className="mt-5"><EmptyState title={t("playground.noPublishedGuardrails")} description={t("playground.noPublishedGuardrailsDescription")} /></div> : null}
      {!loading && selected ? (
        <PlaygroundWorkspace
          key={`${selected.id}:${selectedVersion?.version ?? 0}`}
          guardrail={selected}
          guardrails={publishedGuardrails}
          versions={versions}
          selectedVersion={selectedVersion}
          versionsLoading={versionsQuery.isLoading}
          models={models}
          onGuardrailChange={selectGuardrail}
          onVersionChange={selectVersion}
        />
      ) : null}
    </section>
  );
}

function PlaygroundWorkspace({ guardrail, guardrails, versions, selectedVersion, versionsLoading, models, onGuardrailChange, onVersionChange }: { guardrail: Guardrail; guardrails: Guardrail[]; versions: GuardrailVersion[]; selectedVersion?: GuardrailVersion; versionsLoading: boolean; models: PlaygroundModel[]; onGuardrailChange: (value: string) => void; onVersionChange: (value: number) => void }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [modelId, setModelId] = useState("");
  const { turns, appendTurn, clearTurns } = usePlaygroundSession(guardrail.id, selectedVersion?.version ?? 0);
  const [details, setDetails] = useState<PlaygroundInteraction | null>(null);

  useEffect(() => {
    if (models.length && !models.some((model) => model.id === modelId)) setModelId(models[0].id);
  }, [modelId, models]);

  const interaction = useMutation({
    mutationFn: (input: { guardrail_version: number; model_id: string; message: string; history: { role: "user" | "assistant"; content: string }[] }) => createPlaygroundInteraction(guardrail.id, input),
    onSuccess: (result) => {
      appendTurn(result);
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.metrics }),
        queryClient.invalidateQueries({ queryKey: queryKeys.evidence }),
      ]);
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : t("guardrails.operationFailed")),
  });
  const submit = async (message: string) => {
    const trimmed = message.trim();
    if (!trimmed || interaction.isPending || !modelId || !selectedVersion) return;
    await interaction.mutateAsync({
      guardrail_version: selectedVersion.version,
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
          versions={versions}
          selectedVersion={selectedVersion}
          versionsLoading={versionsLoading}
          turns={turns}
          models={models}
          modelId={modelId}
          pending={interaction.isPending}
          onGuardrailChange={onGuardrailChange}
          onVersionChange={onVersionChange}
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

function hasPublishedVersion(guardrail: Guardrail) {
  return guardrail.published_version_count === undefined
    ? guardrail.published_current
    : guardrail.published_version_count > 0;
}

export function resolvePublishedVersion(versions: GuardrailVersion[], requested: number) {
  if (versions.some((item) => item.version === requested)) return requested;
  return versions.reduce((latest, item) => Math.max(latest, item.version), 0);
}

function usePlaygroundSelection(guardrails: Guardrail[]) {
  const initial = initialPlaygroundSelection();
  const [selection, setSelection] = useState(initial);
  useEffect(() => {
    if (!guardrails.length || guardrails.some((item) => item.id === selection.guardrailId)) return;
    const next = { guardrailId: guardrails[0].id, guardrailVersion: 0 };
    setSelection(next);
    syncPlaygroundSearch(next);
  }, [guardrails, selection.guardrailId]);
  const selectGuardrail = useCallback((guardrailId: string) => {
    const next = { guardrailId, guardrailVersion: 0 };
    setSelection(next);
    syncPlaygroundSearch(next);
  }, []);
  const selectVersion = useCallback((guardrailVersion: number) => {
    setSelection((current) => {
      const next = { ...current, guardrailVersion };
      syncPlaygroundSearch(next);
      return next;
    });
  }, []);
  return { ...selection, selectGuardrail, selectVersion };
}

function initialPlaygroundSelection() {
  if (typeof window === "undefined") return { guardrailId: "", guardrailVersion: 0 };
  const search = new URLSearchParams(window.location.search);
  const version = Number(search.get("version"));
  return {
    guardrailId: search.get("guardrail") ?? "",
    guardrailVersion: Number.isInteger(version) && version > 0 ? version : 0,
  };
}

function syncPlaygroundSearch(selection: { guardrailId: string; guardrailVersion: number }) {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  if (selection.guardrailId) url.searchParams.set("guardrail", selection.guardrailId);
  else url.searchParams.delete("guardrail");
  if (selection.guardrailVersion > 0) url.searchParams.set("version", String(selection.guardrailVersion));
  else url.searchParams.delete("version");
  window.history.replaceState(window.history.state, "", url);
}
