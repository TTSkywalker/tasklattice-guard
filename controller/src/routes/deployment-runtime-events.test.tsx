import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { DeploymentRuntimeTrace } from "@/lib/api";
import { DeploymentRuntimeEventTable } from "./deployment-detail";

vi.mock("react-i18next", () => ({
  initReactI18next: { type: "3rdParty", init: () => undefined },
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en", exists: () => false } }),
}));

vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { role: "admin" } }) }));

const trace: DeploymentRuntimeTrace = {
  id: "trace-1",
  created_at: "2026-08-14T03:11:02.123Z",
  deployment_id: "deployment-1",
  guardrail_id: "guardrail-1",
  guardrail_version: 1,
  integration_id: "integration-1",
  protocol: "litellm",
  phase: "output",
  outcome: "transform",
  action: "redact",
  risk: null,
  severity: null,
  latency_ms: 15,
  timed_out: false,
  runtime_engine: "llmrails",
  config_checksum: "checksum",
  detail: "A native rail modified the interaction.",
  findings: [],
  steps: [],
};

describe("Deployment runtime event density", () => {
  afterEach(cleanup);

  it("shows millisecond timestamps in compact rows", () => {
    render(<DeploymentRuntimeEventTable traces={[trace]} loading={false} error={null} policies={[]} onInspect={() => undefined} />);
    expect(screen.getByText(/\d{2}:\d{2}:\d{2}\.123/)).toBeTruthy();
    expect(screen.getByText("15 ms")).toBeTruthy();
    expect(screen.getByRole("row", { name: /\d{2}:\d{2}:\d{2}\.123/ }).className).toContain("h-11");
  });
});
