import { useEffect, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "@tanstack/react-router";
import { ArrowLeft, Check, FlaskConical, History, LoaderCircle, Pencil, Plus, Rocket, Save, ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { EntitySheet } from "@/components/entity-sheet";
import { PolicyBindingEditor } from "@/components/policy-binding-editor";
import { EmptyState, ErrorNotice, InfoNotice, Metric, PageHeader, StateBadge } from "@/components/product-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { queryKeys } from "@/features/query-keys";
import {
  createTestCase,
  getDeployments,
  getGuardrail,
  getGuardrails,
  getGuardrailVersions,
  getPolicies,
  getTestCases,
  rollbackGuardrail,
  updateGuardrail,
  type Guardrail,
  type GuardrailPolicyBinding,
  type GuardrailVersion,
  type Policy,
  type TestCase,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { CreateGuardrailWizard } from "@/routes/create-guardrail-wizard";
import { CreateDeploymentSheet } from "@/routes/deployments";

const EMPTY_POLICIES: Policy[] = [];

export function GuardrailsPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: queryKeys.guardrails, queryFn: getGuardrails });
  const [createOpen, setCreateOpen] = useState(false);
  const guardrails = [...(query.data?.items ?? [])].sort((left, right) => Number(right.is_default) - Number(left.is_default));

  return (
    <section className="py-6 sm:py-8">
      <PageHeader title={t("pages.guardrails.title")} description={t("guardrails.description")} action={<Button className="min-h-11" onClick={() => setCreateOpen(true)}><Plus />{t("guardrails.create")}</Button>} />
      {query.error ? <div className="mt-5"><ErrorNotice error={query.error} /></div> : null}
      {query.isLoading ? <Skeleton className="mt-5 h-80 rounded-xl" /> : null}
      {!query.isLoading && !guardrails.length ? <div className="mt-5"><EmptyState title={t("guardrails.emptyTitle")} description={t("guardrails.emptyDescription")} action={<Button onClick={() => setCreateOpen(true)}><Plus />{t("guardrails.createFirst")}</Button>} /></div> : null}
      {guardrails.length ? (
        <section className="mt-5 overflow-hidden rounded-xl border bg-card shadow-xs">
          <header className="border-b bg-muted/25 px-5 py-3"><p className="text-xs font-medium text-muted-foreground">{t("guardrails.registry", { count: guardrails.length })}</p></header>
          <Table>
            <TableHeader><TableRow className="hover:bg-transparent"><TableHead className="min-w-64 px-5">{t("guardrails.guardrail")}</TableHead><TableHead>{t("common.status")}</TableHead><TableHead className="hidden md:table-cell">{t("guardrails.policies")}</TableHead><TableHead className="hidden lg:table-cell">{t("guardrails.validation")}</TableHead><TableHead className="hidden xl:table-cell">{t("guardrails.updated")}</TableHead></TableRow></TableHeader>
            <TableBody>{guardrails.map((guardrail) => (
              <TableRow key={guardrail.id} tabIndex={0} className="cursor-pointer focus-visible:outline-2 focus-visible:outline-ring" onClick={() => navigate({ to: "/guardrails/$guardrailId", params: { guardrailId: guardrail.id } })} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") navigate({ to: "/guardrails/$guardrailId", params: { guardrailId: guardrail.id } }); }}>
                <TableCell className="px-5"><span className="flex items-start gap-3"><span className="grid size-9 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary"><ShieldCheck className="size-4" /></span><span className="min-w-0"><strong className="block truncate text-sm">{guardrail.name}</strong><span className="mt-1 line-clamp-1 text-xs text-muted-foreground">{guardrail.purpose}</span></span></span></TableCell>
                <TableCell><StateBadge state={guardrail.status} /></TableCell>
                <TableCell className="hidden font-mono text-xs md:table-cell">{guardrail.policy_bindings.length}</TableCell>
                <TableCell className="hidden lg:table-cell">{guardrail.latest_validation_run ? <span className="flex items-center gap-2"><StateBadge state={guardrail.latest_validation_run.status} /><span className="font-mono text-xs text-muted-foreground">{guardrail.latest_validation_run.metrics.compliance_rate}%</span></span> : <span className="text-xs text-muted-foreground">{t("guardrails.notRun")}</span>}</TableCell>
                <TableCell className="hidden text-xs text-muted-foreground xl:table-cell">{new Date(guardrail.updated_at).toLocaleString(i18n.language)}</TableCell>
              </TableRow>
            ))}</TableBody>
          </Table>
        </section>
      ) : null}
      <CreateGuardrailWizard open={createOpen} onOpenChange={setCreateOpen} onCreated={async (id) => { setCreateOpen(false); await queryClient.invalidateQueries({ queryKey: queryKeys.guardrails }); navigate({ to: "/guardrails/$guardrailId", params: { guardrailId: id } }); }} />
    </section>
  );
}

