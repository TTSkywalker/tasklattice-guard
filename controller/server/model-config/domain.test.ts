import { describe, expect, it } from "vitest";

import {
  assignmentTargetAcceptsModel,
  assignmentTargetProfiles,
  capabilityBindingContracts,
  controlPlaneProfiles,
  emptyModelAssignments,
  modelInputSchema,
  normalizeModelAssignments,
  profileContracts,
  profileTransports,
  providerAcceptsProfile,
} from "./domain.js";

describe("Guardrail Catalog capability binding profiles", () => {
  it("assigns Nemotron Content Safety only to the content-safety detector", () => {
    const profile = "tali.nemotron-content-safety.v1";
    expect(assignmentTargetProfiles("content_safety.input")).toContain(profile);
    expect(assignmentTargetProfiles("content_safety.output")).toContain(profile);
    expect(controlPlaneProfiles).not.toContain(profile);
    expect(profileContracts[profile]).toEqual(["tali.guard.content-safety.v1"]);
    expect(modelInputSchema.parse({
      providerId: "2da89935-e001-4a43-a47b-95f419666bb0",
      name: "NVIDIA Nemotron Content Safety",
      model: "nvidia/nemotron-3.5-content-safety",
      profile,
    }).profile).toBe(profile);
  });

  it("keeps interchangeable jailbreak implementations under one detector type", () => {
    const profile = "tali.nemoguard-jailbreak-detect.v1";
    expect(assignmentTargetProfiles("jailbreak.input")).toContain(profile);
    expect(assignmentTargetProfiles("jailbreak.input")).toContain("tali.openai-compatible-jailbreak.v1");
    expect(controlPlaneProfiles).not.toContain(profile);
    expect(assignmentTargetProfiles("content_safety.input")).not.toContain(profile);
    expect(profileContracts[profile]).toEqual(["tali.guard.jailbreak.v1"]);
    expect(profileTransports[profile]).toBe("nemoguard_jailbreak_detect");
  });

  it("keeps content safety, topic control, and jailbreak independently replaceable", () => {
    expect(assignmentTargetProfiles("content_safety.input")).toContain("tali.nemotron-safety-guard-v3.v1");
    expect(assignmentTargetProfiles("topic_control.input")).toContain("tali.nemoguard-topic-control.v1");
    expect(assignmentTargetProfiles("jailbreak.input")).toContain("tali.openai-compatible-jailbreak.v1");
  });

  it("reserves DeepSeek for the Control Plane even when a Data Plane profile is supplied", () => {
    expect(assignmentTargetAcceptsModel("control_plane", "generic-chat", "deepseek")).toBe(true);
    expect(assignmentTargetAcceptsModel("topic_control.input", "tali.taxonomy-judge.v1", "deepseek")).toBe(false);
    expect(assignmentTargetAcceptsModel("content_safety.output", "tali.qwen3guard.v1", "qwen")).toBe(true);
    expect(providerAcceptsProfile("deepseek", "generic-chat")).toBe(true);
    expect(providerAcceptsProfile("deepseek", "tali.grounding-judge.v1")).toBe(false);
  });

  it("rejects the retired Nano model while allowing another OpenAI-compatible judge", () => {
    const base = {
      providerId: "2da89935-e001-4a43-a47b-95f419666bb0",
      name: "Jailbreak judge",
      profile: "tali.openai-compatible-jailbreak.v1",
    };
    expect(modelInputSchema.safeParse({ ...base, model: "nvidia/nvidia-nemotron-nano-9b-v2" }).success).toBe(false);
    expect(modelInputSchema.safeParse({ ...base, model: "example/jailbreak-judge" }).success).toBe(true);
  });
});

describe("capability bindings", () => {
  it("normalizes the explicit catalog shape without legacy role inference", () => {
    expect(normalizeModelAssignments({ bindings: { "content_safety.input": "safety" } })).toEqual({
      ...emptyModelAssignments(),
      bindings: { ...emptyModelAssignments().bindings, "content_safety.input": "safety" },
    });
    expect(normalizeModelAssignments({})).toEqual(emptyModelAssignments());
  });

  it("projects a multi-purpose profile into only the selected detector contract", () => {
    expect(capabilityBindingContracts("content_safety.input", "tali.qwen3guard.v1")).toEqual([
      "tali.guard.content-safety.v1",
    ]);
    expect(capabilityBindingContracts("jailbreak.input", "tali.qwen3guard.v1")).toEqual([
      "tali.guard.jailbreak.v1",
    ]);
    expect(capabilityBindingContracts("pii_semantic.output", "tali.qwen3guard.v1")).toEqual([
      "tali.guard.pii.semantic.v1",
    ]);
  });
});
