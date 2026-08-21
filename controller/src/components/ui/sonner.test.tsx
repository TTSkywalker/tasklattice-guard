import { cleanup, render, waitFor } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { toast } from "sonner";

import { Toaster } from "./sonner";

describe("Toaster", () => {
  beforeAll(() => {
    vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));
  });

  afterAll(() => vi.unstubAllGlobals());

  afterEach(() => {
    toast.dismiss();
    cleanup();
  });

  it("shows global notifications at the top right below the application header", async () => {
    render(<Toaster />);
    toast.success("Saved");

    await waitFor(() => {
      const toaster = document.querySelector<HTMLOListElement>("[data-sonner-toaster]");
      expect(toaster?.dataset.yPosition).toBe("top");
      expect(toaster?.dataset.xPosition).toBe("right");
      expect(toaster?.style.getPropertyValue("--offset-top")).toBe("calc(4rem + 1rem)");
      expect(toaster?.style.getPropertyValue("--offset-right")).toBe("1rem");
      expect(toaster?.style.getPropertyValue("--mobile-offset-top")).toBe("calc(4rem + 1rem)");
    });
  });
});
