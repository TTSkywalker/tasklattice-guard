import { describe, expect, it } from "vitest";

import type { GuardrailVersion } from "@/lib/api";

import { resolvePublishedVersion } from "./playground";

function version(number: number): GuardrailVersion {
  return {
    guardrail_id: "guardrail-1",
    version: number,
    source_draft_version: number,
    compiler_version: "nemo-native-v1",
    plan_checksum: `plan-${number}`,
    created_at: `2026-08-${String(10 + number).padStart(2, "0")}T08:00:00Z`,
    active: number === 3,
    runtime_engine: "llmrails",
    config_checksum: `config-${number}`,
    execution_mode: "nemo_only",
  };
}

describe("resolvePublishedVersion", () => {
  const versions = [version(2), version(3), version(1)];

  it("defaults to the latest published version", () => {
    expect(resolvePublishedVersion(versions, 0)).toBe(3);
  });

  it("preserves an explicitly selected historical published version", () => {
    expect(resolvePublishedVersion(versions, 1)).toBe(1);
  });

  it("does not invent a version when nothing has been published", () => {
    expect(resolvePublishedVersion([], 4)).toBe(0);
  });
});
