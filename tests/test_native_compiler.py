from __future__ import annotations

from dataclasses import replace

import pytest

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
