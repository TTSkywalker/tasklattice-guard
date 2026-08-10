import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import type { TFunction } from "i18next";
import {
  Bot,
  CheckCircle2,
  CircleSlash2,
  Eraser,
  FlaskConical,
  LoaderCircle,
  MessageSquareText,
  Send,
  ShieldAlert,
  UserRound,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { EmptyState, ErrorNotice, PageHeader, StateBadge } from "@/components/product-shell";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { queryKeys } from "@/features/query-keys";
import {
  createEvaluation,
  getSafes,
  type PlaygroundEvaluation,
  type PlaygroundMessage,
  type Safe,
} from "@/lib/api";
import { cn } from "@/lib/utils";

type EvaluatedTurn = PlaygroundMessage & {
  id: string;
  evaluation: PlaygroundEvaluation;
};

type PendingTurn = PlaygroundMessage & {
  id: string;
  safe_id: string;
  messages: PlaygroundMessage[];
};

export function ConversationPlaygroundPage() {
  const { t } = useTranslation();
  const profilesQuery = useQuery({ queryKey: queryKeys.safes, queryFn: getSafes });
  const profiles = profilesQuery.data?.items ?? [];
  const [profileId, setProfileId] = useState("");
  const [role, setRole] = useState<PlaygroundMessage["role"]>("user");
  const [draft, setDraft] = useState("");
  const [turns, setTurns] = useState<EvaluatedTurn[]>([]);
  const [selectedTurnId, setSelectedTurnId] = useState<string | null>(null);
  const conversationRef = useRef<HTMLDivElement>(null);

  const selectedProfile = profiles.find((item) => item.id === profileId) ?? null;
  const selectedTurn = turns.find((item) => item.id === selectedTurnId) ?? null;

  useEffect(() => {
    if (!profiles.length) return;
    if (!profiles.some((item) => item.id === profileId)) {
      const preferred = profiles.find((item) => item.status === "protected")
        ?? profiles.find((item) => item.status === "ready")
        ?? profiles[0];
      setProfileId(preferred.id);
    }
  }, [profileId, profiles]);

  useEffect(() => {
    const container = conversationRef.current;
    if (container) container.scrollTop = container.scrollHeight;
  }, [turns]);

  const evaluation = useMutation({
    mutationFn: ({ id: _id, ...input }: PendingTurn) => createEvaluation(input),
    onSuccess: (result, pending) => {
      const turn: EvaluatedTurn = {
        id: pending.id,
        role: pending.role,
        content: pending.content,
        evaluation: result,
      };
      setTurns((current) => [...current, turn]);
      setSelectedTurnId(turn.id);
      setDraft("");
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : t("playground.evaluationFailed"));
    },
  });

  function changeProfile(nextProfileId: string) {
    setProfileId(nextProfileId);
    clearConversation();
  }

  function clearConversation() {
    setTurns([]);
    setSelectedTurnId(null);
    setDraft("");
    evaluation.reset();
  }

  function submit() {
    const content = draft.trim();
    if (!profileId || !content || evaluation.isPending) return;
    evaluation.mutate({
      id: crypto.randomUUID(),
      safe_id: profileId,
      role,
      content,
      messages: turns.map(({ role: turnRole, content: turnContent }) => ({
        role: turnRole,
        content: turnContent,
      })),
    });
  }

  return (
    <section className="py-6 sm:py-8">
      <PageHeader
        eyebrow={t("playground.eyebrow")}
        title={t("pages.playground.title")}
        description={t("playground.description")}
        action={
          <Button
            variant="outline"
            className="min-h-11 self-start bg-card"
            disabled={!turns.length || evaluation.isPending}
            onClick={clearConversation}
          >
            <Eraser />
            {t("playground.clearConversation")}
          </Button>
        }
      />

      {profilesQuery.error ? <div className="mt-5"><ErrorNotice error={profilesQuery.error} /></div> : null}
      {profilesQuery.isLoading ? <Skeleton className="mt-5 h-[660px] rounded-xl" /> : null}

      {!profilesQuery.isLoading && !profiles.length ? (
        <div className="mt-5">
          <EmptyState title={t("playground.noProfilesTitle")} description={t("playground.noProfilesDescription")} />
        </div>
      ) : null}

      {profiles.length ? (
        <>
          <ProfileSelector
            disabled={evaluation.isPending}
            profile={selectedProfile}
            profileId={profileId}
            profiles={profiles}
            onChange={changeProfile}
          />

          <div className="mt-4 grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1.45fr)_minmax(340px,0.75fr)] xl:items-start">
            <section className="surface flex min-h-[650px] min-w-0 flex-col" aria-label={t("playground.conversation")}>
              <div className="surface-header flex items-center justify-between gap-3">
                <div>
                  <h2 className="flex items-center gap-2 text-sm font-semibold"><MessageSquareText className="size-4 text-primary" />{t("playground.conversation")}</h2>
                  <p className="mt-1 text-xs text-muted-foreground">{t("playground.conversationHint")}</p>
                </div>
                <span className="font-mono text-xs text-muted-foreground">{t("playground.turnCount", { count: turns.length })}</span>
              </div>

              <div ref={conversationRef} className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4 sm:p-5" aria-live="polite">
                {!turns.length ? <ConversationEmpty /> : null}
                {turns.map((turn, index) => (
                  <ConversationTurn
                    key={turn.id}
                    index={index}
                    selected={turn.id === selectedTurnId}
                    turn={turn}
                    onSelect={() => setSelectedTurnId(turn.id)}
                  />
                ))}
                {evaluation.isPending ? <PendingEvaluation role={role} contextCount={turns.length} /> : null}
              </div>

              <div className="border-t bg-card p-4 sm:p-5">
                <div className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div role="group" aria-label={t("playground.messageRole")} className="inline-flex w-fit rounded-lg border bg-muted/40 p-1">
                    <RoleButton active={role === "user"} icon={UserRound} onClick={() => setRole("user")}>{t("playground.userInput")}</RoleButton>
                    <RoleButton active={role === "assistant"} icon={Bot} onClick={() => setRole("assistant")}>{t("playground.assistantOutput")}</RoleButton>
                  </div>
                  <p className="text-xs text-muted-foreground">{t(role === "user" ? "playground.inputPhaseHint" : "playground.outputPhaseHint")}</p>
                </div>

                <Textarea
                  aria-label={t(role === "user" ? "playground.userInput" : "playground.assistantOutput")}
                  className="min-h-28 resize-y rounded-lg bg-background"
                  disabled={!profileId || evaluation.isPending}
                  value={draft}
                  placeholder={t(role === "user" ? "playground.inputPlaceholder" : "playground.outputPlaceholder")}
                  onChange={(event) => {
                    setDraft(event.target.value);
                    if (evaluation.error) evaluation.reset();
                  }}
                  onKeyDown={(event) => {
                    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
                      event.preventDefault();
                      submit();
                    }
                  }}
                />
                {evaluation.error ? <div className="mt-3"><ErrorNotice error={evaluation.error} /></div> : null}
                <div className="mt-3 flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <p className="text-xs leading-5 text-muted-foreground">{t("playground.ephemeralHint")}</p>
                  <Button className="min-h-11" disabled={!profileId || !draft.trim() || evaluation.isPending} onClick={submit}>
                    {evaluation.isPending ? <LoaderCircle className="animate-spin" /> : <Send />}
                    {t(evaluation.isPending ? "playground.evaluating" : "playground.evaluateTurn")}
                  </Button>
                </div>
              </div>
            </section>

            <EvidencePanel turn={selectedTurn} />
          </div>
        </>
      ) : null}
    </section>
  );
}

