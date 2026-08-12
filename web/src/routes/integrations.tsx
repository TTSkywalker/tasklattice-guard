import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Cable, ChevronRight, Copy, KeyRound, Plus } from "lucide-react";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";

import { EntitySheet } from "@/components/entity-sheet";
import { EmptyState, ErrorNotice, InfoNotice, PageHeader, StateBadge } from "@/components/product-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { queryKeys } from "@/features/query-keys";
import { createIntegration, getIntegrations, type Integration } from "@/lib/api";

export function IntegrationsPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: queryKeys.integrations, queryFn: getIntegrations });
  const [createOpen, setCreateOpen] = useState(false);
  const [selected, setSelected] = useState<Integration | null>(null);
  const integrations = query.data?.items ?? [];
  return (
    <section className="py-6 sm:py-8">
      <PageHeader
        title={t("pages.integrations.title")}
        description={t("integrations.description")}
        action={<Button className="min-h-11 self-start" onClick={() => setCreateOpen(true)}><Plus />{t("integrations.register")}</Button>}
      />
      {query.error ? <div className="mt-5"><ErrorNotice error={query.error} /></div> : null}
      {query.isLoading ? <Skeleton className="mt-5 h-60 rounded-lg" /> : null}

      {integrations.length ? (
        <>
          <section className="mt-5 surface">
            <div className="hidden grid-cols-[minmax(0,1fr)_170px_170px_130px_28px] border-b bg-muted/40 px-5 py-3 text-xs font-medium text-muted-foreground md:grid"><span>{t("integrations.integration")}</span><span>{t("integrations.environment")}</span><span>{t("integrations.traffic")}</span><span>{t("integrations.runtime")}</span><span /></div>
            <div className="divide-y divide-border">{integrations.map((integration) => <button key={integration.id} type="button" onClick={() => setSelected(integration)} className="group relative grid min-h-20 w-full gap-4 p-5 text-left transition-colors hover:bg-muted/50 focus-visible:outline-2 focus-visible:outline-ring md:grid-cols-[minmax(0,1fr)_170px_170px_130px_28px] md:items-center"><div><span className="flex items-center gap-2"><Cable className="size-4 text-primary" /><strong className="text-sm font-medium">{integration.name}</strong></span><span className="mt-1.5 block text-xs text-muted-foreground">{t(`integrations.protocols.${integration.protocol}`)}</span></div><span className="text-xs capitalize">{integration.environment}</span><span className="font-mono text-xs">{t("integrations.requestErrorCount", { requests: integration.request_count, errors: integration.error_count })}</span><StateBadge state={integration.runtime_status} /><ChevronRight className="absolute right-4 top-5 size-4 text-muted-foreground md:static" /></button>)}</div>
          </section>
        </>
      ) : !query.isLoading ? <div className="mt-5"><EmptyState title={t("integrations.emptyTitle")} description={t("integrations.emptyDescription")} action={<Button onClick={() => setCreateOpen(true)}><Plus />{t("integrations.register")}</Button>} /></div> : null}

      <IntegrationDetail integration={selected} onOpenChange={(open) => !open && setSelected(null)} />
      <CreateIntegrationSheet open={createOpen} onOpenChange={setCreateOpen} onCreated={async () => { setCreateOpen(false); await Promise.all([queryClient.invalidateQueries({ queryKey: queryKeys.integrations }), queryClient.invalidateQueries({ queryKey: queryKeys.systemStatus })]); }} />
    </section>
  );
}

function IntegrationDetail({ integration, onOpenChange }: { integration: Integration | null; onOpenChange: (open: boolean) => void }) {
  const { t, i18n } = useTranslation();
  if (!integration) return null;
  return <EntitySheet open onOpenChange={onOpenChange} eyebrow={t("integrations.details")} title={integration.name} description={t("integrations.detailsDescription")} width="md" footer={<Button variant="outline" onClick={() => onOpenChange(false)}>{t("common.close")}</Button>}>
    <div className="space-y-5">
      <section className="overflow-hidden rounded-lg border bg-card"><div className="flex items-center justify-between border-b bg-muted/40 p-4"><div className="flex items-center gap-3"><span className="flex size-9 items-center justify-center rounded-lg bg-accent text-accent-foreground"><Cable className="size-4" /></span><div><p className="text-sm font-medium">{integration.protocol.toUpperCase()}</p><p className="mt-0.5 text-xs capitalize text-muted-foreground">{integration.environment}</p></div></div><StateBadge state={integration.runtime_status} /></div><dl className="divide-y divide-border"><Detail label={t("integrations.id")} mono copyValue={integration.id}>{integration.id}</Detail><Detail label={t("integrations.protocol")}>{t(`integrations.protocols.${integration.protocol}`)}</Detail><Detail label={t("integrations.credential")} mono>{integration.credential_prefix || t("integrations.waitingCredential")}</Detail><Detail label={t("integrations.verification")}><StateBadge state={integration.verification_status} /></Detail></dl></section>
      <section className="overflow-hidden rounded-lg border bg-card"><div className="border-b bg-muted/40 px-4 py-3"><h3 className="text-sm font-semibold">{t("integrations.runtimeActivity")}</h3></div><dl className="divide-y divide-border"><Detail label={t("integrations.requests")} mono>{integration.request_count.toLocaleString(i18n.language)}</Detail><Detail label={t("integrations.errors")} mono>{integration.error_count.toLocaleString(i18n.language)}</Detail><Detail label={t("integrations.lastActivity")}>{integration.last_seen_at ? new Date(integration.last_seen_at).toLocaleString(i18n.language) : t("integrations.noTraffic")}</Detail></dl></section>
      <InfoNotice title={t("integrations.trustedContext")}>{t("integrations.trustedContextDescription")}</InfoNotice>
    </div>
  </EntitySheet>;
}

