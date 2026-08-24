import { readFileSync } from "node:fs";
import { randomUUID } from "node:crypto";

import {
  Server,
  ServerCredentials,
  type ServerDuplexStream,
  type ServiceDefinition,
  status,
  loadPackageDefinition,
} from "@grpc/grpc-js";
import { loadSync } from "@grpc/proto-loader";

import type { ControllerConfig } from "../config.js";
import type { RunnerLoad } from "../db/schema.js";
import type { ValidationCaseResult, ValidationMetrics } from "../domain/models.js";
import type { ControllerMetrics } from "../metrics.js";
import type { ControlPlaneService } from "../services/control-plane.js";

type WireMessage = Record<string, unknown>;
type RunnerStream = ServerDuplexStream<WireMessage, WireMessage>;

type Connection = {
  stream: RunnerStream;
  runnerId: string;
  bootId: string;
  poolId: string;
  compilerCapable: boolean;
  appliedGeneration: number;
  lastReconcileGeneration: number;
};

type Registration = {
  runnerId: string;
  bootId: string;
  poolId: string;
  runnerVersion: string;
  nemoVersion: string;
  maxConcurrency: number;
  compilerCapable: boolean;
  labels?: Record<string, string>;
  appliedGeneration: string | number;
};

type Heartbeat = {
  runnerId: string;
  bootId: string;
  sequence: string | number;
  appliedGeneration: string | number;
  load?: Partial<Record<keyof RunnerLoad, string | number>>;
};

type CompileResult = {
  runnerId: string;
  compileId: string;
  accepted: boolean;
  reason?: string;
  artifact?: Record<string, unknown>;
};

type ValidationResult = {
  runnerId: string;
  runId: string;
  accepted: boolean;
  reason?: string;
  status?: string;
  metricsJson?: string;
  resultsJson?: string;
};

export class RunnerControlServer {
  private readonly grpc = new Server();
  private readonly connections = new Map<string, Connection>();
  private timers: NodeJS.Timeout[] = [];

  constructor(
    private readonly config: ControllerConfig,
    private readonly service: ControlPlaneService,
    private readonly metrics: ControllerMetrics,
  ) {
    const definition = loadSync(config.protoPath, {
      keepCase: false,
      longs: String,
      enums: String,
      defaults: true,
      oneofs: true,
    });
    const descriptor = loadPackageDefinition(definition) as unknown as {
      tasklattice: { guard: { control: { v1: { RunnerControl: { service: ServiceDefinition } } } } };
    };
    this.grpc.addService(descriptor.tasklattice.guard.control.v1.RunnerControl.service, {
      connect: (stream: RunnerStream) => this.connect(stream),
    });
  }

  async start(): Promise<void> {
    const credentials = this.credentials();
    await new Promise<void>((resolve, reject) => {
      this.grpc.bindAsync(`${this.config.grpc.host}:${this.config.grpc.port}`, credentials, (error) => {
        if (error) reject(error);
        else resolve();
      });
    });
    this.timers = [
      setInterval(() => void this.dispatchCompileRequests(), 1_000),
      setInterval(() => void this.dispatchValidationRequests(), 1_000),
      setInterval(() => void this.dispatchDesiredStateChanges(), 1_000),
      setInterval(() => void this.reconcileAll(), 30_000),
      setInterval(() => void this.service.markStaleRunnersOffline(), this.config.offlineAfterSeconds * 1_000),
    ];
    for (const timer of this.timers) timer.unref();
  }

  async stop(): Promise<void> {
    for (const timer of this.timers) clearInterval(timer);
    this.timers = [];
    for (const connection of this.connections.values()) connection.stream.end();
    await new Promise<void>((resolve) => this.grpc.tryShutdown(() => resolve()));
  }

  hasDefaultCompiler(): boolean {
    return [...this.connections.values()].some((item) => item.poolId === "default" && item.compilerCapable);
  }

  async distributeDesiredState(poolId = "default", timeoutMs = 2_500): Promise<{
    desiredGeneration: number;
    distributionStatus: "ready" | "syncing";
  }> {
    const desiredGeneration = await this.service.desiredGeneration();
    await this.dispatchDesiredStateChanges();
    const deadline = Date.now() + timeoutMs;
    while (Date.now() <= deadline) {
      const runners = [...this.connections.values()].filter((item) => item.poolId === poolId);
      if (runners.length > 0 && runners.every((item) => item.appliedGeneration >= desiredGeneration)) {
        return { desiredGeneration, distributionStatus: "ready" };
      }
      await new Promise((resolve) => setTimeout(resolve, 25));
    }
    return { desiredGeneration, distributionStatus: "syncing" };
  }

