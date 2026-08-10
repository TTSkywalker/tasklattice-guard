import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, Building2, Cable, ChevronRight, Copy, KeyRound, Plus, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";

import { EntitySheet } from "@/components/entity-sheet";
import { EmptyState, ErrorNotice, InfoNotice, PageHeader, StateBadge } from "@/components/product-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { queryKeys } from "@/features/query-keys";
import { createIntegration, getIntegrations, getSystemStatus, type Integration } from "@/lib/api";

export function GatewaysPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: queryKeys.integrations, queryFn: getIntegrations });
  const summary = useQuery({ queryKey: queryKeys.systemStatus, queryFn: getSystemStatus, refetchInterval: 15_000 });
  const [createOpen, setCreateOpen] = useState(false);
  const [selected, setSelected] = useState<Integration | null>(null);
  const gateways = query.data?.items ?? [];
  const healthTone = summary.isLoading ? "checking" : summary.error || summary.data?.status === "degraded" ? "degraded" : "healthy";
  return (
    <section className="py-6 sm:py-8">
      <PageHeader
        eyebrow={t("gateways.eyebrow")}
        title={t("pages.gateways.title")}
        description={t("gateways.description")}
        action={<Button className="min-h-11 self-start" onClick={() => setCreateOpen(true)}><Plus />{t("gateways.register")}</Button>}
      />
      {query.error ? <div className="mt-5"><ErrorNotice error={query.error} /></div> : null}
      {query.isLoading ? <Skeleton className="mt-5 h-60 rounded-lg" /> : null}

      <section className="mt-5 overflow-hidden rounded-xl border bg-card">
        <div className="flex flex-col gap-3 border-b bg-muted/35 px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <span className={`size-2.5 shrink-0 rounded-full ${healthTone === "checking" ? "bg-muted-foreground/40" : healthTone === "degraded" ? "bg-amber-500" : "bg-emerald-500"}`} />
            <div>
              <h2 className="text-sm font-semibold">{t("gateways.systemHealth")}</h2>
              <p className="mt-0.5 text-xs text-muted-foreground">{t(healthTone === "checking" ? "gateways.healthChecking" : healthTone === "degraded" ? "gateways.healthDegraded" : "gateways.healthHealthy")}</p>
            </div>
          </div>
          <div className="flex gap-5 text-xs text-muted-foreground">
            <span className="flex items-center gap-1.5"><Building2 className="size-3.5" />{t("gateways.activeWorkloads", { count: summary.data?.active_workloads ?? "—" })}</span>
            <span className="flex items-center gap-1.5"><Activity className="size-3.5" />{t("gateways.onlineGateways", { online: summary.data?.online_gateways ?? "—", total: summary.data?.total_gateways ?? "—" })}</span>
          </div>
        </div>
        <div className="grid gap-px bg-border sm:grid-cols-3">
          <Capability name={t("gateways.localDetection")} ready />
          <Capability name={t("gateways.fastSemantic")} ready={Boolean(summary.data?.capabilities.fast_semantic)} />
          <Capability name={t("gateways.deepJudge")} ready={Boolean(summary.data?.capabilities.deep_judge)} />
        </div>
      </section>

      {gateways.length ? (
        <>
          <section className="mt-5 surface">
            <div className="hidden grid-cols-[minmax(0,1fr)_170px_170px_130px_28px] border-b bg-muted/40 px-5 py-3 text-xs font-medium text-muted-foreground md:grid"><span>{t("gateways.gateway")}</span><span>{t("gateways.environment")}</span><span>{t("gateways.traffic")}</span><span>{t("gateways.runtime")}</span><span /></div>
            <div className="divide-y divide-border">{gateways.map((gateway) => <button key={gateway.id} type="button" onClick={() => setSelected(gateway)} className="group relative grid min-h-20 w-full gap-4 p-5 text-left transition-colors hover:bg-muted/50 focus-visible:outline-2 focus-visible:outline-ring md:grid-cols-[minmax(0,1fr)_170px_170px_130px_28px] md:items-center"><div><span className="flex items-center gap-2"><Cable className="size-4 text-primary" /><strong className="text-sm font-medium">{gateway.name}</strong></span><span className="mt-1.5 block text-xs text-muted-foreground">{t(`gateways.protocols.${gateway.type}`)}</span></div><span className="text-xs capitalize">{gateway.environment}</span><span className="font-mono text-xs">{t("gateways.requestErrorCount", { requests: gateway.request_count, errors: gateway.error_count })}</span><StateBadge state={gateway.runtime_status} /><ChevronRight className="absolute right-4 top-5 size-4 text-muted-foreground md:static" /></button>)}</div>
          </section>
        </>
      ) : !query.isLoading ? <div className="mt-5"><EmptyState title={t("gateways.emptyTitle")} description={t("gateways.emptyDescription")} action={<Button onClick={() => setCreateOpen(true)}><Plus />{t("gateways.register")}</Button>} /></div> : null}

      <GatewayDetail gateway={selected} onOpenChange={(open) => !open && setSelected(null)} />
      <CreateGatewaySheet open={createOpen} onOpenChange={setCreateOpen} onCreated={async () => { setCreateOpen(false); await Promise.all([queryClient.invalidateQueries({ queryKey: queryKeys.integrations }), queryClient.invalidateQueries({ queryKey: queryKeys.systemStatus })]); }} />
    </section>
  );
}

