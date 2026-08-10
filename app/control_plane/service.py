from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import threading
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from ..engine.contracts import (
    GuardrailPlanSnapshot,
    GuardrailPlanStep,
    PlanResolution,
    RequestContext,
)
from .catalog import PROTECTIONS, safety_template, safety_templates
from .compiler import GuardrailCompiler
from .domain import (
    ControlPlaneError,
    DecisionEvent,
    EvaluationCaseResult,
    EvaluationMetrics,
    EvaluationRun,
    Gateway,
    GatewayAuthenticationError,
    GatewayRegistration,
    NotFoundError,
    ProfileRevision,
    ProfileRisk,
    ProfileTestCase,
    ProtectedWorkload,
    WorkloadFilterExpression,
    SafetyProfile,
    TestedProfileVersion,
    ValidationError,
)
from .filtering import (
    filter_expression_from_payload,
    filter_expression_matches,
    filter_expression_signature,
    filter_expression_specificity,
    filter_rule_count,
    normalize_filter_expression,
)


SCHEMA_VERSION = "tasklattice-guard-v10"
LEGACY_SCHEMA_VERSION = "tasklattice-guard-v9"


class ControlPlaneService:
    """Persist enterprise safety intent, tested versions, and workload state."""

    def __init__(
        self,
        database_path: Path,
        *,
        fast_semantic_configured: bool = False,
        deep_judge_configured: bool = False,
    ) -> None:
        self._database_path = database_path
        self._fast_semantic_configured = fast_semantic_configured
        self._deep_judge_configured = deep_judge_configured
        self._compiler = GuardrailCompiler()
        self._write_lock = threading.Lock()
        self._runtime_lock = threading.Lock()
        self._gateway_runtime: dict[str, dict[str, object]] = {}
        self._plans: dict[tuple[str, int], GuardrailPlanSnapshot] = {}
        self._workloads: tuple[ProtectedWorkload, ...] = ()
        self._credential_index: dict[str, str] = {}
        self._initialize()

    # Creation resources. These support the Profile workflow but are not
    # first-class navigation objects.

    def templates(self):
        return safety_templates()

    def protections(self):
        return PROTECTIONS

    # Safety Profiles

    def profiles(self) -> tuple[SafetyProfile, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM safes ORDER BY name COLLATE NOCASE, id"
            ).fetchall()
        return tuple(_profile_from_row(row) for row in rows)

    def profile(self, profile_id: str) -> SafetyProfile:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM safes WHERE id = ?", (profile_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError(f"Safety Profile {profile_id!r} was not found.")
        return _profile_from_row(row)

    def create_profile(
        self,
        *,
        name: str,
        purpose: str | None = None,
        template_id: str | None = None,
        allowed_topics: tuple[str, ...] = (),
        restricted_topics: tuple[str, ...] = (),
        risks: tuple[ProfileRisk, ...] = (),
        template_parameters: tuple[tuple[str, str], ...] = (),
        safety_level: str = "balanced",
        output_delivery: str = "window_buffered",
    ) -> SafetyProfile:
        clean_name = name.strip()
        if not clean_name:
            raise ValidationError("Safety Profile name is required.")
        if template_id:
            try:
                template = safety_template(template_id)
            except StopIteration as error:
                raise ValidationError("Unknown Safety Template.") from error
            purpose = purpose.strip() if purpose and purpose.strip() else template.purpose
            allowed_topics = allowed_topics or template.allowed_topics
            restricted_topics = restricted_topics or template.restricted_topics
            risks = risks or tuple(ProfileRisk(item.risk, item.action) for item in template.risks)
            safety_level = template.safety_level
            output_delivery = template.output_delivery
            template_parameters = tuple(
                sorted(
                    (key.strip(), value.strip())
                    for key, value in template_parameters
                    if key.strip() and value.strip()
                )
            )
            supplied = dict(template_parameters)
            missing = [
                item.label
                for item in template.parameters
                if item.required and not supplied.get(item.name, "").strip()
            ]
            if missing:
                raise ValidationError(f"Template requires: {', '.join(missing)}.")
        self._validate_profile_fields(purpose or "", risks, safety_level, output_delivery)
        profile_id = f"safe-{uuid.uuid4().hex[:12]}"
        now = _now()
        with self._write_lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO safes
                    (id, name, purpose, allowed_topics_json, restricted_topics_json,
                     protections_json, safety_level, output_delivery, source_template_id,
                     template_parameters_json, draft_version, active_revision, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, NULL, ?)
                """,
                (
                    profile_id,
                    clean_name,
                    (purpose or "").strip(),
                    _json(allowed_topics),
                    _json(restricted_topics),
                    _risks_json(risks),
                    safety_level,
                    output_delivery,
                    template_id,
                    _json(dict(template_parameters)),
                    now,
                ),
            )
            self._insert_activity(
                connection,
                kind="profile.created",
                outcome="success",
                profile_id=profile_id,
                detail=f"Created Safety Profile {clean_name}.",
            )
            connection.commit()
        return self.profile(profile_id)

    def update_profile(
        self,
        profile_id: str,
        *,
        name: str | None = None,
        purpose: str | None = None,
        allowed_topics: tuple[str, ...] | None = None,
        restricted_topics: tuple[str, ...] | None = None,
        risks: tuple[ProfileRisk, ...] | None = None,
        safety_level: str | None = None,
        output_delivery: str | None = None,
    ) -> SafetyProfile:
        current = self.profile(profile_id)
        next_name = current.name if name is None else name.strip()
        next_purpose = current.purpose if purpose is None else purpose.strip()
        next_risks = current.risks if risks is None else risks
        next_level = current.safety_level if safety_level is None else safety_level
        next_delivery = current.output_delivery if output_delivery is None else output_delivery
        if not next_name:
            raise ValidationError("Safety Profile name is required.")
        self._validate_profile_fields(next_purpose, next_risks, next_level, next_delivery)
        with self._write_lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE safes
                SET name = ?, purpose = ?, allowed_topics_json = ?,
                    restricted_topics_json = ?, protections_json = ?, safety_level = ?,
                    output_delivery = ?, draft_version = draft_version + 1,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    next_name,
                    next_purpose,
                    _json(current.allowed_topics if allowed_topics is None else allowed_topics),
                    _json(
                        current.restricted_topics
                        if restricted_topics is None
                        else restricted_topics
                    ),
                    _risks_json(next_risks),
                    next_level,
                    next_delivery,
                    _now(),
                    profile_id,
                ),
            )
            self._insert_activity(
                connection,
                kind="profile.updated",
                outcome="success",
                profile_id=profile_id,
                detail=f"Updated safety intent for {next_name}; tests are now stale.",
            )
            connection.commit()
        return self.profile(profile_id)

    def compile_draft(self, profile_id: str) -> GuardrailPlanSnapshot:
        profile = self.profile(profile_id)
        return self._compiler.compile(profile, (profile.active_revision or 0) + 1)

    def activate_tested_version(self, profile_id: str) -> TestedProfileVersion:
        """Create the immutable deployable snapshot after a passing test run."""
        profile = self.profile(profile_id)
        latest = self.latest_evaluation(profile_id)
        if (
            latest is None
            or latest.source_draft_version != profile.draft_version
            or latest.status != "passed"
        ):
            raise ValidationError("Run and pass tests for the current changes first.")

        existing = next(
            (
                item
                for item in self.revisions(profile_id)
                if item.source_draft_version == profile.draft_version
            ),
            None,
        )
        if existing is not None:
            if latest.profile_revision != existing.revision:
                with self._write_lock, self._connect() as connection:
                    connection.execute(
                        "UPDATE test_runs SET safe_revision = ? WHERE id = ?",
                        (existing.revision, latest.id),
                    )
                    connection.commit()
            return TestedProfileVersion(profile, existing, self.plan(profile_id, existing.revision))

        next_revision = (profile.active_revision or 0) + 1
        plan = self._compiler.compile(profile, next_revision)
        checksum = self._compiler.checksum(plan)
        created_at = _now()
        with self._write_lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO safe_revisions
                    (safe_id, revision, source_draft_version, safe_json,
                     plan_json, compiler_version, plan_checksum, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile_id,
                    next_revision,
                    profile.draft_version,
                    _json(asdict(profile)),
                    _json(asdict(plan)),
                    plan.compiler_version,
                    checksum,
                    created_at,
                ),
            )
            connection.execute(
                "UPDATE safes SET active_revision = ?, updated_at = ? WHERE id = ?",
                (next_revision, created_at, profile_id),
            )
            connection.execute(
                "UPDATE test_runs SET safe_revision = ? WHERE id = ?",
                (next_revision, latest.id),
            )
            self._insert_activity(
                connection,
                kind="profile.tested",
                outcome="passed",
                profile_id=profile_id,
                detail=f"Tests passed; {profile.name} is ready to protect workloads.",
            )
            connection.commit()
        self._reload_runtime()
        revision = ProfileRevision(
            profile_id=profile_id,
            revision=next_revision,
            source_draft_version=profile.draft_version,
            compiler_version=plan.compiler_version,
            plan_checksum=checksum,
            created_at=created_at,
            active=True,
        )
        return TestedProfileVersion(self.profile(profile_id), revision, plan)

    def revisions(self, profile_id: str) -> tuple[ProfileRevision, ...]:
        profile = self.profile(profile_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT safe_id, revision, source_draft_version, compiler_version,
                    plan_checksum, created_at
                FROM safe_revisions WHERE safe_id = ? ORDER BY revision DESC
                """,
                (profile_id,),
            ).fetchall()
        return tuple(
            ProfileRevision(
                profile_id=str(row[0]),
                revision=int(row[1]),
                source_draft_version=int(row[2]),
                compiler_version=str(row[3]),
                plan_checksum=str(row[4]),
                created_at=str(row[5]),
                active=int(row[1]) == profile.active_revision,
            )
            for row in rows
        )

    def plan(self, profile_id: str, revision: int) -> GuardrailPlanSnapshot:
        plan = self._plans.get((profile_id, revision))
        if plan is not None:
            return plan
        with self._connect() as connection:
            row = connection.execute(
                "SELECT plan_json FROM safe_revisions WHERE safe_id = ? AND revision = ?",
                (profile_id, revision),
            ).fetchone()
        if row is None:
            raise NotFoundError("Tested Safety Profile version was not found.")
        return _plan_from_payload(json.loads(str(row[0])))

    # Test evidence

    def save_evaluation(
        self,
        *,
        profile_id: str,
        profile_revision: int | None,
        source_draft_version: int,
        status: str,
        metrics: EvaluationMetrics,
        results: tuple[EvaluationCaseResult, ...],
    ) -> EvaluationRun:
        run_id = f"test-{uuid.uuid4().hex[:12]}"
        created_at = _now()
        with self._write_lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO test_runs
                    (id, safe_id, safe_revision, source_draft_version,
                     status, metrics_json, results_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    profile_id,
                    profile_revision,
                    source_draft_version,
                    status,
                    _json(asdict(metrics)),
                    _json([asdict(item) for item in results]),
                    created_at,
                ),
            )
            self._insert_activity(
                connection,
                kind="profile.test.completed",
                outcome=status,
                profile_id=profile_id,
                detail=f"Safety tests completed with {metrics.compliance_rate:.1f}% compliance.",
            )
            connection.commit()
        return self.evaluation(run_id)

    def evaluations(self, profile_id: str | None = None) -> tuple[EvaluationRun, ...]:
        query = "SELECT * FROM test_runs"
        params: tuple[object, ...] = ()
        if profile_id:
            query += " WHERE safe_id = ?"
            params = (profile_id,)
        query += " ORDER BY created_at DESC, id DESC"
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return tuple(_evaluation_from_row(row) for row in rows)

    def evaluation(self, run_id: str) -> EvaluationRun:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM test_runs WHERE id = ?", (run_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError("Safety test run was not found.")
        return _evaluation_from_row(row)

    def latest_evaluation(self, profile_id: str) -> EvaluationRun | None:
        runs = self.evaluations(profile_id)
        return runs[0] if runs else None

    def test_cases(self, profile_id: str) -> tuple[ProfileTestCase, ...]:
        self.profile(profile_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM test_cases
                WHERE safe_id = ?
                ORDER BY CASE origin WHEN 'generated' THEN 0 ELSE 1 END,
                         name COLLATE NOCASE, id
                """,
                (profile_id,),
            ).fetchall()
        return tuple(_test_case_from_row(row) for row in rows)

    def sync_generated_test_cases(
        self,
        profile_id: str,
        cases: tuple[object, ...],
    ) -> tuple[ProfileTestCase, ...]:
        """Refresh generated cases while keeping reviewed custom cases intact."""
        profile = self.profile(profile_id)
        now = _now()
        with self._write_lock, self._connect() as connection:
            connection.execute(
                "DELETE FROM test_cases WHERE safe_id = ? AND origin = 'generated'",
                (profile_id,),
            )
            for case in cases:
                self._validate_test_case(
                    profile,
                    str(case.name),
                    str(case.risk),
                    str(case.phase),
                    str(case.content),
                    str(case.expected_decision),
                    str(getattr(case, "target_source", "user_input")),
                )
                connection.execute(
                    """
                    INSERT INTO test_cases
                        (id, safe_id, name, risk, phase, content,
                         trusted_instruction, target_source, expected_decision,
                         origin, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'generated', ?)
                    """,
                    (
                        str(case.id), profile_id, str(case.name), str(case.risk),
                        str(case.phase), str(case.content),
                        str(getattr(case, "trusted_instruction", "")),
                        str(getattr(case, "target_source", "user_input")),
                        str(case.expected_decision), now,
                    ),
                )
            connection.commit()
        return self.test_cases(profile_id)

    def create_test_case(
        self,
        profile_id: str,
        *,
        name: str,
        risk: str,
        phase: str,
        content: str,
        expected_decision: str,
        trusted_instruction: str = "",
        target_source: str = "user_input",
    ) -> ProfileTestCase:
        profile = self.profile(profile_id)
        self._validate_test_case(
            profile, name, risk, phase, content, expected_decision, target_source
        )
        case_id = f"case-{uuid.uuid4().hex[:12]}"
        now = _now()
        with self._write_lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO test_cases
                    (id, safe_id, name, risk, phase, content,
                     trusted_instruction, target_source, expected_decision,
                     origin, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'custom', ?)
                """,
                (
                    case_id, profile_id, name.strip(), risk, phase,
                    content.strip(), trusted_instruction.strip(), target_source,
                    expected_decision, now,
                ),
            )
            connection.execute(
                "UPDATE safes SET draft_version = draft_version + 1, updated_at = ? WHERE id = ?",
                (now, profile_id),
            )
            self._insert_activity(
                connection,
                kind="profile.test_case.created",
                outcome="success",
                profile_id=profile_id,
                risk=risk,
                detail=f"Added reviewed test case {name.strip()}.",
            )
            connection.commit()
        return next(item for item in self.test_cases(profile_id) if item.id == case_id)

    def delete_test_case(self, profile_id: str, case_id: str) -> None:
        self.profile(profile_id)
        with self._write_lock, self._connect() as connection:
            row = connection.execute(
                "SELECT name FROM test_cases WHERE safe_id = ? AND id = ?",
                (profile_id, case_id),
            ).fetchone()
            if row is None:
                raise NotFoundError("Safety test case was not found.")
            connection.execute(
                "DELETE FROM test_cases WHERE safe_id = ? AND id = ?",
                (profile_id, case_id),
            )
            connection.execute(
                "UPDATE safes SET draft_version = draft_version + 1, updated_at = ? WHERE id = ?",
                (_now(), profile_id),
            )
            self._insert_activity(
                connection,
                kind="profile.test_case.deleted",
                outcome="success",
                profile_id=profile_id,
                detail=f"Removed test case {str(row[0])}.",
            )
            connection.commit()

    # Workloads

    def workloads(self) -> tuple[ProtectedWorkload, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM workloads ORDER BY name COLLATE NOCASE, id"
            ).fetchall()
        return tuple(_workload_from_row(row) for row in rows)

    def workload(self, workload_id: str) -> ProtectedWorkload:
        item = next((item for item in self.workloads() if item.id == workload_id), None)
        if item is None:
            raise NotFoundError("Protected Workload was not found.")
        return item

    def create_workload(
        self,
        *,
        name: str,
        profile_id: str,
        filter: WorkloadFilterExpression,
        enabled: bool = True,
    ) -> ProtectedWorkload:
        profile = self.profile(profile_id)
        tested_current = any(
            item.source_draft_version == profile.draft_version
            for item in self.revisions(profile_id)
        )
        if profile.active_revision is None or not tested_current:
            raise ValidationError("Test the current Safety Profile before protecting a workload.")
        if not name.strip():
            raise ValidationError("Protected Workload name is required.")
        normalized = normalize_filter_expression(filter)
        signature = filter_expression_signature(normalized)
        duplicate = next(
            (
                item
                for item in self.workloads()
                if filter_expression_signature(item.filter) == signature
            ),
            None,
        )
        if duplicate is not None:
            raise ValidationError(
                f"This traffic filter is already assigned to {duplicate.name}."
            )

        workload_id = f"workload-{uuid.uuid4().hex[:12]}"
        now = _now()
        with self._write_lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO workloads
                    (id, name, safe_id, safe_revision, filter_json, enabled, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    workload_id,
                    name.strip(),
                    profile_id,
                    profile.active_revision,
                    _json(asdict(normalized)),
                    int(enabled),
                    now,
                ),
            )
            self._insert_activity(
                connection,
                kind="workload.protected",
                outcome="success",
                profile_id=profile_id,
                workload_id=workload_id,
                detail=f"Enabled protection for {name.strip()}.",
            )
            connection.commit()
        self._reload_runtime()
        return self.workload(workload_id)

    def set_workload_enabled(self, workload_id: str, enabled: bool) -> ProtectedWorkload:
        current = self.workload(workload_id)
        with self._write_lock, self._connect() as connection:
            connection.execute(
                "UPDATE workloads SET enabled = ?, updated_at = ? WHERE id = ?",
                (int(enabled), _now(), workload_id),
            )
            self._insert_activity(
                connection,
                kind="workload.updated",
                outcome="success",
                profile_id=current.profile_id,
                workload_id=workload_id,
                detail=f"Protection {'enabled' if enabled else 'paused'} for {current.name}.",
            )
            connection.commit()
        self._reload_runtime()
        return self.workload(workload_id)

    # Runtime resolution

    def resolve(self, context: RequestContext) -> PlanResolution:
        gateway = self.gateway(context.gateway_id) if context.gateway_id else None
        candidates = [
            item
            for item in self._workloads
            if item.enabled
            and filter_expression_matches(item.filter, context)
            and (item.profile_id, item.profile_revision) in self._plans
        ]
        if not candidates:
            raise ControlPlaneError("No Protected Workload matches this model interaction.")
        ranked = sorted(
            candidates,
            key=lambda item: tuple(-value for value in filter_expression_specificity(item.filter)) + (item.id,),
        )
        selected = ranked[0]
        top_specificity = filter_expression_specificity(selected.filter)
        equally_specific = [
            item
            for item in ranked
            if filter_expression_specificity(item.filter) == top_specificity
        ]
        if len(equally_specific) > 1:
            raise ControlPlaneError(
                "Multiple equally specific Workload filters match this model interaction."
            )
        plan = self._plans[(selected.profile_id, selected.profile_revision)]
        trace = []
        if gateway is not None:
            trace.append(_resolution_step("adapter", gateway.name, gateway.id))
        else:
            trace.append(
                _resolution_step(
                    "runtime",
                    "Local TaskLattice runtime",
                    "Resolved without an external Gateway Adapter.",
                )
            )
        trace.extend((
            _resolution_step(
                "workload",
                selected.name,
                f"Matched {len(candidates)} Workload expression(s); selected "
                f"{filter_rule_count(selected.filter)} rule(s) by specificity.",
            ),
            _resolution_step(
                "profile",
                self.profile(selected.profile_id).name,
                "Pinned the last tested Safety Profile version for this model call.",
            ),
        ))
        return PlanResolution(
            plan=plan,
            workload_id=selected.id,
            gateway_id=gateway.id if gateway else None,
            trace=tuple(trace),
        )

    # Gateways

    def gateways(self) -> tuple[Gateway, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT a.*,
                       COALESCE((SELECT secret_prefix FROM adapter_credentials c
                                 WHERE c.adapter_instance_id = a.id AND c.revoked_at IS NULL
                                 ORDER BY c.created_at DESC LIMIT 1), '') AS credential_prefix
                FROM adapter_instances a ORDER BY a.name COLLATE NOCASE, a.id
                """
            ).fetchall()
        return tuple(self._gateway_from_row(row) for row in rows)

    def gateway(self, gateway_id: str) -> Gateway:
        item = next((item for item in self.gateways() if item.id == gateway_id), None)
        if item is None:
            raise NotFoundError("Gateway was not found.")
        return item

    def create_gateway(
        self,
        *,
        name: str,
        description: str,
        environment: str,
        protocol: str = "litellm",
    ) -> GatewayRegistration:
        if not name.strip():
            raise ValidationError("Gateway name is required.")
        if environment not in {"production", "staging", "development", "test"}:
            raise ValidationError("Unsupported Gateway environment.")
        if protocol not in {"litellm", "http", "a2a"}:
            raise ValidationError("Unsupported Integration protocol.")
        gateway_id = f"gateway-{uuid.uuid4().hex[:12]}"
        credential = _new_credential()
        now = _now()
        with self._write_lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO adapter_instances
                    (id, type_key, name, description, environment, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (gateway_id, protocol, name.strip(), description.strip(), environment, now, now),
            )
            self._insert_credential(connection, gateway_id, credential, "generated")
            self._insert_activity(
                connection,
                kind="gateway.registered",
                outcome="success",
                detail=f"Registered {protocol.upper()} Integration {name.strip()}.",
            )
            connection.commit()
        self._reload_runtime()
        return GatewayRegistration(self.gateway(gateway_id), credential)

    def authenticate_gateway(self, credential: str | None, protocol: str) -> Gateway:
        if not credential:
            raise GatewayAuthenticationError("Gateway credential is required.")
        gateway_id = self._credential_index.get(_hash(credential))
        if not gateway_id:
            raise GatewayAuthenticationError("Gateway credential is invalid.")
        gateway = self.gateway(gateway_id)
        if not gateway.enabled or gateway.protocol != protocol:
            raise GatewayAuthenticationError("Gateway credential is invalid.")
        return gateway

    def record_gateway_activity(self, gateway_id: str, *, success: bool) -> None:
        with self._runtime_lock:
            item = self._gateway_runtime.setdefault(
                gateway_id,
                {"last_seen_at": None, "request_count": 0, "error_count": 0},
            )
            item["last_seen_at"] = _now()
            item["request_count"] = int(item["request_count"]) + 1
            if not success:
                item["error_count"] = int(item["error_count"]) + 1

    # Evidence and system summary

    def activities(self, limit: int = 100) -> tuple[DecisionEvent, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM evidence_events ORDER BY created_at DESC, id DESC LIMIT ?",
                (max(1, min(limit, 500)),),
            ).fetchall()
        return tuple(
            DecisionEvent(
                id=str(row[0]),
                created_at=str(row[1]),
                kind=str(row[2]),
                outcome=str(row[3]),
                profile_id=str(row[4]) if row[4] else None,
                workload_id=str(row[5]) if row[5] else None,
                risk=str(row[6]) if row[6] else None,
                detail=str(row[7]),
            )
            for row in rows
        )

    def record_decision(
        self,
        *,
        outcome: str,
        profile_id: str | None,
        workload_id: str | None,
        risk: str | None,
        detail: str,
    ) -> None:
        with self._write_lock, self._connect() as connection:
            self._insert_activity(
                connection,
                kind="interaction.decision",
                outcome=outcome,
                profile_id=profile_id,
                workload_id=workload_id,
                risk=risk,
                detail=detail,
            )
            connection.commit()

    def summary(self) -> dict[str, object]:
        gateways = self.gateways()
        active = [item for item in self._workloads if item.enabled]
        degraded = any(item.runtime_status == "degraded" for item in gateways)
        return {
            "status": "degraded" if degraded else "healthy",
            "active_workloads": len(active),
            "online_gateways": len(
                [item for item in gateways if item.runtime_status in {"healthy", "waiting"}]
            ),
            "total_gateways": len(gateways),
            "capabilities": {
                "deterministic": True,
                "fast_semantic": self._fast_semantic_configured,
                "deep_judge": self._deep_judge_configured,
            },
        }

    # Persistence internals

    def _initialize(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            has_meta = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='control_plane_meta'"
            ).fetchone()
            if not has_meta:
                self._create_schema(connection)
                self._seed(connection)
            else:
                row = connection.execute(
                    "SELECT value FROM control_plane_meta WHERE key='schema_version'"
                ).fetchone()
                version = str(row[0]) if row else ""
                if version == LEGACY_SCHEMA_VERSION:
                    self._migrate_v9_to_v10(connection)
                elif version != SCHEMA_VERSION:
                    raise ControlPlaneError(
                        "This database does not use the TaskLattice Guard v10 schema."
                    )
            connection.commit()
        self._reload_runtime()

    @staticmethod
    def _create_schema(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE control_plane_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE safes (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                purpose TEXT NOT NULL,
                allowed_topics_json TEXT NOT NULL,
                restricted_topics_json TEXT NOT NULL,
                protections_json TEXT NOT NULL,
                safety_level TEXT NOT NULL,
                output_delivery TEXT NOT NULL,
                source_template_id TEXT,
                template_parameters_json TEXT NOT NULL,
                draft_version INTEGER NOT NULL,
                active_revision INTEGER,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE safe_revisions (
                safe_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                source_draft_version INTEGER NOT NULL,
                safe_json TEXT NOT NULL,
                plan_json TEXT NOT NULL,
                compiler_version TEXT NOT NULL,
                plan_checksum TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (safe_id, revision),
                FOREIGN KEY (safe_id) REFERENCES safes(id) ON DELETE CASCADE
            );
            CREATE TABLE adapter_instances (
                id TEXT PRIMARY KEY,
                type_key TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                environment TEXT NOT NULL,
                enabled INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE adapter_credentials (
                id TEXT PRIMARY KEY,
                adapter_instance_id TEXT NOT NULL,
                secret_hash TEXT NOT NULL UNIQUE,
                secret_prefix TEXT NOT NULL,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL,
                revoked_at TEXT,
                FOREIGN KEY (adapter_instance_id) REFERENCES adapter_instances(id) ON DELETE CASCADE
            );
            CREATE TABLE workloads (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                safe_id TEXT NOT NULL,
                safe_revision INTEGER NOT NULL,
                filter_json TEXT NOT NULL,
                enabled INTEGER NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (safe_id, safe_revision)
                    REFERENCES safe_revisions(safe_id, revision)
            );
            CREATE TABLE test_runs (
                id TEXT PRIMARY KEY,
                safe_id TEXT NOT NULL,
                safe_revision INTEGER,
                source_draft_version INTEGER NOT NULL,
                status TEXT NOT NULL,
                metrics_json TEXT NOT NULL,
                results_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (safe_id) REFERENCES safes(id) ON DELETE CASCADE
            );
            CREATE TABLE test_cases (
                id TEXT NOT NULL,
                safe_id TEXT NOT NULL,
                name TEXT NOT NULL,
                risk TEXT NOT NULL,
                phase TEXT NOT NULL,
                content TEXT NOT NULL,
                trusted_instruction TEXT NOT NULL DEFAULT '',
                target_source TEXT NOT NULL DEFAULT 'user_input',
                expected_decision TEXT NOT NULL,
                origin TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (safe_id, id),
                FOREIGN KEY (safe_id) REFERENCES safes(id) ON DELETE CASCADE
            );
            CREATE TABLE evidence_events (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                kind TEXT NOT NULL,
                outcome TEXT NOT NULL,
                safe_id TEXT,
                workload_id TEXT,
                risk TEXT,
                detail TEXT NOT NULL
            );
            CREATE TABLE users (
                id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                email TEXT NOT NULL COLLATE NOCASE UNIQUE,
                role TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                enabled INTEGER NOT NULL,
                preferred_language TEXT NOT NULL DEFAULT 'en',
                last_login_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE user_sessions (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            """
        )
        connection.execute(
            "INSERT INTO control_plane_meta (key, value) VALUES ('schema_version', ?)",
            (SCHEMA_VERSION,),
        )

    @staticmethod
    def _migrate_v9_to_v10(connection: sqlite3.Connection) -> None:
        """Replace flat Workload rules with the recursive Filter Expression schema."""
        connection.executescript(
            """
            DROP TABLE workloads;
            CREATE TABLE workloads (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                safe_id TEXT NOT NULL,
                safe_revision INTEGER NOT NULL,
                filter_json TEXT NOT NULL,
                enabled INTEGER NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (safe_id, safe_revision)
                    REFERENCES safe_revisions(safe_id, revision)
            );
            """
        )
        connection.execute(
            "UPDATE control_plane_meta SET value = ? WHERE key = 'schema_version'",
            (SCHEMA_VERSION,),
        )

    def _seed(self, connection: sqlite3.Connection) -> None:
        self._insert_activity(
            connection,
            kind="system.seeded",
            outcome="success",
            detail="Initialized the standalone TaskLattice control plane.",
        )

    @staticmethod
    def _insert_credential(
        connection: sqlite3.Connection,
        gateway_id: str,
        credential: str,
        source: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO adapter_credentials
                (id, adapter_instance_id, secret_hash, secret_prefix, source, created_at, revoked_at)
            VALUES (?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                f"credential-{uuid.uuid4().hex[:12]}",
                gateway_id,
                _hash(credential),
                credential[:8] + "…",
                source,
                _now(),
            ),
        )

    @staticmethod
    def _insert_activity(
        connection: sqlite3.Connection,
        *,
        kind: str,
        outcome: str,
        detail: str,
        profile_id: str | None = None,
        workload_id: str | None = None,
        risk: str | None = None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO evidence_events
                (id, created_at, kind, outcome, safe_id, workload_id, risk, detail)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"evidence-{uuid.uuid4().hex[:12]}",
                _now(),
                kind,
                outcome,
                profile_id,
                workload_id,
                risk,
                detail,
            ),
        )

    def _reload_runtime(self) -> None:
        plans: dict[tuple[str, int], GuardrailPlanSnapshot] = {}
        credentials: dict[str, str] = {}
        with self._connect() as connection:
            for row in connection.execute(
                "SELECT safe_id, revision, plan_json FROM safe_revisions"
            ).fetchall():
                plans[(str(row[0]), int(row[1]))] = _plan_from_payload(
                    json.loads(str(row[2]))
                )
            for row in connection.execute(
                "SELECT secret_hash, adapter_instance_id FROM adapter_credentials WHERE revoked_at IS NULL"
            ).fetchall():
                credentials[str(row[0])] = str(row[1])
        self._plans = plans
        self._workloads = self.workloads()
        self._credential_index = credentials

    def _gateway_from_row(self, row: sqlite3.Row) -> Gateway:
        with self._runtime_lock:
            runtime = self._gateway_runtime.get(str(row["id"]), {})
        last_seen = runtime.get("last_seen_at")
        requests = int(runtime.get("request_count", 0))
        errors = int(runtime.get("error_count", 0))
        enabled = bool(row["enabled"])
        return Gateway(
            id=str(row["id"]),
            protocol=str(row["type_key"]),
            name=str(row["name"]),
            description=str(row["description"]),
            environment=str(row["environment"]),
            enabled=enabled,
            credential_prefix=str(row["credential_prefix"]),
            verification_status="verified" if last_seen else "waiting",
            runtime_status=(
                "disabled"
                if not enabled
                else "degraded"
                if errors
                else "healthy"
                if last_seen
                else "waiting"
            ),
            last_seen_at=str(last_seen) if last_seen else None,
            request_count=requests,
            error_count=errors,
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _validate_profile_fields(
        purpose: str,
        risks: tuple[ProfileRisk, ...],
        safety_level: str,
        output_delivery: str,
    ) -> None:
        if not purpose.strip():
            raise ValidationError("Describe what this AI is allowed to do.")
        if safety_level not in {"balanced", "strict"}:
            raise ValidationError("Enforcement mode must be balanced or strict.")
        if output_delivery not in {"interruptible", "window_buffered", "full_buffered"}:
            raise ValidationError("Unsupported output delivery mode.")
        known = {item.id: item for item in PROTECTIONS}
        if not risks:
            raise ValidationError("Select at least one risk to protect.")
        if len({item.risk for item in risks}) != len(risks):
            raise ValidationError("A risk may only be configured once.")
        for risk in risks:
            definition = known.get(risk.risk)
            if definition is None:
                raise ValidationError(f"Unknown risk {risk.risk!r}.")
            if risk.action not in definition.allowed_actions:
                raise ValidationError(f"Unsupported action for {risk.risk}.")

    @staticmethod
    def _validate_test_case(
        profile: SafetyProfile,
        name: str,
        risk: str,
        phase: str,
        content: str,
        expected_decision: str,
        target_source: str = "user_input",
    ) -> None:
        if not name.strip() or not content.strip():
            raise ValidationError("Test case name and model content are required.")
        if risk not in {item.risk for item in profile.risks}:
            raise ValidationError("Test case risk must be enabled in this Safety Profile.")
        if phase not in {"input", "output"}:
            raise ValidationError("Test case phase must be input or output.")
        if expected_decision not in {"allow", "block", "transform", "intervene"}:
            raise ValidationError("Unsupported expected test decision.")
        if target_source not in {"user_input", "retrieved_content", "tool_output"}:
            raise ValidationError("Unsupported test target source.")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection


def _profile_from_row(row: sqlite3.Row) -> SafetyProfile:
    raw_risks = json.loads(str(row["protections_json"]))
    return SafetyProfile(
        id=str(row["id"]),
        name=str(row["name"]),
        purpose=str(row["purpose"]),
        allowed_topics=tuple(json.loads(str(row["allowed_topics_json"]))),
        restricted_topics=tuple(json.loads(str(row["restricted_topics_json"]))),
        risks=tuple(ProfileRisk(str(item["risk"]), str(item["action"])) for item in raw_risks),
        safety_level=str(row["safety_level"]),
        output_delivery=str(row["output_delivery"]),
        source_template_id=(
            str(row["source_template_id"]) if row["source_template_id"] else None
        ),
        template_parameters=tuple(
            sorted(json.loads(str(row["template_parameters_json"])).items())
        ),
        draft_version=int(row["draft_version"]),
        active_revision=(
            int(row["active_revision"]) if row["active_revision"] is not None else None
        ),
        updated_at=str(row["updated_at"]),
    )


def _plan_from_payload(payload: dict[str, object]) -> GuardrailPlanSnapshot:
    return GuardrailPlanSnapshot(
        profile_id=str(payload["profile_id"]),
        profile_revision=int(payload["profile_revision"]),
        compiler_version=str(payload["compiler_version"]),
        safety_level=str(payload["safety_level"]),
        output_delivery=str(payload["output_delivery"]),
        steps=tuple(GuardrailPlanStep(**item) for item in payload["steps"]),
    )


def _workload_from_row(row: sqlite3.Row) -> ProtectedWorkload:
    return ProtectedWorkload(
        id=str(row["id"]),
        name=str(row["name"]),
        profile_id=str(row["safe_id"]),
        profile_revision=int(row["safe_revision"]),
        filter=filter_expression_from_payload(
            json.loads(str(row["filter_json"]))
        ),
        enabled=bool(row["enabled"]),
        updated_at=str(row["updated_at"]),
    )


def _evaluation_from_row(row: sqlite3.Row) -> EvaluationRun:
    return EvaluationRun(
        id=str(row["id"]),
        profile_id=str(row["safe_id"]),
        profile_revision=(
            int(row["safe_revision"]) if row["safe_revision"] is not None else None
        ),
        source_draft_version=int(row["source_draft_version"]),
        status=str(row["status"]),
        metrics=EvaluationMetrics(**json.loads(str(row["metrics_json"]))),
        results=tuple(
            _evaluation_result_from_payload(item)
            for item in json.loads(str(row["results_json"]))
        ),
        created_at=str(row["created_at"]),
    )


def _evaluation_result_from_payload(payload: dict[str, object]) -> EvaluationCaseResult:
    """Load both current evidence and older result rows without hiding the run."""
    values = dict(payload)
    values.setdefault("phase", "input")
    values.setdefault("input_content", "")
    values.setdefault(
        "action",
        {"allow": "pass", "block": "reject"}.get(
            str(values.get("actual_decision", "")), ""
        ),
    )
    values.setdefault("output_content", "")
    values.setdefault("trusted_instruction", "")
    values.setdefault("target_source", "user_input")
    values["findings"] = tuple(values.get("findings") or ())
    values["trace"] = tuple(values.get("trace") or ())
    return EvaluationCaseResult(**values)


def _test_case_from_row(row: sqlite3.Row) -> ProfileTestCase:
    return ProfileTestCase(
        id=str(row["id"]),
        profile_id=str(row["safe_id"]),
        name=str(row["name"]),
        risk=str(row["risk"]),
        phase=str(row["phase"]),
        content=str(row["content"]),
        expected_decision=str(row["expected_decision"]),
        origin=str(row["origin"]),
        updated_at=str(row["updated_at"]),
        trusted_instruction=str(row["trusted_instruction"]),
        target_source=str(row["target_source"]),
    )


def _resolution_step(kind: str, name: str, detail: str):
    from ..engine.contracts import EvaluationTraceStep

    return EvaluationTraceStep(
        id=f"resolution:{kind}", kind=kind, name=name, status="selected", detail=detail
    )


def _risks_json(risks: tuple[ProfileRisk, ...]) -> str:
    return _json([asdict(item) for item in risks])


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _new_credential() -> str:
    return "tali_gate_" + secrets.token_urlsafe(30)


def _now() -> str:
    return datetime.now(UTC).isoformat()
