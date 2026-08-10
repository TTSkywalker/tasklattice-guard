from __future__ import annotations

import sqlite3

import pytest

from app.control_plane.domain import (
    ControlPlaneError,
    EvaluationCaseResult,
    EvaluationMetrics,
    ProfileRisk,
    ValidationError,
    WorkloadFilterExpression,
    WorkloadFilterRule,
)
from app.control_plane.service import ControlPlaneService
from app.engine.contracts import RequestContext


def filter_rule(
    field: str, operator: str, value: str, *, key: str = ""
) -> WorkloadFilterRule:
    return WorkloadFilterRule(field=field, operator=operator, value=value, key=key)


def filter_expression(
    *rules: WorkloadFilterRule | WorkloadFilterExpression,
    combinator: str = "and",
) -> WorkloadFilterExpression:
    return WorkloadFilterExpression(combinator=combinator, rules=rules)


def pass_current_profile(service: ControlPlaneService, profile_id: str):
    profile = service.profile(profile_id)
    service.save_evaluation(
        profile_id=profile.id,
        profile_revision=None,
        source_draft_version=profile.draft_version,
        status="passed",
        metrics=EvaluationMetrics(1, 1, 100, 0, 0, 5, 10),
        results=(
            EvaluationCaseResult(
                "case", "case", "secrets", "block", "block", True, "deterministic", 1, "blocked"
            ),
        ),
    )
    return service.activate_tested_version(profile.id)


def test_profile_compiles_from_global_enforcement_mode_and_tests_create_version(tmp_path):
    service = ControlPlaneService(tmp_path / "v2.db")
    profile = service.create_profile(
        name="Finance Safety",
        purpose="Keep the Finance assistant inside approved financial topics.",
        allowed_topics=("Financial analysis",),
        restricted_topics=("Biomedical research",),
        risks=(ProfileRisk("topic_control", "redirect"),),
    )
    plan = service.compile_draft(profile.id)

    assert {step.stage for step in plan.steps} == {"deterministic", "deep_judge"}
    assert any(step.escalation == "on_uncertain" for step in plan.steps)
    with pytest.raises(ValidationError, match="Run and pass tests"):
        service.activate_tested_version(profile.id)

    tested = pass_current_profile(service, profile.id)

    assert tested.profile.active_revision == 1
    assert tested.revision.plan_checksum


def test_protected_workload_resolves_one_immutable_profile_version(tmp_path):
    service = ControlPlaneService(tmp_path / "v2.db")
    baseline = service.create_profile(
        name="Company Baseline",
        purpose="Protect internal model interactions from secrets.",
        risks=(ProfileRisk("secrets", "reject"),),
    )
    pass_current_profile(service, baseline.id)
    baseline = service.profile(baseline.id)
    workload = service.create_workload(
        name="Finance Knowledge Assistant",
        profile_id=baseline.id,
        filter=filter_expression(
            filter_rule("http.header", "equals", "finance-copilot", key="x-app-id"),
            filter_rule("model", "glob", "qwen/*"),
        ),
    )
    resolution = service.resolve(
        RequestContext(
            gateway="local",
            gateway_id=None,
            headers=(("x-app-id", "finance-copilot"),),
            fields=(("model", "qwen/chat"),),
        )
    )

    assert resolution.workload_id == workload.id
    assert resolution.plan.profile_id == baseline.id
    assert resolution.plan.profile_revision == baseline.active_revision

    service.update_profile(baseline.id, purpose="Updated company baseline requiring new tests.")
    pinned = service.resolve(
        RequestContext(
            gateway="local",
            gateway_id=None,
            headers=(("X-App-ID", "finance-copilot"),),
            fields=(("model", "qwen/chat"),),
        )
    )
    assert pinned.plan.profile_revision == workload.profile_revision


@pytest.mark.parametrize(
    ("filter", "context"),
    (
        (filter_expression(filter_rule("http.header", "equals", "finance-agent", key="x-app-id")), RequestContext("http", headers=(("X-App-ID", "finance-agent"),))),
        (filter_expression(filter_rule("litellm.api_key_alias", "equals", "batch-api-client")), RequestContext("litellm", fields=(("litellm.api_key_alias", "batch-api-client"),))),
        (filter_expression(filter_rule("a2a.extensions", "contains", "payments/v1")), RequestContext("a2a", fields=(("a2a.extensions", "https://example.com/payments/v1,https://example.com/citations/v1"),))),
    ),
)
def test_workload_filters_match_http_litellm_and_a2a_facts(tmp_path, filter, context):
    service = ControlPlaneService(tmp_path / f"{context.gateway}.db")
    safe = service.create_profile(
        name=f"Safe for {context.gateway}",
        purpose="Protect a distinct trusted traffic identity.",
        risks=(ProfileRisk("secrets", "reject"),),
    )
    pass_current_profile(service, safe.id)
    workload = service.create_workload(
        name=f"Workload for {context.gateway}",
        profile_id=safe.id,
        filter=filter,
    )

    resolution = service.resolve(context)

    assert resolution.workload_id == workload.id
    assert resolution.plan.profile_id == safe.id