  async distributionStatus(poolId = "default"): Promise<{
    desiredGeneration: number;
    distributionStatus: "ready" | "syncing";
  }> {
    const desiredGeneration = await this.service.desiredGeneration();
    const runners = [...this.connections.values()].filter((item) => item.poolId === poolId);
    return {
      desiredGeneration,
      distributionStatus: runners.length > 0 && runners.every((item) => item.appliedGeneration >= desiredGeneration)
        ? "ready"
        : "syncing",
    };
  }

  private connect(stream: RunnerStream): void {
    const authorization = stream.metadata.get("authorization")[0];
    if (authorization !== `Bearer ${this.config.runnerToken}`) {
      this.metrics.observeControlMessage("received", "authentication", "rejected");
      const error = Object.assign(new Error("Runner authentication failed."), { code: status.UNAUTHENTICATED });
      stream.destroy(error);
      return;
    }
    let connection: Connection | null = null;
    let messageChain = Promise.resolve();
    stream.on("data", (message: WireMessage) => {
      const messageType = wireMessageType(message);
      messageChain = messageChain.then(async () => {
        const registered = await this.handleMessage(stream, message, connection);
        if (registered) connection = registered;
        this.metrics.observeControlMessage("received", messageType);
      }).catch((error: unknown) => {
        this.metrics.observeControlMessage("received", messageType, "error");
        const detail = error instanceof Error ? error.message : "Unknown Runner control error.";
        stream.emit("error", Object.assign(new Error(detail), { code: status.INTERNAL }));
      });
    });
    const disconnected = () => {
      if (!connection) return;
      const current = this.connections.get(connection.runnerId);
      if (current?.bootId === connection.bootId) {
        this.connections.delete(connection.runnerId);
        this.metrics.controlConnection(connection.poolId, false);
      }
      void this.service.disconnectRunner(connection.runnerId, connection.bootId);
    };
    stream.once("end", disconnected);
    stream.once("close", disconnected);
    stream.once("error", disconnected);
  }

  private async handleMessage(
    stream: RunnerStream,
    message: WireMessage,
    current: Connection | null,
  ): Promise<Connection | null> {
    if (message.registration) {
      if (current) throw new Error("Runner registered more than once on one stream.");
      const registration = message.registration as Registration;
      const desiredGeneration = await this.service.registerRunner({
        runnerId: registration.runnerId,
        bootId: registration.bootId,
        poolId: registration.poolId,
        runnerVersion: registration.runnerVersion,
        nemoVersion: registration.nemoVersion,
        maxConcurrency: number(registration.maxConcurrency),
        compilerCapable: registration.compilerCapable,
        labels: registration.labels ?? {},
        appliedGeneration: number(registration.appliedGeneration),
      });
      const connection: Connection = {
        stream,
        runnerId: registration.runnerId,
        bootId: registration.bootId,
        poolId: registration.poolId,
        compilerCapable: registration.compilerCapable,
        appliedGeneration: number(registration.appliedGeneration),
        lastReconcileGeneration: -1,
      };
      const prior = this.connections.get(connection.runnerId);
      if (prior) this.metrics.controlConnection(prior.poolId, false);
      this.connections.set(connection.runnerId, connection);
      this.metrics.controlConnection(connection.poolId, true);
      this.write(stream, {
        registrationAccepted: {
          desiredGeneration: String(desiredGeneration),
          heartbeatIntervalSeconds: this.config.heartbeatIntervalSeconds,
        },
      });
      await this.reconcile(connection);
      return connection;
    }
    if (!current) throw new Error("Runner must register before sending control messages.");
    if (message.heartbeat) {
      const heartbeat = message.heartbeat as Heartbeat;
      if (heartbeat.runnerId !== current.runnerId || heartbeat.bootId !== current.bootId) {
        throw new Error("Heartbeat identity does not match the registered stream.");
      }
      try {
        const accepted = await this.service.recordHeartbeat({
          runnerId: heartbeat.runnerId,
          bootId: heartbeat.bootId,
          sequence: number(heartbeat.sequence),
          appliedGeneration: number(heartbeat.appliedGeneration),
          load: normalizeLoad(heartbeat.load),
        });
        this.metrics.observeHeartbeat(current.poolId, accepted ? "accepted" : "stale_or_unknown");
        if (!accepted) return null;
      } catch (error) {
        this.metrics.observeHeartbeat(current.poolId, "error");
        throw error;
      }
      current.appliedGeneration = number(heartbeat.appliedGeneration);
      const desired = await this.service.desiredGeneration();
      if (number(heartbeat.appliedGeneration) !== desired) await this.reconcile(current);
    } else if (message.compileResult) {
      const result = message.compileResult as CompileResult;
      this.metrics.observeJob("compile", result.accepted);
      await this.handleCompileResult(result);
      await this.reconcileAll();
    } else if (message.validationResult) {
      const result = message.validationResult as ValidationResult;
      if (result.runnerId !== current.runnerId) throw new Error("Validation result identity does not match the registered stream.");
      this.metrics.observeJob("validation", result.accepted);
      await this.handleValidationResult(result);
    } else if (message.artifactResult) {
      // The following heartbeat advances applied_generation after an atomic
      // activation. NACK keeps the prior last-known-good generation in place.
      const result = message.artifactResult as { accepted?: boolean };
      this.metrics.observeArtifactResult(current.poolId, Boolean(result.accepted));
      if (result.accepted) await this.reconcile(current);
      else current.lastReconcileGeneration = -1;
    }
    return null;
  }

