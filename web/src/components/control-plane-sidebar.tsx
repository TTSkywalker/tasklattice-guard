import { useQuery } from "@tanstack/react-query";
import { Link, useRouterState } from "@tanstack/react-router";
import { Activity, Cable, CircleHelp, FlaskConical, LayoutDashboard, LibraryBig, ListChecks, Rocket, ScrollText, ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";

import { AccountMenu } from "@/components/account-menu";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  useSidebar,
} from "@/components/ui/sidebar";
import { queryKeys } from "@/features/query-keys";
import { getDeployments, getGuardrails, getIntegrations } from "@/lib/api";

const navigation = [
  {
    label: "nav.home",
    items: [
      { label: "nav.dashboard", to: "/dashboard", icon: LayoutDashboard },
      { label: "nav.playground", to: "/playground", icon: FlaskConical },
    ],
  },
  {
    label: "nav.buildValidate",
    items: [
      { label: "nav.guardrails", to: "/guardrails", icon: ShieldCheck, count: "guardrails" },
      { label: "nav.policyLibrary", to: "/policy-library", icon: LibraryBig },
      { label: "nav.validation", to: "/validation", icon: ListChecks },
    ],
  },
  {
    label: "nav.runtime",
    items: [
      { label: "nav.deployments", to: "/deployments", icon: Rocket, count: "deployments" },
      { label: "nav.integrations", to: "/integrations", icon: Cable, count: "integrations" },
    ],
  },
  {
    label: "nav.assurance",
    items: [
      { label: "nav.evidence", to: "/evidence", icon: Activity },
      { label: "nav.logs", to: "/logs", icon: ScrollText },
    ],
  },
] as const;

export function ControlPlaneSidebar() {
  const { t } = useTranslation();
  const { isMobile, setOpenMobile, state } = useSidebar();
  const pathname = useRouterState({ select: (routerState) => routerState.location.pathname });
  const guardrails = useQuery({ queryKey: queryKeys.guardrails, queryFn: getGuardrails });
  const deployments = useQuery({ queryKey: queryKeys.deployments, queryFn: getDeployments });
  const integrations = useQuery({ queryKey: queryKeys.integrations, queryFn: getIntegrations });
  const counts: Record<string, number | undefined> = {
    guardrails: guardrails.data?.count,
    deployments: deployments.data?.count,
    integrations: integrations.data?.count,
  };
  return (
    <Sidebar collapsible="icon" className="border-r border-sidebar-border">
      <SidebarHeader className="h-16 justify-center border-b border-sidebar-border px-4 group-data-[collapsible=icon]:px-3">
        <Link
          to="/dashboard"
          aria-label="TaskLattice Guard"
          onClick={() => setOpenMobile(false)}
          className="flex min-h-11 items-center gap-2.5 rounded-lg px-1 outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring group-data-[collapsible=icon]:justify-center"
        >
          <ShieldCheck className="size-5 shrink-0 text-primary" strokeWidth={2.2} />
          <span className="min-w-0 text-sm font-semibold tracking-[-0.02em] text-foreground group-data-[collapsible=icon]:hidden">
            TaskLattice <span className="font-medium text-muted-foreground">Guard</span>
          </span>
        </Link>
      </SidebarHeader>

      <SidebarContent className="px-2 py-3">
        {navigation.map((group) => {
          return (
            <SidebarGroup key={group.label} className="px-0 py-2 group-data-[collapsible=icon]:px-1">
              {group.label ? <SidebarGroupLabel className="h-7 px-2.5 text-[11px] font-medium text-sidebar-foreground/55 group-data-[collapsible=icon]:hidden">
                {t(group.label)}
              </SidebarGroupLabel> : null}
              <SidebarGroupContent>
                <SidebarMenu className="gap-1">
                  {group.items.map((item) => {
                    const active = pathname === item.to || (item.to === "/guardrails" && pathname.startsWith("/guardrails/"));
                    const count = "count" in item ? counts[item.count] : undefined;
                    const label = t(item.label);
                    return (
                      <SidebarMenuItem key={item.to}>
                        <SidebarMenuButton
                          asChild
                          isActive={active}
                          tooltip={label}
                          className="h-10 rounded-lg px-2.5 text-[13px] text-sidebar-foreground/80 data-active:bg-accent data-active:font-medium data-active:text-accent-foreground group-data-[collapsible=icon]:mx-auto group-data-[collapsible=icon]:size-10! group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:p-0!"
                        >
                          <Link
                            to={item.to}
                            aria-label={state === "collapsed" ? label : undefined}
                            onClick={() => setOpenMobile(false)}
                          >
                            <item.icon className="size-4.5" strokeWidth={active ? 2.2 : 1.8} />
                            <span className="group-data-[collapsible=icon]:hidden">{label}</span>
                          </Link>
                        </SidebarMenuButton>
                        {count !== undefined ? <SidebarMenuBadge className="right-2 text-[11px] font-medium text-sidebar-foreground/45">{count}</SidebarMenuBadge> : null}
                      </SidebarMenuItem>
                    );
                  })}
                </SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>
          );
        })}
        <SidebarGroup className="mt-auto px-0 pt-3 pb-0 group-data-[collapsible=icon]:px-1">
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton
                  asChild
                  isActive={pathname === "/help"}
                  tooltip={t("nav.helpCenter")}
                  className="h-10 rounded-lg px-2.5 text-[13px] text-sidebar-foreground/80 data-active:bg-accent data-active:font-medium data-active:text-accent-foreground group-data-[collapsible=icon]:mx-auto group-data-[collapsible=icon]:size-10! group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:p-0!"
                >
                  <Link
                    to="/help"
                    aria-label={state === "collapsed" ? t("nav.helpCenter") : undefined}
                    onClick={() => setOpenMobile(false)}
                  >
                    <CircleHelp className="size-4.5" strokeWidth={pathname === "/help" ? 2.2 : 1.8} />
                    <span className="group-data-[collapsible=icon]:hidden">{t("nav.helpCenter")}</span>
                  </Link>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter className="gap-1.5 border-t border-sidebar-border p-2.5">
        <AccountMenu collapsed={!isMobile && state === "collapsed"} onNavigate={() => setOpenMobile(false)} />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}
