import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { RuntimeLogInteraction } from "@/lib/api";

import { buildTraceForest, RuntimeCheckpoint, CheckpointHistory } from "./logs";

vi.mock("react-i18next", () => ({
  initReactI18next: { type: "3rdParty", init: () => undefined },
  useTranslation: () => ({
    t: (key: string, values?: Record<string, string | number>) =>
      values?.version === undefined ? key : `${key} ${values.version}`,
    i18n: { language: "en-US", exists: () => false },
  }),
}));

vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { role: "admin" } }) }));

const interaction: RuntimeLogInteraction = {
  id: "runtime-log-1",
  created_at: "2026-08-15T05:00:00Z",
  completed_at: "2026-08-15T05:00:01Z",
  guardrail_id: "guardrail-1",
  guardrail_version: "20260904-030000.003Z",
  deployment_id: "deployment-1",
  integration_id: null,
  protocol: "openai",
  outcome: "block",
  capture_level: "trace",
  entries: [
    {
      id: "entry-input",
      trace_id: "trace-input",
      created_at: "2026-08-15T05:00:00Z",
      phase: "input",
      outcome: "allow",
      action: "pass",
      risk: null,
      latency_ms: 5,
      timed_out: false,
      detail: "Inbound request approved",
      content_before: null,
      content_after: null,
      content_available: true,
      findings: [],
      steps: [],
    },
    {
      id: "entry-output",
      trace_id: "trace-output",
      created_at: "2026-08-15T05:00:01Z",
      phase: "output",
      outcome: "block",
      action: "block",
      risk: "sensitive_data",
      latency_ms: 8,
      timed_out: false,
      detail: "Outbound response blocked",
      content_before: null,
      content_after: null,
      content_available: true,
      findings: [],
      steps: [],
    },
  ],
};

const baseProps = {
  interactions: [interaction],
  loading: false,
  error: null,
  onInspect: vi.fn(),
  guardrailName: () => "Runtime Guardrail",
  deploymentName: () => "Runtime Deployment",
};

describe("CheckpointHistory", () => {
  afterEach(cleanup);

  it("renders one traffic checkpoint per inbound and outbound log entry", () => {
    render(<CheckpointHistory {...baseProps} />);

    expect(screen.getByText("Inbound request approved")).toBeTruthy();
    expect(screen.getByText("Outbound response blocked")).toBeTruthy();
    expect(screen.getAllByRole("row")).toHaveLength(3);
    expect(screen.queryByText(/policy \/ version \/ published/i)).toBeNull();
    expect(screen.queryByText(/validation completed/i)).toBeNull();
  });

  it("renders only checkpoints supplied by the shared runtime query", () => {
    render(<CheckpointHistory {...baseProps} interactions={[{ ...interaction, entries: [interaction.entries[0]!] }]} />);

    expect(screen.getByText("Inbound request approved")).toBeTruthy();
    expect(screen.queryByText("Outbound response blocked")).toBeNull();
    expect(screen.getAllByRole("row")).toHaveLength(2);
  });
});


describe("runtime detail", () => {
  afterEach(cleanup);
  const step = (id: string, parent_id?: string) => ({ id, parent_id, name: id, kind: "action", outcome: "allow", latency_ms: 4 } as RuntimeLogInteraction["entries"][number]["steps"][number]);

  it("uses parent links even when children arrive first, and retains orphan/cyclic spans", () => {
    const forest = buildTraceForest([step("child", "root"), step("root"), step("orphan", "missing"), step("a", "b"), step("b", "a")]);
    expect(forest.map((node) => node.step.id)).toEqual(["root", "orphan", "a", "b"]);
    expect(forest[0]?.children[0]?.step.id).toBe("child");
  });

  it("labels model text and supports branch collapse and span inspection", () => {
    const entry = { ...interaction.entries[1]!, steps: [step("root"), { ...step("child", "root"), detail: "Recorded evaluation detail" }], content_before: [{ id: "text", role: "model_output", source: "model_output", text: "Model response body", truncated: false }] };
    render(<RuntimeCheckpoint entry={entry} admin />);
    expect(screen.getByRole("heading", { name: "logs.modelOutput" })).toBeTruthy();
    expect(screen.getByText("Model response body")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "logs.collapseSpan" }));
    expect(screen.queryByText("child")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "logs.expandSpan" }));
    fireEvent.click(screen.getAllByRole("button", { name: "logs.inspectSpan" })[1]!);
    expect(screen.getByText("Recorded evaluation detail")).toBeTruthy();
  });

  it("keeps captured content hidden from non-admins and explains absent traces", () => {
    render(<RuntimeCheckpoint entry={{ ...interaction.entries[1]!, content_before: [{ id: "text", role: "model_output", source: "model_output", text: "Private body", truncated: false }] }} admin={false} />);
    expect(screen.queryByText("Private body")).toBeNull();
    expect(screen.getByText("logs.traceEmpty")).toBeTruthy();
  });
});
