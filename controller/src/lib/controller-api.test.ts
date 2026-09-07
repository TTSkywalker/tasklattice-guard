import { afterEach, describe, expect, it, vi } from "vitest";
import { requestController } from "./controller-api";

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe("Controller authorization recovery", () => {
  it.each([401, 403, 500])("preserves HTTP %s errors without replaying writes", async (status) => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { message: "Rejected write" } }), { status }));
    vi.stubGlobal("fetch", fetch);
    const dispatch = vi.spyOn(window, "dispatchEvent");
    await expect(requestController("/api/v1/guardrails", { method: "POST", body: "{}" })).rejects.toThrow("Rejected write");
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(dispatch.mock.calls.filter(([event]) => event.type === "tasklattice:unauthorized")).toHaveLength(status === 500 ? 0 : 1);
  });
});
