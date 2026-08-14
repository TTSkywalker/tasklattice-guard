import { useCallback, useMemo } from "react";
import { Link } from "@tanstack/react-router";
import {
  AssistantRuntimeProvider,
  ComposerPrimitive,
  ErrorPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  getExternalStoreMessages,
  useAuiState,
  useExternalStoreRuntime,
  type AppendMessage,
  type TextMessagePartProps,
  type ThreadMessageLike,
} from "@assistant-ui/react";
import { Eraser, ExternalLink, LoaderCircle, MessageSquareText, Send, ShieldCheck, Tags } from "lucide-react";
import { useTranslation } from "react-i18next";

import { GuardrailResultCard } from "@/components/playground/guardrail-result-card";
import { ModelMark } from "@/components/playground/model-mark";
import type { PlaygroundTurn } from "@/components/playground/types";
import { formatGuardrailReleaseId } from "@/components/guardrail-version-workspace";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { Guardrail, GuardrailVersion, PlaygroundInteraction, PlaygroundModel } from "@/lib/api";

type PlaygroundThreadMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  turn?: PlaygroundTurn;
};

const MESSAGE_PARTS = { Text: PlaygroundMessageText };

export function ProbeConversationPanel({
  guardrail,
  guardrails,
  versions,
  selectedVersion,
  versionsLoading,
  turns,
  models,
  modelId,
  pending,
  onModelChange,
  onSubmitMessage,
  onClear,
  onGuardrailChange,
  onVersionChange,
  onViewDetails,
}: {
  guardrail: Guardrail;
  guardrails: Guardrail[];
  versions: GuardrailVersion[];
  selectedVersion?: GuardrailVersion;
  versionsLoading: boolean;
  turns: PlaygroundTurn[];
  models: PlaygroundModel[];
  modelId: string;
  pending: boolean;
  onModelChange: (modelId: string) => void;
  onSubmitMessage: (message: string) => Promise<void>;
  onClear: () => void;
  onGuardrailChange: (guardrailId: string) => void;
  onVersionChange: (version: number) => void;
  onViewDetails: (result: PlaygroundInteraction) => void;
}) {
  const { t } = useTranslation();
  const selectedModel = models.find((model) => model.id === modelId);
  const messages = useMemo(() => threadMessages(turns), [turns]);
  const onNew = useCallback(async (message: AppendMessage) => {
    const text = message.content
      .filter((part) => part.type === "text")
      .map((part) => part.text)
      .join("\n")
      .trim();
    if (text) await onSubmitMessage(text);
  }, [onSubmitMessage]);
  const runtime = useExternalStoreRuntime<PlaygroundThreadMessage>({
    messages,
    convertMessage,
    onNew,
    isRunning: pending,
    isDisabled: !models.length || !selectedVersion,
    isSendDisabled: !selectedModel || !selectedVersion,
  });

  return (
    <section className="flex h-[calc(100dvh-14rem)] min-h-[34rem] min-w-0 flex-col overflow-hidden rounded-2xl border bg-card shadow-xs">
      <header className="flex items-center gap-3 border-b bg-muted/20 px-4 py-3.5 sm:px-5">
        <span className="grid size-9 place-items-center rounded-xl border bg-card text-primary"><MessageSquareText className="size-4.5" /></span>
        <div className="min-w-0 flex-1"><h2 className="text-sm font-semibold">{t("playground.conversationTitle")}</h2><p className="mt-0.5 truncate text-xs text-muted-foreground">{t("playground.conversationDescription")}</p></div>
        <Button type="button" variant="ghost" className="min-h-11 shrink-0 text-muted-foreground" disabled={!turns.length} onClick={onClear} aria-label={t("playground.clearSession")}>
          <Eraser />
          <span className="hidden sm:inline">{t("playground.clearSession")}</span>
        </Button>
      </header>

      <AssistantRuntimeProvider runtime={runtime}>
        <ThreadPrimitive.Root className="flex min-h-0 flex-1 flex-col">
          <ThreadPrimitive.Viewport className="min-h-0 flex-1 space-y-8 overflow-y-auto bg-background/40 p-4 sm:p-6" aria-live="polite">
            <ThreadPrimitive.Messages>
              {({ message }) => message.role === "user"
                ? <PlaygroundUserMessage />
                : <PlaygroundAssistantMessage model={selectedModel} onViewDetails={onViewDetails} />}
            </ThreadPrimitive.Messages>
          </ThreadPrimitive.Viewport>
          <PlaygroundComposer
            guardrail={guardrail}
            guardrails={guardrails}
            versions={versions}
            selectedVersion={selectedVersion}
            versionsLoading={versionsLoading}
            models={models}
            modelId={modelId}
            pending={pending}
            onGuardrailChange={onGuardrailChange}
            onVersionChange={onVersionChange}
            onModelChange={onModelChange}
          />
        </ThreadPrimitive.Root>
      </AssistantRuntimeProvider>
    </section>
  );
}

