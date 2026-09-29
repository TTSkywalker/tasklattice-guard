import { createMemoryHistory, createRouter } from "@tanstack/react-router";
import { describe, expect, it } from "vitest";
import { routeTree } from "./app-router";

// Use the actual application route tree so renamed links cannot silently 404.
describe("Integration navigation", () => {
  it("restores canonical event filters from shareable URLs and browser history", async () => {
    const history = createMemoryHistory({ initialEntries: ["/guardrails/guardrail-default?tab=findings&window=7d&severity=high,critical,high,invalid"] });
    const router = createRouter({ routeTree, history });
    await router.load();
    expect(router.state.matches.at(-1)?.search).toMatchObject({ tab: "findings", window: "7d", severity: "critical,high" });
    await router.navigate({ to: "/guardrails/$guardrailId", params: { guardrailId: "guardrail-default" }, search: { tab: "findings", window: "7d" } });
    expect(router.state.matches.at(-1)?.search.severity).toBeUndefined();
    history.back();
    await router.load();
    expect(router.state.matches.at(-1)?.search.severity).toBe("critical,high");
  });

  it.each([["testing", "testing"], ["validation", undefined]])("handles Guardrail tab %s without a legacy alias", async (tab, expected) => {
    const router = createRouter({ routeTree, history: createMemoryHistory({ initialEntries: [`/guardrails/guardrail-default?tab=${tab}`] }) });
    await router.load();
    expect(router.state.matches.at(-1)?.routeId).toBe("/guardrails/$guardrailId");
    expect(router.state.matches.at(-1)?.search.tab).toBe(expected);
  });

  it.each([
    ["/account", "/account", {}],
    ["/account/security", "/account/security", {}],
    ["/account/access-tokens", "/account/access-tokens", {}],
    ["/integration/routers", "/integration/routers", {}],
    ["/integration/routers/router-123", "/integration/routers/$routerId", { routerId: "router-123" }],
    ["/integration/endpoint", "/integration/endpoint", {}],
  ])("resolves %s", async (path, routeId, params) => {
    const router = createRouter({ routeTree, history: createMemoryHistory({ initialEntries: [path] }) });
    await router.load();
    expect(router.state.matches.at(-1)?.routeId).toBe(routeId);
    expect(router.state.matches.at(-1)?.params).toEqual(params);
    expect(router.state.matches.at(-1)?.status).toBe("success");
  });
});