export function GuardrailDetailPage() {
  const { t } = useTranslation();
  const { guardrailId } = useParams({ strict: false }) as { guardrailId: string };
  const queryClient = useQueryClient();
  const guardrailQuery = useQuery({ queryKey: queryKeys.guardrail(guardrailId), queryFn: () => getGuardrail(guardrailId) });
  const policiesQuery = useQuery({ queryKey: queryKeys.policies, queryFn: getPolicies });
  const versionsQuery = useQuery({ queryKey: queryKeys.guardrailVersions(guardrailId), queryFn: () => getGuardrailVersions(guardrailId) });
  const testsQuery = useQuery({ queryKey: queryKeys.testCases(guardrailId), queryFn: () => getTestCases(guardrailId) });
  const deploymentsQuery = useQuery({ queryKey: queryKeys.deployments, queryFn: getDeployments });
  const [editOpen, setEditOpen] = useState(false);
  const [testOpen, setTestOpen] = useState(false);
  const [deploymentOpen, setDeploymentOpen] = useState(false);

  async function refresh() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.guardrail(guardrailId) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.guardrails }),
      queryClient.invalidateQueries({ queryKey: queryKeys.guardrailVersions(guardrailId) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.testCases(guardrailId) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.allValidationRuns }),
    ]);
  }

  if (guardrailQuery.isLoading) return <Skeleton className="mt-8 h-[34rem] rounded-xl" />;
  if (guardrailQuery.error || !guardrailQuery.data) return <div className="py-8"><ErrorNotice error={guardrailQuery.error ?? new Error(t("guardrails.notFound"))} /></div>;
  const guardrail = guardrailQuery.data;
  const policies = policiesQuery.data?.items ?? EMPTY_POLICIES;
  const deployments = deploymentsQuery.data?.items.filter((item) => item.guardrail_id === guardrail.id) ?? [];

  return (
    <section className="py-6 sm:py-8">
      <Link to="/guardrails" className="inline-flex min-h-11 items-center gap-2 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="size-4" />{t("guardrails.back")}</Link>
      <div className="mt-3 flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h1 className="font-display text-2xl font-semibold tracking-[-0.015em] sm:text-3xl">{guardrail.name}</h1><StateBadge state={guardrail.status} />{guardrail.system_managed ? <Badge variant="outline">{t("guardrails.systemManaged")}</Badge> : null}</div><p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">{guardrail.purpose}</p></div>
        <div className="flex flex-wrap gap-2">
          {!guardrail.system_managed ? <Button variant="outline" onClick={() => setEditOpen(true)}><Pencil />{t("common.edit")}</Button> : null}
          <Button variant="outline" asChild><Link to="/validation" search={{ guardrail: guardrail.id }}><FlaskConical />{t("guardrails.openValidation")}</Link></Button>
          {!guardrail.system_managed && guardrail.tested_current ? <Button onClick={() => setDeploymentOpen(true)}><Rocket />{t("guardrails.createDeployment")}</Button> : null}
        </div>
      </div>

      <WorkflowStatus guardrail={guardrail} />
      <div className="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-4"><Metric label={t("guardrails.policies")} value={String(guardrail.policy_bindings.length)} detail={t("guardrails.versionPinned")} /><Metric label={t("guardrails.testCases")} value={String(guardrail.test_case_count)} detail={t("guardrails.executableCases")} /><Metric label={t("guardrails.validation")} value={guardrail.latest_validation_run ? `${guardrail.latest_validation_run.metrics.compliance_rate}%` : "—"} detail={guardrail.latest_validation_run?.status ?? t("guardrails.notRun")} /><Metric label={t("guardrails.deployments")} value={String(deployments.length)} detail={t("guardrails.trafficBindings")} /></div>

      <Tabs defaultValue="policies" className="mt-6">
        <TabsList aria-label={t("guardrails.detailViews")}><TabsTrigger value="policies">{t("guardrails.policies")}</TabsTrigger><TabsTrigger value="tests">{t("guardrails.testCases")}</TabsTrigger><TabsTrigger value="versions">{t("guardrails.versions")}</TabsTrigger></TabsList>
        <TabsContent value="policies" className="pt-4"><PolicyBindings bindings={guardrail.policy_bindings} policies={policies} /></TabsContent>
        <TabsContent value="tests" className="pt-4"><TestCases cases={testsQuery.data?.items ?? []} loading={testsQuery.isLoading} onAdd={() => setTestOpen(true)} /></TabsContent>
        <TabsContent value="versions" className="pt-4"><VersionHistory guardrailId={guardrail.id} versions={versionsQuery.data?.items ?? []} loading={versionsQuery.isLoading} onChanged={refresh} /></TabsContent>
      </Tabs>

      <EditGuardrailSheet guardrail={guardrail} policies={policies} open={editOpen} onOpenChange={setEditOpen} onSaved={async () => { setEditOpen(false); await refresh(); }} />
      <AddTestCaseSheet guardrail={guardrail} open={testOpen} onOpenChange={setTestOpen} onCreated={async () => { setTestOpen(false); await refresh(); }} />
      <CreateDeploymentSheet open={deploymentOpen} onOpenChange={setDeploymentOpen} guardrails={[guardrail]} onCreated={async () => { setDeploymentOpen(false); await refresh(); }} />
    </section>
  );
}