function Capability({ name, ready }: { name: string; ready: boolean }) { const { t } = useTranslation(); return <div className="flex min-h-20 items-center gap-3 bg-card p-4"><ShieldCheck className="size-4 text-primary" /><div className="min-w-0 flex-1"><p className="text-xs font-medium">{name}</p><p className="mt-1 text-xs text-muted-foreground">{t(ready ? "gateways.available" : "gateways.notConfigured")}</p></div><StateBadge state={ready ? "ready" : "unavailable"} /></div>; }

function GatewayDetail({ gateway, onOpenChange }: { gateway: Integration | null; onOpenChange: (open: boolean) => void }) {
  const { t, i18n } = useTranslation();
  if (!gateway) return null;
  return <EntitySheet open onOpenChange={onOpenChange} eyebrow={t("gateways.details")} title={gateway.name} description={t("gateways.detailsDescription")} width="md" footer={<Button variant="outline" onClick={() => onOpenChange(false)}>{t("common.close")}</Button>}>
    <div className="space-y-5">
      <section className="overflow-hidden rounded-lg border bg-card"><div className="flex items-center justify-between border-b bg-muted/40 p-4"><div className="flex items-center gap-3"><span className="flex size-9 items-center justify-center rounded-lg bg-accent text-accent-foreground"><Cable className="size-4" /></span><div><p className="text-sm font-medium">{gateway.type.toUpperCase()}</p><p className="mt-0.5 text-xs capitalize text-muted-foreground">{gateway.environment}</p></div></div><StateBadge state={gateway.runtime_status} /></div><dl className="divide-y divide-border"><Detail label={t("gateways.id")} mono copyValue={gateway.id}>{gateway.id}</Detail><Detail label={t("gateways.protocol")}>{t(`gateways.protocols.${gateway.type}`)}</Detail><Detail label={t("gateways.credential")} mono>{gateway.credential_prefix || t("gateways.waitingCredential")}</Detail><Detail label={t("gateways.verification")}><StateBadge state={gateway.verification_status} /></Detail></dl></section>
      <section className="overflow-hidden rounded-lg border bg-card"><div className="border-b bg-muted/40 px-4 py-3"><h3 className="text-sm font-semibold">{t("gateways.runtimeActivity")}</h3></div><dl className="divide-y divide-border"><Detail label={t("gateways.requests")} mono>{gateway.request_count.toLocaleString(i18n.language)}</Detail><Detail label={t("gateways.errors")} mono>{gateway.error_count.toLocaleString(i18n.language)}</Detail><Detail label={t("gateways.lastActivity")}>{gateway.last_seen_at ? new Date(gateway.last_seen_at).toLocaleString(i18n.language) : t("gateways.noTraffic")}</Detail></dl></section>
      <InfoNotice title={t("gateways.trustedContext")}>{t("gateways.trustedContextDescription")}</InfoNotice>
    </div>
  </EntitySheet>;
}

function Detail({ children, copyValue, label, mono = false }: { children: React.ReactNode; copyValue?: string; label: string; mono?: boolean }) { return <div className="grid min-h-12 grid-cols-[120px_minmax(0,1fr)_auto] items-center gap-3 px-4 py-3"><dt className="text-xs font-medium text-muted-foreground">{label}</dt><dd className={mono ? "min-w-0 break-all font-mono text-xs" : "min-w-0 text-sm"}>{children}</dd>{copyValue ? <Button type="button" size="icon-sm" variant="ghost" aria-label={`Copy ${label}`} onClick={() => copyText(copyValue, label)}><Copy /></Button> : null}</div>; }

