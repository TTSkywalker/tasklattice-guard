from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

from ..engine.contracts import GuardrailPlanSnapshot, GuardrailPlanStep
from ..policy_packs.litellm import LITELLM_POLICY_PACK_VERSION, policy_template
from .catalog import protection
from .domain import PlanCompilationError, SafetyProfile


COMPILER_VERSION = "guardrail-plan-v1"


class GuardrailCompiler:
    """Compile human-facing Safety Profiles into immutable execution plans."""

    def compile(self, profile: SafetyProfile, revision: int) -> GuardrailPlanSnapshot:
        if not profile.purpose.strip():
            raise PlanCompilationError("A Safety Profile requires a clear purpose.")
        if not profile.risks:
            raise PlanCompilationError("Select at least one risk before testing.")

        steps: list[GuardrailPlanStep] = []
        for configured in profile.risks:
            definition = protection(configured.risk)
            stages = definition.available_stages
            phases = self._phases(profile, configured.risk, definition.default_phases)
            parameters = self._profile_parameters(profile, configured.risk)
            if not stages:
                raise PlanCompilationError(f"No evaluator is available for {configured.risk}.")

            if "deterministic" in stages:
                steps.append(
                    GuardrailPlanStep(
                        id=f"{configured.risk}:deterministic",
                        risk=configured.risk,
                        stage="deterministic",
                        phases=phases,
                        on_unsafe=configured.action,
                        parameters=parameters,
                    )
                )

            use_fast_semantic = "fast_semantic" in stages and (
                "deterministic" not in stages or profile.safety_level == "strict"
            )
            if use_fast_semantic:
                has_deep = "deep_judge" in stages
                steps.append(
                    GuardrailPlanStep(
                        id=f"{configured.risk}:fast-semantic",
                        risk=configured.risk,
                        stage="fast_semantic",
                        phases=phases,
                        on_unsafe=configured.action,
                        escalation=(
                            "on_uncertain"
                            if configured.risk in {"prompt_injection", "jailbreak"} and has_deep
                            else "always"
                            if profile.safety_level == "strict" and has_deep
                            else "on_uncertain"
                            if has_deep
                            else "never"
                        ),
                        threshold=0.85,
                        parameters=parameters,
                    )
                )

            if "deep_judge" in stages:
                steps.append(
                    GuardrailPlanStep(
                        id=f"{configured.risk}:deep-judge",
                        risk=configured.risk,
                        stage="deep_judge",
                        phases=phases,
                        on_unsafe=configured.action,
                        escalation=(
                            "on_uncertain"
                            if configured.risk in {"prompt_injection", "jailbreak"}
                            else "always"
                            if profile.safety_level == "strict" or stages == ("deep_judge",)
                            else "on_uncertain"
                        ),
                        parameters=parameters,
                    )
                )

        return GuardrailPlanSnapshot(
            profile_id=profile.id,
            profile_revision=revision,
            compiler_version=COMPILER_VERSION,
            safety_level=profile.safety_level,
            output_delivery=profile.output_delivery,
            steps=tuple(steps),
        )

    @staticmethod
    def checksum(plan: GuardrailPlanSnapshot) -> str:
        payload = json.dumps(asdict(plan), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()

    @staticmethod
    def _profile_parameters(profile: SafetyProfile, risk: str) -> tuple[tuple[str, str], ...]:
        if risk == "builtin_content_filter":
            if not profile.source_template_id:
                raise PlanCompilationError(
                    "A built-in content-filter protection requires a source template."
                )
            try:
                template = policy_template(profile.source_template_id)
            except StopIteration as error:
                raise PlanCompilationError(
                    f"Unknown built-in template {profile.source_template_id!r}."
                ) from error
            return (
                ("policy_pack_version", LITELLM_POLICY_PACK_VERSION),
                ("template_id", template.id),
                ("controls", "\n".join(item.name for item in template.controls)),
                *tuple(
                    (f"template_parameter.{key}", value)
                    for key, value in profile.template_parameters
                ),
            )
        if risk not in {"topic_control", "company_policy"}:
            return ()
        return (
            ("purpose", profile.purpose),
            ("allowed_topics", "\n".join(profile.allowed_topics)),
            ("restricted_topics", "\n".join(profile.restricted_topics)),
        )

    @staticmethod
    def _phases(
        profile: SafetyProfile,
        risk: str,
        defaults: tuple[str, ...],
    ) -> tuple[str, ...]:
        if risk != "builtin_content_filter" or not profile.source_template_id:
            return defaults
        try:
            template = policy_template(profile.source_template_id)
        except StopIteration as error:
            raise PlanCompilationError(
                f"Unknown built-in template {profile.source_template_id!r}."
            ) from error
        phases = {phase for control in template.controls for phase in control.phases}
        return tuple(phase for phase in ("input", "output") if phase in phases)