function WorkflowStatus({ guardrail }: { guardrail: Guardrail }) {
  const { t } = useTranslation();
  const steps = [
    { label: t("guardrails.flowIntent"), complete: Boolean(guardrail.purpose) },
    { label: t("guardrails.flowPolicies"), complete: guardrail.policy_bindings.length > 0 },
    { label: t(guardrail.tested_current ? "guardrails.flowValidationPassed" : "guardrails.flowValidationRequired"), complete: guardrail.tested_current },
    { label: t(guardrail.deployment_count ? "guardrails.flowDeployments" : "guardrails.flowDeploymentRequired", { count: guardrail.deployment_count }), complete: guardrail.deployment_count > 0 },
  ];
  return <section aria-label={t("guardrails.workflowLabel")} className="mt-6 grid overflow-hidden rounded-xl border bg-card sm:grid-cols-4">{steps.map((step, index) => <div key={step.label} className="flex min-h-16 items-center gap-3 border-b px-4 py-3 last:border-b-0 sm:border-r sm:border-b-0 sm:last:border-r-0"><span className={cn("grid size-7 shrink-0 place-items-center rounded-full border font-mono text-[10px] text-muted-foreground", step.complete && "border-emerald-200 bg-emerald-50 text-emerald-700")}>{step.complete ? <Check className="size-3.5" /> : index + 1}</span><span className="text-xs font-medium">{step.label}</span></div>)}</section>;
}

