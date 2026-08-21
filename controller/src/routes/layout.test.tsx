import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { SystemStatus } from "@/lib/controller-api";

import { RuntimeHealthMenu } from "./layout";

vi.mock("@tanstack/react-router", () => ({
  Link: ({ children }: { children: ReactNode }) => <a href="/runners">{children}</a>,
  Outlet: () => null,
  useRouterState: () => "/dashboard",
}));

vi.mock("@/lib/auth", () => ({
  useAuth: () => ({ isLoading: false, status: { authenticated: true }, user: { role: "admin" } }),
}));

vi.mock("@/components/control-plane-sidebar", () => ({ ControlPlaneSidebar: () => null }));
vi.mock("@/routes/login", () => ({ LoginPage: () => null }));

vi.mock("react-i18next", () => ({
  initReactI18next: { type: "3rdParty", init: () => undefined },
  useTranslation: () => ({
    t: (key: string) => ({
      "runtimeHealth.open": "Open runtime health",
      "runtimeHealth.title": "Runtime health",
      "runtimeHealth.ready": "Runtime ready",
      "runtimeHealth.readyDescription": "Required services are ready.",
      "runtimeHealth.modelConnections": "Model connections",
      "runtimeHealth.controlPlane": "Control Plane",
      "runtimeHealth.dataPlane": "Data Plane",
      "runtimeHealth.policyAnalysis": "Policy analysis",
      "runtimeHealth.contentSafety": "Content safety",
      "runtimeHealth.topicControl": "Topic control",
      "runtimeHealth.jailbreak": "Jailbreak detection",
      "runtimeHealth.runtimeState": "Runtime state",
      "runtimeHealth.generation": "Desired generation",
      "runtimeHealth.defaultRunner": "GuardRails 0",
      "runtimeHealth.runnerReady": "Ready",
      "runtimeHealth.baselineReady": "Controller and Runner are ready.",
      "runtimeHealth.openRunners": "Open Runner capacity",
    } as Record<string, string>)[key] ?? key,
  }),
}));

const status: SystemStatus = {
  status: "ready",
  deploymentComplete: true,
  desiredGeneration: 16,
  defaultRunnerReady: true,
  modelConnections: {
    controlPlane: { provider: "DeepSeek", model: "deepseek-v4-flash" },
    dataPlane: {
      provider: "NVIDIA",
      models: [
        { capability: "contentSafety", model: "nvidia/llama-3.1-nemotron-safety-guard-8b-v3" },
        { capability: "topicControl", model: "nvidia/llama-3.1-nemoguard-8b-topic-control" },
        { capability: "jailbreak", model: "nvidia/nvidia-nemotron-nano-9b-v2" },
      ],
    },
  },
};

describe("RuntimeHealthMenu", () => {
  afterEach(cleanup);

  it("keeps both model-plane providers visible in the global trigger and menu", () => {
    render(<RuntimeHealthMenu loading={false} error={null} status={status} />);

    const trigger = screen.getByRole("button", { name: /DeepSeek · NVIDIA, Runtime ready/ });
    expect(trigger.textContent).toContain("DeepSeek · NVIDIA");
    fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false, pointerType: "mouse" });

    expect(screen.getByText("Control Plane")).toBeTruthy();
    expect(screen.getByText("Data Plane")).toBeTruthy();
    expect(screen.getByText("deepseek-v4-flash")).toBeTruthy();
    expect(screen.getByText("nvidia/llama-3.1-nemotron-safety-guard-8b-v3")).toBeTruthy();
    expect(screen.getByText("nvidia/llama-3.1-nemoguard-8b-topic-control")).toBeTruthy();
  });
});
