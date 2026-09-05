"""Delivery guarantees derived from the immutable execution plan, not UI toggles."""
from dataclasses import dataclass

from .contracts import GuardrailPlanSnapshot, OutputDeliveryMode


@dataclass(frozen=True, slots=True)
class OutputStreamContract:
    requested_mode: OutputDeliveryMode
    effective_mode: OutputDeliveryMode
    reason: str


def output_stream_contract(plan: GuardrailPlanSnapshot) -> OutputStreamContract:
    requested = plan.output_delivery
    if requested == "full_buffered":
        return OutputStreamContract(requested, requested, "Complete response checked before release.")
    # Pattern/PII redaction, grounding, formal reasoning and arbitrary Colang
    # programs have no finite-prefix safety guarantee. Do not invent one from
    # chunk size, model callability, or an operator's preferred delivery mode.
    steps = plan.steps_for("output")
    custom_output = any(
        binding.rail_type == "output"
        for version in plan.policy_versions
        for binding in version.rail_bindings
    )
    incremental = not custom_output and all(
        step.capability == "content_safety" and step.on_unsafe in {"reject", "report", "pass"}
        for step in steps
    )
    if not incremental:
        return OutputStreamContract(requested, "full_buffered",
                                    "Output rules require complete-response checks; text is held until final=true.")
    return OutputStreamContract(requested, requested,
                                "Checks accumulated output before release. Earlier released text cannot be recalled; cancel upstream on terminate=true.")