function PolicyBindings({ bindings, policies }: { bindings: GuardrailPolicyBinding[]; policies: Policy[] }) {
  const { t } = useTranslation();
  return bindings.length ? <div className="grid gap-4 lg:grid-cols-2">{bindings.map((binding) => { const policy = policies.find((item) => item.id === binding.policy_id); return <article key={`${binding.policy_id}@${binding.policy_version}`} className="rounded-xl border bg-card p-4 shadow-xs"><div className="flex items-start justify-between gap-3"><span className="min-w-0"><strong className="block truncate text-sm">{policy?.name ?? binding.policy_id}</strong><span className="mt-1 block font-mono text-xs text-muted-foreground">{binding.policy_id}@{binding.policy_version}</span></span><Badge variant="outline">{binding.action ?? t("guardrails.policyBehavior")}</Badge></div><p className="mt-3 line-clamp-2 text-xs leading-5 text-muted-foreground">{policy?.description}</p><div className="mt-4 flex flex-wrap gap-2"><Badge variant="secondary">{t("guardrails.ruleCount", { count: binding.enabled_rule_ids.length })}</Badge>{binding.enabled_rails.map((rail) => <Badge key={rail} variant="outline" className="font-mono uppercase">{rail}</Badge>)}</div></article>; })}</div> : <EmptyState title={t("guardrails.noPolicies")} description={t("guardrails.noPoliciesDescription")} />;
}

function TestCases({ cases, loading, onAdd }: { cases: TestCase[]; loading: boolean; onAdd: () => void }) {
  const { t } = useTranslation();
  if (loading) return <Skeleton className="h-64 rounded-xl" />;
  return <section className="overflow-hidden rounded-xl border bg-card"><header className="flex items-center justify-between gap-3 border-b bg-muted/25 p-4"><div><h3 className="text-sm font-semibold">{t("guardrails.testCases")}</h3><p className="mt-1 text-xs text-muted-foreground">{t("guardrails.testCasesDescription")}</p></div><Button variant="outline" onClick={onAdd}><Plus />{t("guardrails.addTestCase")}</Button></header>{cases.length ? <div className="divide-y">{cases.map((item) => <article key={item.id} className="grid gap-2 p-4 sm:grid-cols-[minmax(0,1fr)_9rem_8rem]"><span className="min-w-0"><strong className="block truncate text-sm">{item.name}</strong><span className="mt-1 block truncate font-mono text-xs text-muted-foreground">{item.policy_id} · {item.source_case_id ?? item.origin}</span></span><Badge variant="outline" className="w-fit">{item.phase}</Badge><StateBadge state={item.expected_decision} /></article>)}</div> : <div className="p-4"><InfoNotice title={t("guardrails.noCases")}>{t("guardrails.noCasesDescription")}</InfoNotice></div>}</section>;
}

function VersionHistory({ guardrailId, versions, loading, onChanged }: { guardrailId: string; versions: GuardrailVersion[]; loading: boolean; onChanged: () => Promise<void> }) {
  const { t, i18n } = useTranslation();
  const rollback = useMutation({ mutationFn: (version: number) => rollbackGuardrail(guardrailId, version), onSuccess: async () => { toast.success(t("guardrails.rollbackSucceeded")); await onChanged(); }, onError: (error) => notifyError(error, t("guardrails.operationFailed")) });
  if (loading) return <Skeleton className="h-48 rounded-xl" />;
  if (!versions.length) return <EmptyState title={t("guardrails.noVersions")} description={t("guardrails.noVersionsDescription")} />;
  return <section className="overflow-hidden rounded-xl border bg-card"><div className="divide-y">{versions.map((version) => <article key={version.version} className="grid gap-3 p-4 sm:grid-cols-[6rem_minmax(0,1fr)_11rem_9rem] sm:items-center"><span className="flex items-center gap-2"><History className="size-4 text-primary" /><strong className="font-mono text-sm">v{version.version}</strong></span><span className="min-w-0"><span className="block text-xs">{version.compiler_version} · {version.runtime_engine}</span><code className="mt-1 block truncate text-xs text-muted-foreground">{version.config_checksum || version.plan_checksum}</code></span><time className="text-xs text-muted-foreground">{new Date(version.created_at).toLocaleString(i18n.language)}</time><span>{version.active ? <StateBadge state="active" /> : <Button size="sm" variant="outline" disabled={rollback.isPending} onClick={() => rollback.mutate(version.version)}>{rollback.isPending && rollback.variables === version.version ? <LoaderCircle className="animate-spin" /> : <History />}{t("guardrails.rollback")}</Button>}</span></article>)}</div></section>;
}

