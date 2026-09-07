import { describe, expect, it } from "vitest";

import { deriveRunnerFleetStatus } from "./platform-status.js";

const runner = (status: "syncing" | "ready" | "busy" | "saturated" | "offline") => ({ status, appliedGeneration: 7, lastHeartbeatAt: new Date("2026-09-06T05:00:00Z") });
const evidence = { observedAt: new Date("2026-09-06T05:00:10Z"), offlineAfterSeconds: 30, desiredGeneration: 7 };

describe("deriveRunnerFleetStatus", () => {
  it("does not trust a persisted ready status after its heartbeat expires", () => {
    expect(deriveRunnerFleetStatus({ desiredReplicas: 1,
      instances: [{ ...runner("ready"), lastHeartbeatAt: new Date("2026-09-06T04:59:00Z") }],
      capacity: { readyRunners: 1, status: "ready" },
    }, evidence)).toMatchObject({ status: "unavailable", servingRunners: 0, connectedRunners: 0, reasons: ["no_connected_runners", "runner_heartbeat_stale"] });
  });
  it.each([6, 8])("does not count generation %s as evidence for current generation 7", (appliedGeneration) => {
    expect(deriveRunnerFleetStatus({ desiredReplicas: 1,
      instances: [{ ...runner("ready"), appliedGeneration }], capacity: { readyRunners: 1, status: "ready" },
    }, evidence)).toMatchObject({ status: "initializing", servingRunners: 0, convergedRunners: 0, connectedRunners: 1 });
  });
  it("counts only fresh converged instances despite cached pool capacity", () => {
    expect(deriveRunnerFleetStatus({ desiredReplicas: 3, instances: [runner("ready"),
      { ...runner("ready"), appliedGeneration: 6 },
      { ...runner("ready"), lastHeartbeatAt: new Date("2026-09-06T04:59:00Z") },
    ], capacity: { readyRunners: 3, status: "ready" } }, evidence)).toMatchObject({
      status: "degraded", servingRunners: 1, convergedRunners: 1, connectedRunners: 2,
      reasons: ["runner_capacity_below_desired", "runner_configuration_syncing", "runner_heartbeat_stale"],
    });
  });
  it.each(["saturated", "degraded"] as const)("ignores stale %s pressure evidence", (status) => {
    expect(deriveRunnerFleetStatus({ desiredReplicas: 1, instances: [runner("ready"),
      { ...runner("saturated"), lastHeartbeatAt: new Date("2026-09-06T04:59:00Z") },
    ], capacity: { readyRunners: 2, status } }, evidence)).toMatchObject({
      servingRunners: 1, reasons: ["runner_heartbeat_stale"],
    });
  });
  it("is unavailable when no Runner is connected", () => {
    expect(deriveRunnerFleetStatus({
      desiredReplicas: 2,
      instances: [runner("offline")],
      capacity: { readyRunners: 0, status: "offline" },
    }, evidence)).toMatchObject({ status: "unavailable", reasons: ["no_connected_runners"] });
  });

  it("is initializing while connected Runners apply desired configuration", () => {
    expect(deriveRunnerFleetStatus({
      desiredReplicas: 2,
      instances: [runner("syncing"), runner("syncing")],
      capacity: { readyRunners: 0, status: "offline" },
    }, evidence)).toMatchObject({ status: "initializing", reasons: ["runner_configuration_syncing"] });
  });

  it("is unavailable when connected Runners cannot serve traffic", () => {
    expect(deriveRunnerFleetStatus({
      desiredReplicas: 1,
      instances: [runner("ready")],
      capacity: { readyRunners: 0, status: "offline" },
    }, evidence)).toMatchObject({ status: "unavailable", reasons: ["no_serving_runners"] });
  });

  it("is degraded but serving when capacity is below the desired replica count", () => {
    expect(deriveRunnerFleetStatus({
      desiredReplicas: 2,
      instances: [runner("ready"), runner("offline")],
      capacity: { readyRunners: 1, status: "ready" },
    }, evidence)).toMatchObject({ status: "degraded", reasons: ["runner_capacity_below_desired"], servingRunners: 1 });
  });

  it("is degraded when a serving Runner is saturated", () => {
    expect(deriveRunnerFleetStatus({
      desiredReplicas: 1,
      instances: [runner("saturated")],
      capacity: { readyRunners: 1, status: "saturated" },
    }, evidence)).toMatchObject({ status: "degraded", reasons: ["runner_saturated"] });
  });

  it("is healthy only when desired capacity is serving and converged", () => {
    expect(deriveRunnerFleetStatus({
      desiredReplicas: 2,
      instances: [runner("ready"), runner("busy")],
      capacity: { readyRunners: 2, status: "busy" },
    }, evidence)).toMatchObject({
      status: "healthy",
      reasons: ["all_required_components_ready"],
      servingRunners: 2,
      connectedRunners: 2,
      convergedRunners: 2,
    });
  });
});