function ProfileSelector({
  disabled,
  onChange,
  profile,
  profileId,
  profiles,
}: {
  disabled: boolean;
  onChange: (value: string) => void;
  profile: Safe | null;
  profileId: string;
  profiles: Safe[];
}) {
  const { t } = useTranslation();
  return (
    <section className="mt-5 flex flex-col gap-4 rounded-xl border bg-card p-4 shadow-[var(--shadow-surface)] lg:flex-row lg:items-center lg:justify-between">
      <div className="flex min-w-0 items-start gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-accent text-accent-foreground"><FlaskConical className="size-4.5" /></span>
        <div className="min-w-0">
          <h2 className="text-sm font-semibold">{t("playground.profileUnderReview")}</h2>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">{t("playground.currentRulesHint")}</p>
        </div>
      </div>
      <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-center">
        <Select disabled={disabled} value={profileId} onValueChange={onChange}>
          <SelectTrigger aria-label={t("playground.selectProfile")} className="h-11 min-w-0 bg-background sm:w-[320px]"><SelectValue placeholder={t("playground.selectProfile")} /></SelectTrigger>
          <SelectContent>{profiles.map((item) => <SelectItem key={item.id} value={item.id}>{item.name}</SelectItem>)}</SelectContent>
        </Select>
        {profile ? <StateBadge state={profile.status} /> : null}
      </div>
    </section>
  );
}

