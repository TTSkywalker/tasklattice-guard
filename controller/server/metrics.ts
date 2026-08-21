import { collectDefaultMetrics, Gauge, Registry } from "prom-client";

import type { ControlPlaneService } from "./services/control-plane.js";

export class ControllerMetrics {
  readonly registry = new Registry();
  private readonly desiredGeneration: Gauge;
  private readonly runnerInstances: Gauge;
  private readonly poolUtilization: Gauge;
  private readonly poolRps: Gauge;
  private readonly poolSafeRps: Gauge;
  private readonly poolRecommendedReplicas: Gauge;
  private readonly poolQueueDepth: Gauge;
  private readonly poolErrorRate: Gauge;
  private readonly poolLatencyP95: Gauge;

  constructor() {
    collectDefaultMetrics({ register: this.registry, prefix: "guard_controller_process_" });
    this.desiredGeneration = this.gauge("guard_controller_desired_generation", "Current global desired-state generation.");
    this.runnerInstances = this.gauge("guard_controller_runner_instances", "Runner instances by pool and state.", ["pool", "status"]);
    this.poolUtilization = this.gauge("guard_controller_runner_pool_utilization_ratio", "Highest resource pressure ratio by Runner pool.", ["pool"]);
    this.poolRps = this.gauge("guard_controller_runner_pool_requests_per_second", "Observed request rate by Runner pool.", ["pool"]);
    this.poolSafeRps = this.gauge("guard_controller_runner_pool_safe_rps_capacity", "Configured safe request capacity by Runner pool.", ["pool"]);
    this.poolRecommendedReplicas = this.gauge("guard_controller_runner_pool_recommended_replicas", "Recommended Runner replicas including capacity safety factor.", ["pool"]);
    this.poolQueueDepth = this.gauge("guard_controller_runner_pool_queue_depth", "Total queued requests by Runner pool.", ["pool"]);
    this.poolErrorRate = this.gauge("guard_controller_runner_pool_error_ratio", "Highest observed Runner error ratio by pool.", ["pool"]);
    this.poolLatencyP95 = this.gauge("guard_controller_runner_pool_latency_p95_milliseconds", "Highest observed Runner p95 latency by pool.", ["pool"]);
  }

  async render(service: ControlPlaneService): Promise<string> {
    const [generation, pools] = await Promise.all([
      service.desiredGeneration(),
      service.listRunnerPoolsWithCapacity(),
    ]);
    this.desiredGeneration.set(generation);
    for (const metric of [
      this.runnerInstances,
      this.poolUtilization,
      this.poolRps,
      this.poolSafeRps,
      this.poolRecommendedReplicas,
      this.poolQueueDepth,
      this.poolErrorRate,
      this.poolLatencyP95,
    ]) metric.reset();
    for (const pool of pools) {
      const states = new Map<string, number>();
      for (const runner of pool.instances) states.set(runner.status, (states.get(runner.status) ?? 0) + 1);
      for (const [status, count] of states) this.runnerInstances.labels(pool.id, status).set(count);
      this.poolUtilization.labels(pool.id).set(pool.capacity.utilization);
      this.poolRps.labels(pool.id).set(pool.capacity.currentRps);
      this.poolSafeRps.labels(pool.id).set(pool.capacity.safeRpsCapacity);
      this.poolRecommendedReplicas.labels(pool.id).set(pool.capacity.recommendedReplicas);
      this.poolQueueDepth.labels(pool.id).set(pool.capacity.queueDepth);
      this.poolErrorRate.labels(pool.id).set(pool.capacity.errorRate);
      this.poolLatencyP95.labels(pool.id).set(pool.capacity.latencyP95Ms);
    }
    return this.registry.metrics();
  }

  private gauge(name: string, help: string, labelNames: string[] = []) {
    return new Gauge({ name, help, labelNames, registers: [this.registry] });
  }
}
