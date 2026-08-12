from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from typing import Any

import yaml
from nemoguardrails import RailsConfig

from ..runtime.contracts import (
    GuardrailPhase,
    GuardrailPlanModule,
    GuardrailPlanSnapshot,
    NeMoActionBinding,
    NeMoConfigSnapshot,
)
from .domain import ControlDraft, PlanCompilationError


NEMO_COMPILER_VERSION = "tasklattice-nemo-config-v3"

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

                for step in steps:
                    binding_steps[step.id] = step
                    binding_phases.setdefault(step.id, []).append(phase)

            flows[phase].extend(native_detection)
            flows[phase].extend(native_mutation)

        builtin_bindings = tuple(
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
        custom_bindings = _custom_action_bindings(plan)
        bindings = builtin_bindings + custom_bindings

        missing = required_models - self._model_types
        if missing:
            raise PlanCompilationError(
                "NeMo model configuration is required for: "
                + ", ".join(sorted(missing))
                + "."
            )

        prompts = self._prompts_for(plan, required_models)
        runtime_engine = (
            "iorails"
            if not bindings
            and "sensitive_data_detection" not in required_features
            and all(
                flow in _NATIVE_IORAILS_FLOWS
                for items in flows.values()
                for flow in items
            )
            else "llmrails"
        )
        config = self._config(
            flows,
            prompts,
            required_features,
            colang_version="1.0" if runtime_engine == "iorails" else "2.x",
            include_flow_lists=runtime_engine == "iorails",
        )
        config_yaml = yaml.safe_dump(
            config,
            allow_unicode=True,
            sort_keys=False,
        )
        colang_content = (
            ""
            if runtime_engine == "iorails"
            else _colang_v2(plan, flows, builtin_bindings, custom_bindings)
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
    def validate_control(control_id: str, draft: ControlDraft) -> None:
        declared = {
            match.group(1)
            for source in draft.sources
            for match in re.finditer(
                r"(?m)^flow\s+([A-Za-z_][A-Za-z0-9_]*)\b", source.content
            )
        }
        if "main" in declared:
            raise PlanCompilationError(
                f"Control {control_id!r} must not declare the process-wide main flow."
            )
        missing = tuple(
            binding.flow_name
            for binding in draft.rail_bindings
            if binding.flow_name not in declared
        )
        if missing:
            raise PlanCompilationError(
                f"Control {control_id!r} has Rail bindings for undefined flows: "
                + ", ".join(missing)
                + "."
            )
        colang = "\n".join(
            (
                "import core" if draft.colang_version == "2.x" else "",
                *(source.content for source in draft.sources),
                (
                    "flow main\n  user said something as $message\n  pass"
                    if draft.colang_version == "2.x"
                    else 'define user express greeting\n  "hello"'
                ),
            )
        )
        try:
            RailsConfig.from_content(
                yaml_content=yaml.safe_dump(
                    {"colang_version": draft.colang_version, "models": []}
                ),
                colang_content=colang,
            )
        except Exception as error:
            raise PlanCompilationError(
                f"Control {control_id!r} Colang is invalid: "
                f"{type(error).__name__}: {error}"
            ) from error

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
        *,
        colang_version: str,
        include_flow_lists: bool,
    ) -> dict[str, Any]:
        rails: dict[str, Any] = {}
        if include_flow_lists:
            rails.update(
                {
                    phase: {"flows": items, "parallel": True}
                    for phase, items in flows.items()
                    if items
                }
            )
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
            "colang_version": colang_version,
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
    if module is None:
        return 2_000
    step = next(item for item in plan.steps if item.id == step_id)
    serial_steps = sum(
        1
        for candidate_id in module.step_ids
        if (
            (candidate := next(
                (item for item in plan.steps if item.id == candidate_id),
                None,
            ))
            is not None
            and candidate.risk == step.risk
            and phase in candidate.phases
        )
    )
    # Risks in a module run concurrently, while escalation steps for one risk
    # run serially. Dividing the module budget prevents a risk chain from
    # silently multiplying the declared latency bound.
    return max(1, module.timeout_ms // max(1, serial_steps))


def _colang_v2(
    plan: GuardrailPlanSnapshot,
    native_flows: dict[GuardrailPhase, list[str]],
    bindings: tuple[NeMoActionBinding, ...],
    custom_bindings: tuple[NeMoActionBinding, ...],
) -> str:
    """Compile the policy graph into Colang 2.x so NeMo owns orchestration."""
    imports = {"import core"}
    configured_native = {
        flow for flows in native_flows.values() for flow in flows
    }
    if any(flow.startswith("content safety check") for flow in configured_native):
        imports.add("import nemoguardrails.library.content_safety")
    if any(flow.startswith("topic safety check") for flow in configured_native):
        imports.add("import nemoguardrails.library.topic_safety")
    if "jailbreak detection model" in configured_native:
        imports.add("import nemoguardrails.library.jailbreak_detection")

    lines = [
        *sorted(imports),
        "",
        "flow main",
        "  user said something as $message",
        "  global $tasklattice_phase",
        '  if $tasklattice_phase == "output"',
        "    await tasklattice output rails $message.transcript",
        "  else",
        "    await tasklattice input rails $message.transcript",
        "",
    ]

    custom_sources = _compiled_control_sources(plan)
    if custom_sources:
        lines.extend((custom_sources, ""))

    for phase in ("input", "output"):
        phase_bindings = tuple(item for item in bindings if phase in item.phases)
        phase_custom = tuple(
            item for item in custom_bindings if phase in item.phases
        )
        risks = tuple(dict.fromkeys(
            tuple(_native_risk(flow) for flow in native_flows[phase])
            + tuple(item.risk for item in phase_bindings)
        ))
        risks = tuple(risk for risk in risks if risk)
        if not risks and not phase_custom:
            continue

        lines.extend((f"flow tasklattice {phase} rails $text",))
        message_var = "$user_message" if phase == "input" else "$bot_message"
        lines.extend((f"  global {message_var}", f"  {message_var} = $text"))

        modules = _phase_modules(plan, phase, risks) if risks else ()
        detection_custom = tuple(
            item for item in phase_custom if item.execution_mode == "detect"
        )
        mutation_custom = tuple(
            sorted(
                (item for item in phase_custom if item.execution_mode == "mutate"),
                key=lambda item: int(item.parameter("priority") or 0),
            )
        )
        first_wave = tuple(
            _module_flow_name(phase, module.id)
            for module in (_module_waves(modules)[0] if modules else ())
        ) + tuple(_compiled_flow_name(item) for item in detection_custom)
        if first_wave:
            lines.extend(_await_parallel(first_wave, "$text", indent="  "))
        if modules:
            for wave in _module_waves(modules)[1:]:
                flow_names = tuple(
                    _module_flow_name(phase, module.id) for module in wave
                )
                lines.extend(_await_parallel(flow_names, "$text", indent="  "))
        for binding in mutation_custom:
            lines.append(
                f"  await {_compiled_flow_name(binding)}(text=$text)"
            )
        lines.extend(("  $decision = await TaskLatticeResolveAction(text=$text)", ""))

        risk_to_native = {
            _native_risk(flow): flow for flow in native_flows[phase]
        }
        for module in modules:
            module_risks = tuple(
                risk for risk in risks if _module_for_risk(plan, phase, risk) == module.id
            )
            lines.append(f"flow {_module_flow_name(phase, module.id)} $text")
            lines.extend(
                _await_parallel(
                    tuple(_risk_flow_name(phase, risk) for risk in module_risks),
                    "$text",
                    indent="  ",
                )
            )
            lines.append("")

            for risk in module_risks:
                flow_name = _risk_flow_name(phase, risk)
                native = risk_to_native.get(risk)
                selected = tuple(item for item in phase_bindings if item.risk == risk)
                lines.append(f"flow {flow_name} $text")
                if native:
                    lines.extend(_native_flow_lines(native, phase))
                else:
                    lines.extend(_binding_flow_lines(selected))
                lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _binding_flow_lines(bindings: tuple[NeMoActionBinding, ...]) -> list[str]:
    lines: list[str] = []
    previous = "$result"
    for index, binding in enumerate(bindings):
        call = (
            "$result = await TaskLatticeEvaluateStepAction("
            f'text=$text, step_id="{binding.id}")'
        )
        if index == 0:
            lines.append(f"  {call}")
            continue
        condition = {
            "always": (
                f'{previous}["verdict"] == "safe" or '
                f'{previous}["verdict"] == "uncertain"'
            ),
            "on_uncertain": f'{previous}["verdict"] == "uncertain"',
            "never": "false",
        }[binding.escalation]
        lines.extend((f"  if {condition}", f"    {call}"))
    return lines


def _native_flow_lines(flow: str, phase: GuardrailPhase) -> list[str]:
    if flow.startswith("content safety check"):
        action = (
            "ContentSafetyCheckInputAction"
            if phase == "input"
            else "ContentSafetyCheckOutputAction"
        )
        return [
            f'  $response = await {action}(model_name="content_safety")',
            "  $recorded = await TaskLatticeRecordNativeAction("
            'risk="content_safety", safe=$response["allowed"], text=$text, '
            'details=$response["policy_violations"])',
        ]
    if flow.startswith("topic safety check"):
        return [
            '  $response = await TopicSafetyCheckInputAction(model_name="topic_control")',
            "  $recorded = await TaskLatticeRecordNativeAction("
            'risk="topic_control", safe=$response["on_topic"], text=$text)',
        ]
    if flow == "jailbreak detection model":
        return [
            "  $detected = await JailbreakDetectionModelAction",
            "  if $detected",
            "    $recorded = await TaskLatticeRecordNativeAction("
            'risk="jailbreak", safe=False, text=$text)',
            "  else",
            "    $recorded = await TaskLatticeRecordNativeAction("
            'risk="jailbreak", safe=True, text=$text)',
        ]
    if "sensitive data" in flow:
        action = (
            "MaskSensitiveDataAction"
            if flow.startswith("mask ")
            else "DetectSensitiveDataAction"
        )
        return [
            f'  $pii_result = await {action}(source="{phase}", text=$text)'
        ]
    raise PlanCompilationError(f"Unsupported NeMo native flow {flow!r}.")


def _await_parallel(
    flow_names: tuple[str, ...],
    argument: str,
    *,
    indent: str,
) -> list[str]:
    if not flow_names:
        return [f"{indent}pass"]
    if len(flow_names) == 1:
        return [f"{indent}await {flow_names[0]}(text={argument})"]
    refs = tuple(f"$parallel_{index}" for index in range(len(flow_names)))
    lines = [
        f"{indent}start {name}(text={argument}) as {ref}"
        for name, ref in zip(flow_names, refs, strict=True)
    ]
    joined = " and ".join(f"{ref}.Finished()" for ref in refs)
    lines.append(f"{indent}match {joined}")
    return lines


def _phase_modules(
    plan: GuardrailPlanSnapshot,
    phase: GuardrailPhase,
    risks: tuple[str, ...],
) -> tuple[GuardrailPlanModule, ...]:
    modules = list(plan.modules_for(phase))
    unassigned = tuple(
        risk
        for risk in risks
        if not any(
            _module_contains_risk(plan, item.id, risk)
            for item in modules
        )
    )
    if unassigned:
        raise PlanCompilationError(
            "NeMo policy risks must belong to a Control module: "
            + ", ".join(unassigned)
            + "."
        )
    return tuple(modules)


def _module_waves(
    modules: tuple[GuardrailPlanModule, ...],
) -> tuple[tuple[GuardrailPlanModule, ...], ...]:
    pending = list(modules)
    completed: set[str] = set()
    waves = []
    while pending:
        wave = tuple(item for item in pending if set(item.depends_on) <= completed)
        if not wave:
            raise PlanCompilationError("NeMo module dependencies contain a cycle.")
        waves.append(wave)
        completed.update(item.id for item in wave)
        pending = [item for item in pending if item not in wave]
    return tuple(waves)


def _module_for_risk(
    plan: GuardrailPlanSnapshot,
    phase: GuardrailPhase,
    risk: str,
) -> str:
    try:
        return next(
            module.id
            for module in plan.modules_for(phase)
            if _module_contains_risk(plan, module.id, risk)
        )
    except StopIteration as error:
        raise PlanCompilationError(
            f"NeMo policy risk {risk!r} has no {phase} Control module."
        ) from error


def _module_contains_risk(
    plan: GuardrailPlanSnapshot,
    module_id: str,
    risk: str,
) -> bool:
    module = next((item for item in plan.modules if item.id == module_id), None)
    if module is None:
        return False
    steps = {step.id: step for step in plan.steps}
    return any(
        step_id in steps and steps[step_id].risk == risk
        for step_id in module.step_ids
    )


def _module_flow_name(phase: GuardrailPhase, module_id: str) -> str:
    return f"tasklattice_module_{phase}_{_flow_identifier(module_id)}"


def _risk_flow_name(phase: GuardrailPhase, risk: str) -> str:
    return f"tasklattice_risk_{phase}_{_flow_identifier(risk)}"


def _flow_identifier(value: str) -> str:
    return "_".join(re.sub(r"[^a-zA-Z0-9]+", " ", value).split()).lower()


def _native_risk(flow: str) -> str | None:
    if flow.startswith("content safety check"):
        return "content_safety"
    if flow.startswith("topic safety check"):
        return "topic_control"
    if flow == "jailbreak detection model":
        return "jailbreak"
    if "sensitive data" in flow:
        return "pii"
    return None


def _custom_action_bindings(
    plan: GuardrailPlanSnapshot,
) -> tuple[NeMoActionBinding, ...]:
    versions = {
        (item.control_id, item.version): item for item in plan.control_versions
    }
    bindings: list[NeMoActionBinding] = []
    for selected in plan.control_bindings:
        version = versions.get((selected.control_id, selected.control_version))
        if version is None:
            raise PlanCompilationError(
                f"Guardrail references missing Control Version "
                f"{selected.control_id}@{selected.control_version}."
            )
        if version.colang_version != "2.x":
            raise PlanCompilationError(
                f"Custom Control {version.control_id}@{version.version} must use "
                "Colang 2.x in an LLMRails Guardrail."
            )
        action = next(
            (
                item
                for item in version.action_references
                if item.name != "TaskLatticeRecordControlAction"
            ),
            None,
        )
        for rail in version.rail_bindings:
            if rail.rail_type not in selected.enabled_rails:
                continue
            if rail.rail_type not in {"input", "output"}:
                raise PlanCompilationError(
                    f"R1 does not execute {rail.rail_type!r} Rail bindings yet."
                )
            binding_id = (
                f"tl.{version.control_id}.v{version.version}.{rail.flow_name}"
            )
            bindings.append(
                NeMoActionBinding(
                    id=binding_id,
                    risk=version.control_id,
                    stage="deterministic",
                    phases=(rail.rail_type,),
                    on_unsafe=rail.on_unsafe,
                    timeout_ms=rail.timeout_ms,
                    parameters=(
                        *selected.parameter_values,
                        ("priority", str(rail.priority or 0)),
                    ),
                    control_id=version.control_id,
                    control_version=version.version,
                    flow_name=rail.flow_name,
                    action_name=action.name if action else None,
                    action_version=action.version if action else None,
                    parallel_group=rail.parallel_group,
                    execution_mode=rail.execution_mode,
                    failure_mode=rail.failure_mode,
                )
            )
    return tuple(bindings)


def _compiled_control_sources(plan: GuardrailPlanSnapshot) -> str:
    selected = {
        (item.control_id, item.control_version): item
        for item in plan.control_bindings
    }
    output: list[str] = []
    for version in plan.control_versions:
        binding = selected.get((version.control_id, version.version))
        if binding is None:
            continue
        declared = tuple(
            dict.fromkeys(
                match.group(1)
                for source in version.sources
                for match in re.finditer(
                    r"(?m)^flow\s+([A-Za-z_][A-Za-z0-9_]*)\b",
                    source.content,
                )
            )
        )
        replacements = {
            name: _namespaced_flow_name(version.control_id, version.version, name)
            for name in declared
        }
        parameters = dict(binding.parameter_values)
        for source in version.sources:
            content = re.sub(r"(?m)^\s*import\s+core\s*$", "", source.content)
            for name, replacement in replacements.items():
                content = re.sub(rf"\b{re.escape(name)}\b", replacement, content)
            for name, value in parameters.items():
                content = content.replace("${" + name + "}", value)
            output.append(
                f"# Control {version.control_id}@{version.version}: {source.path}\n"
                + content.strip()
            )
    return "\n\n".join(output)


def _compiled_flow_name(binding: NeMoActionBinding) -> str:
    if binding.control_id is None or binding.control_version is None or not binding.flow_name:
        raise PlanCompilationError(
            f"Custom Action binding {binding.id!r} is missing Control metadata."
        )
    return _namespaced_flow_name(
        binding.control_id, binding.control_version, binding.flow_name
    )


def _namespaced_flow_name(control_id: str, version: int, flow_name: str) -> str:
    # Colang 2.x does not accept dots in flow identifiers. The immutable
    # artifact retains the canonical dotted binding ID while executable Colang
    # uses the equivalent collision-free underscore form.
    return "_".join(
        (
            "tl",
            _flow_identifier(control_id),
            f"v{version}",
            _flow_identifier(flow_name),
        )
    )
