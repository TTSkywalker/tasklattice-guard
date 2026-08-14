import { afterEach, describe, expect, it, vi } from "vitest";

import { excludeGuardrailTestCase, updateGuardrail } from "./api";

describe("API error responses", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("renders FastAPI validation issues as readable field messages", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      status: 422,
      ok: false,
      url: "http://test/api/v1/guardrails/guardrail-1",
      json: async () => ({
        detail: [
          { loc: ["body", "policy_bindings", 0, "parameter_values"], msg: "Input should be a valid dictionary" },
          { loc: ["body", "policy_bindings", 0, "rule_actions"], msg: "Input should be a valid dictionary" },
        ],
      }),
    }));

    await expect(updateGuardrail("guardrail-1", { name: "Banker" })).rejects.toThrow(
      "policy_bindings.0.parameter_values: Input should be a valid dictionary; "
      + "policy_bindings.0.rule_actions: Input should be a valid dictionary",
    );
  });

  it("sends slash-containing Test Case IDs in the validation-scope body", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      status: 200,
      ok: true,
      url: "http://test/api/v1/guardrails/guardrail-1/validation-scope",
      json: async () => ({}),
    });
    vi.stubGlobal("fetch", fetchMock);

    await excludeGuardrailTestCase(
      "guardrail-1",
      "library-policy/rule-acceptance",
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/guardrails/guardrail-1/validation-scope",
      {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          case_id: "library-policy/rule-acceptance",
          excluded: true,
        }),
      },
    );
  });
});
