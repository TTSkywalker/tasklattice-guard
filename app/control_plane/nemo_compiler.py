from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Any

import yaml
from nemoguardrails import RailsConfig

from ..engine.contracts import (
    GuardrailPhase,
    GuardrailPlanSnapshot,
    NeMoActionBinding,
    NeMoConfigSnapshot,
)
from .domain import PlanCompilationError


NEMO_COMPILER_VERSION = "tasklattice-nemo-config-v2"

_NATIVE_IORAILS_FLOWS = {
    "content safety check input $model=content_safety",
    "content safety check output $model=content_safety",
    "topic safety check input $model=topic_control",
    "jailbreak detection model",
}


class NeMoConfigCompiler:
    """Compile a released Guardrail plan into an immutable NeMo configuration."""

    def __init__(
        self,
        *,
        models: tuple[dict[str, Any], ...] = (),
        profile_prompts_yaml: str = "",
        jailbreak_detection: dict[str, Any] | None = None,
        otel_enabled: bool = False,
    ) -> None:
        self._models = tuple(dict(item) for item in models)
        self._model_types = frozenset(str(item.get("type", "")) for item in models)
        self._profile_prompts = _prompts(profile_prompts_yaml)
        self._jailbreak_detection = (
            dict(jailbreak_detection) if jailbreak_detection else None
        )
        self._otel_enabled = otel_enabled

    def compile(self, plan: GuardrailPlanSnapshot) -> NeMoConfigSnapshot:
        flows: dict[GuardrailPhase, list[str]] = {"input": [], "output": []}
        binding_phases: dict[str, list[GuardrailPhase]] = {}
        binding_steps = {}
        required_models: set[str] = set()
        required_features: set[str] = set()

        risks = tuple(dict.fromkeys(step.risk for step in plan.steps))
        for phase in ("input", "output"):
            native_detection: list[str] = []
            native_mutation: list[str] = []
            has_custom_actions = False
            for risk in risks:
                steps = tuple(
                    step
                    for step in plan.steps
                    if step.risk == risk and phase in step.phases
                )
                if not steps:
                    continue

                native = self._native_flow(risk, phase, steps[0].on_unsafe)
                if native is not None:
                    target = native_mutation if native.startswith("mask ") else native_detection
                    target.append(native)
                    if risk == "content_safety":
                        required_models.add("content_safety")
                    elif risk == "topic_control":
                        required_models.add("topic_control")
                    elif risk == "pii":
                        required_features.add("sensitive_data_detection")
                    elif risk == "jailbreak":
                        required_features.add("jailbreak_detection")
                    continue

                has_custom_actions = True
                for step in steps:
                    binding_steps[step.id] = step
                    binding_phases.setdefault(step.id, []).append(phase)

            flows[phase].extend(native_detection)
            if has_custom_actions:
                flows[phase].append(f"tasklattice evaluate {phase}")
            flows[phase].extend(native_mutation)
            if has_custom_actions:
                flows[phase].append(f"tasklattice enforce {phase}")

        bindings = tuple(
            NeMoActionBinding(
                id=step_id,
                risk=binding_steps[step_id].risk,
                stage=binding_steps[step_id].stage,
                phases=tuple(dict.fromkeys(phases)),
                on_unsafe=binding_steps[step_id].on_unsafe,
                escalation=binding_steps[step_id].escalation,
                timeout_ms=max(
                    _timeout_for(plan, step_id, phase) for phase in phases
                ),
                parameters=binding_steps[step_id].parameters,
            )
            for step_id, phases in binding_phases.items()
        )

        missing = required_models - self._model_types
        if missing:
            raise PlanCompilationError(
                "NeMo model configuration is required for: "
                + ", ".join(sorted(missing))
                + "."
            )

        prompts = self._prompts_for(plan, required_models)
        config = self._config(flows, prompts, required_features)
        config_yaml = yaml.safe_dump(
            config,
            allow_unicode=True,
            sort_keys=False,
        )
        colang_content = _colang(bindings)
        runtime_engine = (
            "iorails"
            if not bindings
            and all(flow in _NATIVE_IORAILS_FLOWS for items in flows.values() for flow in items)
            else "llmrails"
        )
        snapshot = NeMoConfigSnapshot(
            guardrail_id=plan.guardrail_id,
            guardrail_version=plan.guardrail_version,
            compiler_version=NEMO_COMPILER_VERSION,
            output_delivery=plan.output_delivery,
            config_yaml=config_yaml,
            colang_content=colang_content,
            prompts_yaml=yaml.safe_dump(
                {"prompts": prompts}, allow_unicode=True, sort_keys=False
            ) if prompts else "",
            action_bindings=bindings,
            required_models=tuple(sorted(required_models)),
            required_features=tuple(sorted(required_features)),
            runtime_engine=runtime_engine,
        )
        self.validate(snapshot)
        return snapshot

    @staticmethod
    def checksum(snapshot: NeMoConfigSnapshot) -> str:
        payload = json.dumps(asdict(snapshot), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()

    @staticmethod
    def validate(snapshot: NeMoConfigSnapshot) -> None:
        try:
            RailsConfig.from_content(
                yaml_content=snapshot.config_yaml,
                colang_content=snapshot.colang_content or None,
            )
        except Exception as error:
            raise PlanCompilationError(
                f"Compiled NeMo configuration is invalid: {type(error).__name__}: {error}"
            ) from error

    def _native_flow(
        self,
        risk: str,
        phase: GuardrailPhase,
        action: str,
    ) -> str | None:
        if risk == "content_safety":
            return f"content safety check {phase} $model=content_safety"
        if risk == "topic_control" and phase == "input" and "topic_control" in self._model_types:
            return "topic safety check input $model=topic_control"
        if risk == "pii":
            operation = "mask" if action in {"redact", "rewrite"} else "detect"
            return f"{operation} sensitive data on {phase}"
        if (
            risk == "jailbreak"
            and phase == "input"
            and self._jailbreak_detection is not None
        ):
            return "jailbreak detection model"
        return None

    def _prompts_for(
        self,
        plan: GuardrailPlanSnapshot,
        required_models: set[str],
    ) -> list[dict[str, Any]]:
        prompts = [
            dict(item)
            for item in self._profile_prompts
            if str(item.get("task", "")).startswith("content_safety_check_")
            and "content_safety" in required_models
        ]
        if "topic_control" in required_models:
            topic_step = next(step for step in plan.steps if step.risk == "topic_control")
            parameters = dict(topic_step.parameters)
            prompts.append(
                {
                    "task": "topic_safety_check_input $model=topic_control",
                    "content": "\n".join(
                        (
                            "You are the topic policy evaluator for an enterprise assistant.",
                            f"Authorized purpose: {parameters.get('purpose', '')}",
                            "Allowed topics:",
                            parameters.get("allowed_topics", ""),
                            "Restricted topics:",
                            parameters.get("restricted_topics", ""),
                            "Classify the primary requested task, not entities merely mentioned as context.",
                        )
                    ),
                    "max_tokens": 10,
                }
            )
        return prompts

    def _config(
        self,
        flows: dict[GuardrailPhase, list[str]],
        prompts: list[dict[str, Any]],
        required_features: set[str],
    ) -> dict[str, Any]:
        rails: dict[str, Any] = {
            phase: {"flows": items, "parallel": False}
            for phase, items in flows.items()
            if items
        }
        if "sensitive_data_detection" in required_features:
            rails["config"] = {
                "sensitive_data_detection": {
                    "input": {"entities": ["EMAIL_ADDRESS", "CREDIT_CARD", "US_SSN"]},
                    "output": {"entities": ["EMAIL_ADDRESS", "CREDIT_CARD", "US_SSN"]},
                    "retrieval": {"entities": ["EMAIL_ADDRESS", "CREDIT_CARD", "US_SSN"]},
                }
            }
        if "jailbreak_detection" in required_features:
            rails.setdefault("config", {})["jailbreak_detection"] = dict(
                self._jailbreak_detection or {}
            )
        config: dict[str, Any] = {
            "colang_version": "1.0",
            "enable_rails_exceptions": False,
            "rails": rails,
            "tracing": {
                "enabled": self._otel_enabled,
                "adapters": [{"name": "OpenTelemetry"}],
                "span_format": "opentelemetry",
                "enable_content_capture": False,
            },
            "metrics": {"enabled": self._otel_enabled},
        }
        if self._models:
            config["models"] = [dict(item) for item in self._models]
        if prompts:
            config["prompts"] = prompts
        return config


def _prompts(raw: str) -> tuple[dict[str, Any], ...]:
    if not raw.strip():
        return ()
    payload = yaml.safe_load(raw) or {}
    return tuple(dict(item) for item in payload.get("prompts", ()))


def _timeout_for(
    plan: GuardrailPlanSnapshot,
    step_id: str,
    phase: GuardrailPhase,
) -> int:
    module = next(
        (
            item
            for item in plan.modules
            if item.phase == phase and step_id in item.step_ids
        ),
        None,
    )
    return module.timeout_ms if module is not None else 2_000


def _colang(bindings: tuple[NeMoActionBinding, ...]) -> str:
    lines = [
        'define bot tasklattice refuse to respond',
        '  "The interaction was blocked by the active Guardrail."',
        "",
    ]
    for phase in ("input", "output"):
        phase_bindings = tuple(item for item in bindings if phase in item.phases)
        if phase_bindings:
            variable = "$user_message" if phase == "input" else "$bot_message"
            lines.extend(
                (
                    f"define flow tasklattice evaluate {phase}",
                    f'  $tasklattice_actions = execute tasklattice_evaluate_phase(text={variable}, phase="{phase}")',
                    "",
                    f"define flow tasklattice enforce {phase}",
                    f"  $tasklattice_decision = execute tasklattice_resolve(text={variable})",
                    '  if $tasklattice_decision["blocked"]',
                    "    bot tasklattice refuse to respond",
                    "    stop",
                    '  if $tasklattice_decision["modified"]',
                    f"    {variable} = $tasklattice_decision[\"content\"]",
                    "",
                )
            )
    return "\n".join(lines).rstrip() + "\n"
