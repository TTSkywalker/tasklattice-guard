from __future__ import annotations

from dataclasses import replace

import pytest

from app.control_plane.catalog import CONTROL_DEFINITIONS
from app.control_plane.domain import (
    ActionReference,
    ControlDraft,
    ControlSourceFile,
    GuardrailControlBinding,
    NotFoundError,
    RailBinding,
    ValidationError,
)
from app.control_plane.service import ControlPlaneService
from app.control_plane.nemo_compiler import NeMoConfigCompiler


SOURCE_V1 = """\
flow check_input $text
  pass
"""
SOURCE_V2 = """\
flow check_input $text
  $checked = True
"""


def _draft(source: str = SOURCE_V1, **changes) -> ControlDraft:
    value = ControlDraft(
        colang_version="2.x",
        sources=(ControlSourceFile("main.co", source),),
        parameter_schema=(),
        rail_bindings=(
            RailBinding(
                "input", "check_input", "detect", "reject",
                parallel_group="native-control-tests",
            ),
        ),
        action_references=(),
    )
    return replace(value, **changes)


def test_published_versions_are_immutable_and_guardrails_stay_pinned(tmp_path):
    service = ControlPlaneService(tmp_path / "controls.db")
    package = service.create_control(
        name="Versioned Control",
        description="Exercise immutable Control releases.",
        owner="platform",
        draft=_draft(),
    )
    version_one = service.publish_control(package.id)
    service.update_control_draft(package.id, draft=_draft(SOURCE_V2))
    version_two = service.publish_control(package.id)
    guardrail = service.create_guardrail(
        name="Pinned Guardrail",
        purpose="Prove that Control upgrades do not alter released intent.",
        control_bindings=(GuardrailControlBinding(package.id, 1, enabled_rails=("input",)),),
    )
    plan = service.compile_draft(guardrail.id)

    stored_one = service.control_version(package.id, 1)
    assert (version_one.version, version_two.version) == (1, 2)
    assert stored_one.sources[0].content == SOURCE_V1
    assert stored_one.checksum == version_one.checksum
    assert plan.control_bindings[0].control_version == 1
    assert plan.control_versions[0].checksum == version_one.checksum


@pytest.mark.parametrize(
    ("changes", "message"),
    (
        (
            {"action_references": (ActionReference("MissingAction", "1.0.0"),)},
            "unregistered Action",
        ),
        ({"model_dependencies": ("missing-model",)}, "unregistered Models"),
        ({"prompt_dependencies": ("missing-prompt",)}, "unregistered Prompts"),
    ),
)
def test_missing_dependencies_block_control_publication(tmp_path, changes, message):
    service = ControlPlaneService(tmp_path / f"{message}.db")
    package = service.create_control(
        name="Incomplete Control",
        description="Drafts may be saved before providers are ready.",
        owner="platform",
        draft=_draft(**changes),
    )

    with pytest.raises(ValidationError, match=message):
        service.publish_control(package.id)
    assert service.control_versions(package.id) == ()


def test_builtins_are_published_control_versions_and_compile_when_bound(tmp_path):
    service = ControlPlaneService(tmp_path / "builtins.db")
    builtins = tuple(item for item in service.controls() if item.source == "built-in")
    assert len(builtins) == len(CONTROL_DEFINITIONS)
    assert all(service.control_versions(item.id)[0].version == 1 for item in builtins)

    secrets = next(item for item in builtins if item.id == "builtin-secrets")
    with pytest.raises(ValidationError, match="system managed"):
        service.update_control_draft(secrets.id, description="changed")

    guardrail = service.create_guardrail(
        name="Native built-in binding",
        purpose="Compile a built-in Control Version through the native binding model.",
        control_bindings=(
            GuardrailControlBinding(secrets.id, 1, enabled_rails=("input", "output")),
        ),
    )
    plan = service.compile_draft(guardrail.id)
    assert {item.risk for item in plan.steps} == {"secrets"}
    assert plan.control_versions[0].source == "built-in"
    assert dict(plan.control_versions[0].execution_contract) == {
        "native_risk": "secrets"
    }
    assert plan.control_versions[0].action_references[0].name == (
        "TaskLatticeSecretsAction"
    )
    config = NeMoConfigCompiler().compile(plan)
    binding = next(item for item in config.action_bindings if item.risk == "secrets")
    assert binding.control_id == secrets.id
    assert binding.control_version == 1
    assert binding.action_name == "TaskLatticeSecretsAction"


def test_guardrail_binding_requires_an_existing_fixed_control_version(tmp_path):
    service = ControlPlaneService(tmp_path / "missing-version.db")
    with pytest.raises(NotFoundError, match="was not found"):
        service.create_guardrail(
            name="Invalid binding",
            purpose="Reject unresolved Control Versions.",
            control_bindings=(
                GuardrailControlBinding("missing-control", 99, enabled_rails=("input",)),
            ),
        )
