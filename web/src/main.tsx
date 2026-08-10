import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createBrowserHistory, createRootRoute, createRoute, createRouter, RouterProvider } from "@tanstack/react-router";
import { ThemeProvider } from "next-themes";

import { ControlPlaneLayout } from "@/routes/layout";
import { SafeDetailPage, SafetyProfilesPage } from "@/routes/safety-profiles";
import { ProtectedWorkloadsPage } from "@/routes/protected-workloads";
import { ActivityPage } from "@/routes/activity";
import { GatewaysPage } from "@/routes/gateways";
import { UsersPage } from "@/routes/users";
import { ConversationPlaygroundPage } from "@/routes/conversation-playground";
import { OverviewPage } from "@/routes/overview";
import { AuthProvider } from "@/lib/auth";
import "@/i18n";
import "@/styles.css";

const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 10_000, retry: 1 } } });
const rootRoute = createRootRoute({ component: ControlPlaneLayout });
const indexRoute = createRoute({ getParentRoute: () => rootRoute, path: "/", component: OverviewPage });
const profilesRoute = createRoute({ getParentRoute: () => rootRoute, path: "/governance/safes", component: SafetyProfilesPage });
const safeDetailRoute = createRoute({ getParentRoute: () => rootRoute, path: "/governance/safes/$safeId", component: SafeDetailPage });
const workloadsRoute = createRoute({ getParentRoute: () => rootRoute, path: "/governance/workloads", component: ProtectedWorkloadsPage });
const playgroundRoute = createRoute({ getParentRoute: () => rootRoute, path: "/playground", component: ConversationPlaygroundPage });
const activityRoute = createRoute({ getParentRoute: () => rootRoute, path: "/governance/evidence", component: ActivityPage });
const gatewaysRoute = createRoute({ getParentRoute: () => rootRoute, path: "/system/integrations", component: GatewaysPage });
const usersRoute = createRoute({ getParentRoute: () => rootRoute, path: "/system/access", component: UsersPage });
const routeTree = rootRoute.addChildren([
  indexRoute,
  profilesRoute,
  safeDetailRoute,
  workloadsRoute,
  playgroundRoute,
  activityRoute,
  gatewaysRoute,
  usersRoute,
]);
const router = createRouter({ routeTree, history: createBrowserHistory() });
declare module "@tanstack/react-router" { interface Register { router: typeof router } }

ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><ThemeProvider attribute="class" defaultTheme="light" forcedTheme="light"><QueryClientProvider client={queryClient}><AuthProvider><RouterProvider router={router} /></AuthProvider></QueryClientProvider></ThemeProvider></React.StrictMode>);