function EditGuardrailSheet({ guardrail, policies, open, onOpenChange, onSaved }: { guardrail: Guardrail; policies: Policy[]; open: boolean; onOpenChange: (open: boolean) => void; onSaved: () => void }) {
  const { t } = useTranslation();
  const [name, setName] = useState(guardrail.name);
  const [purpose, setPurpose] = useState(guardrail.purpose);
  const [allowed, setAllowed] = useState(guardrail.allowed_topics.join("\n"));
  const [restricted, setRestricted] = useState(guardrail.restricted_topics.join("\n"));
  const [bindings, setBindings] = useState(guardrail.policy_bindings);
  const [level, setLevel] = useState(guardrail.safety_level);
  const [delivery, setDelivery] = useState(guardrail.output_delivery);
  useEffect(() => { if (open) { setName(guardrail.name); setPurpose(guardrail.purpose); setAllowed(guardrail.allowed_topics.join("\n")); setRestricted(guardrail.restricted_topics.join("\n")); setBindings(guardrail.policy_bindings); setLevel(guardrail.safety_level); setDelivery(guardrail.output_delivery); } }, [guardrail, open]);
  const mutation = useMutation({ mutationFn: () => updateGuardrail(guardrail.id, { name, purpose, allowed_topics: lines(allowed), restricted_topics: lines(restricted), policy_bindings: bindings, safety_level: level, output_delivery: delivery }), onSuccess: () => { toast.success(t("guardrails.updated")); onSaved(); }, onError: (error) => notifyError(error, t("guardrails.operationFailed")) });
  return <EntitySheet open={open} onOpenChange={onOpenChange} eyebrow={t("guardrails.editEyebrow")} title={t("guardrails.editTitle", { name: guardrail.name })} description={t("guardrails.editDescription")} width="xl" footer={<><Button variant="outline" onClick={() => onOpenChange(false)}>{t("common.cancel")}</Button><Button disabled={!name.trim() || !purpose.trim() || !bindings.length || mutation.isPending} onClick={() => mutation.mutate()}>{mutation.isPending ? <LoaderCircle className="animate-spin" /> : <Save />}{t(mutation.isPending ? "common.saving" : "common.save")}</Button></>}><div className="grid gap-5"><Field label={t("guardrails.guardrailName")}><Input className="min-h-11" value={name} onChange={(event) => setName(event.target.value)} /></Field><Field label={t("guardrails.businessPurpose")}><Textarea className="min-h-28" value={purpose} onChange={(event) => setPurpose(event.target.value)} /></Field><div className="grid gap-4 sm:grid-cols-2"><Field label={t("guardrails.allowedDomains")}><Textarea className="min-h-24" value={allowed} onChange={(event) => setAllowed(event.target.value)} /></Field><Field label={t("guardrails.restrictedDomains")}><Textarea className="min-h-24" value={restricted} onChange={(event) => setRestricted(event.target.value)} /></Field></div><div className="grid gap-4 sm:grid-cols-2"><Field label={t("guardrailWizard.safetyLevel")}><Select value={level} onValueChange={(next) => setLevel(next as typeof level)}><SelectTrigger className="min-h-11"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="balanced">{t("guardrails.balanced")}</SelectItem><SelectItem value="strict">{t("guardrails.strict")}</SelectItem></SelectContent></Select></Field><Field label={t("guardrailWizard.outputDelivery")}><Select value={delivery} onValueChange={(next) => setDelivery(next as typeof delivery)}><SelectTrigger className="min-h-11"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="interruptible">{t("guardrails.outputRealtime")}</SelectItem><SelectItem value="window_buffered">{t("guardrails.outputWindow")}</SelectItem><SelectItem value="full_buffered">{t("guardrails.outputFull")}</SelectItem></SelectContent></Select></Field></div><section><h3 className="mb-3 text-sm font-semibold">{t("guardrails.policyBindings")}</h3><PolicyBindingEditor policies={policies} value={bindings} onChange={setBindings} /></section></div></EntitySheet>;
}