def test_unrelated_request_fields_do_not_select_a_workload(tmp_path):
    service = ControlPlaneService(tmp_path / "unrelated-field.db")
    safe = service.create_profile(
        name="Cluster Safe",
        purpose="Protect a technical runtime cluster.",
        risks=(ProfileRisk("secrets", "reject"),),
    )
    pass_current_profile(service, safe.id)
    service.create_workload(
        name="Scheduler cluster",
        profile_id=safe.id,
        filter=filter_expression(filter_rule("http.header", "equals", "scheduler-cluster", key="x-cluster-id")),
    )

    with pytest.raises(ControlPlaneError, match="No Protected Workload matches"):
        service.resolve(
            RequestContext(
                gateway="local",
                gateway_id=None,
                fields=(("sdk.cluster", "scheduler-cluster"),),
            )
        )


def test_equally_specific_workload_matches_fail_closed(tmp_path):
    service = ControlPlaneService(tmp_path / "ambiguous.db")
    safe = service.create_profile(
        name="Ambiguous Safe",
        purpose="Protect ambiguous filter tests.",
        risks=(ProfileRisk("secrets", "reject"),),
    )
    pass_current_profile(service, safe.id)
    service.create_workload(
        name="Agent filter",
        profile_id=safe.id,
        filter=filter_expression(filter_rule("http.header", "equals", "finance-agent", key="x-app-id")),
    )
    service.create_workload(
        name="Client filter",
        profile_id=safe.id,
        filter=filter_expression(filter_rule("litellm.api_key_alias", "equals", "batch-client")),
    )

    with pytest.raises(ControlPlaneError, match="equally specific"):
        service.resolve(
            RequestContext(
                gateway="local",
                gateway_id=None,
                headers=(("x-app-id", "finance-agent"),),
                fields=(("litellm.api_key_alias", "batch-client"),),
            )
        )


def test_new_control_plane_starts_without_fake_profiles_or_workloads(tmp_path):
    service = ControlPlaneService(tmp_path / "v5.db")

    assert service.profiles() == ()
    assert service.workloads() == ()
    assert service.gateways() == ()


def test_v9_upgrade_preserves_safes_and_removes_flat_workloads(tmp_path):
    database_path = tmp_path / "upgrade.db"
    service = ControlPlaneService(database_path)
    safe = service.create_profile(
        name="Preserved Safe",
        purpose="Preserve reviewed policy state during the Filter replacement.",
        risks=(ProfileRisk("secrets", "reject"),),
    )
    pass_current_profile(service, safe.id)
    safe = service.profile(safe.id)

    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            DROP TABLE workloads;
            CREATE TABLE workloads (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                safe_id TEXT NOT NULL,
                safe_revision INTEGER NOT NULL,
                filters_json TEXT NOT NULL,
                enabled INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        connection.execute(
            "INSERT INTO workloads VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "legacy-workload",
                "Legacy Workload",
                safe.id,
                safe.active_revision,
                "[]",
                1,
                safe.updated_at,
            ),
        )
        connection.execute(
            "UPDATE control_plane_meta SET value = 'tasklattice-guard-v9' WHERE key = 'schema_version'"
        )
        connection.commit()

    migrated = ControlPlaneService(database_path)

    assert migrated.profile(safe.id).name == "Preserved Safe"
    assert migrated.workloads() == ()


def test_nested_filter_expression_matches_either_trusted_finance_identity(tmp_path):
    service = ControlPlaneService(tmp_path / "nested.db")
    safe = service.create_profile(
        name="Finance identities",
        purpose="Protect finance HTTP callers selected from verified request facts.",
        risks=(ProfileRisk("secrets", "reject"),),
    )
    pass_current_profile(service, safe.id)
    workload = service.create_workload(
        name="Finance callers",
        profile_id=safe.id,
        filter=filter_expression(
            filter_rule("protocol", "equals", "http"),
            filter_expression(
                filter_rule("http.header", "equals", "finance-agent", key="x-app-id"),
                filter_rule("auth.jwt_claim", "equals", "finance", key="department"),
                combinator="or",
            ),
        ),
    )

    header_resolution = service.resolve(
        RequestContext(
            "http",
            headers=(("X-App-ID", "finance-agent"),),
            fields=(("protocol", "http"),),
        )
    )
    claim_resolution = service.resolve(
        RequestContext(
            "http",
            jwt_claims=(("department", "finance"),),
            fields=(("protocol", "http"),),
        )
    )

    assert header_resolution.workload_id == workload.id
    assert claim_resolution.workload_id == workload.id


def test_impossible_and_filter_is_rejected_with_or_recovery(tmp_path):
    service = ControlPlaneService(tmp_path / "conflicting-filter.db")
    safe = service.create_profile(
        name="Protocol safe",
        purpose="Protect requests selected by their protocol.",
        risks=(ProfileRisk("secrets", "reject"),),
    )
    pass_current_profile(service, safe.id)

    with pytest.raises(ValidationError, match="use an OR group"):
        service.create_workload(
            name="Impossible protocol filter",
            profile_id=safe.id,
            filter=filter_expression(
                filter_rule("protocol", "equals", "http"),
                filter_rule("protocol", "equals", "a2a"),
            ),
        )


def test_catalog_supports_profile_creation_without_exposing_evaluator_configuration(tmp_path):
    service = ControlPlaneService(tmp_path / "v2.db")

    assert {item.id for item in service.templates()} >= {
        "topic-filtering",
        "mas-ai-risk-management",
        "advanced-au-pii-protection",
    }
    assert len(service.templates()) == 17
    assert {item.id for item in service.protections()} >= {"secrets", "pii", "company_policy"}
    assert all(item.purpose for item in service.templates())
    assert all(set(item.__dataclass_fields__) == {"risk", "action"} for template in service.templates() for item in template.risks)
