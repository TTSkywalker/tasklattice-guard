import type { RunnerStatus } from "../../shared/lifecycle.js";
import type {
  PlatformOperationalStatus,
  PlatformStatusReason,
} from "../../shared/platform-status.js";

type RunnerPoolStatusInput = {
  desiredReplicas: number;
  instances: Array<{
    status: RunnerStatus;
    lastHeartbeatAt: Date;
    appliedGeneration: number;
    load?: { requestsDelta: number; errorsDelta: number; timeoutsDelta: number } | null;
  }>;
  capacity: {
    readyRunners: number;
    status: "ready" | "busy" | "saturated" | "degraded" | "offline";
  };
};

export type DerivedRunnerFleetStatus = {
  status: PlatformOperationalStatus;
  reasons: PlatformStatusReason[];
  servingRunners: number;
  desiredRunners: number;
  connectedRunners: number;
  totalRunners: number;
  convergedRunners: number;
  saturatedRunners: number;
};

export function deriveRunnerFleetStatus(pool: RunnerPoolStatusInput | undefined, evidence: {
  observedAt: Date;
  offlineAfterSeconds: number;
  desiredGeneration: number;
}): DerivedRunnerFleetStatus {
  const instances = pool?.instances ?? [];
  const cutoff = evidence.observedAt.getTime() - evidence.offlineAfterSeconds * 1_000;
  const connected = instances.filter((runner) => runner.status !== "offline"
    && runner.lastHeartbeatAt instanceof Date && runner.lastHeartbeatAt.getTime() >= cutoff);
  const stale = instances.filter((runner) => runner.status !== "offline" && !connected.includes(runner));
  const converged = connected.filter((runner) => runner.status !== "syncing" && runner.appliedGeneration === evidence.desiredGeneration);
  const saturated = converged.filter((runner) => runner.status === "saturated");
  const servingRunners = Math.min(converged.length, pool?.capacity.readyRunners ?? 0);
  const desiredRunners = pool?.desiredReplicas ?? 0;

  const summary = {
    servingRunners,
    desiredRunners,
    connectedRunners: connected.length,
    totalRunners: instances.length,
    convergedRunners: converged.length,
    saturatedRunners: saturated.length,
  };

  if (connected.length === 0) {
    return { status: "unavailable", reasons: ["no_connected_runners", ...(stale.length ? ["runner_heartbeat_stale" as const] : [])], ...summary };
  }
  if (servingRunners === 0 && converged.length === 0) {
    return { status: "initializing", reasons: ["runner_configuration_syncing"], ...summary };
  }
  if (servingRunners === 0) {
    return { status: "unavailable", reasons: ["no_serving_runners"], ...summary };
  }

  const reasons: PlatformStatusReason[] = [];
  if (servingRunners < desiredRunners) reasons.push("runner_capacity_below_desired");
  if (connected.length > converged.length) reasons.push("runner_configuration_syncing");
  if (stale.length) reasons.push("runner_heartbeat_stale");
  // A stale or old-generation Runner must not contribute current error evidence.
  const allServingConverged = instances.filter((runner) => ["ready", "busy", "saturated"].includes(runner.status))
    .every((runner) => converged.includes(runner));
  if (saturated.length > 0 || allServingConverged && pool?.capacity.status === "saturated") reasons.push("runner_saturated");
  if ((allServingConverged && pool?.capacity.status === "degraded") || converged.some((runner) => {
    const load = runner.load;
    return load && load.requestsDelta > 0 && (load.errorsDelta + load.timeoutsDelta) / load.requestsDelta >= 0.05;
  })) reasons.push("runner_errors");

  return reasons.length > 0
    ? { status: "degraded", reasons, ...summary }
    : { status: "healthy", reasons: ["all_required_components_ready"], ...summary };
}
