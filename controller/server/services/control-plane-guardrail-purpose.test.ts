import { describe, expect, it } from "vitest";

import { ConflictError } from "../domain/errors.js";
import { assertGuardrailBusinessPurposeImmutable } from "./control-plane.js";

const purpose = {
  description: "Support account operations.",
  purposeDetails: {
    audience: "Support agents",
    tasks: "Answer account questions",
    protect: "Customer identifiers",
    outOfScope: "Medical advice",
  },
};

describe("Guardrail business purpose", () => {
  it("allows an unchanged purpose while other draft fields are edited", () => {
    expect(() => assertGuardrailBusinessPurposeImmutable(purpose, structuredClone(purpose))).not.toThrow();
  });

  it("rejects changes to either freeform or structured purpose after creation", () => {
    for (const next of [
      { ...purpose, description: "A different purpose." },
      { ...purpose, purposeDetails: { ...purpose.purposeDetails, tasks: "A different task" } },
    ]) {
      try {
        assertGuardrailBusinessPurposeImmutable(purpose, next);
        throw new Error("expected an immutable-purpose conflict");
      } catch (error) {
        expect(error).toBeInstanceOf(ConflictError);
        expect(error).toMatchObject({ code: "guardrail_business_purpose_immutable", status: 409 });
      }
    }
  });
});
