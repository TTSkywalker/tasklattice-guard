from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

from ..runtime.contracts import (
    AutomatedReasoningPolicySnapshot,
    GuardrailPlanModule,
    GuardrailPlanSnapshot,
    GuardrailPlanStep,
    ControlModule,
    ControlVersionSnapshot,
    GuardrailControlBindingSnapshot,
)
from ..policy_packs.litellm import LITELLM_POLICY_PACK_VERSION, policy_template
from .catalog import control
from .domain import PlanCompilationError, Guardrail


COMPILER_VERSION = "guardrail-plan-v3"

_MODULE_TIMEOUT_MS: dict[ControlModule, int] = {
    "data_protection": 750,
    "interaction_safety": 2_500,
    "business_assurance": 5_000,
}
_AUTOMATED_REASONING_TIMEOUT_MS = 30_000


class GuardrailCompiler:
    """Compile human-facing Guardrails into immutable execution plans."""

    def compile(
        self,
        guardrail: Guardrail,
        version: int,
        *,
        control_versions: tuple[ControlVersionSnapshot, ...] = (),
        control_bindings: tuple[GuardrailControlBindingSnapshot, ...] = (),
    ) -> GuardrailPlanSnapshot:
        if not guardrail.purpose.strip():
            raise PlanCompilationError("A Guardrail requires a clear purpose.")
        if not guardrail.controls and not control_bindings:
            raise PlanCompilationError("Select at least one Control before testing.")

        steps: list[GuardrailPlanStep] = []
        for configured in guardrail.controls:
            definition = control(configured.risk)
            stages = definition.available_stages
            phases = self._phases(guardrail, configured.risk, definition.default_phases)
            parameters = self._guardrail_parameters(guardrail, configured.risk)
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
                "deterministic" not in stages or guardrail.safety_level == "strict"
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
                            if guardrail.safety_level == "strict" and has_deep
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
                            if guardrail.safety_level == "strict" or stages == ("deep_judge",)
                            else "on_uncertain"
                        ),
                        parameters=parameters,
                    )
                )

        reasoning_policies = self._reasoning_policies(guardrail)
        modules = self._modules(tuple(steps))
        self._validate_modules(tuple(steps), modules)
        return GuardrailPlanSnapshot(
            guardrail_id=guardrail.id,
            guardrail_version=version,
            compiler_version=COMPILER_VERSION,
            safety_level=guardrail.safety_level,
            output_delivery=guardrail.output_delivery,
            steps=tuple(steps),
            modules=modules,
            reasoning_policies=reasoning_policies,
            control_versions=control_versions,
            control_bindings=control_bindings,
        )

    @staticmethod
    def _modules(steps: tuple[GuardrailPlanStep, ...]) -> tuple[GuardrailPlanModule, ...]:
        modules: list[GuardrailPlanModule] = []
        for phase in ("input", "output"):
            for module in (
                "data_protection",
                "interaction_safety",
                "business_assurance",
            ):
                step_ids = tuple(
                    step.id
                    for step in steps
                    if phase in step.phases
                    and control(step.risk).module == module
                    and step.risk not in {"contextual_grounding", "automated_reasoning"}
                )
                if not step_ids:
                    continue
                modules.append(
                    GuardrailPlanModule(
                        id=f"{module}:{phase}",
                        module=module,
                        phase=phase,
                        step_ids=step_ids,
                        timeout_ms=_MODULE_TIMEOUT_MS[module],
                    )
                )
            grounding_step_ids = tuple(
                step.id
                for step in steps
                if phase in step.phases and step.risk == "contextual_grounding"
            )
            if grounding_step_ids:
                data_module_id = f"data_protection:{phase}"
                dependencies = (
                    (data_module_id,)
                    if any(item.id == data_module_id for item in modules)
                    else ()
                )
                modules.append(
                    GuardrailPlanModule(
                        id=f"business_assurance:contextual_grounding:{phase}",
                        module="business_assurance",
                        phase=phase,
                        step_ids=grounding_step_ids,
                        depends_on=dependencies,
                        input_view="masked" if dependencies else "original",
                        timeout_ms=_MODULE_TIMEOUT_MS["business_assurance"],
                    )
                )
            reasoning_step_ids = tuple(
                step.id
                for step in steps
                if phase in step.phases and step.risk == "automated_reasoning"
            )
            if reasoning_step_ids:
                data_module_id = f"data_protection:{phase}"
                dependencies = (
                    (data_module_id,)
                    if any(item.id == data_module_id for item in modules)
                    else ()
                )
                modules.append(
                    GuardrailPlanModule(
                        id=f"business_assurance:automated_reasoning:{phase}",
                        module="business_assurance",
                        phase=phase,
                        step_ids=reasoning_step_ids,
                        depends_on=dependencies,
                        input_view="masked" if dependencies else "complete_output",
                        timeout_ms=_AUTOMATED_REASONING_TIMEOUT_MS,
                    )
                )
        return tuple(modules)

    @staticmethod
    def _validate_modules(
        steps: tuple[GuardrailPlanStep, ...],
        modules: tuple[GuardrailPlanModule, ...],
    ) -> None:
        step_by_id = {step.id: step for step in steps}
        module_by_id = {module.id: module for module in modules}
        if len(module_by_id) != len(modules):
            raise PlanCompilationError("Compiled module identifiers must be unique.")

        for module in modules:
            if module.timeout_ms <= 0:
                raise PlanCompilationError(f"Module {module.id} requires a positive timeout.")
            if module.input_view in {"masked", "previous_output"} and not module.depends_on:
                raise PlanCompilationError(
                    f"Module {module.id} requires a dependency for {module.input_view!r} input."
                )
            for dependency in module.depends_on:
                if dependency not in module_by_id:
                    raise PlanCompilationError(
                        f"Module {module.id} depends on unknown module {dependency}."
                    )
            for step_id in module.step_ids:
                step = step_by_id.get(step_id)
                if step is None:
                    raise PlanCompilationError(
                        f"Module {module.id} references unknown plan step {step_id}."
                    )
                if module.phase not in step.phases:
                    raise PlanCompilationError(
                        f"Module {module.id} references a step outside its phase."
                    )

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(module_id: str) -> None:
            if module_id in visiting:
                raise PlanCompilationError("Compiled control modules must form an acyclic graph.")
            if module_id in visited:
                return
            visiting.add(module_id)
            for dependency in module_by_id[module_id].depends_on:
                visit(dependency)
            visiting.remove(module_id)
            visited.add(module_id)

        for module_id in module_by_id:
            visit(module_id)

    @staticmethod
    def checksum(plan: GuardrailPlanSnapshot) -> str:
        payload = json.dumps(asdict(plan), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()

    @staticmethod
    def _guardrail_parameters(guardrail: Guardrail, risk: str) -> tuple[tuple[str, str], ...]:
        if risk == "builtin_content_filter":
            composed = tuple(
                item
                for item in guardrail.control_configurations
                if item.runtime_risk == "builtin_content_filter"
            )
            if composed:
                template_controls = tuple(
                    item for item in composed if item.kind == "template" and item.template_id
                )
                enabled_rules = {
                    item.template_id: [
                        rule.id
                        for rule in item.rules
                        if rule.enabled and not rule.id.startswith("dynamic-")
                    ]
                    for item in template_controls
                }
                rule_actions = {
                    f"{item.template_id}:{rule.id}": rule.action
                    for item in template_controls
                    for rule in item.rules
                    if rule.enabled
                }
                custom_rules = [
                    {
                        "id": rule.id,
                        "name": rule.name,
                        "detector": rule.detector,
                        "action": rule.action,
                        "phases": list(rule.phases),
                        "expression": rule.expression,
                        "keywords": list(rule.keywords),
                    }
                    for item in composed
                    if item.kind == "custom" or item.kind == "template"
                    for rule in item.rules
                    if rule.enabled
                    and rule.detector in {"regex", "keyword"}
                    and (item.kind == "custom" or rule.id.startswith("dynamic-"))
                ]
                return (
                    ("policy_pack_version", LITELLM_POLICY_PACK_VERSION),
                    ("template_id", "composed-control-library"),
                    (
                        "controls",
                        "\n".join(item.template_id or "" for item in template_controls),
                    ),
                    (
                        "enabled_rules_json",
                        json.dumps(enabled_rules, sort_keys=True, separators=(",", ":")),
                    ),
                    (
                        "rule_actions_json",
                        json.dumps(rule_actions, sort_keys=True, separators=(",", ":")),
                    ),
                    (
                        "custom_rules_json",
                        json.dumps(custom_rules, sort_keys=True, separators=(",", ":")),
                    ),
                    *tuple(
                        (f"template_parameter.{key}", value)
                        for key, value in guardrail.template_parameters
                    ),
                )
            if not guardrail.source_template_id:
                raise PlanCompilationError(
                    "A built-in content-filter Control requires a source template."
                )
            try:
                template = policy_template(guardrail.source_template_id)
            except StopIteration as error:
                raise PlanCompilationError(
                    f"Unknown built-in template {guardrail.source_template_id!r}."
                ) from error
            return (
                ("policy_pack_version", LITELLM_POLICY_PACK_VERSION),
                ("template_id", template.id),
                ("controls", "\n".join(item.name for item in template.controls)),
                *tuple(
                    (f"template_parameter.{key}", value)
                    for key, value in guardrail.template_parameters
                ),
            )
        if risk == "contextual_grounding":
            configured = dict(guardrail.template_parameters)
            thresholds = (
                ("grounding_threshold", configured.get("grounding_threshold", "0.7")),
                ("relevance_threshold", configured.get("relevance_threshold", "0.7")),
            )
            for name, raw in thresholds:
                try:
                    value = float(raw)
                except ValueError as error:
                    raise PlanCompilationError(f"{name} must be numeric.") from error
                if not 0 <= value < 1:
                    raise PlanCompilationError(f"{name} must be between 0 and 0.99.")
            return thresholds
        if risk == "automated_reasoning":
            configured = next(item for item in guardrail.controls if item.risk == risk)
            binding = configured.reasoning_policy
            if binding is None:
                raise PlanCompilationError(
                    "Automated reasoning requires a deployed policy binding."
                )
            if guardrail.output_delivery != "full_buffered":
                raise PlanCompilationError(
                    "Automated reasoning requires full-buffered output delivery."
                )
            return (
                (
                    "policy_snapshot_id",
                    f"automated-reasoning:{binding.policy_id}:{binding.policy_version}",
                ),
            )
        if risk not in {"topic_control", "company_policy"}:
            return ()
        return (
            ("purpose", guardrail.purpose),
            ("allowed_topics", "\n".join(guardrail.allowed_topics)),
            ("restricted_topics", "\n".join(guardrail.restricted_topics)),
        )

    @staticmethod
    def _reasoning_policies(
        guardrail: Guardrail,
    ) -> tuple[AutomatedReasoningPolicySnapshot, ...]:
        snapshots: list[AutomatedReasoningPolicySnapshot] = []
        for configured in guardrail.controls:
            if configured.risk != "automated_reasoning":
                continue
            binding = configured.reasoning_policy
            if binding is None:
                raise PlanCompilationError(
                    "Automated reasoning requires a deployed policy binding."
                )
            policy_id = binding.policy_id.strip()
            policy_version = binding.policy_version.strip()
            if not policy_id or not policy_version:
                raise PlanCompilationError(
                    "Automated reasoning policy ID and version are required."
                )
            if not 0 <= binding.confidence_threshold <= 1:
                raise PlanCompilationError(
                    "Automated reasoning confidence threshold must be between 0 and 1."
                )
            snapshots.append(
                AutomatedReasoningPolicySnapshot(
                    id=f"automated-reasoning:{policy_id}:{policy_version}",
                    policy_id=policy_id,
                    policy_version=policy_version,
                    confidence_threshold=binding.confidence_threshold,
                )
            )
        return tuple(snapshots)

    @staticmethod
    def _phases(
        guardrail: Guardrail,
        risk: str,
        defaults: tuple[str, ...],
    ) -> tuple[str, ...]:
        configured_phases = {
            phase
            for configuration in guardrail.control_configurations
            if configuration.runtime_risk == risk
            for rule in configuration.rules
            if rule.enabled
            for phase in rule.phases
        }
        if configured_phases:
            return tuple(
                phase for phase in ("input", "output") if phase in configured_phases
            )
        if risk != "builtin_content_filter" or not guardrail.source_template_id:
            return defaults
        try:
            template = policy_template(guardrail.source_template_id)
        except StopIteration as error:
            raise PlanCompilationError(
                f"Unknown built-in template {guardrail.source_template_id!r}."
            ) from error
        phases = {phase for control in template.controls for phase in control.phases}
        return tuple(phase for phase in ("input", "output") if phase in phases)
