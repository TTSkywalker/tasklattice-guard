import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";

import { RuntimePostureFields } from "./runtime-posture-fields";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => ({
      "guardrailWizard.safetyLevel": "Safety level",
      "guardrailWizard.safetyLevelHelpLabel": "How safety level works",
      "guardrailWizard.safetyLevelHelp": "Controls escalation to deeper evaluators.",
      "guardrailWizard.safetyLevelOptions.balanced": "Balanced · Escalate uncertainty",
      "guardrailWizard.safetyLevelOptions.strict": "Strict · Broader deep review",
      "guardrailWizard.safetyLevelDescriptions.balanced": "Review uncertain results with lower latency.",
      "guardrailWizard.safetyLevelDescriptions.strict": "Review more eligible traffic with higher latency.",
      "guardrailWizard.outputDelivery": "Output delivery",
      "guardrailWizard.outputDeliveryHelpLabel": "How output delivery works",
      "guardrailWizard.outputDeliveryHelp": "Controls output buffering.",
      "guardrailWizard.outputDeliveryOptions.interruptible": "Interruptible · Release immediately",
      "guardrailWizard.outputDeliveryOptions.window_buffered": "Window buffered · Check in segments",
      "guardrailWizard.outputDeliveryOptions.full_buffered": "Full buffered · Check before release",
      "guardrailWizard.outputDeliveryDescriptions.interruptible": "Already released content cannot be recalled.",
      "guardrailWizard.outputDeliveryDescriptions.window_buffered": "Check short windows before release.",
      "guardrailWizard.outputDeliveryDescriptions.full_buffered": "Hold the complete response until checks finish.",
    }[key] ?? key),
  }),
}));

function fields(safetyLevel: "balanced" | "strict", outputDelivery: "interruptible" | "window_buffered" | "full_buffered") {
  return (
    <TooltipProvider>
      <RuntimePostureFields
        safetyLevel={safetyLevel}
        outputDelivery={outputDelivery}
        onSafetyLevelChange={vi.fn()}
        onOutputDeliveryChange={vi.fn()}
      />
    </TooltipProvider>
  );
}

describe("RuntimePostureFields", () => {
  beforeAll(() => {
    vi.stubGlobal("ResizeObserver", class {
      observe() {}
      unobserve() {}
      disconnect() {}
    });
  });
  afterAll(() => vi.unstubAllGlobals());
  afterEach(cleanup);

  it("associates both selects with labels, help triggers, and current behavior", () => {
    render(fields("balanced", "window_buffered"));

    expect(screen.getByRole("combobox", { name: "Safety level" })).toBeTruthy();
    expect(screen.getByRole("combobox", { name: "Output delivery" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "How safety level works" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "How output delivery works" })).toBeTruthy();
    expect(screen.getByText("Review uncertain results with lower latency.")).toBeTruthy();
    expect(screen.getByText("Check short windows before release.")).toBeTruthy();
  });

  it("updates the consequence copy with the selected posture", () => {
    const view = render(fields("balanced", "window_buffered"));

    view.rerender(fields("strict", "interruptible"));

    expect(screen.getByText("Review more eligible traffic with higher latency.")).toBeTruthy();
    expect(screen.getByText("Already released content cannot be recalled.")).toBeTruthy();
  });

  it("opens help on click for touch and keyboard users", () => {
    render(fields("balanced", "window_buffered"));

    fireEvent.click(screen.getByRole("button", { name: "How safety level works" }));

    expect(screen.getByRole("tooltip").textContent).toContain("Controls escalation to deeper evaluators.");
  });
});