  private async handleCompileResult(result: CompileResult): Promise<void> {
    const artifact = result.artifact ?? {};
    if (!result.accepted) {
      await this.service.rejectCompile({
        compileId: result.compileId,
        guardrailId: string(artifact.guardrailId),
        guardrailVersion: number(artifact.guardrailVersion),
        reason: result.reason || "GuardRails 0 rejected the Guardrail plan.",
      });
      return;
    }
    await this.service.acceptCompiledArtifact({
      compileId: result.compileId,
      guardrailId: string(artifact.guardrailId),
      guardrailVersion: number(artifact.guardrailVersion),
      generation: number(artifact.generation),
      compilerVersion: string(artifact.compilerVersion),
      nemoVersion: string(artifact.nemoVersion),
      runtimeProfile: string(artifact.runtimeProfile),
      plan: jsonObject(artifact.planJson),
      configYaml: string(artifact.configYaml),
      colangContent: string(artifact.colangContent),
      prompts: jsonArray(artifact.promptsJson),
      actionBindings: jsonArray(artifact.actionBindingsJson),
      dependencyManifest: jsonArray(artifact.dependencyManifestJson),
    });
  }

  private async handleValidationResult(result: ValidationResult): Promise<void> {
    if (!result.accepted) {
      await this.service.rejectValidation({
        runId: result.runId,
        reason: result.reason || "GuardRails 0 could not execute Guardrail Validation.",
      });
      return;
    }
    const metrics = validationMetrics(result.metricsJson);
    const results = validationResults(result.resultsJson);
    await this.service.completeValidation({
      runId: result.runId,
      status: result.status === "passed" ? "passed" : "failed",
      metrics,
      results,
      ...(result.reason ? { reason: result.reason } : {}),
    });
  }

  private async reconcileAll(): Promise<void> {
    await Promise.allSettled([...this.connections.values()].map((connection) => this.reconcile(connection)));
  }

