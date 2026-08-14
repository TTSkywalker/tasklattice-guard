from __future__ import annotations

from dataclasses import replace
import json
import sqlite3

import pytest

from app.control_plane.catalog import BUILTIN_POLICY_CAPABILITIES
from app.control_plane.domain import (
    ActionReference,
    PolicyDraft,
    PolicySourceFile,
    GuardrailPolicyBinding,
    NotFoundError,
    RailBinding,
    PolicyTestCaseDefinition,
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


def _draft(source: str = SOURCE_V1, **changes) -> PolicyDraft:
    value = PolicyDraft(
        colang_version="2.x",
        sources=(PolicySourceFile("main.co", source),),
        parameter_schema=(),
        rail_bindings=(
            RailBinding(
                "input", "check_input", "detect", "reject",
                parallel_group="policy-tests",
            ),
        ),
        action_references=(),
        test_cases=(
            PolicyTestCaseDefinition(
                id="input-allow",
                name="Allow ordinary input",
                rail_type="input",
                content="ordinary safe input",
                expected_decision="allow",
                covered_rule_ids=("flow/input/check_input",),
            ),
        ),
    )
    return replace(value, **changes)


def test_published_versions_are_immutable_and_guardrails_stay_pinned(tmp_path):
    service = ControlPlaneService(tmp_path / "policies.db")
    record = service.create_policy(
        name="Versioned Policy",
        description="Exercise immutable Policy releases.",
        owner="platform",
        draft=_draft(),
    )
    service.validate_policy(record.id)
    service.save_policy_validation_run(
        policy_id=record.id,
        draft_revision=record.draft_revision,
        status="passed",
        results=(),
    )
    version_one = service.publish_policy(record.id)
    service.update_policy_draft(record.id, draft=_draft(SOURCE_V2))
    updated = service.policy_record(record.id)
    service.validate_policy(record.id)
    service.save_policy_validation_run(
        policy_id=record.id,
        draft_revision=updated.draft_revision,
        status="passed",
        results=(),
    )
    version_two = service.publish_policy(record.id)
    guardrail = service.create_guardrail(
        name="Pinned Guardrail",
        purpose="Prove that Policy upgrades do not alter released intent.",
        policy_bindings=(GuardrailPolicyBinding(record.id, 1, enabled_rails=("input",)),),
    )
    plan = service.compile_draft(guardrail.id)

    stored_one = service.policy_version(record.id, 1)
    assert (version_one.version, version_two.version) == (1, 2)
    assert stored_one.sources[0].content == SOURCE_V1
    assert stored_one.checksum == version_one.checksum
    assert plan.policy_bindings[0].policy_version == "1"
    assert plan.policy_versions[0].checksum == version_one.checksum


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
def test_missing_dependencies_block_policy_publication(tmp_path, changes, message):
    service = ControlPlaneService(tmp_path / f"{message}.db")
    record = service.create_policy(
        name="Incomplete Policy",
        description="Drafts may be saved before providers are ready.",
        owner="platform",
        draft=_draft(**changes),
    )

    with pytest.raises(ValidationError, match=message):
        service.publish_policy(record.id)
    assert service.policy_versions(record.id) == ()


def test_builtins_are_published_policy_versions_and_compile_when_bound(tmp_path):
    service = ControlPlaneService(tmp_path / "builtins.db")
    builtins = tuple(item for item in service.policies() if item.source == "built-in")
    assert len(builtins) == len(BUILTIN_POLICY_CAPABILITIES)
    assert all(service.policy_versions(item.id)[0].version == 1 for item in builtins)

    secrets = next(item for item in builtins if item.id == "builtin-secrets")
    with pytest.raises(ValidationError, match="system managed"):
        service.update_policy_draft(secrets.id, description="changed")

    guardrail = service.create_guardrail(
        name="Native built-in binding",
        purpose="Compile a built-in Policy Version through the native binding model.",
        policy_bindings=(
            GuardrailPolicyBinding(secrets.id, 1, enabled_rails=("input", "output")),
        ),
    )
    plan = service.compile_draft(guardrail.id)
    assert {item.risk for item in plan.steps} == {"secrets"}
    assert plan.policy_versions[0].source == "built-in"
    assert dict(plan.policy_versions[0].execution_contract) == {
        "native_risk": "secrets"
    }
    assert plan.policy_versions[0].action_references[0].name == (
        "GuardSecretsAction"
    )
    config = NeMoConfigCompiler().compile(plan)
    binding = next(item for item in config.action_bindings if item.risk == "secrets")
    assert binding.policy_id == secrets.id
    assert binding.policy_version == "1"
    assert binding.action_name == "GuardSecretsAction"


def test_startup_never_rewrites_a_released_builtin_policy_version(tmp_path):
    database = tmp_path / "immutable-builtins.db"
    service = ControlPlaneService(database)
    original = service.policy_version("builtin-secrets", 1)
    sentinel_checksum = "reviewed-release-sentinel"

    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT version_json FROM policy_versions "
            "WHERE policy_id = 'builtin-secrets' AND version = 1"
        ).fetchone()
        assert row is not None
        payload = json.loads(row[0])
        payload["name"] = "Reviewed built-in release"
        connection.execute(
            "UPDATE policy_versions SET version_json = ?, checksum = ? "
            "WHERE policy_id = 'builtin-secrets' AND version = 1",
            (json.dumps(payload), sentinel_checksum),
        )

    restarted = ControlPlaneService(database)
    stored = restarted.policy_version("builtin-secrets", 1)

    assert stored.version == original.version == 1
    assert stored.name == "Reviewed built-in release"
    assert stored.checksum == sentinel_checksum


