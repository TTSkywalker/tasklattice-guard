import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createBrowserHistory, createRootRoute, createRoute, createRouter, Navigate, RouterProvider } from "@tanstack/react-router";
import { ThemeProvider } from "next-themes";

import { ControlPlaneLayout } from "@/routes/layout";
import { GuardrailDetailPage, GuardrailsPage } from "@/routes/guardrails";
import { DeploymentsPage } from "@/routes/deployments";
import { EvidencePage } from "@/routes/evidence";
import { IntegrationsPage } from "@/routes/integrations";
import { ValidationPage } from "@/routes/validation";
import { PlaygroundPage } from "@/routes/playground";
import { UsersPage } from "@/routes/users";
import { DashboardPage } from "@/routes/dashboard";
import { PolicyLibraryPage } from "@/routes/policy-library";
import { AuthProvider } from "@/lib/auth";
import "@/i18n";
import "@/styles.css";

const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 10_000, retry: 1 } } });
const rootRoute = createRootRoute({ component: ControlPlaneLayout });
const indexRoute = createRoute({ getParentRoute: () => rootRoute, path: "/", component: () => <Navigate to="/dashboard" replace /> });
const dashboardRoute = createRoute({ getParentRoute: () => rootRoute, path: "/dashboard", component: DashboardPage });
const guardrailsRoute = createRoute({ getParentRoute: () => rootRoute, path: "/guardrails", component: GuardrailsPage });
const guardrailDetailRoute = createRoute({ getParentRoute: () => rootRoute, path: "/guardrails/$guardrailId", component: GuardrailDetailPage });
const policyLibraryRoute = createRoute({ getParentRoute: () => rootRoute, path: "/policy-library", component: PolicyLibraryPage });
const guardrailSearch = (search: Record<string, unknown>) => ({ guardrail: typeof search.guardrail === "string" ? search.guardrail : undefined });
const playgroundRoute = createRoute({ getParentRoute: () => rootRoute, path: "/playground", validateSearch: guardrailSearch, component: PlaygroundPage });
const validationRoute = createRoute({ getParentRoute: () => rootRoute, path: "/validation", validateSearch: guardrailSearch, component: ValidationPage });
const deploymentsRoute = createRoute({ getParentRoute: () => rootRoute, path: "/deployments", component: DeploymentsPage });
const integrationsRoute = createRoute({ getParentRoute: () => rootRoute, path: "/integrations", component: IntegrationsPage });
const evidenceRoute = createRoute({ getParentRoute: () => rootRoute, path: "/evidence", component: EvidencePage });
const usersRoute = createRoute({ getParentRoute: () => rootRoute, path: "/access", component: UsersPage });
const routeTree = rootRoute.addChildren([
  indexRoute,
  dashboardRoute,
  guardrailsRoute,
  guardrailDetailRoute,
  policyLibraryRoute,
  playgroundRoute,
  validationRoute,
  deploymentsRoute,
  integrationsRoute,
  evidenceRoute,
  usersRoute,
]);
const router = createRouter({ routeTree, history: createBrowserHistory() });
declare module "@tanstack/react-router" { interface Register { router: typeof router } }

ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><ThemeProvider attribute="class" defaultTheme="light" forcedTheme="light"><QueryClientProvider client={queryClient}><AuthProvider><RouterProvider router={router} /></AuthProvider></QueryClientProvider></ThemeProvider></React.StrictMode>);