function RoleButton({ active, children, icon: Icon, onClick }: { active: boolean; children: React.ReactNode; icon: typeof UserRound; onClick: () => void }) {
  return <Button type="button" size="sm" variant={active ? "secondary" : "ghost"} className={cn("min-h-9 shadow-none", active && "bg-card ring-1 ring-border")} aria-pressed={active} onClick={onClick}><Icon />{children}</Button>;
}

function ConversationEmpty() {
  const { t } = useTranslation();
  return (
    <div className="flex flex-1 items-center justify-center py-12 text-center">
      <div className="max-w-md">
        <span className="mx-auto grid size-11 place-items-center rounded-full bg-muted text-muted-foreground"><MessageSquareText className="size-5" /></span>
        <h3 className="mt-4 text-base font-semibold">{t("playground.emptyConversationTitle")}</h3>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">{t("playground.emptyConversationDescription")}</p>
      </div>
    </div>
  );
}

function PendingEvaluation({ contextCount, role }: { contextCount: number; role: PlaygroundMessage["role"] }) {
  const { t } = useTranslation();
  return (
    <div className={cn("flex", role === "user" ? "justify-end" : "justify-start")}>
      <div className="flex min-h-20 w-full max-w-[78%] items-center gap-3 rounded-xl border border-dashed bg-muted/30 px-4 py-3 text-sm text-muted-foreground">
        <LoaderCircle className="size-4 shrink-0 animate-spin text-primary" />
        <span>{t("playground.evaluatingContext", { count: contextCount })}</span>
      </div>
    </div>
  );
}

function ConversationTurn({ index, onSelect, selected, turn }: { index: number; onSelect: () => void; selected: boolean; turn: EvaluatedTurn }) {
  const { t } = useTranslation();
  const user = turn.role === "user";
  return (
    <div className={cn("flex", user ? "justify-end" : "justify-start")}>
      <button
        type="button"
        aria-pressed={selected}
        onClick={onSelect}
        className={cn(
          "w-full max-w-[88%] rounded-xl border p-4 text-left outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring/40 sm:max-w-[78%]",
          user ? "border-primary/15 bg-accent/70" : "bg-card",
          selected && "border-primary/45 ring-2 ring-primary/10",
        )}
      >
        <span className="flex items-center justify-between gap-3">
          <span className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
            {user ? <UserRound className="size-3.5" /> : <Bot className="size-3.5" />}
            {t(user ? "playground.userInput" : "playground.assistantOutput")} · {index + 1}
          </span>
          <StateBadge state={turn.evaluation.decision} />
        </span>
        <span className="mt-3 block whitespace-pre-wrap break-words text-sm leading-6">{turn.content}</span>
        <span className="mt-3 block border-t border-border/70 pt-3 text-xs leading-5 text-muted-foreground">{turn.evaluation.reason}</span>
      </button>
    </div>
  );
}

function EvidencePanel({ turn }: { turn: EvaluatedTurn | null }) {
  const { t } = useTranslation();
  return (
    <aside className="surface min-w-0 xl:sticky xl:top-20" aria-label={t("playground.evidence")}>
      <div className="surface-header">
        <h2 className="flex items-center gap-2 text-sm font-semibold"><ShieldAlert className="size-4 text-primary" />{t("playground.evidence")}</h2>
        <p className="mt-1 text-xs text-muted-foreground">{t("playground.evidenceHint")}</p>
      </div>
      {!turn ? (
        <div className="flex min-h-64 items-center justify-center p-6 text-center">
          <div className="max-w-xs">
            <CircleSlash2 className="mx-auto size-6 text-muted-foreground/60" />
            <p className="mt-3 text-sm font-medium">{t("playground.noEvidenceTitle")}</p>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">{t("playground.noEvidenceDescription")}</p>
          </div>
        </div>
      ) : <Evidence turn={turn} />}
    </aside>
  );
}

