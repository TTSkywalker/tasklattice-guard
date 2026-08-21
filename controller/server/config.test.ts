import { describe, expect, it } from "vitest";

import { loadConfig } from "./config.js";

const requiredEnvironment = {
  NODE_ENV: "test",
  CONTROLLER_DATABASE_URL: "postgresql://controller:controller@localhost/controller",
  CONTROLLER_RUNNER_TOKEN: "runner-token-that-is-at-least-32-characters",
  CONTROLLER_ARTIFACT_SIGNING_KEY_PATH: "/tmp/controller-signing-key.pem",
  BETTER_AUTH_SECRET: "better-auth-secret-that-is-at-least-32-characters",
};

describe("Controller config", () => {
  it("keeps the production password minimum at 12 by default", () => {
    expect(loadConfig(requiredEnvironment)).toMatchObject({
      minPasswordLength: 12,
      allowLocalDefaultCredentials: false,
    });
  });

  it("allows only the established admin/admin exception in the local development profile", () => {
    expect(loadConfig({
      ...requiredEnvironment,
      NODE_ENV: "development",
      CONTROLLER_PUBLIC_URL: "http://localhost:38081",
      CONTROLLER_ALLOW_LOCAL_DEFAULT_CREDENTIALS: "true",
      CONTROLLER_BOOTSTRAP_ADMIN_EMAIL: "admin@tasklattice.local",
      CONTROLLER_BOOTSTRAP_ADMIN_PASSWORD: "admin",
    })).toMatchObject({
      minPasswordLength: 12,
      allowLocalDefaultCredentials: true,
      bootstrapAdmin: {
        email: "admin@tasklattice.local",
        password: "admin",
      },
    });
  });

  it("rejects any other short bootstrap password even when the local exception is enabled", () => {
    expect(() => loadConfig({
      ...requiredEnvironment,
      CONTROLLER_PUBLIC_URL: "http://127.0.0.1:38081",
      CONTROLLER_ALLOW_LOCAL_DEFAULT_CREDENTIALS: "true",
      CONTROLLER_BOOTSTRAP_ADMIN_EMAIL: "another-admin@tasklattice.local",
      CONTROLLER_BOOTSTRAP_ADMIN_PASSWORD: "admin",
    })).toThrow(/at least 12 characters/);
  });

  it("exposes a configurable Policy catalog directory", () => {
    expect(loadConfig({
      ...requiredEnvironment,
      CONTROLLER_POLICY_CATALOG_DIR: "/var/lib/tasklattice/policies",
    }).policyCatalogDir).toBe("/var/lib/tasklattice/policies");
  });

  it("uses the Runner toolkit assets for local development by default", () => {
    expect(loadConfig(requiredEnvironment).policyCatalogDir).toBe("../runner/toolkit/policy_library/assets");
  });

  it("keeps the stable Runtime Service origin separate from the Controller origin", () => {
    expect(loadConfig(requiredEnvironment).runtimeServiceUrl).toBe("http://localhost:8091");
    expect(loadConfig({
      ...requiredEnvironment,
      CONTROLLER_PUBLIC_URL: "https://controller.example.test/",
      CONTROLLER_RUNTIME_SERVICE_URL: "https://runtime.example.test/",
    })).toMatchObject({
      publicUrl: "https://controller.example.test",
      runtimeServiceUrl: "https://runtime.example.test",
    });
  });

  it("exposes the selected control-plane and data-plane models without credentials", () => {
    expect(loadConfig(requiredEnvironment).modelConnections).toEqual({
      controlPlane: {
        provider: "DeepSeek",
        model: "deepseek-v4-flash",
      },
      dataPlane: {
        provider: "NVIDIA",
        models: [
          { capability: "contentSafety", model: "nvidia/llama-3.1-nemotron-safety-guard-8b-v3" },
          { capability: "topicControl", model: "nvidia/llama-3.1-nemoguard-8b-topic-control" },
          { capability: "jailbreak", model: "nvidia/nvidia-nemotron-nano-9b-v2" },
        ],
      },
    });

    expect(loadConfig({
      ...requiredEnvironment,
      MODEL_GUARDRAILS_CONTROL_PLANE_AI_MODEL: "deepseek-chat",
      MODEL_GUARDRAILS_CONTENT_SAFETY_MODEL: "nvidia/custom-safety-model",
      MODEL_GUARDRAILS_TOPIC_CONTROL_MODEL: "nvidia/custom-topic-model",
      MODEL_GUARDRAILS_JAILBREAK_MODEL: "nvidia/custom-jailbreak-model",
    }).modelConnections).toMatchObject({
      controlPlane: { provider: "DeepSeek", model: "deepseek-chat" },
      dataPlane: {
        provider: "NVIDIA",
        models: [
          { capability: "contentSafety", model: "nvidia/custom-safety-model" },
          { capability: "topicControl", model: "nvidia/custom-topic-model" },
          { capability: "jailbreak", model: "nvidia/custom-jailbreak-model" },
        ],
      },
    });
  });

  it("restores the optional control-plane authoring model contract", () => {
    expect(loadConfig(requiredEnvironment).controlPlaneAi).toBeNull();
    expect(loadConfig({
      ...requiredEnvironment,
      MODEL_GUARDRAILS_CONTROL_PLANE_AI_BASE_URL: "https://api.deepseek.com/v1/",
      MODEL_GUARDRAILS_CONTROL_PLANE_AI_MODEL: "deepseek-test",
      MODEL_GUARDRAILS_CONTROL_PLANE_AI_API_KEY: "secret",
    }).controlPlaneAi).toEqual({
      provider: "DeepSeek",
      baseUrl: "https://api.deepseek.com/v1",
      model: "deepseek-test",
      apiKey: "secret",
      timeoutMs: 45_000,
    });
  });

  it("rejects a partially configured control-plane authoring model", () => {
    expect(() => loadConfig({
      ...requiredEnvironment,
      MODEL_GUARDRAILS_CONTROL_PLANE_AI_BASE_URL: "https://api.deepseek.com/v1",
    })).toThrow(/must be configured together/);
    expect(() => loadConfig({
      ...requiredEnvironment,
      MODEL_GUARDRAILS_CONTROL_PLANE_AI_API_KEY: "secret",
    })).toThrow(/base URL and model are required/);
  });
});