  private async reconcile(connection: Connection): Promise<void> {
    const started = performance.now();
    try {
      const desired = await this.service.desiredStateForPool(connection.poolId);
      if (connection.lastReconcileGeneration === desired.generation) {
        this.metrics.observeReconcile(connection.poolId, "noop", (performance.now() - started) / 1_000);
        return;
      }
      this.write(connection.stream, {
      desiredState: {
        generation: String(desired.generation),
        artifacts: desired.artifacts.map((artifact) => ({
          artifactId: artifact.id,
          guardrailId: artifact.guardrailId,
          guardrailVersion: artifact.guardrailVersion,
          generation: String(artifact.generation),
          compilerVersion: artifact.compilerVersion,
          nemoVersion: artifact.nemoVersion,
          runtimeProfile: artifact.runtimeProfile,
          planJson: JSON.stringify(artifact.plan),
          configYaml: artifact.configYaml,
          colangContent: artifact.colangContent,
          promptsJson: JSON.stringify(artifact.prompts),
          actionBindingsJson: JSON.stringify(artifact.actionBindings),
          dependencyManifestJson: JSON.stringify(artifact.dependencyManifest),
          checksum: artifact.checksum,
          signature: artifact.signature,
        })),
        disabledGuardrailIds: desired.disabledGuardrailIds,
        disabledIntegrationIds: desired.disabledIntegrationIds,
        deployments: desired.deployments.map((deployment) => ({
          deploymentId: deployment.deploymentId,
          guardrailId: deployment.guardrailId,
          artifactId: deployment.artifactId,
          integrationId: deployment.integrationId ?? "",
          routeOrder: deployment.routeOrder,
          trafficScopeJson: JSON.stringify(deployment.trafficScope),
        })),
        integrations: desired.integrations.map((integration) => ({
          integrationId: integration.integrationId,
          adapter: integration.adapter,
          verificationJson: JSON.stringify(integration.verification),
        })),
        guardrailLoggingLevels: desired.guardrailLoggingLevels,
      },
      });
      connection.lastReconcileGeneration = desired.generation;
      this.metrics.observeReconcile(connection.poolId, "dispatched", (performance.now() - started) / 1_000);
    } catch (error) {
      this.metrics.observeReconcile(connection.poolId, "error", (performance.now() - started) / 1_000);
      throw error;
    }
  }

  private async dispatchCompileRequests(): Promise<void> {
    const compiler = [...this.connections.values()].find((item) => item.poolId === "default" && item.compilerCapable);
    if (!compiler) return;
    const events = await this.service.pendingOutbox("guardrail.compile_requested", 10);
    for (const event of events) {
      const payload = event.payload;
      this.write(compiler.stream, {
        compileRequest: {
          compileId: string(payload.compileId),
          guardrailId: string(payload.guardrailId),
          guardrailVersion: number(payload.guardrailVersion),
          generation: String(number(payload.generation)),
          planJson: JSON.stringify(payload.plan ?? {}),
          runtimeProfile: string(payload.runtimeProfile),
        },
      });
      await this.service.deferOutbox(event.id, 30);
    }
  }

  private async dispatchValidationRequests(): Promise<void> {
    const compiler = [...this.connections.values()].find((item) => item.poolId === "default" && item.compilerCapable);
    if (!compiler) return;
    const events = [
      ...await this.service.pendingOutbox("guardrail.validation_requested", 10),
      ...await this.service.pendingOutbox("policy.validation_requested", 10),
    ].sort((left, right) => left.createdAt.getTime() - right.createdAt.getTime()).slice(0, 10);
    for (const event of events) {
      const payload = event.payload;
      this.write(compiler.stream, {
        validationRequest: {
          runId: string(payload.runId),
          guardrailId: string(payload.guardrailId),
          candidateVersion: number(payload.candidateVersion),
          sourceDraftRevision: number(payload.sourceDraftRevision),
          planJson: JSON.stringify(payload.plan ?? {}),
          runtimeProfile: string(payload.runtimeProfile),
          testCasesJson: JSON.stringify(payload.testCases ?? []),
        },
      });
      await this.service.markValidationRunning(event.id);
      await this.service.deferOutbox(event.id, 30);
    }
  }

  private async dispatchDesiredStateChanges(): Promise<void> {
    const events = await this.service.pendingOutbox("runner.desired_state_changed", 50);
    if (events.length === 0) return;
    for (const connection of this.connections.values()) connection.lastReconcileGeneration = -1;
    await this.reconcileAll();
    await Promise.all(events.map((event) => this.service.markOutboxProcessed(event.id)));
  }

  private write(stream: RunnerStream, body: WireMessage): void {
    stream.write({ messageId: randomUUID(), sentAtUnixMs: String(Date.now()), ...body });
    this.metrics.observeControlMessage("sent", wireMessageType(body));
  }

  private credentials(): ServerCredentials {
    if (this.config.grpcTls) {
      return ServerCredentials.createSsl(
        readFileSync(this.config.grpcTls.clientCaPath),
        [{
          cert_chain: readFileSync(this.config.grpcTls.certPath),
          private_key: readFileSync(this.config.grpcTls.keyPath),
        }],
        true,
      );
    }
    if (this.config.nodeEnv === "production") {
      throw new Error("Controller gRPC mTLS certificate, key, and client CA are required in production.");
    }
    return ServerCredentials.createInsecure();
  }
}

