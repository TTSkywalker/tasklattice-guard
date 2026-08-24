import { resolve } from "node:path";

import { describe, expect, it, vi } from "vitest";

import type { ControllerAuth } from "../auth.js";
import { loadConfig } from "../config.js";
import type { RunnerControlServer } from "../control-channel/control-server.js";
import type { ControllerMetrics } from "../metrics.js";
import type { ControlPlaneService } from "../services/control-plane.js";
import { createHttpApp } from "./app.js";

const config = loadConfig({
  NODE_ENV: "test",
  CONTROLLER_DATABASE_URL: "postgresql://controller:controller@localhost/controller",
  CONTROLLER_RUNNER_TOKEN: "runner-token-that-is-at-least-32-characters",
  CONTROLLER_ARTIFACT_SIGNING_KEY_PATH: "/tmp/controller-signing-key.pem",
  CONTROLLER_POLICY_CATALOG_DIR: resolve("../runner/toolkit/policy_library/assets"),
  BETTER_AUTH_SECRET: "better-auth-secret-that-is-at-least-32-characters",
});

describe("Deployment deletion HTTP routes", () => {
  it("requires an administrator to inspect impact or delete a Deployment", async () => {
    const app = appWith({ user: { id: "member-1", role: "user" } }, {});

    expect((await app.request("/api/v1/deployments/deployment-1/deletion-impact")).status).toBe(403);
    expect((await app.request("/api/v1/deployments/deployment-1", {
      method: "DELETE",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ reason: "Retired route" }),
    })).status).toBe(403);
  });

  it("forwards protected soft-delete confirmation and distributes the new desired state", async () => {
    const deploymentDeletionImpact = vi.fn().mockResolvedValue({
      resourceId: "deployment-1",
      windowMinutes: 30,
      incomingRequestCount: 12,
      lastRequestAt: "2026-08-24T08:00:00.000Z",
      activeDeploymentCount: 1,
      telemetryFresh: true,
      telemetryWatermark: "2026-08-24T08:00:01.000Z",
      requiresSecondConfirmation: true,
    });
    const softDeleteDeployment = vi.fn().mockResolvedValue(undefined);
    const distributeDesiredState = vi.fn().mockResolvedValue({ desiredGeneration: 8, distributionStatus: "ready" });
    const app = appWith(
      { user: { id: "admin-1", role: "admin" } },
      { deploymentDeletionImpact, softDeleteDeployment },
      distributeDesiredState,
    );

    const impact = await app.request("/api/v1/deployments/deployment-1/deletion-impact");
    const deleted = await app.request("/api/v1/deployments/deployment-1", {
      method: "DELETE",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        reason: "Traffic moved to the regional route",
        confirmRecentTraffic: true,
        confirmationName: "Regional traffic",
      }),
    });

    expect(impact.status).toBe(200);
    expect(await impact.json()).toMatchObject({ resourceId: "deployment-1", incomingRequestCount: 12 });
    expect(deleted.status).toBe(204);
    expect(softDeleteDeployment).toHaveBeenCalledWith({
      id: "deployment-1",
      actorId: "admin-1",
      reason: "Traffic moved to the regional route",
      confirmRecentTraffic: true,
      confirmationName: "Regional traffic",
    });
    expect(distributeDesiredState).toHaveBeenCalledOnce();
  });
});

function appWith(
  session: { user: { id: string; role: string } } | null,
  service: Partial<ControlPlaneService>,
  distributeDesiredState = vi.fn().mockResolvedValue({ desiredGeneration: 7, distributionStatus: "ready" }),
) {
  const auth = {
    api: { getSession: vi.fn().mockResolvedValue(session) },
    handler: vi.fn(),
  } as unknown as ControllerAuth;
  return createHttpApp({
    config,
    auth,
    service: service as ControlPlaneService,
    runnerControl: {
      distributionStatus: vi.fn().mockResolvedValue({ desiredGeneration: 7, distributionStatus: "ready" }),
      distributeDesiredState,
    } as unknown as RunnerControlServer,
    metrics: {} as ControllerMetrics,
  });
}
