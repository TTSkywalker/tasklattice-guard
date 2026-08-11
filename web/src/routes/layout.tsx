import { Outlet, useRouterState } from "@tanstack/react-router";
import { Building2, ShieldCheck } from "lucide-react";
import type { CSSProperties } from "react";
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
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useAuth } from "@/lib/auth";
import { LoginPage } from "@/routes/login";

const names: Record<string, { group: string; page: string }> = {
  "/": { group: "nav.home", page: "nav.overview" },
  "/guardrails": { group: "nav.buildValidate", page: "nav.guardrails" },
  "/control-library": { group: "nav.buildValidate", page: "nav.controlLibrary" },
  "/playground": { group: "nav.buildValidate", page: "nav.playground" },
  "/evaluations": { group: "nav.buildValidate", page: "nav.evaluations" },
  "/deployments": { group: "nav.runtime", page: "nav.deployments" },
  "/assignments": { group: "nav.runtime", page: "nav.deployments" },
  "/enforcements": { group: "nav.runtime", page: "nav.deployments" },
  "/integrations": { group: "nav.runtime", page: "nav.integrations" },
  "/evidence": { group: "nav.assurance", page: "nav.evidence" },
  "/access": { group: "nav.system", page: "nav.access" },
};

export function ControlPlaneLayout() {
  const { t } = useTranslation();
  const auth = useAuth();
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const location = names[pathname] ?? (pathname.startsWith("/guardrails/") ? names["/guardrails"] : { group: "nav.home", page: "nav.overview" });

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
            <div className="hidden items-center gap-2 text-xs text-muted-foreground sm:flex">
              <Building2 className="size-4" />
              {t("nav.enterpriseSafety")}
            </div>
          </header>
          <main className="mx-auto w-full max-w-[1600px] min-w-0 flex-1 px-4 pb-12 sm:px-6 lg:px-8">
            <Outlet />
          </main>
        </SidebarInset>
        <Toaster position="bottom-right" richColors />
      </SidebarProvider>
    </TooltipProvider>
  );
}