def test_guardrail_binding_requires_an_existing_fixed_policy_version(tmp_path):
    service = ControlPlaneService(tmp_path / "missing-version.db")
    with pytest.raises(NotFoundError, match="was not found"):
        service.create_guardrail(
            name="Invalid binding",
            purpose="Reject unresolved Policy Versions.",
            policy_bindings=(
                GuardrailPolicyBinding("missing-policy", 99, enabled_rails=("input",)),
            ),
        )


def test_every_flow_backed_rule_requires_explicit_acceptance_coverage(tmp_path):
    service = ControlPlaneService(tmp_path / "rule-coverage.db")
    uncovered = _draft(
        source="flow first $text\n  pass\nflow second $text\n  pass",
        rail_bindings=(
            RailBinding("input", "first", "detect", "reject"),
            RailBinding("input", "second", "detect", "reject"),
        ),
        test_cases=(
            PolicyTestCaseDefinition(
                id="first-allow",
                name="Accept the first Rule",
                rail_type="input",
                content="ordinary safe input",
                expected_decision="allow",
                covered_rule_ids=("flow/input/first",),
            ),
        ),
    )
    policy = service.create_policy(
        name="Two Rule Policy",
        description="Prove that Rail-level coverage cannot hide an untested Rule.",
        owner="platform",
        draft=uncovered,
    )

    with pytest.raises(
        ValidationError,
        match=r"Every Policy Rule requires a reviewed Test Case; missing flow/input/second",
    ):
        service.validate_policy(policy.id)


def test_guardrail_binding_filters_custom_rules_and_applies_rule_action(tmp_path):
    service = ControlPlaneService(tmp_path / "selected-rules.db")
    draft = _draft(
        source="flow first $text\n  pass\nflow second $text\n  pass",
        rail_bindings=(
            RailBinding("input", "first", "detect", "reject"),
            RailBinding("input", "second", "detect", "reject"),
        ),
        test_cases=(
            PolicyTestCaseDefinition(
                id="first-allow",
                name="Accept the first Rule",
                rail_type="input",
                content="ordinary safe input",
                expected_decision="allow",
                covered_rule_ids=("flow/input/first",),
            ),
            PolicyTestCaseDefinition(
                id="second-allow",
                name="Accept the second Rule",
                rail_type="input",
                content="another safe input",
                expected_decision="allow",
                covered_rule_ids=("flow/input/second",),
            ),
        ),
    )
    policy = service.create_policy(
        name="Selectable Rules Policy",
        description="Prove that Guardrail Rule selection reaches NeMo compilation.",
        owner="platform",
        draft=draft,
    )
    service.validate_policy(policy.id)
    service.save_policy_validation_run(
        policy_id=policy.id,
        draft_revision=policy.draft_revision,
        status="passed",
        results=(),
    )
    version = service.publish_policy(policy.id)
    guardrail = service.create_guardrail(
        name="Selected Rule Guardrail",
        purpose="Run only the reviewed first Rule with its approved override.",
        policy_bindings=(
            GuardrailPolicyBinding(
                policy.id,
                str(version.version),
                enabled_rule_ids=("flow/input/first",),
                rule_actions=(("flow/input/first", "redirect"),),
                enabled_rails=("input",),
            ),
        ),
    )

    plan = service.compile_draft(guardrail.id)
    config = NeMoConfigCompiler().compile(plan)
    selected = tuple(
        binding
        for binding in config.action_bindings
        if binding.policy_id == policy.id
    )

    assert [(item.flow_name, item.on_unsafe) for item in selected] == [
        ("first", "redirect")
    ]


def test_custom_guardrail_binding_rejects_unknown_rule_identity(tmp_path):
    service = ControlPlaneService(tmp_path / "unknown-rule.db")
    policy = service.create_policy(
        name="Known Rule Policy",
        description="Reject a Guardrail binding to a Rule outside this Policy.",
        owner="platform",
        draft=_draft(),
    )
    service.validate_policy(policy.id)
    service.save_policy_validation_run(
        policy_id=policy.id,
        draft_revision=policy.draft_revision,
        status="passed",
        results=(),
    )
    version = service.publish_policy(policy.id)

    with pytest.raises(ValidationError, match="enables unknown Rules"):
        service.create_guardrail(
            name="Invalid Rule Guardrail",
            purpose="Reject unresolved product Rule identities.",
            policy_bindings=(
                GuardrailPolicyBinding(
                    policy.id,
                    str(version.version),
                    enabled_rule_ids=("flow/input/missing",),
                    enabled_rails=("input",),
                ),
            ),
        )
