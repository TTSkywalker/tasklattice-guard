import { Link, Outlet, useRouterState } from "@tanstack/react-router";
import { Activity, Building2, CircleAlert, Gauge, ShieldCheck } from "lucide-react";
import type { CSSProperties } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { ControlPlaneSidebar } from "@/components/control-plane-sidebar";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { Separator } from "@/components/ui/separator";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useAuth } from "@/lib/auth";
import { LoginPage } from "@/routes/login";
import { queryKeys } from "@/features/query-keys";
import { getSystemStatus } from "@/lib/api";

const names: Record<string, { group: string; page: string }> = {
  "/": { group: "nav.home", page: "nav.dashboard" },
  "/dashboard": { group: "nav.home", page: "nav.dashboard" },
  "/guardrails": { group: "nav.buildValidate", page: "nav.guardrails" },
  "/policy-library": { group: "nav.buildValidate", page: "nav.policyLibrary" },
  "/playground": { group: "nav.home", page: "nav.playground" },
  "/validation": { group: "nav.buildValidate", page: "nav.validation" },
  "/deployments": { group: "nav.runtime", page: "nav.deployments" },
  "/integrations": { group: "nav.runtime", page: "nav.integrations" },
  "/evidence": { group: "nav.assurance", page: "nav.evidence" },
  "/access": { group: "nav.system", page: "nav.access" },
  "/account": { group: "nav.system", page: "account.title" },
};

export function ControlPlaneLayout() {
  const { t } = useTranslation();
  const auth = useAuth();
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const location = names[pathname]
    ?? (pathname.startsWith("/guardrails/") ? names["/guardrails"] : undefined)
    ?? (pathname.startsWith("/deployments/") ? names["/deployments"] : undefined)
    ?? { group: "nav.home", page: "nav.dashboard" };
  const systemStatus = useQuery({ queryKey: queryKeys.systemStatus, queryFn: getSystemStatus, refetchInterval: 15_000, enabled: Boolean(auth.status?.authenticated) });

  if (auth.isLoading) {
    return <div className="flex min-h-dvh items-center justify-center bg-background"><div className="flex items-center gap-3 text-sm text-muted-foreground"><ShieldCheck className="size-5 animate-pulse text-primary" />{t("auth.sessionLoading")}</div></div>;
  }
  if (!auth.status?.authenticated || !auth.user) return <LoginPage />;

  return (
    <TooltipProvider>
      <SidebarProvider style={{ "--sidebar-width": "15.75rem" } as CSSProperties}>
        <ControlPlaneSidebar />
        <SidebarInset className="min-w-0 bg-background">
          <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b bg-card/90 px-4 backdrop-blur-md sm:px-6">
            <div className="flex min-w-0 items-center gap-3">
              <SidebarTrigger className="size-11 rounded-lg" />
              <Separator orientation="vertical" className="h-5" />
              <Breadcrumb className="min-w-0">
                <BreadcrumbList className="flex-nowrap">
                  <BreadcrumbItem className="hidden sm:inline-flex">
                    <ShieldCheck className="size-4 text-primary" />
                    <span>TaskLattice Guard</span>
                  </BreadcrumbItem>
                  <BreadcrumbSeparator className="hidden sm:block" />
                  <BreadcrumbItem className="hidden md:inline-flex">{t(location.group)}</BreadcrumbItem>
                  <BreadcrumbSeparator className="hidden md:block" />
                  <BreadcrumbItem className="min-w-0">
                    <BreadcrumbPage className="truncate">{t(location.page)}</BreadcrumbPage>
                  </BreadcrumbItem>
                </BreadcrumbList>
              </Breadcrumb>
            </div>
            <RuntimeHealthMenu loading={systemStatus.isLoading} status={systemStatus.data} />
          </header>
          <main className="w-full min-w-0 flex-1 px-4 pb-12 sm:px-6 lg:px-8">
            <Outlet />
          </main>
        </SidebarInset>
        <Toaster position="bottom-right" richColors />
      </SidebarProvider>
    </TooltipProvider>
  );
}

function RuntimeHealthMenu({ loading, status }: { loading: boolean; status?: Awaited<ReturnType<typeof getSystemStatus>> }) {
  const { t } = useTranslation();
  const degraded = Boolean(status?.status === "degraded");
  const capabilities = status ? [
    [t("integrations.localDetection"), status.capabilities.deterministic],
    [t("integrations.fastSemantic"), status.capabilities.fast_semantic],
    [t("integrations.specializedEvaluators"), status.capabilities.specialized_evaluators.length > 0],
    [t("integrations.automatedReasoning"), status.capabilities.automated_reasoning],
  ] as const : [];
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" className="min-h-11 gap-2 px-3" aria-label={t("runtimeHealth.open")}>
          <span className={`size-2 rounded-full ${loading ? "bg-muted-foreground/50" : degraded ? "bg-amber-500" : "bg-emerald-500"}`} />
          <span className="hidden text-xs sm:inline">{t(loading ? "runtimeHealth.checking" : degraded ? "runtimeHealth.attention" : "runtimeHealth.ready")}</span>
          <Gauge className="size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80 p-2">
        <DropdownMenuLabel className="px-3 py-2"><span className="block text-sm font-semibold text-foreground">{t("runtimeHealth.title")}</span><span className="mt-1 block font-normal leading-5">{t(degraded ? "runtimeHealth.degradedDescription" : "runtimeHealth.readyDescription")}</span></DropdownMenuLabel>
        <DropdownMenuSeparator />
        <div className="grid grid-cols-2 gap-2 p-2 text-xs">
          <div className="rounded-lg bg-muted/50 p-3"><p className="text-muted-foreground">{t("runtimeHealth.deployments")}</p><p className="mt-1 font-mono text-base text-foreground">{status?.active_deployments ?? "—"}</p></div>
          <div className="rounded-lg bg-muted/50 p-3"><p className="text-muted-foreground">{t("runtimeHealth.integrations")}</p><p className="mt-1 font-mono text-base text-foreground">{status ? `${status.enabled_integrations}/${status.total_integrations}` : "—"}</p></div>
        </div>
        <div className="space-y-1 px-2 pb-2">
          {capabilities.map(([name, configured]) => <div key={name} className="flex min-h-9 items-center gap-2 rounded-lg px-2 text-xs"><span className={`size-1.5 rounded-full ${configured ? "bg-emerald-500" : "bg-muted-foreground/35"}`} /><span className="min-w-0 flex-1">{name}</span><span className="text-muted-foreground">{t(configured ? "runtimeHealth.available" : "runtimeHealth.optional")}</span></div>)}
        </div>
        {degraded ? <div className="mx-2 mb-2 flex gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900"><CircleAlert className="mt-0.5 size-4 shrink-0" />{t("runtimeHealth.integrationWarning")}</div> : <div className="mx-2 mb-2 flex gap-2 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-900"><Activity className="mt-0.5 size-4 shrink-0" />{t("runtimeHealth.runtimeReady")}</div>}
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild><Link to="/integrations"><Building2 />{t("runtimeHealth.openIntegrations")}</Link></DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