function Detail({ children, copyValue, label, mono = false }: { children: React.ReactNode; copyValue?: string; label: string; mono?: boolean }) { return <div className="grid min-h-12 grid-cols-[120px_minmax(0,1fr)_auto] items-center gap-3 px-4 py-3"><dt className="text-xs font-medium text-muted-foreground">{label}</dt><dd className={mono ? "min-w-0 break-all font-mono text-xs" : "min-w-0 text-sm"}>{children}</dd>{copyValue ? <Button type="button" size="icon-sm" variant="ghost" aria-label={`Copy ${label}`} onClick={() => copyText(copyValue, label)}><Copy /></Button> : null}</div>; }

function CreateIntegrationSheet({ open, onOpenChange, onCreated }: { open: boolean; onOpenChange: (open: boolean) => void; onCreated: () => void }) {
  const { t } = useTranslation();
  const [name, setName] = useState(""); const [environment, setEnvironment] = useState<"production" | "staging" | "development" | "test">("production"); const [protocol, setProtocol] = useState<"litellm" | "http" | "a2a">("litellm"); const [credential, setCredential] = useState("");
  useEffect(() => { if (open) { setName(""); setEnvironment("production"); setProtocol("litellm"); setCredential(""); } }, [open]);
  const mutation = useMutation({ mutationFn: () => createIntegration({ name, environment, protocol }), onSuccess: (result) => { setCredential(result.credential); toast.success(t("integrations.registered")); }, onError: (error) => toast.error(error instanceof Error ? error.message : t("integrations.registrationFailed")) });
  return <EntitySheet open={open} onOpenChange={(next) => { if (!next && credential) onCreated(); else onOpenChange(next); }} eyebrow={`Integration / ${protocol.toUpperCase()}`} title={t(credential ? "integrations.credentialTitle" : "integrations.register")} description={t(credential ? "integrations.credentialDescription" : "integrations.registerDescription")} footer={credential ? <Button onClick={onCreated}>{t("integrations.done")}</Button> : <><Button variant="outline" onClick={() => onOpenChange(false)}>{t("common.cancel")}</Button><Button disabled={!name.trim() || mutation.isPending} onClick={() => mutation.mutate()}><Plus />{t(mutation.isPending ? "integrations.registering" : "integrations.register")}</Button></>}>
    {credential ? <div className="rounded-lg border border-primary/20 bg-primary/5 p-5"><p className="flex items-center gap-2 text-xs font-medium text-primary"><KeyRound className="size-4" />{t("integrations.oneTimeCredential")}</p><code className="mt-3 block break-all rounded-md border bg-card p-4 font-mono text-xs leading-6">{credential}</code><Button variant="outline" className="mt-3 min-h-11" onClick={() => copyText(credential, t("integrations.credential"))}><Copy />{t("integrations.copyCredential")}</Button></div> : <div className="grid gap-5"><Field label={t("integrations.name")}><Input autoFocus className="min-h-11 rounded-lg bg-card" value={name} onChange={(event) => setName(event.target.value)} placeholder="Corporate AI ingress" /></Field><Field label={t("integrations.integrationProtocol")}><Select value={protocol} onValueChange={(value) => setProtocol(value as typeof protocol)}><SelectTrigger className="min-h-11 rounded-lg bg-card"><SelectValue /></SelectTrigger><SelectContent className="rounded-lg"><SelectItem value="litellm">{t("integrations.protocols.litellm")}</SelectItem><SelectItem value="http">{t("integrations.protocols.http")}</SelectItem><SelectItem value="a2a">{t("integrations.protocols.a2a")}</SelectItem></SelectContent></Select></Field><Field label={t("integrations.environment")}><Select value={environment} onValueChange={(value) => setEnvironment(value as typeof environment)}><SelectTrigger className="min-h-11 rounded-lg bg-card"><SelectValue /></SelectTrigger><SelectContent className="rounded-lg"><SelectItem value="production">Production</SelectItem><SelectItem value="staging">Staging</SelectItem><SelectItem value="development">Development</SelectItem><SelectItem value="test">Test</SelectItem></SelectContent></Select></Field></div>}
  </EntitySheet>;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) { return <label className="grid gap-2 text-sm font-medium">{label}{children}</label>; }
function copyText(value: string, label: string) { navigator.clipboard.writeText(value).then(() => toast.success(`${label} copied.`)).catch(() => toast.error(`${label} could not be copied.`)); }