function normalizeLoad(load: Heartbeat["load"]): RunnerLoad {
  return {
    inflight: number(load?.inflight),
    maxConcurrency: number(load?.maxConcurrency),
    queueDepth: number(load?.queueDepth),
    requestsDelta: number(load?.requestsDelta),
    errorsDelta: number(load?.errorsDelta),
    timeoutsDelta: number(load?.timeoutsDelta),
    latencyP95Ms: number(load?.latencyP95Ms),
    cpuUtilization: number(load?.cpuUtilization),
    memoryUtilization: number(load?.memoryUtilization),
    activeGuardrails: number(load?.activeGuardrails),
    compileQueueDepth: number(load?.compileQueueDepth),
    observationIntervalMs: number(load?.observationIntervalMs),
  };
}

function wireMessageType(message: WireMessage): string {
  return [
    "registration", "heartbeat", "artifactResult", "compileResult", "validationResult",
    "registrationAccepted", "desiredState", "compileRequest", "validationRequest", "drainRequest",
  ].find((key) => message[key] !== undefined) ?? "unknown";
}

function number(value: unknown): number {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

function string(value: unknown): string {
  return typeof value === "string" ? value : String(value ?? "");
}

function jsonObject(value: unknown): Record<string, unknown> {
  const parsed = JSON.parse(string(value) || "{}") as unknown;
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") throw new Error("Expected a JSON object.");
  return parsed as Record<string, unknown>;
}

function jsonArray(value: unknown): unknown[] {
  const parsed = JSON.parse(string(value) || "[]") as unknown;
  if (!Array.isArray(parsed)) throw new Error("Expected a JSON array.");
  return parsed;
}

function validationMetrics(value: unknown): ValidationMetrics {
  const parsed = jsonObject(value);
  return {
    total: number(parsed.total),
    passed: number(parsed.passed),
    complianceRate: number(parsed.complianceRate),
    falsePositiveRate: number(parsed.falsePositiveRate),
    falseNegativeRate: number(parsed.falseNegativeRate),
    deepEscalationRate: number(parsed.deepEscalationRate),
    p95LatencyMs: number(parsed.p95LatencyMs),
  };
}

function validationResults(value: unknown): ValidationCaseResult[] {
  return jsonArray(value).map((item) => {
    if (!item || Array.isArray(item) || typeof item !== "object") throw new Error("Validation result entries must be JSON objects.");
    const row = item as Record<string, unknown>;
    const phase = string(row.phase);
    return {
      caseId: string(row.caseId),
      name: string(row.name),
      policyId: string(row.policyId),
      expectedDecision: string(row.expectedDecision),
      actualDecision: string(row.actualDecision),
      passed: Boolean(row.passed),
      stageReached: string(row.stageReached),
      latencyMs: number(row.latencyMs),
      reason: string(row.reason),
      phase: phase === "output" ? "output" : "input",
      inputContent: string(row.inputContent),
      action: string(row.action),
      outputContent: string(row.outputContent),
      findings: records(row.findings),
      trace: records(row.trace),
      trustedInstruction: string(row.trustedInstruction),
      targetSource: string(row.targetSource),
      query: string(row.query),
      groundingSources: strings(row.groundingSources),
      expectedReasoningResult: nullableString(row.expectedReasoningResult),
      actualReasoningResult: nullableString(row.actualReasoningResult),
      caseType: string(row.caseType),
      required: Boolean(row.required),
      expectedFailure: nullableString(row.expectedFailure),
      actualFailure: nullableString(row.actualFailure),
      concurrencyGroup: nullableString(row.concurrencyGroup),
      sourcePolicyId: nullableString(row.sourcePolicyId),
      sourcePolicyVersion: nullableString(row.sourcePolicyVersion),
      sourceCaseId: nullableString(row.sourceCaseId),
      coveredRuleIds: strings(row.coveredRuleIds),
      matchedRuleIds: strings(row.matchedRuleIds),
    };
  });
}

function records(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> => Boolean(item) && !Array.isArray(item) && typeof item === "object")
    : [];
}
function strings(value: unknown): string[] { return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : []; }
function nullableString(value: unknown): string | null { const result = string(value); return result || null; }