function CreateGatewaySheet({ open, onOpenChange, onCreated }: { open: boolean; onOpenChange: (open: boolean) => void; onCreated: () => void }) {
  const { t } = useTranslation();
  const [name, setName] = useState(""); const [description, setDescription] = useState(""); const [environment, setEnvironment] = useState<"production" | "staging" | "development" | "test">("production"); const [protocol, setProtocol] = useState<"litellm" | "http" | "a2a">("litellm"); const [credential, setCredential] = useState("");
  useEffect(() => { if (open) { setName(""); setDescription(""); setEnvironment("production"); setProtocol("litellm"); setCredential(""); } }, [open]);
  const mutation = useMutation({ mutationFn: () => createIntegration({ name, description, environment, protocol }), onSuccess: (result) => { setCredential(result.credential); toast.success(t("gateways.registered")); }, onError: (error) => toast.error(error instanceof Error ? error.message : t("gateways.registrationFailed")) });
  return <EntitySheet open={open} onOpenChange={(next) => { if (!next && credential) onCreated(); else onOpenChange(next); }} eyebrow={`Integration / ${protocol.toUpperCase()}`} title={t(credential ? "gateways.credentialTitle" : "gateways.register")} description={t(credential ? "gateways.credentialDescription" : "gateways.registerDescription")} footer={credential ? <Button onClick={onCreated}>{t("gateways.done")}</Button> : <><Button variant="outline" onClick={() => onOpenChange(false)}>{t("common.cancel")}</Button><Button disabled={!name.trim() || mutation.isPending} onClick={() => mutation.mutate()}><Plus />{t(mutation.isPending ? "gateways.registering" : "gateways.register")}</Button></>}>
    {credential ? <div className="rounded-lg border border-primary/20 bg-primary/5 p-5"><p className="flex items-center gap-2 text-xs font-medium text-primary"><KeyRound className="size-4" />{t("gateways.oneTimeCredential")}</p><code className="mt-3 block break-all rounded-md border bg-card p-4 font-mono text-xs leading-6">{credential}</code><Button variant="outline" className="mt-3 min-h-11" onClick={() => copyText(credential, t("gateways.credential"))}><Copy />{t("gateways.copyCredential")}</Button></div> : <div className="grid gap-5"><Field label={t("common.name")}><Input autoFocus className="min-h-11 rounded-lg bg-card" value={name} onChange={(event) => setName(event.target.value)} placeholder="Corporate AI ingress" /></Field><Field label={t("gateways.integrationProtocol")}><Select value={protocol} onValueChange={(value) => setProtocol(value as typeof protocol)}><SelectTrigger className="min-h-11 rounded-lg bg-card"><SelectValue /></SelectTrigger><SelectContent className="rounded-lg"><SelectItem value="litellm">{t("gateways.protocols.litellm")}</SelectItem><SelectItem value="http">{t("gateways.protocols.http")}</SelectItem><SelectItem value="a2a">{t("gateways.protocols.a2a")}</SelectItem></SelectContent></Select></Field><Field label={t("gateways.environment")}><Select value={environment} onValueChange={(value) => setEnvironment(value as typeof environment)}><SelectTrigger className="min-h-11 rounded-lg bg-card"><SelectValue /></SelectTrigger><SelectContent className="rounded-lg"><SelectItem value="production">Production</SelectItem><SelectItem value="staging">Staging</SelectItem><SelectItem value="development">Development</SelectItem><SelectItem value="test">Test</SelectItem></SelectContent></Select></Field><Field label={t("gateways.descriptionLabel")}><Textarea className="min-h-28 rounded-lg bg-card" value={description} onChange={(event) => setDescription(event.target.value)} placeholder={t("gateways.descriptionPlaceholder")} /></Field></div>}
  </EntitySheet>;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) { return <label className="grid gap-2 text-sm font-medium">{label}{children}</label>; }
function copyText(value: string, label: string) { navigator.clipboard.writeText(value).then(() => toast.success(`${label} copied.`)).catch(() => toast.error(`${label} could not be copied.`)); }
