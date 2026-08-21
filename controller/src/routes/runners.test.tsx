import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { RunnerPool } from "@/lib/controller-api";

import { RunnersPage } from "./runners";

const mocks = vi.hoisted(() => ({
  listRunnerPools: vi.fn(),
  removeRunnerInstance: vi.fn(),
  role: "admin",
  toastSuccess: vi.fn(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, string>) => {
      const labels: Record<string, string> = {
        "runners.removeAria": "Remove {{runnerId}}",
        "runners.removal.title": "Remove this offline Runner?",
        "runners.removal.retentionNote": "The Runner pool, Kubernetes workload, runtime events, and audit history remain.",
        "runners.removal.delete": "Remove Runner",
        "runners.removed": "Offline Runner removed",
      };
      return Object.entries(values ?? {}).reduce(
        (label, [name, value]) => label.replace(`{{${name}}}`, value),
        labels[key] ?? key.split(".").at(-1) ?? key,
      );
    },
    i18n: { language: "en", exists: () => false },
  }),
}));

vi.mock("sonner", () => ({
  toast: { success: mocks.toastSuccess, error: vi.fn() },
}));

vi.mock("@/lib/auth", () => ({
  useAuth: () => ({ user: { role: mocks.role } }),
}));

vi.mock("@/lib/controller-api", () => ({
  listRunnerPools: (...args: unknown[]) => mocks.listRunnerPools(...args),
  removeRunnerInstance: (...args: unknown[]) => mocks.removeRunnerInstance(...args),
  updateRunnerPool: vi.fn(),
}));

const runnerPool: RunnerPool = {
  id: "default",
  name: "GuardRails 0",
  isDefault: true,
  desiredReplicas: 2,
  safeRpsPerRunner: 50,
  maxConcurrencyPerRunner: 64,
  instances: [
    {
      runnerId: "runner-offline",
      bootId: "boot-offline",
      poolId: "default",
      status: "offline",
      runnerVersion: "0.2.0",
      nemoVersion: "0.23.0",
      compilerCapable: true,
      maxConcurrency: 64,
      desiredGeneration: 2,
      appliedGeneration: 2,
      load: null,
      lastHeartbeatAt: "2026-08-20T10:00:00.000Z",
    },
    {
      runnerId: "runner-ready",
      bootId: "boot-ready",
      poolId: "default",
      status: "ready",
      runnerVersion: "0.2.0",
      nemoVersion: "0.23.0",
      compilerCapable: true,
      maxConcurrency: 64,
      desiredGeneration: 2,
      appliedGeneration: 2,
      load: null,
      lastHeartbeatAt: "2026-08-20T10:01:00.000Z",
    },
  ],
  capacity: {
    readyRunners: 1,
    totalRunners: 2,
    currentRps: 0,
    safeRpsCapacity: 50,
    utilization: 0,
    inflightUtilization: 0,
    cpuUtilization: 0,
    memoryUtilization: 0,
    queueDepth: 0,
    errorRate: 0,
    latencyP95Ms: 0,
    recommendedReplicas: 1,
    headroomRps: 50,
  },
};

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={client}><RunnersPage /></QueryClientProvider>);
}

describe("Runner capacity removal", () => {
  beforeEach(() => {
    mocks.role = "admin";
    mocks.listRunnerPools.mockReset().mockResolvedValue({ items: [runnerPool] });
    mocks.removeRunnerInstance.mockReset().mockResolvedValue(undefined);
    mocks.toastSuccess.mockReset();
  });

  afterEach(cleanup);

  it("offers removal only for an offline Runner and confirms it in the shared side Sheet", async () => {
    renderPage();

    const removeOffline = await screen.findByRole("button", { name: "Remove runner-offline" });
    expect(screen.queryByRole("button", { name: "Remove runner-ready" })).toBeNull();

    fireEvent.click(removeOffline);
    expect(screen.getByText("Remove this offline Runner?")).toBeTruthy();
    expect(screen.getByText(/runtime events, and audit history remain/i)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Remove Runner" }));

    await waitFor(() => expect(mocks.removeRunnerInstance).toHaveBeenCalledWith("runner-offline"));
    await waitFor(() => expect(mocks.toastSuccess).toHaveBeenCalledWith("Offline Runner removed"));
  });

  it("does not expose removal controls to a non-administrator", async () => {
    mocks.role = "member";
    renderPage();

    expect(await screen.findByText("runner-offline")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Remove runner-/ })).toBeNull();
  });

  it("keeps the Sheet open and shows a reconnect conflict", async () => {
    mocks.removeRunnerInstance.mockRejectedValue(new Error("Only an offline Runner registration can be removed."));
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Remove runner-offline" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove Runner" }));

    expect((await screen.findByRole("alert")).textContent).toContain("Only an offline Runner registration can be removed.");
    expect(screen.getByText("Remove this offline Runner?")).toBeTruthy();
  });
});
