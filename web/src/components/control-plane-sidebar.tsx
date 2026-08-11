import { useQuery } from "@tanstack/react-query";
import { Link, useRouterState } from "@tanstack/react-router";
import { Activity, Cable, ChevronsUpDown, Globe2, ListFilter, LockKeyhole, LogOut, ShieldCheck, UsersRound } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
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
import type { SupportedLanguage } from "@/i18n";
import { useAuth } from "@/lib/auth";
import { getAssignments, getGuardrails, getIntegrations } from "@/lib/api";

const navigation = [
  {
    label: "nav.governance",
    items: [
      { label: "nav.guardrails", to: "/guardrails", icon: ShieldCheck, count: "guardrails" },
      { label: "nav.assignments", to: "/assignments", icon: ListFilter, count: "assignments" },
      { label: "nav.enforcements", to: "/enforcements", icon: LockKeyhole },
    ],
  },
  {
    label: "nav.operations",
    items: [
      { label: "nav.integrations", to: "/integrations", icon: Cable, count: "integrations" },
      { label: "nav.evidence", to: "/evidence", icon: Activity },
    ],
  },
] as const;

export function ControlPlaneSidebar() {
  const { t, i18n } = useTranslation();
  const { user, logout, logoutPending, setLanguage } = useAuth();
  const { setOpenMobile, state } = useSidebar();
  const pathname = useRouterState({ select: (routerState) => routerState.location.pathname });
  const guardrails = useQuery({ queryKey: queryKeys.guardrails, queryFn: getGuardrails });
  const assignments = useQuery({ queryKey: queryKeys.assignments, queryFn: getAssignments });
  const integrations = useQuery({ queryKey: queryKeys.integrations, queryFn: getIntegrations });
  const counts: Record<string, number | undefined> = {
    guardrails: guardrails.data?.count,
    assignments: assignments.data?.count,
    integrations: integrations.data?.count,
  };
  const language: SupportedLanguage = i18n.language.toLowerCase().startsWith("zh") ? "zh-CN" : "en";

  async function signOut() {
    try {
      await logout();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("common.unknownError"));
    }
  }

  async function changeLanguage(value: string) {
    try {
      await setLanguage(value as SupportedLanguage);
      toast.success(t("sidebar.languageUpdated"));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("common.unknownError"));
    }
  }

  return (
    <Sidebar collapsible="icon" className="border-r border-sidebar-border">
      <SidebarHeader className="h-16 justify-center border-b border-sidebar-border px-4 group-data-[collapsible=icon]:px-3">
        <Link
          to="/"
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
          const items = group.items.filter((item) => !("adminOnly" in item && item.adminOnly && user?.role !== "admin"));
          return (
            <SidebarGroup key={group.label} className="px-0 py-2 group-data-[collapsible=icon]:px-1">
              {group.label ? <SidebarGroupLabel className="h-7 px-2.5 text-[11px] font-medium text-sidebar-foreground/55 group-data-[collapsible=icon]:hidden">
                {t(group.label)}
              </SidebarGroupLabel> : null}
              <SidebarGroupContent>
                <SidebarMenu className="gap-1">
                  {items.map((item) => {
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
      </SidebarContent>

      <SidebarFooter className="gap-1.5 border-t border-sidebar-border p-2.5">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button type="button" className="flex min-h-12 w-full items-center gap-3 rounded-xl border border-transparent px-1.5 text-left outline-none transition-colors hover:border-sidebar-border hover:bg-sidebar-accent focus-visible:ring-2 focus-visible:ring-sidebar-ring data-[state=open]:border-sidebar-border data-[state=open]:bg-sidebar-accent group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-0" aria-label={t("sidebar.accountMenu")}>
              <Avatar className="size-8 rounded-lg"><AvatarFallback>{initials(user?.display_name ?? "")}</AvatarFallback></Avatar>
              <span className="min-w-0 flex-1 group-data-[collapsible=icon]:hidden"><span className="block truncate text-xs font-semibold text-sidebar-foreground">{user?.display_name}</span><span className="mt-0.5 block truncate text-[10px] text-sidebar-foreground/50">{user?.email}</span></span>
              <ChevronsUpDown className="mr-1 size-3.5 text-sidebar-foreground/40 group-data-[collapsible=icon]:hidden" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent side="top" align="start" className="w-64">
            <div className="flex items-center gap-3 px-2.5 py-2.5">
              <Avatar className="size-9"><AvatarFallback>{initials(user?.display_name ?? "")}</AvatarFallback></Avatar>
              <div className="min-w-0"><p className="truncate text-sm font-semibold">{user?.display_name}</p><p className="truncate text-xs text-muted-foreground">{user?.email}</p><p className="mt-1 text-[10px] font-medium uppercase tracking-wide text-primary">{t(user?.role === "admin" ? "common.admin" : "common.member")}</p></div>
            </div>
            <DropdownMenuSeparator />
            <DropdownMenuLabel className="flex items-center gap-2"><Globe2 />{t("sidebar.profilePreferences")}</DropdownMenuLabel>
            <DropdownMenuRadioGroup value={language} onValueChange={(value) => void changeLanguage(value)}>
              <DropdownMenuRadioItem value="en">English</DropdownMenuRadioItem>
              <DropdownMenuRadioItem value="zh-CN">简体中文</DropdownMenuRadioItem>
            </DropdownMenuRadioGroup>
            <DropdownMenuSeparator />
            {user?.role === "admin" ? <DropdownMenuItem asChild><Link to="/access" onClick={() => setOpenMobile(false)}><UsersRound />{t("auth.manageUsers")}</Link></DropdownMenuItem> : null}
            <DropdownMenuItem variant="destructive" disabled={logoutPending} onSelect={() => void signOut()}><LogOut />{t(logoutPending ? "auth.signingOut" : "auth.signOut")}</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}

function initials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "U";
  if (parts.length === 1) return Array.from(parts[0]).slice(0, 2).join("").toUpperCase();
  return `${Array.from(parts[0])[0] ?? ""}${Array.from(parts.at(-1) ?? "")[0] ?? ""}`.toUpperCase();
}