function PlaygroundUserMessage() {
  return (
    <MessagePrimitive.Root className="flex w-full justify-end">
      <div className="w-fit max-w-[88%] rounded-2xl rounded-br-md bg-slate-800 px-4 py-3 text-white shadow-sm sm:max-w-3xl">
        <MessagePrimitive.Parts components={MESSAGE_PARTS} />
      </div>
    </MessagePrimitive.Root>
  );
}

function PlaygroundAssistantMessage({ model, onViewDetails }: { model?: PlaygroundModel; onViewDetails: (result: PlaygroundInteraction) => void }) {
  const { t } = useTranslation();
  const source = useAuiState((state) => getExternalStoreMessages<PlaygroundThreadMessage>(state.message)[0]);
  const turn = source?.turn;
  const effectiveModel = turn?.model ?? model;
  return (
    <MessagePrimitive.Root className="w-full space-y-3">
      <div className="mr-auto flex max-w-[92%] items-start gap-3 sm:max-w-3xl">
        <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-xl border bg-white shadow-xs"><ModelMark model={effectiveModel} className="size-5" /></span>
        {turn && !turn.assistant_message ? (
          <div className="rounded-2xl rounded-tl-md border border-red-200 bg-red-50/60 px-4 py-3">
            <p className="text-sm font-semibold text-red-900">{t(turn.state === "input_blocked" ? "playground.requestStopped" : "playground.responseWithheld")}</p>
            <p className="mt-1 text-xs leading-5 text-red-800/75">{t(turn.state === "input_blocked" ? "playground.requestStoppedDescription" : "playground.responseWithheldDescription")}</p>
          </div>
        ) : (
          <div className="min-w-0 rounded-2xl rounded-tl-md border bg-card px-4 py-3 shadow-xs">
            <p className="mb-1.5 text-[11px] font-semibold text-muted-foreground">{effectiveModel ? `${effectiveModel.provider} · ${effectiveModel.name}` : t("playground.processingTurn")}</p>
            {turn ? <MessagePrimitive.Parts components={MESSAGE_PARTS} /> : <div className="flex items-center gap-2 text-sm text-muted-foreground"><LoaderCircle className="size-4 animate-spin" />{t("playground.processingTurnDescription")}</div>}
            <ErrorPrimitive.Root className="mt-2 text-xs text-red-700 empty:hidden"><ErrorPrimitive.Message /></ErrorPrimitive.Root>
          </div>
        )}
      </div>
      {turn ? <div className="mr-auto w-full max-w-[94%] sm:max-w-3xl sm:pl-11"><GuardrailResultCard result={turn} onViewDetails={() => onViewDetails(turn)} /></div> : null}
    </MessagePrimitive.Root>
  );
}

