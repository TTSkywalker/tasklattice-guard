from __future__ import annotations

from dataclasses import replace

import pytest
import yaml

from app.control_plane.nemo_compiler import NeMoConfigCompiler
from app.control_plane.domain import (
    ActionReference,
    ControlDraft,
    ControlParameterDefinition,
    ControlSourceFile,
    GuardrailControlBinding,
    PlanCompilationError,
    RailBinding,
    ValidationError,
)
from app.control_plane.service import ControlPlaneService
from app.nemo.builtin_controls.content_safety import prompts_yaml
from app.runtime.contracts import (
    GuardrailPlanModule,
    GuardrailPlanSnapshot,
    GuardrailPlanStep,
)


def _draft(
    source: str = "flow check_input $text\n  pass",
    *,
    bindings: tuple[RailBinding, ...] | None = None,
    actions: tuple[ActionReference, ...] = (),
    **changes,
) -> ControlDraft:
    value = ControlDraft(
        colang_version="2.x",
        sources=(ControlSourceFile("main.co", source),),
        parameter_schema=(),
        rail_bindings=bindings
        or (RailBinding("input", "check_input", "detect", "reject"),),
        action_references=actions,
    )
    return replace(value, **changes)


def _publish(service: ControlPlaneService, draft: ControlDraft):
    package = service.create_control(
        name="Compiler Control",
        description="Exercise native compiler validation.",
        owner="compiler-tests",
        draft=draft,
    )
    return package, service.publish_control(package.id)


def test_compiler_snapshot_is_deterministic_and_self_describing(tmp_path):
    service = ControlPlaneService(tmp_path / "compiler.db")
    package, version = _publish(service, _draft())
    guardrail = service.create_guardrail(
        name="Compiler preview",
        purpose="Read immutable runtime facts without re-inferring the draft.",
        control_bindings=(
            GuardrailControlBinding(package.id, version.version, enabled_rails=("input",)),
        ),
    )

    first_plan, first, first_checksum = service.compile_preview(guardrail.id)
    second_plan, second, second_checksum = service.compile_preview(guardrail.id)

    assert first_checksum == second_checksum
    assert first == second
    assert first_plan == second_plan
    assert first.runtime_engine == "llmrails"
    assert first.colang_version == "2.x"
    assert first.runtime_profile == "llmrails_colang2_programmable"
    assert first.rail_flows == (("input", f"tl.{package.id}.v1.check_input"),)
    assert ("control", package.id, f"v1:{version.checksum}") in first.dependency_manifest
    assert any(item[0] == "source" for item in first.dependency_manifest)
    assert first.estimated_critical_path_ms == 2_000


@pytest.mark.parametrize(
    ("draft", "message"),
    (
        (
            _draft(
                "flow duplicate $text\n  pass",
                sources=(
                    ControlSourceFile("one.co", "flow duplicate $text\n  pass"),
                    ControlSourceFile("two.co", "flow duplicate $text\n  pass"),
                ),
                bindings=(RailBinding("input", "duplicate", "detect", "reject"),),
            ),
            "duplicate Flow.*two.co:1",
        ),
        (
            _draft(bindings=(RailBinding("input", "missing", "detect", "reject"),)),
            "undefined flows",
        ),
        (_draft("import os\nflow check_input $text\n  pass"), "forbidden import.*main.co:1"),
        (
            _draft("flow check_input $text\n  await missing_flow(text=$text)"),
            "undefined Flow.*main.co:2",
        ),
        (
            _draft("flow check_input $text\n  await MissingAction(text=$text)"),
            "unreferenced Action.*main.co:2",
        ),
        (
            _draft(
                "flow first $text\n  pass\nflow second $text\n  pass",
                bindings=(
                    RailBinding("input", "first", "detect", "reject", depends_on=("second",)),
                    RailBinding("input", "second", "detect", "reject", depends_on=("first",)),
                ),
            ),
            "dependencies contain a cycle",
        ),
        (replace(_draft(), colang_version="1.0"), "must use Colang 2.x"),
    ),
)
def test_compiler_rejects_unsafe_or_incomplete_colang(tmp_path, draft, message):
    service = ControlPlaneService(tmp_path / "invalid.db")
    package = service.create_control(
        name="Invalid compiler input",
        description="Saved as a draft but cannot be published.",
        owner="compiler-tests",
        draft=draft,
    )
    with pytest.raises(PlanCompilationError, match=message):
        service.publish_control(package.id)


