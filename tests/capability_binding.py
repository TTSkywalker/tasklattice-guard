from __future__ import annotations

from runner import generated as protocol


_BINDINGS = {
    "content_safety": ("content_safety.input", "content_safety", protocol.RAIL_TYPE_INPUT, "tali.runtime.safety-model.v1"),
    "jailbreak_detection": ("jailbreak.input", "jailbreak", protocol.RAIL_TYPE_INPUT, "tali.runtime.safety-model.v1"),
    "pii_detection": ("pii_semantic.input", "pii_semantic", protocol.RAIL_TYPE_INPUT, "tali.runtime.safety-model.v1"),
    "topic_control": ("topic_control.input", "topic_control", protocol.RAIL_TYPE_INPUT, "tali.runtime.topic-judge.v1"),
    "contextual_grounding": ("contextual_grounding.output", "contextual_grounding", protocol.RAIL_TYPE_OUTPUT, "tali.runtime.grounding-judge.v1"),
    "automated_reasoning": ("automated_reasoning.output", "automated_reasoning", protocol.RAIL_TYPE_OUTPUT, "tali.runtime.automated-reasoning.v1"),
}


def capability_binding(
    *,
    detector_type: str,
    model_ref: str,
    profile_ref: str,
    contract_refs: list[str],
) -> protocol.CapabilityBinding:
    binding_id, capability_ref, rail_type, implementation_ref = _BINDINGS[detector_type]
    return protocol.CapabilityBinding(
        binding_id=binding_id,
        capability_ref=capability_ref,
        rail_type=rail_type,
        implementation_ref=implementation_ref,
        model_ref=model_ref,
        profile_ref=profile_ref,
        contract_refs=contract_refs,
    )
