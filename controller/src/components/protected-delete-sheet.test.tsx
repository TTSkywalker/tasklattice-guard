import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ProtectedDeleteSheet, type ProtectedDeleteCopy } from "./protected-delete-sheet";

const copy: ProtectedDeleteCopy = {
  eyebrow: "Protected delete",
  title: "Disable Guardrail",
  description: "Check traffic first.",
  protectedMessage: "Recent traffic requires confirmation.",
  clearMessage: "No recent traffic.",
  retentionNote: "Audit and runtime history remain unchanged.",
  continueLabel: "Continue",
  deleteLabel: "Disable",
  deletingLabel: "Disabling",
  confirmTitle: "Confirm risk",
  confirmDescription: "Type the resource name.",
  confirmWarning: "Traffic may be affected.",
  typeNameLabel: "Resource name",
  protectedDeleteLabel: "Confirm disable",
  cancelLabel: "Cancel",
  backLabel: "Back",
  retryLabel: "Retry",
  reasonLabel: "Reason",
};

describe("ProtectedDeleteSheet", () => {
  it("requires a reason and a second exact-name confirmation when recent traffic exists", () => {
    const confirm = vi.fn();
    const { rerender } = render(<ProtectedDeleteSheet copy={copy} deleting={false} entityName="payments" error={null} impactItems={[{ label: "Incoming", value: 12 }]} loading={false} onConfirm={confirm} onOpenChange={() => undefined} onRetry={() => undefined} open ready requiresConfirmation reason="" onReasonChange={() => undefined} />);
    expect((screen.getByRole("button", { name: "Continue" }) as HTMLButtonElement).disabled).toBe(true);

    rerender(<ProtectedDeleteSheet copy={copy} deleting={false} entityName="payments" error={null} impactItems={[{ label: "Incoming", value: 12 }]} loading={false} onConfirm={confirm} onOpenChange={() => undefined} onRetry={() => undefined} open ready requiresConfirmation reason="production cleanup" onReasonChange={() => undefined} />);
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    const confirmButton = screen.getByRole("button", { name: "Confirm disable" });
    expect((confirmButton as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Resource name"), { target: { value: "payments" } });
    fireEvent.click(confirmButton);
    expect(confirm).toHaveBeenCalledWith(true, "payments");
  });
});