def test_required_parameters_are_resolved_into_the_immutable_plan(tmp_path):
    service = ControlPlaneService(tmp_path / "parameters.db")
    package, version = _publish(
        service,
        _draft(
            parameter_schema=(
                ControlParameterDefinition("tenant", "string", required=True),
                ControlParameterDefinition("region", "string", default="eu-west"),
            )
        ),
    )
    with pytest.raises(ValidationError, match="requires tenant"):
        service.create_guardrail(
            name="Missing parameter",
            purpose="Required parameters must be supplied before compilation.",
            control_bindings=(GuardrailControlBinding(package.id, version.version),),
        )

    guardrail = service.create_guardrail(
        name="Resolved parameters",
        purpose="Defaults and explicit values are fixed in the plan.",
        control_bindings=(
            GuardrailControlBinding(
                package.id,
                version.version,
                parameter_values=(("tenant", "acme"),),
                enabled_rails=("input",),
            ),
        ),
    )
    plan = service.compile_draft(guardrail.id)
    assert dict(plan.control_bindings[0].parameter_values) == {
        "region": "eu-west",
        "tenant": "acme",
    }


def test_full_buffered_control_cannot_compile_for_interruptible_output(tmp_path):
    service = ControlPlaneService(tmp_path / "delivery.db")
    package, version = _publish(
        service,
        _draft(execution_contract=(("output_delivery", "full_buffered"),)),
    )
    guardrail = service.create_guardrail(
        name="Wrong delivery",
        purpose="Reject incompatible output delivery before release.",
        output_delivery="interruptible",
        control_bindings=(
            GuardrailControlBinding(package.id, version.version, enabled_rails=("input",)),
        ),
    )
    with pytest.raises(PlanCompilationError, match="requires full-buffered"):
        service.compile_draft(guardrail.id)


def _plan(
    *steps: GuardrailPlanStep,
    modules: tuple[GuardrailPlanModule, ...] | None = None,
) -> GuardrailPlanSnapshot:
    selected_modules = modules
    if selected_modules is None:
        grouped: dict[tuple[str, str], list[str]] = {}
        for step in steps:
            module = (
                "data_protection"
                if step.risk in {"secrets", "pii"}
                else "interaction_safety"
                if step.risk in {
                    "builtin_content_filter",
                    "prompt_injection",
                    "jailbreak",
                    "content_safety",
                }
                else "business_assurance"
            )
            for phase in step.phases:
                grouped.setdefault((phase, module), []).append(step.id)
        selected_modules = tuple(
            GuardrailPlanModule(
                id=f"{module}:{phase}",
                module=module,
                phase=phase,
                step_ids=tuple(step_ids),
            )
            for (phase, module), step_ids in grouped.items()
        )
    return GuardrailPlanSnapshot(
        guardrail_id="runtime-profile",
        guardrail_version=1,
        compiler_version="test-plan-v1",
        safety_level="balanced",
        output_delivery="full_buffered",
        steps=steps,
        modules=selected_modules,
    )


def _step(
    risk: str,
    *,
    stage: str = "deterministic",
    phases=("input",),
    action: str = "reject",
    escalation: str = "never",
) -> GuardrailPlanStep:
    return GuardrailPlanStep(
        id=f"{risk}:{stage}",
        risk=risk,
        stage=stage,
        phases=phases,
        on_unsafe=action,
        escalation=escalation,
    )


@pytest.mark.parametrize(
    "step",
    (
        _step("secrets", phases=("input", "output")),
        _step("pii", phases=("input", "output"), action="redact"),
        _step("builtin_content_filter", phases=("input", "output")),
        _step("topic_control", action="redirect"),
        _step("prompt_injection", stage="fast_semantic"),
        _step("company_policy", stage="deep_judge", escalation="always"),
    ),
)
def test_simple_builtin_actions_compile_to_colang1_standard(step):
    config = NeMoConfigCompiler().compile(_plan(step))
    payload = yaml.safe_load(config.config_yaml)

    assert config.runtime_profile == "llmrails_colang1_standard"
    assert config.runtime_engine == "llmrails"
    assert config.colang_version == payload["colang_version"] == "1.0"
    assert config.action_bindings
    assert all(item.result_var for item in config.action_bindings)
    assert all(
        f'${item.result_var}["blocked"]' in config.colang_content
        and f'${item.result_var}["modified"]' in config.colang_content
        for item in config.action_bindings
    )
    assert all(
        flow.startswith("tasklattice check ")
        for rail, flow in config.rail_flows
        if rail in step.phases
    )


def test_colang1_result_variables_are_stable_and_collision_safe():
    first = _step("secrets")
    second = replace(_step("pii", action="reject"), id="secrets_deterministic")
    first = replace(first, id="secrets-deterministic")
    plan = _plan(first, second)

    one = NeMoConfigCompiler().compile(plan)
    two = NeMoConfigCompiler().compile(plan)
    result_vars = tuple(item.result_var for item in one.action_bindings)

    assert one.runtime_profile == "llmrails_colang1_standard"
    assert result_vars == tuple(item.result_var for item in two.action_bindings)
    assert len(result_vars) == len(set(result_vars))