export function AddTestCaseSheet({ guardrail, open, onOpenChange, onCreated }: { guardrail: Guardrail; open: boolean; onOpenChange: (open: boolean) => void; onCreated: () => void }) {
  const { t } = useTranslation();
  const [name, setName] = useState("");
  const [policyId, setPolicyId] = useState(guardrail.policy_bindings[0]?.policy_id ?? "");
  const [phase, setPhase] = useState<"input" | "output">("input");
  const [content, setContent] = useState("");
  const [expected, setExpected] = useState<TestCase["expected_decision"]>("block");
  useEffect(() => { if (open) { setName(""); setPolicyId(guardrail.policy_bindings[0]?.policy_id ?? ""); setPhase("input"); setContent(""); setExpected("block"); } }, [guardrail.policy_bindings, open]);
  const mutation = useMutation({ mutationFn: () => createTestCase(guardrail.id, { name, policy_id: policyId, phase, content, expected_decision: expected, trusted_instruction: "", target_source: phase === "input" ? "user_input" : "model_output", query: "", grounding_sources: [], expected_reasoning_result: null }), onSuccess: () => { toast.success(t("guardrails.caseCreated")); onCreated(); }, onError: (error) => notifyError(error, t("guardrails.operationFailed")) });
  return <EntitySheet open={open} onOpenChange={onOpenChange} eyebrow={t("guardrails.addCaseEyebrow")} title={t("guardrails.addCaseTitle")} description={t("guardrails.addCaseDescription")} footer={<><Button variant="outline" onClick={() => onOpenChange(false)}>{t("common.cancel")}</Button><Button disabled={!name.trim() || !policyId || !content.trim() || mutation.isPending} onClick={() => mutation.mutate()}>{mutation.isPending ? <LoaderCircle className="animate-spin" /> : <Plus />}{t("guardrails.addTestCase")}</Button></>}><div className="grid gap-5"><Field label={t("guardrails.caseName")}><Input autoFocus className="min-h-11" value={name} onChange={(event) => setName(event.target.value)} /></Field><Field label={t("guardrails.policy")}><Select value={policyId} onValueChange={setPolicyId}><SelectTrigger className="min-h-11"><SelectValue /></SelectTrigger><SelectContent>{guardrail.policy_bindings.map((binding) => <SelectItem key={binding.policy_id} value={binding.policy_id}>{binding.policy_id}</SelectItem>)}</SelectContent></Select></Field><div className="grid gap-4 sm:grid-cols-2"><Field label={t("guardrails.modelBoundary")}><Select value={phase} onValueChange={(next) => setPhase(next as typeof phase)}><SelectTrigger className="min-h-11"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="input">Input</SelectItem><SelectItem value="output">Output</SelectItem></SelectContent></Select></Field><Field label={t("guardrails.expectedDecision")}><Select value={expected} onValueChange={(next) => setExpected(next as typeof expected)}><SelectTrigger className="min-h-11"><SelectValue /></SelectTrigger><SelectContent>{["allow", "block", "transform", "intervene"].map((decision) => <SelectItem key={decision} value={decision}>{decision}</SelectItem>)}</SelectContent></Select></Field></div><Field label={t("guardrails.testContent")}><Textarea className="min-h-32" value={content} onChange={(event) => setContent(event.target.value)} /></Field></div></EntitySheet>;
}

function Field({ label, children }: { label: string; children: ReactNode }) { return <label className="grid gap-2"><Label>{label}</Label>{children}</label>; }
function lines(value: string) { return value.split("\n").map((item) => item.trim()).filter(Boolean); }
function notifyError(error: unknown, fallback: string) { toast.error(error instanceof Error ? error.message : fallback); }
