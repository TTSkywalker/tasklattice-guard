import type { ReactNode } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { EvidenceRecord } from "@/lib/api";

import { RuntimeEventStream, shortEventId } from "./runtime-event-stream";

vi.mock("@tanstack/react-router", () => ({
  Link: ({ children, to }: { children: ReactNode; to: string }) => <a href={to}>{children}</a>,
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en-US", exists: () => false },
  }),
}));

describe("RuntimeEventStream", () => {
  afterEach(cleanup);

  it("uses a dense operations table with millisecond timestamps", () => {
    const item: EvidenceRecord = {
      id: "evidence-12345678abcdef12",
      created_at: "2026-08-14T03:17:49.123456+00:00",
      kind: "interaction.decision",
      outcome: "block",
      guardrail_id: "guardrail-banker",
      deployment_id: "deployment-dev",
      integration_id: "integration-dev",
      actor_id: null,
      risk: "critical",
      detail: "SQL injection attempt blocked.",
      metadata: {},
    };

    render(<RuntimeEventStream items={[item]} loading={false} guardrails={[{ id: "guardrail-banker", name: "banker" }]} />);

    expect(screen.getByRole("columnheader", { name: "dashboard.lastSeen" })).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "dashboard.message" })).toBeTruthy();
    expect(screen.getByText(/:17:49\.123/)).toBeTruthy();
    expect(screen.getByText("SQL injection attempt blocked.")).toBeTruthy();
    expect(screen.getByTitle(item.id).textContent).toBe("#abcdef12");
  });

  it("keeps only the final eight characters in the visible event ID", () => {
    expect(shortEventId("evidence-12345678abcdef12")).toBe("abcdef12");
  });
});