def test_standalone_native_check_uses_llmrails_colang1_not_iorails():
    plan = _plan(_step("content_safety", stage="fast_semantic"))
    model = {
        "type": "content_safety",
        "engine": "nim",
        "model": "content-safety-test",
        "parameters": {"base_url": "https://nvidia.example/v1"},
    }

    standalone = NeMoConfigCompiler(
        models=(model,), builtin_prompts_yaml=prompts_yaml()
    ).compile(plan)
    owned = NeMoConfigCompiler(
        models=(model,),
        builtin_prompts_yaml=prompts_yaml(),
        execution_surface="owned_generation",
    ).compile(plan)

    assert standalone.runtime_profile == "llmrails_colang1_standard"
    assert standalone.runtime_engine == "llmrails"
    assert standalone.colang_version == "1.0"
    assert owned.runtime_profile == "iorails_native"
    assert owned.runtime_engine == "iorails"
    assert owned.colang_version == "1.0"


@pytest.mark.parametrize(
    "plan",
    (
        _plan(
            _step(
                "prompt_injection",
                stage="fast_semantic",
                escalation="on_uncertain",
            ),
            _step(
                "prompt_injection",
                stage="deep_judge",
                escalation="on_uncertain",
            ),
        ),
        _plan(_step("contextual_grounding", stage="deep_judge", action="regenerate")),
        _plan(_step("automated_reasoning", stage="deep_judge", action="rewrite")),
    ),
)
def test_complex_plans_remain_colang2_programmable(plan):
    config = NeMoConfigCompiler().compile(plan)

    assert config.runtime_profile == "llmrails_colang2_programmable"
    assert config.runtime_engine == "llmrails"
    assert config.colang_version == "2.x"
    assert all(item.result_var is None for item in config.action_bindings)
    assert "TaskLatticeResolveAction" in config.colang_content
    assert (
        "action",
        "TaskLatticeResolveAction",
        "1.0.0",
    ) in config.dependency_manifest


def test_one_modifier_and_independent_blocker_use_colang1_standard():
    config = NeMoConfigCompiler().compile(
        _plan(
            _step("pii", action="redact"),
            _step("builtin_content_filter"),
        )
    )

    assert config.runtime_profile == "llmrails_colang1_standard"
    assert config.runtime_engine == "llmrails"
    assert config.colang_version == "1.0"
    assert all(item.result_var for item in config.action_bindings)
    assert "TaskLatticeResolveAction" not in config.colang_content


def test_module_dependencies_force_colang2_programmable():
    secrets = _step("secrets")
    policy = _step("company_policy", stage="deep_judge")
    modules = (
        GuardrailPlanModule(
            id="data",
            module="data_protection",
            phase="input",
            step_ids=(secrets.id,),
        ),
        GuardrailPlanModule(
            id="policy",
            module="business_assurance",
            phase="input",
            step_ids=(policy.id,),
            depends_on=("data",),
            input_view="masked",
        ),
    )
    config = NeMoConfigCompiler().compile(_plan(secrets, policy, modules=modules))

    assert config.runtime_profile == "llmrails_colang2_programmable"
    first = config.colang_content.index("await tasklattice_module_input_data")
    second = config.colang_content.index("await tasklattice_module_input_policy")
    assert first < second


def test_observability_configuration_matches_runtime_profile():
    standard = NeMoConfigCompiler(otel_enabled=True).compile(
        _plan(_step("secrets"))
    )
    programmable = NeMoConfigCompiler(otel_enabled=True).compile(
        _plan(
            _step("contextual_grounding", stage="deep_judge", action="regenerate")
        )
    )
    model = {
        "type": "content_safety",
        "engine": "nim",
        "model": "content-safety-test",
        "parameters": {"base_url": "https://nvidia.example/v1"},
    }
    iorails = NeMoConfigCompiler(
        models=(model,),
        builtin_prompts_yaml=prompts_yaml(),
        execution_surface="owned_generation",
        otel_enabled=True,
    ).compile(_plan(_step("content_safety", stage="fast_semantic")))

    standard_payload = yaml.safe_load(standard.config_yaml)
    programmable_payload = yaml.safe_load(programmable.config_yaml)
    iorails_payload = yaml.safe_load(iorails.config_yaml)

    assert standard_payload["tracing"] == {
        "enabled": True,
        "enable_content_capture": False,
        "adapters": [{"name": "OpenTelemetry"}],
        "span_format": "opentelemetry",
    }
    assert standard_payload["metrics"] == {"enabled": False}
    assert programmable_payload["tracing"] == {
        "enabled": False,
        "enable_content_capture": False,
    }
    assert programmable_payload["metrics"] == {"enabled": False}
    assert iorails_payload["tracing"] == {
        "enabled": True,
        "enable_content_capture": False,
    }
    assert iorails_payload["metrics"] == {"enabled": True}
