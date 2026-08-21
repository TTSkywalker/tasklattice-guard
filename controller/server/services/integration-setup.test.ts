import { describe, expect, it } from "vitest";

import { integrationSetup } from "./control-plane.js";

describe("Integration setup", () => {
  it("uses LiteLLM's Basic Guardrail API callback for the LiteLLM adapter", () => {
    const setup = integrationSetup(
      "http://tali-guard-runtime.tali.svc.cluster.local:8091",
      "integration-1",
      "litellm-generic-guardrail",
    );

    expect(setup.api_base_url).toBe(
      "http://tali-guard-runtime.tali.svc.cluster.local:8091/runtime/v1/integrations/integration-1",
    );
    expect(setup.callback_url).toBe(
      `${setup.api_base_url}/beta/litellm_basic_guardrail_api`,
    );
    expect(setup.yaml_template).toContain("guardrail: tasklattice_guard");
    expect(setup.yaml_template).toContain("api_base: os.environ/TASKLATTICE_GUARD_API_BASE");
    expect(setup.yaml_template).not.toContain("callback_url:");
  });

  it("keeps the generic HTTP callback for non-LiteLLM adapters", () => {
    const setup = integrationSetup("https://runtime.example.test", "integration-1", "generic-http-guard");

    expect(setup.callback_url).toBe(`${setup.api_base_url}/guardrails/evaluate`);
  });
});
