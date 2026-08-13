import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RuntimeHealthAlert, type RuntimeHealthAlertMetrics } from "./runtime-health-alert";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, number>) => ({
      "dashboard.degraded": "Degraded",
      "dashboard.healthFailClosed": "Fail-closed decisions were detected.",
      "dashboard.healthLatency": "Runtime latency is elevated.",
      "dashboard.healthIntegration": `${values?.count ?? 0} integrations need attention.`,
      "dashboard.healthSystem": "A required runtime capability needs attention.",
    }[key] ?? key),
  }),
}));

const healthy: RuntimeHealthAlertMetrics = {
  system_status: "healthy",
  latency_slo: { p95_status: "healthy" },
  fail_closed_count: 0,
  degraded_integrations: 0,
};

describe("RuntimeHealthAlert", () => {
  afterEach(cleanup);

  it("renders nothing when the runtime is healthy", () => {
    const view = render(<RuntimeHealthAlert metrics={healthy} />);

    expect(view.container.childElementCount).toBe(0);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("announces the highest-priority runtime anomaly", () => {
    render(<RuntimeHealthAlert metrics={{
      ...healthy,
      system_status: "degraded",
      latency_slo: { p95_status: "breached" },
      fail_closed_count: 2,
      degraded_integrations: 1,
    }} />);

    expect(screen.getByRole("alert").textContent).toContain("Degraded");
    expect(screen.getByRole("alert").textContent).toContain("Fail-closed decisions were detected.");
    expect(screen.queryByText("Runtime latency is elevated.")).toBeNull();
  });

  it("covers a degraded system without a more specific metric anomaly", () => {
    render(<RuntimeHealthAlert metrics={{ ...healthy, system_status: "degraded" }} />);

    expect(screen.getByRole("alert").textContent).toContain("A required runtime capability needs attention.");
  });
});