function Evidence({ turn }: { turn: EvaluatedTurn }) {
  const { t } = useTranslation();
  const result = turn.evaluation;
  const transformed = result.content !== turn.content;
  return (
    <div className="divide-y divide-border">
      <section className="p-4 sm:p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs font-medium text-muted-foreground">{t("playground.finalDecision")}</p>
            <p className="mt-1 text-lg font-semibold">{decisionLabel(result.decision, t)}</p>
          </div>
          <StateBadge state={result.decision} />
        </div>
        <dl className="mt-4 grid grid-cols-2 gap-3 text-xs">
          <EvidenceFact label={t("playground.phase")} value={t(result.phase === "input" ? "playground.inputPhase" : "playground.outputPhase")} />
          <EvidenceFact label={t("playground.action")} value={actionLabel(result.action, t)} />
          <EvidenceFact label={t("playground.profile")} value={result.safe_name} />
          <EvidenceFact label={t("playground.contextTurns")} value={String(result.evaluated_context_count)} />
        </dl>
        <p className="mt-4 text-xs leading-5 text-muted-foreground">{result.reason}</p>
      </section>

      {transformed ? (
        <section className="p-4 sm:p-5">
          <h3 className="text-xs font-semibold">{t("playground.appliedContent")}</h3>
          <p className="mt-2 rounded-lg border bg-muted/40 p-3 text-xs leading-5">{result.content}</p>
        </section>
      ) : null}

      <section className="p-4 sm:p-5">
        <h3 className="text-xs font-semibold">{t("playground.findings")}</h3>
        {result.findings.length ? (
          <div className="mt-3 space-y-3">
            {result.findings.map((finding, index) => (
              <div key={`${finding.risk}-${index}`} className="border-l-2 border-amber-400 pl-3">
                <div className="flex items-center justify-between gap-3"><p className="text-xs font-medium">{riskLabel(finding.risk, t)}</p><span className="font-mono text-[11px] text-muted-foreground">{Math.round(finding.confidence * 100)}%</span></div>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">{finding.evidence}</p>
              </div>
            ))}
          </div>
        ) : <p className="mt-2 flex items-center gap-2 text-xs text-muted-foreground"><CheckCircle2 className="size-3.5 text-emerald-600" />{t("playground.noFindings")}</p>}
      </section>

      <section className="p-4 sm:p-5">
        <h3 className="text-xs font-semibold">{t("playground.executionTrace")}</h3>
        <ol className="mt-3 space-y-0">
          {result.trace.map((step, index) => (
            <li key={`${step.id}-${index}`} className="relative grid grid-cols-[18px_minmax(0,1fr)] gap-3 pb-4 last:pb-0">
              {index < result.trace.length - 1 ? <span className="absolute left-[8px] top-4 h-full w-px bg-border" /> : null}
              <span className={cn("relative z-10 mt-0.5 size-[18px] rounded-full border-4 border-card", step.status === "safe" ? "bg-emerald-500" : step.status === "unsafe" || step.status === "error" ? "bg-destructive" : "bg-muted-foreground/40")} />
              <div className="min-w-0">
                <div className="flex items-center justify-between gap-3"><p className="text-xs font-medium">{stageLabel(step.stage, step.name, t)}</p><span className="font-mono text-[10px] text-muted-foreground">{step.duration_ms} ms</span></div>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">{step.detail}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}

function EvidenceFact({ label, value }: { label: string; value: string }) {
  return <div className="rounded-lg bg-muted/55 p-3"><dt className="text-muted-foreground">{label}</dt><dd className="mt-1 break-words font-medium">{value}</dd></div>;
}

function decisionLabel(decision: PlaygroundEvaluation["decision"], t: TFunction) {
  return t({ allow: "playground.allowed", transform: "playground.intervened", block: "playground.blocked" }[decision]);
}

function actionLabel(action: string, t: TFunction) {
  const labels: Record<string, string> = {
    pass: "states.pass",
    redirect: "states.redirect",
    reject: "states.reject",
    transform: "states.transform",
    redact: "profiles.actionRedact",
    rewrite: "profiles.actionRewrite",
    regenerate: "profiles.actionRegenerate",
    fallback: "profiles.actionFallback",
  };
  return labels[action] ? t(labels[action]) : action.replaceAll("_", " ");
}

function stageLabel(stage: string | null | undefined, fallback: string, t: TFunction) {
  const labels: Record<string, string> = {
    deterministic: "playground.stages.deterministic",
    fast_semantic: "playground.stages.fast_semantic",
    deep_judge: "playground.stages.deep_judge",
  };
  return stage && labels[stage] ? t(labels[stage]) : fallback;
}

function riskLabel(risk: string, t: TFunction) {
  const labels: Record<string, string> = {
    topic_control: "profiles.riskTopic",
    pii: "profiles.riskPii",
    secrets: "profiles.riskSecrets",
    prompt_injection: "profiles.riskInjection",
    jailbreak: "profiles.riskJailbreak",
    unsafe_content: "profiles.riskUnsafe",
    company_policy: "profiles.riskCompany",
    builtin_content_filter: "profiles.riskBuiltin",
  };
  return labels[risk] ? t(labels[risk]) : risk.replaceAll("_", " ");
}
