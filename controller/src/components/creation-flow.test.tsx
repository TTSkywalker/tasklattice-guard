import { useState } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CreationFlow } from "./creation-flow";

vi.mock("@/hooks/use-mobile", () => ({ useIsMobile: () => false }));
afterEach(cleanup);

function Fixture({ freelyNavigable = false }: { freelyNavigable?: boolean }) {
  const [step, setStep] = useState(0);
  return <CreationFlow freelyNavigable={freelyNavigable} contained orientation="sidebar" progressLabel="Protection map"
    steps={[{ label: "Content", description: "Optional" }, { label: "Privacy", description: "Optional" }, { label: "Review", description: "Draft" }]}
    currentStep={step} onStepChange={setStep}><p>Current {step}</p></CreationFlow>;
}

describe("optional creation navigation", () => {
  it("allows jumping ahead without marking skipped protection steps complete", () => {
    const { container } = render(<Fixture freelyNavigable />);
    fireEvent.click(screen.getByRole("tab", { name: /Review/ }));
    expect(screen.getByText("Current 2")).toBeTruthy();
    expect(container.querySelectorAll('[data-slot="stepper-item"][data-state="completed"]').length).toBe(0);
    expect(screen.getByRole("tab", { name: /Review/ }).getAttribute("aria-current")).toBe("step");
  });

  it("supports keyboard navigation and explicit activation", () => {
    render(<Fixture freelyNavigable />);
    const content = screen.getByRole("tab", { name: /Content/ });
    content.focus();
    fireEvent.keyDown(content, { key: "End" });
    const review = screen.getByRole("tab", { name: /Review/ });
    expect(document.activeElement).toBe(review);
    fireEvent.keyDown(review, { key: "Enter" });
    expect(screen.getByText("Current 2")).toBeTruthy();
  });

  it("preserves gated navigation for existing linear wizards", () => {
    render(<Fixture />);
    const review = screen.getByRole("tab", { name: /Review/ });
    expect(review.hasAttribute("disabled")).toBe(true);
    fireEvent.click(review);
    expect(screen.getByText("Current 0")).toBeTruthy();
  });
});
