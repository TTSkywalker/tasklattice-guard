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

describe("Runner instance management HTTP routes", () => {
  it("does not allow a member to remove a Runner registration", async () => {
    const removeRunnerInstance = vi.fn();
    const app = appWith({ user: { id: "member-1", role: "user" } }, { removeRunnerInstance });

    const response = await app.request("/api/v1/runner-instances/runner-offline", { method: "DELETE" });

    expect(response.status).toBe(403);
    expect(removeRunnerInstance).not.toHaveBeenCalled();
  });

  it("forwards an offline Runner removal to the service for an administrator", async () => {
    const removeRunnerInstance = vi.fn().mockResolvedValue(undefined);
    const app = appWith({ user: { id: "admin-1", role: "admin" } }, { removeRunnerInstance });

    const response = await app.request("/api/v1/runner-instances/runner-offline", { method: "DELETE" });

    expect(response.status).toBe(204);
    expect(removeRunnerInstance).toHaveBeenCalledWith({
      runnerId: "runner-offline",
      actorId: "admin-1",
    });
  });
});

function appWith(
  session: { user: { id: string; role: string } } | null,
  service: Partial<ControlPlaneService>,
) {
  const auth = {
    api: { getSession: vi.fn().mockResolvedValue(session) },
    handler: vi.fn(),
  } as unknown as ControllerAuth;
  return createHttpApp({
    config,
    auth,
    service: service as ControlPlaneService,
    runnerControl: {} as RunnerControlServer,
    metrics: {} as ControllerMetrics,
  });
}
