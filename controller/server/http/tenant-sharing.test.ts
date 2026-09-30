// @vitest-environment node
import { resolve } from "node:path";
import { describe, expect, it, vi } from "vitest";

import type { ControllerAuth } from "../auth.js";
import { loadConfig } from "../config.js";
import type { ControllerMetrics } from "../metrics.js";
import type { RunnerControlServer } from "../control-channel/control-server.js";
import type { ControlPlaneService } from "../services/control-plane.js";
import { currentTenantId } from "../services/tenant-context.js";
import type { TenantShareService } from "../services/tenant-shares.js";
import type { AccessTokenService } from "../services/access-tokens.js";
import { createHttpApp } from "./app.js";

const config = loadConfig({
  NODE_ENV: "test", CONTROLLER_DATABASE_URL: "postgresql://controller:controller@localhost/controller",
  CONTROLLER_RUNNER_TOKEN: "runner-token-that-is-at-least-32-characters",
  CONTROLLER_ARTIFACT_SIGNING_KEY_PATH: "/tmp/controller-signing-key.pem",
  CONTROLLER_POLICY_CATALOG_DIR: resolve("../runner/toolkit/policy_library/assets"),
  BETTER_AUTH_SECRET: "better-auth-secret-that-is-at-least-32-characters",
});

function setup(tenantId?: string) {
  const getSession = vi.fn().mockResolvedValue({ user: { id: "actor-b", role: "admin", tenantId } });
  const listShares = vi.fn(async () => [{ id: "grant", tenantId: currentTenantId() }]);
  const createShare = vi.fn(async () => ({ id: "grant", tenantId: currentTenantId() }));
  const revokeShare = vi.fn(async () => undefined);
  const shares = { listShares, createShare, revokeShare } as unknown as TenantShareService;
  const service = { updateRunnerPool: vi.fn() } as unknown as ControlPlaneService;
  const app = createHttpApp({
    config, auth: { api: { getSession } } as unknown as ControllerAuth,
    accessTokens: {} as AccessTokenService, tenantShares: shares,
    service, runnerControl: {} as RunnerControlServer, metrics: {} as ControllerMetrics,
  });
  return { app, listShares, createShare, revokeShare, service };
}

describe("tenant share HTTP boundary", () => {
  it("uses the authenticated tenant for share reads and writes", async () => {
    const { app, createShare } = setup("tenantB");
    const list = await app.request("/api/v1/account/shares");
    expect(list.status).toBe(200);
    expect(await list.json()).toMatchObject({ items: [{ tenantId: "tenantB" }] });
    const create = await app.request("/api/v1/account/shares", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ resourceType: "guardrail", resourceId: "guard", recipientTenantId: "tenantC" }),
    });
    expect(create.status).toBe(201);
    expect(createShare).toHaveBeenCalledWith({ resourceType: "guardrail", resourceId: "guard", recipientTenantId: "tenantC" }, "actor-b");
    expect(await create.json()).toMatchObject({ share: { tenantId: "tenantB" } });
  });

  it("fails closed when an authenticated session has no tenant", async () => {
    const { app, listShares } = setup();
    expect((await app.request("/api/v1/account/shares")).status).toBe(401);
    expect(listShares).not.toHaveBeenCalled();
  });

  it("keeps tenant-owned administrators away from platform runner mutations", async () => {
    const { app, service } = setup("tenantB");
    const response = await app.request("/api/v1/runner-pools/default", { method: "PATCH", body: "not-json" });
    expect(response.status).toBe(403);
    expect(vi.mocked(service.updateRunnerPool)).not.toHaveBeenCalled();
  });
});
