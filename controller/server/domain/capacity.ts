export type RunnerCapacityInput = {
  status: string;
  inflight: number;
  maxConcurrency: number;
  queueDepth: number;
  cpuUtilization: number;
  memoryUtilization: number;
  requestsPerSecond: number;
  errorRate: number;
  latencyP95Ms: number;
};

export type PoolCapacity = {
  readyRunners: number;
  totalRunners: number;
  totalConcurrency: number;
  inflight: number;
  queueDepth: number;
  requestsPerSecond: number;
  currentRps: number;
  safeRpsCapacity: number;
  headroomRps: number;
  utilization: number;
  inflightUtilization: number;
  cpuUtilization: number;
  memoryUtilization: number;
  errorRate: number;
  latencyP95Ms: number;
  status: "ready" | "busy" | "saturated" | "degraded" | "offline";
  recommendedReplicas: number;
  bottleneck: "concurrency" | "queue" | "cpu" | "memory" | "none";
};

export function calculatePoolCapacity(
  runners: readonly RunnerCapacityInput[],
  safeRpsPerRunner: number,
  predictedPeakRps?: number,
  safetyFactor = 1.25,
  minimumReplicas = 1,
): PoolCapacity {
  const ready = runners.filter((runner) => ["ready", "busy", "saturated"].includes(runner.status));
  const totalConcurrency = ready.reduce((sum, runner) => sum + Math.max(0, runner.maxConcurrency), 0);
  const inflight = ready.reduce((sum, runner) => sum + Math.max(0, runner.inflight), 0);
  const queueDepth = ready.reduce((sum, runner) => sum + Math.max(0, runner.queueDepth), 0);
  const requestsPerSecond = ready.reduce((sum, runner) => sum + Math.max(0, runner.requestsPerSecond), 0);
  const concurrency = totalConcurrency > 0 ? inflight / totalConcurrency : 0;
  const cpu = maximum(ready.map((runner) => runner.cpuUtilization));
  const memory = maximum(ready.map((runner) => runner.memoryUtilization));
  const queue = queueDepth > 0 ? Math.min(1, queueDepth / Math.max(1, ready.length * 10)) : 0;
  const pressure = { concurrency, queue, cpu, memory };
  const [bottleneck, utilization] = Object.entries(pressure).reduce(
    (highest, candidate) => candidate[1] > highest[1] ? candidate : highest,
    ["concurrency", concurrency] as [keyof typeof pressure, number],
  );
  const degraded = ready.some((runner) => runner.errorRate >= 0.05);
  const status = ready.length === 0
    ? "offline"
    : degraded
      ? "degraded"
      : utilization >= 0.9 || queueDepth > ready.length * 10
        ? "saturated"
        : utilization >= 0.7
          ? "busy"
          : "ready";
  const demand = Math.max(requestsPerSecond, predictedPeakRps ?? 0);
  const safeRpsCapacity = ready.length * Math.max(0, safeRpsPerRunner);
  const recommendedReplicas = Math.max(
    minimumReplicas,
    safeRpsPerRunner > 0 ? Math.ceil((demand * safetyFactor) / safeRpsPerRunner) : ready.length,
  );
  return {
    readyRunners: ready.length,
    totalRunners: runners.length,
    totalConcurrency,
    inflight,
    queueDepth,
    requestsPerSecond: round(requestsPerSecond),
    currentRps: round(requestsPerSecond),
    safeRpsCapacity: round(safeRpsCapacity),
    headroomRps: round(Math.max(0, safeRpsCapacity - requestsPerSecond)),
    utilization: round(Math.min(1, utilization)),
    inflightUtilization: round(Math.min(1, concurrency)),
    cpuUtilization: round(cpu),
    memoryUtilization: round(memory),
    errorRate: round(maximum(ready.map((runner) => runner.errorRate))),
    latencyP95Ms: round(maximum(ready.map((runner) => runner.latencyP95Ms))),
    status,
    recommendedReplicas,
    bottleneck: utilization === 0 ? "none" : bottleneck as keyof typeof pressure,
  };
}

function maximum(values: readonly number[]): number {
  return values.reduce((result, value) => Math.max(result, Math.max(0, value)), 0);
}

function round(value: number): number {
  return Math.round(value * 10_000) / 10_000;
}
