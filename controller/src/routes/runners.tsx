import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Gauge, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { EntitySheet } from "@/components/entity-sheet";
import { EmptyState, ErrorNotice, Metric, PageHeader, StateBadge } from "@/components/product-shell";
import { ProtectedDeleteSheet } from "@/components/protected-delete-sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAuth } from "@/lib/auth";
import {
  listRunnerPools,
  removeRunnerInstance,
  updateRunnerPool,
  type RunnerInstance,
  type RunnerPool,
} from "@/lib/controller-api";

const runnerPoolKey = ["controller", "runner-pools"] as const;

export function RunnersPage() {
  const { t, i18n } = useTranslation();
  const auth = useAuth();
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: runnerPoolKey, queryFn: listRunnerPools, refetchInterval: 10_000 });
  const [editing, setEditing] = useState<RunnerPool | null>(null);
  const [removing, setRemoving] = useState<{ runner: RunnerInstance; poolName: string } | null>(null);

  return (
    <section className="py-6 sm:py-8">
      <PageHeader
        title={t("runners.title")}
        description={t("runners.description")}
      />
      {query.isLoading ? <Skeleton className="mt-6 h-80 rounded-xl" /> : null}
      {query.error ? <div className="mt-6"><ErrorNotice error={query.error} /></div> : null}
      {!query.isLoading && !query.error && !query.data?.items.length ? <div className="mt-6"><EmptyState title={t("runners.emptyTitle")} description={t("runners.emptyDescription")} /></div> : null}
      <div className="mt-6 grid gap-5">
        {(query.data?.items ?? []).map((pool) => (
          <Card key={pool.id}>
            <CardHeader className="border-b">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2">
                    <CardTitle>{pool.name}</CardTitle>
                    {pool.isDefault ? <Badge>Baseline</Badge> : null}
                  </div>
                  <CardDescription className="mt-2">
                    {t("runners.recommendation", { recommended: pool.capacity.recommendedReplicas, desired: pool.desiredReplicas })}
                  </CardDescription>
                </div>
                {auth.user?.role === "admin" ? (
                  <Button variant="outline" onClick={() => setEditing(pool)}>
                    <Gauge />{t("runners.capacitySettings")}
                  </Button>
                ) : null}
              </div>
            </CardHeader>
            <CardContent>
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
                <Metric label={t("runners.readyRunners")} value={`${pool.capacity.readyRunners}/${pool.capacity.totalRunners}`} />
                <Metric label="RPS" value={pool.capacity.currentRps.toFixed(1)} detail={`${t("runners.safeCapacity")} ${pool.capacity.safeRpsCapacity.toFixed(1)}`} />
                <Metric label={t("runners.inflightUtilization")} value={`${Math.round(pool.capacity.inflightUtilization * 100)}%`} />
                <Metric label="p95" value={`${Math.round(pool.capacity.latencyP95Ms)} ms`} />
                <Metric label={t("runners.errorRate")} value={`${(pool.capacity.errorRate * 100).toFixed(2)}%`} />
              </div>
              <Table className="mt-5">
                <TableHeader><TableRow><TableHead>Runner</TableHead><TableHead>{t("runners.columns.state")}</TableHead><TableHead>{t("runners.columns.generation")}</TableHead><TableHead>{t("runners.columns.inflightQueue")}</TableHead><TableHead>CPU / Memory</TableHead><TableHead>{t("runners.columns.lastHeartbeat")}</TableHead><TableHead className="w-14"><span className="sr-only">{t("runners.columns.actions")}</span></TableHead></TableRow></TableHeader>
                <TableBody>
                  {pool.instances.map((runner) => (
                    <TableRow key={runner.runnerId}>
                      <TableCell><code className="text-xs">{runner.runnerId}</code><p className="mt-1 text-xs text-muted-foreground">NeMo {runner.nemoVersion}{runner.compilerCapable ? " · compiler" : ""}</p></TableCell>
                      <TableCell><StateBadge state={runner.status} /></TableCell>
                      <TableCell className="font-mono text-xs">{runner.appliedGeneration}/{runner.desiredGeneration}</TableCell>
                      <TableCell>{runner.load?.inflight ?? 0} / {runner.load?.queueDepth ?? 0}</TableCell>
                      <TableCell>{Math.round((runner.load?.cpuUtilization ?? 0) * 100)}% / {Math.round((runner.load?.memoryUtilization ?? 0) * 100)}%</TableCell>
                      <TableCell className="text-xs text-muted-foreground">{formatDate(runner.lastHeartbeatAt, i18n.language)}</TableCell>
                      <TableCell className="text-right">
                        {auth.user?.role === "admin" && runner.status === "offline" ? <Button
                          type="button"
                          size="icon"
                          variant="ghost"
                          className="size-11 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                          aria-label={t("runners.removeAria", { runnerId: runner.runnerId })}
                          title={t("runners.removeOffline")}
                          onClick={() => setRemoving({ runner, poolName: pool.name })}
                        ><Trash2 /></Button> : null}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        ))}
      </div>
      <RunnerPoolSheet
        pool={editing}
        onOpenChange={(open) => { if (!open) setEditing(null); }}
        onSaved={async () => {
          setEditing(null);
          await queryClient.invalidateQueries({ queryKey: runnerPoolKey });
        }}
      />
      <RemoveRunnerSheet
        key={removing?.runner.runnerId ?? "closed"}
        target={removing}
        onOpenChange={(open) => { if (!open) setRemoving(null); }}
        onRemoved={async () => {
          setRemoving(null);
          await queryClient.invalidateQueries({ queryKey: runnerPoolKey });
        }}
      />
    </section>
  );
}

function RemoveRunnerSheet({
  target,
  onOpenChange,
  onRemoved,
}: {
  target: { runner: RunnerInstance; poolName: string } | null;
  onOpenChange: (open: boolean) => void;
  onRemoved: () => void;
}) {
  const { t, i18n } = useTranslation();
  const mutation = useMutation({
    mutationFn: () => removeRunnerInstance(target!.runner.runnerId),
    onSuccess: () => {
      toast.success(t("runners.removed"));
      onRemoved();
    },
  });

  if (!target) return null;
  const { runner, poolName } = target;
  return <ProtectedDeleteSheet
    open
    onOpenChange={onOpenChange}
    entityName={runner.runnerId}
    loading={false}
    ready={runner.status === "offline"}
    requiresConfirmation={false}
    deleting={mutation.isPending}
    error={mutation.error instanceof Error ? mutation.error : null}
    onRetry={() => mutation.reset()}
    onConfirm={() => mutation.mutate()}
    impactItems={[
      { label: t("runners.currentState"), value: t("runners.offline") },
      { label: t("runners.columns.lastHeartbeat"), value: formatDate(runner.lastHeartbeatAt, i18n.language) },
    ]}
    copy={{
      eyebrow: `${poolName} / ${runner.runnerId}`,
      title: t("runners.removal.title"),
      description: t("runners.removal.description"),
      protectedMessage: t("runners.removal.protectedMessage"),
      clearMessage: t("runners.removal.clearMessage"),
      retentionNote: t("runners.removal.retentionNote"),
      continueLabel: t("runners.removal.continue"),
      deleteLabel: t("runners.removal.delete"),
      deletingLabel: t("runners.removal.deleting"),
      confirmTitle: t("runners.removal.confirmTitle"),
      confirmDescription: runner.runnerId,
      confirmWarning: t("runners.removal.warning"),
      typeNameLabel: t("runners.removal.typeId"),
      protectedDeleteLabel: t("runners.removal.confirm"),
      cancelLabel: t("common.cancel"),
      backLabel: t("common.back"),
      retryLabel: t("common.retry"),
    }}
  />;
}

function RunnerPoolSheet({ pool, onOpenChange, onSaved }: { pool: RunnerPool | null; onOpenChange: (open: boolean) => void; onSaved: () => void }) {
  const { t } = useTranslation();
  const [desired, setDesired] = useState(1);
  const [safeRps, setSafeRps] = useState(50);
  const [concurrency, setConcurrency] = useState(64);

  useEffect(() => {
    if (!pool) return;
    setDesired(pool.desiredReplicas);
    setSafeRps(pool.safeRpsPerRunner);
    setConcurrency(pool.maxConcurrencyPerRunner);
  }, [pool]);

  const mutation = useMutation({
    mutationFn: () => updateRunnerPool(pool!.id, {
      desiredReplicas: desired,
      safeRpsPerRunner: safeRps,
      maxConcurrencyPerRunner: concurrency,
    }),
    onSuccess: () => {
      toast.success(t("runners.settingsSaved"));
      onSaved();
    },
    onError: (error) => toast.error(error.message),
  });

  if (!pool) return null;
  const minimumDesired = pool?.isDefault ? 2 : 1;
  const valid = Number.isInteger(desired) && desired >= minimumDesired
    && Number.isFinite(safeRps) && safeRps > 0
    && Number.isInteger(concurrency) && concurrency >= 1;
  return (
    <EntitySheet
      open
      onOpenChange={onOpenChange}
      eyebrow={pool.id}
      title={t("runners.settingsTitle")}
      description={t("runners.settingsDescription")}
      footer={<><Button variant="outline" onClick={() => onOpenChange(false)}>{t("common.cancel")}</Button><Button disabled={!valid || mutation.isPending} onClick={() => mutation.mutate()}>{t("common.save")}</Button></>}
    >
      <div className="grid gap-5">
        <NumberField label={t("runners.desiredReplicas")} value={desired} onChange={setDesired} min={minimumDesired} />
        <NumberField label={t("runners.safeRpsPerRunner")} value={safeRps} onChange={setSafeRps} min={0.1} />
        <NumberField label={t("runners.maxConcurrencyPerRunner")} value={concurrency} onChange={setConcurrency} min={1} />
      </div>
    </EntitySheet>
  );
}

function NumberField({ label, value, onChange, min }: { label: string; value: number; onChange: (value: number) => void; min: number }) {
  return <div className="grid gap-2"><Label>{label}</Label><Input type="number" min={min} value={value} onChange={(event) => onChange(Number(event.target.value))} /></div>;
}

function formatDate(value: string | null, locale: string) {
  return value ? new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "—";
}