function PlaygroundComposer({ guardrail, guardrails, versions, selectedVersion, versionsLoading, models, modelId, pending, onGuardrailChange, onVersionChange, onModelChange }: {
  guardrail: Guardrail;
  guardrails: Guardrail[];
  versions: GuardrailVersion[];
  selectedVersion?: GuardrailVersion;
  versionsLoading: boolean;
  models: PlaygroundModel[];
  modelId: string;
  pending: boolean;
  onGuardrailChange: (guardrailId: string) => void;
  onVersionChange: (version: number) => void;
  onModelChange: (modelId: string) => void;
}) {
  const { t } = useTranslation();
  const latestVersion = versions.reduce((latest, item) => Math.max(latest, item.version), 0);
  return (
    <div className="border-t bg-card p-3 sm:p-4">
      <ComposerPrimitive.Root className="rounded-2xl border bg-background shadow-xs transition-shadow focus-within:border-primary/35 focus-within:ring-3 focus-within:ring-primary/10">
        <ComposerPrimitive.Input
          className="block max-h-48 min-h-20 w-full resize-none bg-transparent px-4 pt-4 text-sm leading-6 outline-none placeholder:text-muted-foreground"
          placeholder={!models.length ? t("playground.noModelPlaceholder") : selectedVersion ? t("playground.chatPlaceholder") : t("playground.noPublishedVersionPlaceholder")}
          maxLength={8_000}
          submitMode="enter"
          unstable_insertNewlineOnTouchEnter
          aria-label={t("playground.messageModel")}
        />
        <div className="flex flex-col gap-2 border-t border-border/70 p-2 2xl:flex-row 2xl:items-center 2xl:justify-between">
          <div className="grid min-w-0 gap-2 sm:grid-cols-3 2xl:flex 2xl:items-center">
            <Select value={modelId} onValueChange={onModelChange} disabled={!models.length || pending}>
              <SelectTrigger className="h-11 w-full border-0 bg-muted/55 shadow-none 2xl:w-56" aria-label={t("playground.selectedModel")}>
                <SelectValue placeholder={t("playground.selectModel")} />
              </SelectTrigger>
              <SelectContent>
                {models.map((model) => <SelectItem key={model.id} value={model.id}><ModelMark model={model} className="size-4" /><span className="font-medium">{model.provider}</span><span className="text-muted-foreground">{model.name}</span></SelectItem>)}
              </SelectContent>
            </Select>
            <div className="flex min-w-0 items-center gap-1">
              <Select value={guardrail.id} onValueChange={onGuardrailChange} disabled={pending}>
                <SelectTrigger className="h-11 min-w-0 flex-1 border-0 bg-muted/55 shadow-none 2xl:w-56" aria-label={t("playground.selectedGuardrail")}>
                  <ShieldCheck className="size-4 shrink-0 text-emerald-600" /><SelectValue />
                </SelectTrigger>
                <SelectContent>{guardrails.map((item) => <SelectItem key={item.id} value={item.id}>{item.name}</SelectItem>)}</SelectContent>
              </Select>
              <Button asChild size="icon" variant="ghost" className="size-11 shrink-0 text-muted-foreground" title={t("playground.openGuardrailDefinition")}>
                <Link to="/guardrails/$guardrailId" params={{ guardrailId: guardrail.id }} aria-label={t("playground.openGuardrailDefinition")}><ExternalLink /></Link>
              </Button>
            </div>
            <Select value={selectedVersion ? String(selectedVersion.version) : undefined} onValueChange={(value) => onVersionChange(Number(value))} disabled={pending || versionsLoading || !versions.length}>
              <SelectTrigger className="h-11 w-full border-0 bg-muted/55 text-xs shadow-none 2xl:w-56" aria-label={t("playground.selectedGuardrailVersion")} title={!versionsLoading && !versions.length ? t("playground.noPublishedVersions") : undefined}>
                {versionsLoading ? <LoaderCircle className="size-4 animate-spin text-muted-foreground" /> : <Tags className="size-4 text-muted-foreground" />}
                <SelectValue placeholder={versionsLoading ? t("playground.loadingPublishedVersions") : versions.length ? t("playground.selectPublishedVersion") : t("playground.noPublishedVersions")}>
                  {selectedVersion ? <><span className="font-mono font-medium">{t("playground.versionNumber", { version: selectedVersion.version })}</span>{selectedVersion.version === latestVersion ? <span className="text-muted-foreground">· {t("playground.latestVersion")}</span> : selectedVersion.active ? <span className="text-muted-foreground">· {t("playground.activeVersion")}</span> : null}</> : undefined}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {versions.map((item) => {
                  const releaseId = formatGuardrailReleaseId(item.created_at);
                  const state = item.version === latestVersion ? t("playground.latestVersion") : item.active ? t("playground.activeVersion") : "";
                  return <SelectItem key={item.version} value={String(item.version)}><span className="font-mono font-medium">{t("playground.versionNumber", { version: item.version })}</span><span className="font-mono text-muted-foreground">{releaseId}</span>{state ? <span className="text-muted-foreground">· {state}</span> : null}</SelectItem>;
                })}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center justify-end gap-3 pl-1">
            <span className="hidden text-[11px] text-muted-foreground sm:inline">{t("playground.keyboardHelp")}</span>
            <ComposerPrimitive.Send asChild>
              <Button type="submit" size="icon" className="size-11 shrink-0 rounded-xl" aria-label={t("playground.sendMessage")}>
                {pending ? <LoaderCircle className="animate-spin" /> : <Send />}
              </Button>
            </ComposerPrimitive.Send>
          </div>
        </div>
      </ComposerPrimitive.Root>
    </div>
  );
}

function PlaygroundMessageText({ text }: TextMessagePartProps) {
  return <p className="whitespace-pre-wrap text-sm leading-6">{text}</p>;
}

function threadMessages(turns: PlaygroundTurn[]): PlaygroundThreadMessage[] {
  return turns.flatMap((turn) => [
    { id: `${turn.interaction_id}:user`, role: "user", content: turn.user_message },
    { id: `${turn.interaction_id}:assistant`, role: "assistant", content: turn.assistant_message ?? "", turn },
  ]);
}

function convertMessage(message: PlaygroundThreadMessage): ThreadMessageLike {
  return { id: message.id, role: message.role, content: message.content };
}
