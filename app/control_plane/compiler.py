from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

from ..runtime.contracts import (
    AutomatedReasoningPolicySnapshot,
    GuardrailPlanModule,
    GuardrailPlanSnapshot,
    GuardrailPlanStep,
    PolicyModule,
    PolicyVersionSnapshot,
    GuardrailPolicyBindingSnapshot,
)
from ..policy_library import policy as library_policy
from .catalog import builtin_policy_id, runtime_capability
from .domain import PlanCompilationError, Guardrail, ResolvedPolicyCapability


COMPILER_VERSION = "guardrail-plan-v4"

_MODULE_TIMEOUT_MS: dict[PolicyModule, int] = {
    "data_protection": 750,
    "interaction_safety": 2_500,
    "business_assurance": 5_000,
}
_AUTOMATED_REASONING_TIMEOUT_MS = 30_000


class GuardrailCompiler:
    """Compile human-facing Guardrails into immutable execution plans."""

    def __init__(
        self, *, specialized_evaluator_risks: frozenset[str] = frozenset()
    ) -> None:
        self._specialized_evaluator_risks = specialized_evaluator_risks

    def compile(
        self,
        guardrail: Guardrail,
        version: int,
        *,
        resolved_policies: tuple[ResolvedPolicyCapability, ...],
        policy_versions: tuple[PolicyVersionSnapshot, ...] = (),
        policy_bindings: tuple[GuardrailPolicyBindingSnapshot, ...] = (),
    ) -> GuardrailPlanSnapshot:
        if not guardrail.purpose.strip():
            raise PlanCompilationError("A Guardrail requires a clear purpose.")
        if not resolved_policies and not policy_versions:
            raise PlanCompilationError("Select at least one Policy before testing.")

        steps: list[GuardrailPlanStep] = []
        for configured in resolved_policies:
            definition = runtime_capability(configured.risk)
            stages = tuple(
                stage
                for stage in definition.available_stages
                if not (
                    stage == "deep_judge"
                    and configured.risk not in self._specialized_evaluator_risks
                    and len(definition.available_stages) > 1
                )
            )
            phases = self._phases(guardrail, configured.risk, definition.default_phases)
            parameters = self._guardrail_parameters(
                guardrail,
                configured.risk,
                configured,
            )
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

        reasoning_policies = self._reasoning_policies(resolved_policies)
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
            policy_versions=policy_versions,
            policy_bindings=policy_bindings,
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
                    and runtime_capability(step.risk).module == module
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
                raise PlanCompilationError("Compiled Policy modules must form an acyclic graph.")
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
    def _guardrail_parameters(
        guardrail: Guardrail,
        risk: str,
        configured: ResolvedPolicyCapability,
    ) -> tuple[tuple[str, str], ...]:
        if risk == "builtin_content_filter":
            selections = tuple(
                (binding, library_policy(binding.policy_id))
                for binding in guardrail.policy_bindings
                if library_policy(binding.policy_id) is not None
            )
            enabled_rules = {
                binding.policy_id: list(binding.enabled_rule_ids)
                for binding, _policy in selections
                if binding.enabled_rule_ids
            }
            rule_actions = {
                binding.policy_id: dict(binding.rule_actions)
                for binding, _policy in selections
                if binding.rule_actions
            }
            policy_parameters = {
                binding.policy_id: dict(binding.parameter_values)
                for binding, _policy in selections
                if binding.parameter_values
            }
            return (
                (
                    "policy_versions_json",
                    json.dumps(
                        {
                            binding.policy_id: selected.version
                            for binding, selected in selections
                            if selected is not None
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                ),
                ("policy_ids", "\n".join(binding.policy_id for binding, _ in selections)),
                (
                    "enabled_rules_json",
                    json.dumps(enabled_rules, sort_keys=True, separators=(",", ":")),
                ),
                (
                    "rule_actions_json",
                    json.dumps(rule_actions, sort_keys=True, separators=(",", ":")),
                ),
                (
                    "policy_parameters_json",
                    json.dumps(
                        policy_parameters,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                ),
                ("custom_rules_json", "[]"),
            )
        if risk == "contextual_grounding":
            configured_parameters = _binding_parameters(guardrail, risk)
            thresholds = (
                ("grounding_threshold", configured_parameters.get("grounding_threshold", "0.7")),
                ("relevance_threshold", configured_parameters.get("relevance_threshold", "0.7")),
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
        configured_policies: tuple[ResolvedPolicyCapability, ...],
    ) -> tuple[AutomatedReasoningPolicySnapshot, ...]:
        snapshots: list[AutomatedReasoningPolicySnapshot] = []
        for configured in configured_policies:
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
        if risk != "builtin_content_filter":
            return defaults
        phases = {
            stage
            for binding in guardrail.policy_bindings
            if (selected := library_policy(binding.policy_id)) is not None
            for stage in selected.stages
            if not binding.enabled_rails or stage in binding.enabled_rails
        }
        return tuple(phase for phase in ("input", "output") if phase in phases)


def _binding_parameters(guardrail: Guardrail, risk: str) -> dict[str, str]:
    candidates = tuple(
        binding
        for binding in guardrail.policy_bindings
        if binding.policy_id == builtin_policy_id(risk)
    )
    return dict(candidates[0].parameter_values) if candidates else {}
