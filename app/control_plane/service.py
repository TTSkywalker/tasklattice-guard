from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
import threading
import uuid
from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

from ..runtime.contracts import (
    AutomatedReasoningPolicySnapshot,
    EvaluationTraceStep,
    GuardrailPlanModule,
    GuardrailPlanSnapshot,
    GuardrailPlanStep,
    NeMoActionBinding,
    NeMoConfigSnapshot,
    PlanResolution,
    RequestContext,
    ControlActionReferenceSnapshot,
    ControlRailBindingSnapshot,
    ControlSourceSnapshot,
    ControlVersionSnapshot,
    GuardrailControlBindingSnapshot,
)
from ..nemo.action_registry import (
    ActionCatalog,
    BUILTIN_ACTION_CATALOG,
    action_name_for,
)
from ..control_library import (
    control as library_control,
    control_pack,
    control_packs as library_control_packs,
    controls as library_controls,
)
from ..integrations import adapter_definition
from .catalog import CONTROL_DEFINITIONS, control
from .compiler import GuardrailCompiler
from .nemo_compiler import NeMoConfigCompiler
from .defaults import (
    DEFAULT_GUARDRAIL_ID,
    DEFAULT_GUARDRAIL_NAME,
    DEFAULT_GUARDRAIL_PURPOSE,
    DEFAULT_GUARDRAIL_VERSION,
    DEFAULT_GUARDRAIL_PACK_ID,
    DEFAULT_ASSIGNMENT_ID,
    DEFAULT_ASSIGNMENT_NAME,
    is_default_guardrail,
    is_default_assignment,
)
from .domain import (
    AutomatedReasoningPolicyBinding,
    ConflictError,
    ControlPlaneError,
    DecisionEvent,
    EvaluationCaseResult,
    EvaluationMetrics,
    EvaluationRun,
    Integration,
    IntegrationAuthenticationError,
    IntegrationCredential,
    IntegrationCredentialSecret,
    IntegrationRegistration,
    NotFoundError,
    RuntimeMetricEvent,
    RuntimeStepMetricEvent,
    GuardrailVersion,
    GuardrailControl,
    GuardrailControlConfig,
    GuardrailRuleConfig,
    GuardrailTestCase,
    GuardrailAssignment,
    EvaluationCase,
    TrafficScopeExpression,
    Guardrail,
    TestedGuardrailVersion,
    ValidationError,
    ActionReference,
    ControlDraft,
    ControlPackage,
    ControlParameterDefinition,
    ControlSourceFile,
    ControlTestDefinition,
    ControlVersion,
    GuardrailControlBinding,
    RailBinding,
)
from .filtering import (
    traffic_scope_from_payload,
    traffic_scope_matches,
    traffic_scope_signature,
    traffic_scope_specificity,
    traffic_scope_rule_count,
    normalize_traffic_scope,
)


SCHEMA_VERSION = "tasklattice-guard-schema-v5"


class ControlPlaneService:
    """Persist Guardrail intent, tested versions, and Assignment state."""

    def __init__(
        self,
        database_path: Path,
        *,
        public_runtime_base_url: str = "http://localhost:8091",
        fast_semantic_configured: bool = False,
        deep_judge_configured: bool = False,
        automated_reasoning_configured: bool = False,
        nemo_compiler: NeMoConfigCompiler | None = None,
        action_catalog: ActionCatalog | None = None,
        runtime_p95_budget_ms: int = 2_500,
        runtime_p99_budget_ms: int = 5_000,
    ) -> None:
        self._database_path = database_path
        self._public_runtime_base_url = public_runtime_base_url.rstrip("/")
        self._fast_semantic_configured = fast_semantic_configured
        self._deep_judge_configured = deep_judge_configured
        self._automated_reasoning_configured = automated_reasoning_configured
        self._compiler = GuardrailCompiler(
            deep_judge_configured=deep_judge_configured,
        )
        self._nemo_compiler = nemo_compiler or NeMoConfigCompiler()
        self._action_catalog = action_catalog or BUILTIN_ACTION_CATALOG
        self._runtime_p95_budget_ms = runtime_p95_budget_ms
        self._runtime_p99_budget_ms = runtime_p99_budget_ms
        self._nemo_runtime_validator: (
            Callable[[GuardrailPlanSnapshot, NeMoConfigSnapshot], None] | None
        ) = None
        self._nemo_runtime_reloader: Callable[[], None] | None = None
        self._write_lock = threading.Lock()
        self._plans: dict[tuple[str, int], GuardrailPlanSnapshot] = {}
        self._nemo_configs: dict[tuple[str, int], NeMoConfigSnapshot] = {}
        self._assignments: tuple[GuardrailAssignment, ...] = ()
        self._credential_index: dict[str, str] = {}
        self._initialize()

    # Creation resources. These support the Guardrail workflow but are not
    # first-class navigation objects.

    def control_packs(self):
        return library_control_packs()

    def library_controls(self):
        return library_controls()

    def control_definitions(self):
        return CONTROL_DEFINITIONS

    def actions(self):
        return self._action_catalog.definitions()

    # Native Control packages

    def controls(self) -> tuple[ControlPackage, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM control_packages ORDER BY name COLLATE NOCASE, id"
            ).fetchall()
        return tuple(_control_package_from_row(row) for row in rows)

    def control_package(self, control_id: str) -> ControlPackage:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM control_packages WHERE id = ?", (control_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError(f"Control {control_id!r} was not found.")
        return _control_package_from_row(row)

    def create_control(
        self,
        *,
        name: str,
        description: str,
        owner: str,
        draft: ControlDraft,
        source: str = "custom",
    ) -> ControlPackage:
        clean_name = name.strip()
        if not clean_name:
            raise ValidationError("Control name is required.")
        if source not in {"built-in", "custom"}:
            raise ValidationError("Control source must be built-in or custom.")
        control_id = f"control-{uuid.uuid4().hex[:12]}"
        now = _now()
        self._validate_control_draft(control_id, draft, validate_dependencies=False)
        with self._write_lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO control_packages
                    (id, name, description, source, owner, draft_json,
                     draft_revision, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    control_id,
                    clean_name,
                    description.strip(),
                    source,
                    owner.strip() or "unknown",
                    _json(asdict(draft)),
                    now,
                ),
            )
            self._insert_activity(
                connection,
                kind="control.created",
                outcome="success",
                detail=f"Created Control {clean_name}.",
            )
            connection.commit()
        return self.control_package(control_id)

    def update_control_draft(
        self,
        control_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        owner: str | None = None,
        draft: ControlDraft | None = None,
    ) -> ControlPackage:
        current = self.control_package(control_id)
        next_draft = current.draft if draft is None else draft
        if current.source == "built-in":
            raise ValidationError("Built-in Controls are system managed.")
        self._validate_control_draft(
            control_id, next_draft, validate_dependencies=False
        )
        next_name = current.name if name is None else name.strip()
        if not next_name:
            raise ValidationError("Control name is required.")
        with self._write_lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE control_packages
                SET name = ?, description = ?, owner = ?, draft_json = ?,
                    draft_revision = draft_revision + 1, updated_at = ?
                WHERE id = ?
                """,
                (
                    next_name,
                    current.description if description is None else description.strip(),
                    current.owner if owner is None else owner.strip() or "unknown",
                    _json(asdict(next_draft)),
                    _now(),
                    control_id,
                ),
            )
            connection.commit()
        return self.control_package(control_id)

    def validate_control(self, control_id: str) -> dict[str, object]:
        package = self.control_package(control_id)
        self._validate_control_draft(
            control_id, package.draft, validate_dependencies=True
        )
        self._nemo_compiler.validate_control(control_id, package.draft)
        return {
            "valid": True,
            "control_id": control_id,
            "draft_revision": package.draft_revision,
            "colang_version": package.draft.colang_version,
            "rails": tuple(item.rail_type for item in package.draft.rail_bindings),
        }

    def publish_control(self, control_id: str) -> ControlVersion:
        package = self.control_package(control_id)
        self.validate_control(control_id)
        if package.source == "custom" and package.draft.tests:
            latest = self.latest_control_test_run(control_id)
            if (
                latest is None
                or int(latest["draft_revision"]) != package.draft_revision
                or latest["status"] != "passed"
            ):
                raise ValidationError(
                    "The current Control draft must pass Evaluation before publishing."
                )
        versions = self.control_versions(control_id)
        version_number = max((item.version for item in versions), default=0) + 1
        published_at = _now()
        version_payload = {
            "control_id": package.id,
            "version": version_number,
            "name": package.name,
            "description": package.description,
            "source": package.source,
            "owner": package.owner,
            **asdict(package.draft),
            "published_at": published_at,
        }
        checksum = hashlib.sha256(
            json.dumps(version_payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        with self._write_lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO control_versions
                    (control_id, version, version_json, checksum, published_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    control_id,
                    version_number,
                    _json(version_payload),
                    checksum,
                    published_at,
                ),
            )
            self._insert_activity(
                connection,
                kind="control.version.published",
                outcome="success",
                detail=f"Published Control {package.name} version {version_number}.",
            )
            connection.commit()
        return self.control_version(control_id, version_number)

    def compile_control_draft(
        self, control_id: str
    ) -> tuple[GuardrailPlanSnapshot, NeMoConfigSnapshot]:
        """Compile one draft through the production NeMo compiler for Evaluation."""
        package = self.control_package(control_id)
        self.validate_control(control_id)
        revision = package.draft_revision
        draft = package.draft
        checksum_payload = {
            "control_id": package.id,
            "draft_revision": revision,
            **asdict(draft),
        }
        checksum = hashlib.sha256(
            json.dumps(
                checksum_payload, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        candidate = ControlVersion(
            control_id=package.id,
            version=revision,
            name=package.name,
            description=package.description,
            source=package.source,
            owner=package.owner,
            colang_version=draft.colang_version,
            sources=draft.sources,
            parameter_schema=draft.parameter_schema,
            rail_bindings=draft.rail_bindings,
            action_references=draft.action_references,
            model_dependencies=draft.model_dependencies,
            prompt_dependencies=draft.prompt_dependencies,
            execution_contract=draft.execution_contract,
            tests=draft.tests,
            checksum=checksum,
            published_at="",
        )
        binding = GuardrailControlBindingSnapshot(
            control_id=package.id,
            control_version=revision,
            parameter_values=tuple(
                sorted(
                    (item.name, item.default)
                    for item in draft.parameter_schema
                    if item.default is not None
                )
            ),
            enabled_rails=tuple(
                dict.fromkeys(item.rail_type for item in draft.rail_bindings)
            ),
        )
        guardrail = Guardrail(
            id=f"control-preview-{package.id}",
            name=package.name,
            purpose=package.description or f"Evaluate {package.name}.",
            allowed_topics=(),
            restricted_topics=(),
            controls=(),
            safety_level="balanced",
            output_delivery="window_buffered",
            source_pack_id=None,
            parameters=(),
            draft_version=revision,
            active_version=None,
            updated_at=package.updated_at,
            control_bindings=(
                GuardrailControlBinding(
                    control_id=package.id,
                    control_version=revision,
                    enabled_rails=binding.enabled_rails,
                ),
            ),
        )
        plan = self._compiler.compile(
            guardrail,
            revision,
            control_versions=(_control_version_snapshot(candidate),),
            control_bindings=(binding,),
        )
        config = self._nemo_compiler.compile(plan)
        self._nemo_configs[(plan.guardrail_id, plan.guardrail_version)] = config
        return plan, config

    def save_control_test_run(
        self,
        *,
        control_id: str,
        draft_revision: int,
        status: str,
        results: tuple[dict[str, object], ...],
    ) -> dict[str, object]:
        run_id = f"control-test-{uuid.uuid4().hex[:12]}"
        created_at = _now()
        with self._write_lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO control_test_runs
                    (id, control_id, draft_revision, status, results_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    control_id,
                    draft_revision,
                    status,
                    _json(results),
                    created_at,
                ),
            )
            connection.commit()
        return {
            "id": run_id,
            "control_id": control_id,
            "draft_revision": draft_revision,
            "status": status,
            "results": list(results),
            "created_at": created_at,
        }

    def latest_control_test_run(
        self, control_id: str
    ) -> dict[str, object] | None:
        self.control_package(control_id)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM control_test_runs WHERE control_id = ? "
                "ORDER BY created_at DESC, id DESC LIMIT 1",
                (control_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": str(row["id"]),
            "control_id": str(row["control_id"]),
            "draft_revision": int(row["draft_revision"]),
            "status": str(row["status"]),
            "results": json.loads(str(row["results_json"])),
            "created_at": str(row["created_at"]),
        }

    def control_versions(self, control_id: str) -> tuple[ControlVersion, ...]:
        self.control_package(control_id)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM control_versions WHERE control_id = ? "
                "ORDER BY version DESC",
                (control_id,),
            ).fetchall()
        return tuple(_control_version_from_row(row) for row in rows)

    def control_version(self, control_id: str, version: int) -> ControlVersion:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM control_versions WHERE control_id = ? AND version = ?",
                (control_id, version),
            ).fetchone()
        if row is None:
            raise NotFoundError(
                f"Control Version {control_id}@{version} was not found."
            )
        return _control_version_from_row(row)

    # Guardrails

    def guardrails(self) -> tuple[Guardrail, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM guardrails ORDER BY name COLLATE NOCASE, id"
            ).fetchall()
        return tuple(_guardrail_from_row(row) for row in rows)

    def guardrail(self, guardrail_id: str) -> Guardrail:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM guardrails WHERE id = ?", (guardrail_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError(f"Guardrail {guardrail_id!r} was not found.")
        return _guardrail_from_row(row)

    def create_guardrail(
        self,
        *,
        name: str,
        purpose: str | None = None,
        pack_id: str | None = None,
        allowed_topics: tuple[str, ...] = (),
        restricted_topics: tuple[str, ...] = (),
        controls: tuple[GuardrailControl, ...] = (),
        control_configurations: tuple[GuardrailControlConfig, ...] = (),
        control_bindings: tuple[GuardrailControlBinding, ...] = (),
        parameters: tuple[tuple[str, str], ...] = (),
        safety_level: str = "balanced",
        output_delivery: str = "window_buffered",
    ) -> Guardrail:
        clean_name = name.strip()
        if not clean_name:
            raise ValidationError("Guardrail name is required.")
        parameters = tuple(
            sorted(
                (key.strip(), value.strip())
                for key, value in parameters
                if key.strip() and value.strip()
            )
        )
        if pack_id:
            if control_configurations:
                raise ValidationError(
                    "A Guardrail cannot combine a Control Pack with explicit "
                    "Control configurations."
                )
            pack = control_pack(pack_id)
            if pack is None:
                raise ValidationError("Unknown Control Pack.")
            purpose = purpose.strip() if purpose and purpose.strip() else pack.description
            if not any(
                item.risk == "builtin_content_filter" for item in controls
            ):
                controls = (
                    *controls,
                    GuardrailControl("builtin_content_filter", "reject"),
                )
            safety_level = pack.safety_level
            output_delivery = pack.output_delivery
            supplied = dict(parameters)
            supported_parameters = {item.name for item in pack.parameters}
            unknown = sorted(set(supplied).difference(supported_parameters))
            if unknown:
                raise ValidationError(
                    "Unknown Control Pack parameters: " + ", ".join(unknown) + "."
                )
            missing = [
                item.label
                for item in pack.parameters
                if item.required and not supplied.get(item.name, "").strip()
            ]
            if missing:
                raise ValidationError(f"Control Pack requires: {', '.join(missing)}.")
        control_bindings = _native_control_bindings(controls, control_bindings)
        self._validate_guardrail_fields(
            purpose or "",
            controls,
            safety_level,
            output_delivery,
            control_configurations,
            control_bindings,
        )
        self._validate_guardrail_control_bindings(control_bindings)
        guardrail_id = f"guardrail-{uuid.uuid4().hex[:12]}"
        now = _now()
        with self._write_lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO guardrails
                    (id, name, purpose, allowed_topics_json, restricted_topics_json,
                     controls_json, safety_level, output_delivery, source_pack_id,
                     parameters_json, control_configurations_json,
                     control_bindings_json,
                     draft_version, active_version, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, NULL, ?)
                """,
                (
                    guardrail_id,
                    clean_name,
                    (purpose or "").strip(),
                    _json(allowed_topics),
                    _json(restricted_topics),
                    _controls_json(controls),
                    safety_level,
                    output_delivery,
                    pack_id,
                    _json(dict(parameters)),
                    _control_configurations_json(control_configurations),
                    _json([asdict(item) for item in control_bindings]),
                    now,
                ),
            )
            self._insert_activity(
                connection,
                kind="guardrail.created",
                outcome="success",
                guardrail_id=guardrail_id,
                detail=f"Created Guardrail {clean_name}.",
            )
            connection.commit()
        return self.guardrail(guardrail_id)

    def update_guardrail(
        self,
        guardrail_id: str,
        *,
        name: str | None = None,
        purpose: str | None = None,
        allowed_topics: tuple[str, ...] | None = None,
        restricted_topics: tuple[str, ...] | None = None,
        controls: tuple[GuardrailControl, ...] | None = None,
        control_configurations: tuple[GuardrailControlConfig, ...] | None = None,
        control_bindings: tuple[GuardrailControlBinding, ...] | None = None,
        safety_level: str | None = None,
        output_delivery: str | None = None,
    ) -> Guardrail:
        if is_default_guardrail(guardrail_id):
            raise ValidationError("The Default Guardrail is managed by TaskLattice.")
        current = self.guardrail(guardrail_id)
        next_name = current.name if name is None else name.strip()
        next_purpose = current.purpose if purpose is None else purpose.strip()
        next_controls = current.controls if controls is None else controls
        next_control_configurations = (
            current.control_configurations
            if control_configurations is None
            else control_configurations
        )
        next_control_bindings = (
            current.control_bindings if control_bindings is None else control_bindings
        )
        next_control_bindings = _native_control_bindings(
            next_controls,
            next_control_bindings,
        )
        next_level = current.safety_level if safety_level is None else safety_level
        next_delivery = current.output_delivery if output_delivery is None else output_delivery
        if not next_name:
            raise ValidationError("Guardrail name is required.")
        self._validate_guardrail_fields(
            next_purpose,
            next_controls,
            next_level,
            next_delivery,
            next_control_configurations,
            next_control_bindings,
        )
        self._validate_guardrail_control_bindings(next_control_bindings)
        with self._write_lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE guardrails
                SET name = ?, purpose = ?, allowed_topics_json = ?,
                    restricted_topics_json = ?, controls_json = ?, safety_level = ?,
                    output_delivery = ?, control_configurations_json = ?,
                    control_bindings_json = ?,
                    draft_version = draft_version + 1,
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
                    _controls_json(next_controls),
                    next_level,
                    next_delivery,
                    _control_configurations_json(next_control_configurations),
                    _json([asdict(item) for item in next_control_bindings]),
                    _now(),
                    guardrail_id,
                ),
            )
            self._insert_activity(
                connection,
                kind="guardrail.updated",
                outcome="success",
                guardrail_id=guardrail_id,
                detail=f"Updated safety intent for {next_name}; tests are now stale.",
            )
            connection.commit()
        return self.guardrail(guardrail_id)

    def _compile_guardrail(
        self,
        guardrail: Guardrail,
        version: int,
    ) -> GuardrailPlanSnapshot:
        resolved_versions: list[ControlVersionSnapshot] = []
        resolved_bindings: list[GuardrailControlBindingSnapshot] = []
        native_controls = list(guardrail.controls)
        for binding in guardrail.control_bindings:
            control_version = self.control_version(
                binding.control_id, binding.control_version
            )
            resolved_versions.append(_control_version_snapshot(control_version))
            if control_version.source == "built-in":
                native_risk = dict(control_version.execution_contract).get(
                    "native_risk"
                )
                if native_risk and native_risk not in {
                    item.risk for item in native_controls
                }:
                    action = next(
                        (
                            item.on_unsafe
                            for item in control_version.rail_bindings
                            if item.rail_type in binding.enabled_rails
                        ),
                        "reject",
                    )
                    native_controls.append(GuardrailControl(native_risk, action))
            resolved_parameters = {
                item.name: item.default
                for item in control_version.parameter_schema
                if item.default is not None
            }
            resolved_parameters.update(dict(binding.parameter_values))
            resolved_bindings.append(
                GuardrailControlBindingSnapshot(
                    control_id=binding.control_id,
                    control_version=binding.control_version,
                    parameter_values=tuple(sorted(resolved_parameters.items())),
                    enabled_rails=binding.enabled_rails,
                )
            )
        return self._compiler.compile(
            replace(guardrail, controls=tuple(native_controls)),
            version,
            control_versions=tuple(resolved_versions),
            control_bindings=tuple(resolved_bindings),
        )

    def compile_draft(self, guardrail_id: str) -> GuardrailPlanSnapshot:
        guardrail = self.guardrail(guardrail_id)
        plan = self._compile_guardrail(
            guardrail, self._next_guardrail_version(guardrail_id)
        )
        # Draft evaluation uses the same compiler/runtime as released traffic,
        # without making the candidate deployable or durable.
        self._nemo_configs[(plan.guardrail_id, plan.guardrail_version)] = (
            self._nemo_compiler.compile(plan)
        )
        return plan

    def compile_preview(
        self, guardrail_id: str
    ) -> tuple[GuardrailPlanSnapshot, NeMoConfigSnapshot, str]:
        plan = self.compile_draft(guardrail_id)
        config = self.nemo_config(plan.guardrail_id, plan.guardrail_version)
        return plan, config, self._nemo_compiler.checksum(config)

    def compile_guardrail_candidate(
        self,
        *,
        name: str,
        purpose: str,
        allowed_topics: tuple[str, ...] = (),
        restricted_topics: tuple[str, ...] = (),
        controls: tuple[GuardrailControl, ...] = (),
        control_configurations: tuple[GuardrailControlConfig, ...] = (),
        control_bindings: tuple[GuardrailControlBinding, ...] = (),
        safety_level: str = "balanced",
        output_delivery: str = "window_buffered",
    ) -> tuple[GuardrailPlanSnapshot, NeMoConfigSnapshot, str]:
        """Compile a creation-flow candidate without persisting a Guardrail."""
        self._validate_guardrail_fields(
            purpose,
            controls,
            safety_level,
            output_delivery,
            control_configurations,
            control_bindings,
        )
        self._validate_guardrail_control_bindings(control_bindings)
        guardrail = Guardrail(
            id="guardrail-candidate-preview",
            name=name.strip() or "Guardrail candidate",
            purpose=purpose.strip(),
            allowed_topics=allowed_topics,
            restricted_topics=restricted_topics,
            controls=controls,
            safety_level=safety_level,
            output_delivery=output_delivery,
            source_pack_id=None,
            parameters=(),
            draft_version=1,
            active_version=None,
            updated_at=_now(),
            control_configurations=control_configurations,
            control_bindings=control_bindings,
        )
        plan = self._compile_guardrail(guardrail, 1)
        config = self._nemo_compiler.compile(plan)
        return plan, config, self._nemo_compiler.checksum(config)

    def bind_nemo_runtime(
        self,
        *,
        validator: Callable[[GuardrailPlanSnapshot, NeMoConfigSnapshot], None],
        reloader: Callable[[], None],
    ) -> None:
        """Install activation hooks after the process-wide NeMo registry exists."""
        self._nemo_runtime_validator = validator
        self._nemo_runtime_reloader = reloader

    def activate_tested_version(self, guardrail_id: str) -> TestedGuardrailVersion:
        """Create the immutable deployable snapshot after a passing test run."""
        guardrail = self.guardrail(guardrail_id)
        latest = self.latest_evaluation(guardrail_id)
        if (
            latest is None
            or latest.source_draft_version != guardrail.draft_version
            or latest.status != "passed"
        ):
            raise ValidationError("Run and pass tests for the current changes first.")

        existing = next(
            (
                item
                for item in self.versions(guardrail_id)
                if item.source_draft_version == guardrail.draft_version
            ),
            None,
        )
        if existing is not None:
            if latest.guardrail_version != existing.version:
                with self._write_lock, self._connect() as connection:
                    connection.execute(
                        "UPDATE test_runs SET guardrail_version = ? WHERE id = ?",
                        (existing.version, latest.id),
                    )
                    connection.commit()
            if guardrail.active_version != existing.version:
                existing = self.rollback_guardrail(guardrail_id, existing.version)
                guardrail = self.guardrail(guardrail_id)
            return TestedGuardrailVersion(
                guardrail,
                existing,
                self.plan(guardrail_id, existing.version),
                self.nemo_config(guardrail_id, existing.version),
            )

        next_version = self._next_guardrail_version(guardrail_id)
        plan = self._compile_guardrail(guardrail, next_version)
        nemo_config = self._nemo_compiler.compile(plan)
        checksum = self._nemo_compiler.checksum(nemo_config)
        if self._nemo_runtime_validator is not None:
            # A version is never committed or activated unless its exact immutable
            # NeMo runtime can be constructed successfully.
            self._nemo_runtime_validator(plan, nemo_config)
        created_at = _now()
        with self._write_lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO guardrail_versions
                    (guardrail_id, version, source_draft_version, guardrail_json,
                     plan_json, nemo_config_json, compiler_version, plan_checksum,
                     runtime_engine, config_checksum, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    guardrail_id,
                    next_version,
                    guardrail.draft_version,
                    _json(asdict(guardrail)),
                    _json(asdict(plan)),
                    _json(asdict(nemo_config)),
                    nemo_config.compiler_version,
                    checksum,
                    nemo_config.runtime_engine,
                    checksum,
                    created_at,
                ),
            )
            connection.execute(
                "UPDATE guardrails SET active_version = ?, updated_at = ? WHERE id = ?",
                (next_version, created_at, guardrail_id),
            )
            connection.execute(
                "UPDATE assignments SET guardrail_version = ?, updated_at = ? "
                "WHERE guardrail_id = ?",
                (next_version, created_at, guardrail_id),
            )
            connection.execute(
                "UPDATE test_runs SET guardrail_version = ? WHERE id = ?",
                (next_version, latest.id),
            )
            self._insert_activity(
                connection,
                kind="guardrail.version.created",
                outcome="passed",
                guardrail_id=guardrail_id,
                detail=f"Tests passed; created a new immutable version of {guardrail.name}.",
            )
            connection.commit()
        self._reload_runtime()
        if self._nemo_runtime_reloader is not None:
            self._nemo_runtime_reloader()
        version = GuardrailVersion(
            guardrail_id=guardrail_id,
            version=next_version,
            source_draft_version=guardrail.draft_version,
            compiler_version=nemo_config.compiler_version,
            plan_checksum=checksum,
            created_at=created_at,
            active=True,
            runtime_engine=nemo_config.runtime_engine,
            runtime_profile=nemo_config.runtime_profile,
            config_checksum=checksum,
        )
        return TestedGuardrailVersion(
            self.guardrail(guardrail_id), version, plan, nemo_config
        )

    def _next_guardrail_version(self, guardrail_id: str) -> int:
        """Allocate after every released version, independent of rollback state."""
        return max(
            (item.version for item in self.versions(guardrail_id)),
            default=0,
        ) + 1

    def versions(self, guardrail_id: str) -> tuple[GuardrailVersion, ...]:
        guardrail = self.guardrail(guardrail_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT guardrail_id, version, source_draft_version, compiler_version,
                    plan_checksum, created_at, runtime_engine, config_checksum,
                    execution_mode, nemo_config_json
                FROM guardrail_versions WHERE guardrail_id = ? ORDER BY version DESC
                """,
                (guardrail_id,),
            ).fetchall()
        return tuple(
            GuardrailVersion(
                guardrail_id=str(row[0]),
                version=int(row[1]),
                source_draft_version=int(row[2]),
                compiler_version=str(row[3]),
                plan_checksum=str(row[4]),
                created_at=str(row[5]),
                active=int(row[1]) == guardrail.active_version,
                runtime_engine=str(row[6] or "nemo"),
                runtime_profile=_stored_runtime_profile(row[9]),
                config_checksum=str(row[7] or row[4]),
                execution_mode="nemo_only",
            )
            for row in rows
        )

    def rollback_guardrail(
        self,
        guardrail_id: str,
        version: int,
    ) -> GuardrailVersion:
        """Atomically route new calls to an already-tested immutable version."""
        guardrail = self.guardrail(guardrail_id)
        target = next(
            (item for item in self.versions(guardrail_id) if item.version == version),
            None,
        )
        if target is None:
            raise NotFoundError("Guardrail Version was not found.")
        plan = self.plan(guardrail_id, version)
        config = self.nemo_config(guardrail_id, version)
        if self._nemo_runtime_validator is not None:
            self._nemo_runtime_validator(plan, config)
        if guardrail.active_version == version:
            return target
        now = _now()
        with self._write_lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "UPDATE guardrails SET active_version = ?, updated_at = ? WHERE id = ?",
                (version, now, guardrail_id),
            )
            connection.execute(
                "UPDATE assignments SET guardrail_version = ?, updated_at = ? "
                "WHERE guardrail_id = ?",
                (version, now, guardrail_id),
            )
            self._insert_activity(
                connection,
                kind="guardrail.version.rolled_back",
                outcome="success",
                guardrail_id=guardrail_id,
                detail=f"Rolled {guardrail.name} back to immutable version {version}.",
            )
            connection.commit()
        self._reload_runtime()
        if self._nemo_runtime_reloader is not None:
            self._nemo_runtime_reloader()
        return next(
            item for item in self.versions(guardrail_id) if item.version == version
        )

    def plan(self, guardrail_id: str, version: int) -> GuardrailPlanSnapshot:
        plan = self._plans.get((guardrail_id, version))
        if plan is not None:
            return plan
        with self._connect() as connection:
            row = connection.execute(
                "SELECT plan_json FROM guardrail_versions WHERE guardrail_id = ? AND version = ?",
                (guardrail_id, version),
            ).fetchone()
        if row is None:
            raise NotFoundError("Guardrail Version was not found.")
        return _plan_from_payload(json.loads(str(row[0])))

    def nemo_config(self, guardrail_id: str, version: int) -> NeMoConfigSnapshot:
        config = self._nemo_configs.get((guardrail_id, version))
        if config is not None:
            return config
        with self._connect() as connection:
            row = connection.execute(
                "SELECT nemo_config_json FROM guardrail_versions "
                "WHERE guardrail_id = ? AND version = ?",
                (guardrail_id, version),
            ).fetchone()
        if row is None or row[0] is None:
            raise NotFoundError("Guardrail Version NeMo configuration was not found.")
        return _nemo_config_from_payload(json.loads(str(row[0])))

    def active_plan_keys(self) -> tuple[tuple[str, int], ...]:
        return tuple(
            dict.fromkeys(
                (item.guardrail_id, item.guardrail_version)
                for item in self._assignments
                if item.enabled
            )
        )

    # Test evidence

    def save_evaluation(
        self,
        *,
        guardrail_id: str,
        guardrail_version: int | None,
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
                    (id, guardrail_id, guardrail_version, source_draft_version,
                     status, metrics_json, results_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    guardrail_id,
                    guardrail_version,
                    source_draft_version,
                    status,
                    _json(asdict(metrics)),
                    _json([asdict(item) for item in results]),
                    created_at,
                ),
            )
            self._insert_activity(
                connection,
                kind="guardrail.test.completed",
                outcome=status,
                guardrail_id=guardrail_id,
                detail=f"Guardrail tests completed with {metrics.compliance_rate:.1f}% compliance.",
            )
            connection.commit()
        return self.evaluation(run_id)

    def evaluations(self, guardrail_id: str | None = None) -> tuple[EvaluationRun, ...]:
        query = "SELECT * FROM test_runs"
        params: tuple[object, ...] = ()
        if guardrail_id:
            query += " WHERE guardrail_id = ?"
            params = (guardrail_id,)
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
            raise NotFoundError("Guardrail test run was not found.")
        return _evaluation_from_row(row)

    def latest_evaluation(self, guardrail_id: str) -> EvaluationRun | None:
        runs = self.evaluations(guardrail_id)
        return runs[0] if runs else None

    def test_cases(self, guardrail_id: str) -> tuple[GuardrailTestCase, ...]:
        self.guardrail(guardrail_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM test_cases
                WHERE guardrail_id = ?
                ORDER BY CASE origin WHEN 'generated' THEN 0 ELSE 1 END,
                         name COLLATE NOCASE, id
                """,
                (guardrail_id,),
            ).fetchall()
        return tuple(_test_case_from_row(row) for row in rows)

    def sync_generated_test_cases(
        self,
        guardrail_id: str,
        cases: tuple[EvaluationCase, ...],
    ) -> tuple[GuardrailTestCase, ...]:
        """Refresh generated cases while keeping reviewed custom cases intact."""
        guardrail = self.guardrail(guardrail_id)
        now = _now()
        with self._write_lock, self._connect() as connection:
            connection.execute(
                "DELETE FROM test_cases WHERE guardrail_id = ? AND origin = 'generated'",
                (guardrail_id,),
            )
            for case in cases:
                self._validate_test_case(
                    guardrail,
                    str(case.name),
                    str(case.risk),
                    str(case.phase),
                    str(case.content),
                    str(case.expected_decision),
                    case.target_source,
                    case.query,
                    case.grounding_sources,
                    case.expected_reasoning_result,
                )
                connection.execute(
                    """
                    INSERT INTO test_cases
                        (id, guardrail_id, name, risk, phase, content,
                         trusted_instruction, target_source, expected_decision,
                         query_content, grounding_sources_json,
                         expected_reasoning_result,
                         case_type, required, expected_failure, concurrency_group,
                         origin, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'generated', ?)
                    """,
                    (
                        str(case.id), guardrail_id, str(case.name), str(case.risk),
                        str(case.phase), str(case.content),
                        case.trusted_instruction,
                        case.target_source,
                        str(case.expected_decision),
                        case.query,
                        _json(case.grounding_sources),
                        case.expected_reasoning_result,
                        case.case_type,
                        int(case.required),
                        case.expected_failure,
                        case.concurrency_group,
                        now,
                    ),
                )
            connection.commit()
        return self.test_cases(guardrail_id)

    def create_test_case(
        self,
        guardrail_id: str,
        *,
        name: str,
        risk: str,
        phase: str,
        content: str,
        expected_decision: str,
        trusted_instruction: str = "",
        target_source: str = "user_input",
        query: str = "",
        grounding_sources: tuple[str, ...] = (),
        expected_reasoning_result: str | None = None,
    ) -> GuardrailTestCase:
        guardrail = self.guardrail(guardrail_id)
        self._validate_test_case(
            guardrail,
            name,
            risk,
            phase,
            content,
            expected_decision,
            target_source,
            query,
            grounding_sources,
            expected_reasoning_result,
        )
        case_id = f"case-{uuid.uuid4().hex[:12]}"
        now = _now()
        with self._write_lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO test_cases
                    (id, guardrail_id, name, risk, phase, content,
                     trusted_instruction, target_source, expected_decision,
                     query_content, grounding_sources_json,
                     expected_reasoning_result,
                     case_type, required, expected_failure, concurrency_group,
                     origin, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'unit', 1, NULL, NULL, 'custom', ?)
                """,
                (
                    case_id, guardrail_id, name.strip(), risk, phase,
                    content.strip(), trusted_instruction.strip(), target_source,
                    expected_decision, query.strip(),
                    _json(tuple(item.strip() for item in grounding_sources if item.strip())),
                    expected_reasoning_result,
                    now,
                ),
            )
            connection.execute(
                "UPDATE guardrails SET draft_version = draft_version + 1, updated_at = ? WHERE id = ?",
                (now, guardrail_id),
            )
            self._insert_activity(
                connection,
                kind="guardrail.test_case.created",
                outcome="success",
                guardrail_id=guardrail_id,
                risk=risk,
                detail=f"Added reviewed test case {name.strip()}.",
            )
            connection.commit()
        return next(item for item in self.test_cases(guardrail_id) if item.id == case_id)

    def delete_test_case(self, guardrail_id: str, case_id: str) -> None:
        self.guardrail(guardrail_id)
        with self._write_lock, self._connect() as connection:
            row = connection.execute(
                "SELECT name FROM test_cases WHERE guardrail_id = ? AND id = ?",
                (guardrail_id, case_id),
            ).fetchone()
            if row is None:
                raise NotFoundError("Guardrail test case was not found.")
            connection.execute(
                "DELETE FROM test_cases WHERE guardrail_id = ? AND id = ?",
                (guardrail_id, case_id),
            )
            connection.execute(
                "UPDATE guardrails SET draft_version = draft_version + 1, updated_at = ? WHERE id = ?",
                (_now(), guardrail_id),
            )
            self._insert_activity(
                connection,
                kind="guardrail.test_case.deleted",
                outcome="success",
                guardrail_id=guardrail_id,
                detail=f"Removed test case {str(row[0])}.",
            )
            connection.commit()

    # Assignments

    def assignments(self) -> tuple[GuardrailAssignment, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM assignments ORDER BY name COLLATE NOCASE, id"
            ).fetchall()
        return tuple(_assignment_from_row(row) for row in rows)

    def assignment(self, assignment_id: str) -> GuardrailAssignment:
        item = next((item for item in self.assignments() if item.id == assignment_id), None)
        if item is None:
            raise NotFoundError("Assignment was not found.")
        return item

    def create_assignment(
        self,
        *,
        name: str,
        guardrail_id: str,
        traffic_scope: TrafficScopeExpression,
        enabled: bool = True,
    ) -> GuardrailAssignment:
        guardrail = self.guardrail(guardrail_id)
        if is_default_guardrail(guardrail_id):
            raise ValidationError(
                "The Default Guardrail is reserved for the Default Assignment."
            )
        tested_current = any(
            item.source_draft_version == guardrail.draft_version
            for item in self.versions(guardrail_id)
        )
        if guardrail.active_version is None or not tested_current:
            raise ValidationError("Test the current Guardrail before creating an Assignment.")
        if not name.strip():
            raise ValidationError("Assignment name is required.")
        normalized = normalize_traffic_scope(traffic_scope)
        if not normalized.rules:
            raise ValidationError(
                "Unmatched traffic is already covered by the Default Assignment."
            )
        signature = traffic_scope_signature(normalized)
        duplicate = next(
            (
                item
                for item in self.assignments()
                if traffic_scope_signature(item.traffic_scope) == signature
            ),
            None,
        )
        if duplicate is not None:
            raise ValidationError(
                f"This Traffic Scope is already assigned to {duplicate.name}."
            )

        assignment_id = f"assignment-{uuid.uuid4().hex[:12]}"
        now = _now()
        with self._write_lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO assignments
                    (id, name, guardrail_id, guardrail_version, traffic_scope_json, enabled, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    assignment_id,
                    name.strip(),
                    guardrail_id,
                    guardrail.active_version,
                    _json(asdict(normalized)),
                    int(enabled),
                    now,
                ),
            )
            self._insert_activity(
                connection,
                kind="assignment.created",
                outcome="success",
                guardrail_id=guardrail_id,
                assignment_id=assignment_id,
                detail=f"Created Assignment {name.strip()}.",
            )
            connection.commit()
        self._reload_runtime()
        return self.assignment(assignment_id)

    def set_assignment_enabled(self, assignment_id: str, enabled: bool) -> GuardrailAssignment:
        current = self.assignment(assignment_id)
        if is_default_assignment(assignment_id):
            if not enabled:
                raise ValidationError("The Default Assignment is always enabled.")
            return current
        with self._write_lock, self._connect() as connection:
            connection.execute(
                "UPDATE assignments SET enabled = ?, updated_at = ? WHERE id = ?",
                (int(enabled), _now(), assignment_id),
            )
            self._insert_activity(
                connection,
                kind="assignment.updated",
                outcome="success",
                guardrail_id=current.guardrail_id,
                assignment_id=assignment_id,
                detail=f"Assignment {current.name} {'enabled' if enabled else 'paused'}.",
            )
            connection.commit()
        self._reload_runtime()
        return self.assignment(assignment_id)

    # Runtime resolution

    def resolve(self, context: RequestContext) -> PlanResolution:
        integration = self.integration(context.integration_id) if context.integration_id else None
        candidates = [
            item
            for item in self._assignments
            if item.enabled
            and traffic_scope_matches(item.traffic_scope, context)
            and (item.guardrail_id, item.guardrail_version) in self._plans
        ]
        if not candidates:
            raise ControlPlaneError("No Assignment matches this model interaction.")
        ranked = sorted(
            candidates,
            key=lambda item: tuple(-value for value in traffic_scope_specificity(item.traffic_scope)) + (item.id,),
        )
        selected = ranked[0]
        top_specificity = traffic_scope_specificity(selected.traffic_scope)
        equally_specific = [
            item
            for item in ranked
            if traffic_scope_specificity(item.traffic_scope) == top_specificity
        ]
        if len(equally_specific) > 1:
            raise ControlPlaneError(
                "Multiple equally specific Traffic Scopes match this model interaction."
            )
        plan = self._plans[(selected.guardrail_id, selected.guardrail_version)]
        trace = []
        if integration is not None:
            trace.append(_resolution_step("adapter", integration.name, integration.id))
        else:
            trace.append(
                _resolution_step(
                    "runtime",
                    "Local TaskLattice runtime",
                    "Resolved without an external Integration Adapter.",
                )
            )
        selected_default = is_default_assignment(selected.id)
        trace.extend((
            _resolution_step(
                "assignment",
                selected.name,
                (
                    "No explicit Assignment matched; selected the system-managed baseline."
                    if selected_default
                    else f"Matched {len(candidates)} Assignment Traffic Scope(s); selected "
                    f"{traffic_scope_rule_count(selected.traffic_scope)} rule(s) by specificity."
                ),
            ),
            _resolution_step(
                "guardrail",
                self.guardrail(selected.guardrail_id).name,
                "Pinned the selected Guardrail Version for this model call.",
            ),
        ))
        return PlanResolution(
            plan=plan,
            assignment_id=selected.id,
            integration_id=integration.id if integration else None,
            trace=tuple(trace),
        )

    # Integrations

    def integrations(self) -> tuple[Integration, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM integrations
                ORDER BY name COLLATE NOCASE, id
                """
            ).fetchall()
            return tuple(self._integration_from_row(connection, row) for row in rows)

    def integration(self, integration_id: str) -> Integration:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM integrations WHERE id = ?", (integration_id,)
            ).fetchone()
            if row is None:
                raise NotFoundError("Integration was not found.")
            return self._integration_from_row(connection, row)

    def integration_setup(self, integration_id: str) -> dict[str, object]:
        integration = self.integration(integration_id)
        adapter = adapter_definition(integration.adapter_id)
        if adapter is None:
            raise ControlPlaneError("Stored Integration adapter is not registered.")
        return adapter.setup(self._public_runtime_base_url, integration.id)

    def create_integration(
        self,
        *,
        name: str,
        description: str,
        adapter_id: str,
    ) -> IntegrationRegistration:
        if not name.strip():
            raise ValidationError("Integration name is required.")
        adapter = adapter_definition(adapter_id)
        if adapter is None:
            raise ValidationError("Unsupported Integration adapter.")
        integration_id = str(uuid.uuid4())
        now = _now()
        with self._write_lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO integrations
                    (id, adapter_id, name, description, enabled, request_count,
                     error_count, created_at, updated_at)
                VALUES (?, ?, ?, ?, 1, 0, 0, ?, ?)
                """,
                (integration_id, adapter.id, name.strip(), description.strip(), now, now),
            )
            credential = self._insert_credential(connection, integration_id, "generated")
            self._insert_activity(
                connection,
                kind="integration.registered",
                outcome="success",
                integration_id=integration_id,
                detail=f"Registered {adapter.name} Integration {name.strip()}.",
            )
            connection.commit()
        self._reload_runtime()
        return IntegrationRegistration(self.integration(integration_id), credential)

    def set_integration_enabled(
        self, integration_id: str, enabled: bool
    ) -> Integration:
        current = self.integration(integration_id)
        with self._write_lock, self._connect() as connection:
            connection.execute(
                "UPDATE integrations SET enabled = ?, updated_at = ? WHERE id = ?",
                (int(enabled), _now(), integration_id),
            )
            self._insert_activity(
                connection,
                kind="integration.updated",
                outcome="success",
                integration_id=integration_id,
                detail=f"Integration {current.name} {'enabled' if enabled else 'disabled'}.",
            )
            connection.commit()
        return self.integration(integration_id)

    def rotate_integration_credential(
        self, integration_id: str
    ) -> IntegrationRegistration:
        self.integration(integration_id)
        with self._write_lock, self._connect() as connection:
            credential = self._insert_credential(
                connection, integration_id, "rotated"
            )
            self._insert_activity(
                connection,
                kind="integration.credential.rotated",
                outcome="success",
                integration_id=integration_id,
                detail="Created a new Integration credential.",
            )
            connection.commit()
        self._reload_runtime()
        return IntegrationRegistration(self.integration(integration_id), credential)

    def revoke_integration_credential(
        self, integration_id: str, credential_id: str
    ) -> None:
        self.integration(integration_id)
        with self._write_lock, self._connect() as connection:
            row = connection.execute(
                "SELECT id FROM integration_credentials "
                "WHERE id = ? AND integration_id = ? AND revoked_at IS NULL",
                (credential_id, integration_id),
            ).fetchone()
            if row is None:
                raise NotFoundError("Integration credential was not found.")
            active_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM integration_credentials "
                    "WHERE integration_id = ? AND revoked_at IS NULL",
                    (integration_id,),
                ).fetchone()[0]
            )
            if active_count <= 1:
                raise ConflictError(
                    "An Integration must keep at least one active credential."
                )
            connection.execute(
                "UPDATE integration_credentials SET revoked_at = ? WHERE id = ?",
                (_now(), credential_id),
            )
            self._insert_activity(
                connection,
                kind="integration.credential.revoked",
                outcome="success",
                integration_id=integration_id,
                detail="Revoked an Integration credential.",
            )
            connection.commit()
        self._reload_runtime()

    def authenticate_integration(
        self,
        integration_id: str,
        credential: str | None,
        adapter_id: str,
    ) -> Integration:
        if not credential:
            raise IntegrationAuthenticationError("Integration credential is required.")
        credential_integration_id = self._credential_index.get(_hash(credential))
        if credential_integration_id != integration_id:
            raise IntegrationAuthenticationError("Integration credential is invalid.")
        try:
            integration = self.integration(integration_id)
        except NotFoundError as error:
            raise IntegrationAuthenticationError(
                "Integration credential is invalid."
            ) from error
        if not integration.enabled or integration.adapter_id != adapter_id:
            raise IntegrationAuthenticationError("Integration credential is invalid.")
        return integration

    def record_integration_activity(
        self,
        integration_id: str,
        *,
        phase: str,
        success: bool,
    ) -> None:
        now = _now()
        phase_column = "input_seen_at" if phase == "input" else "output_seen_at"
        with self._write_lock, self._connect() as connection:
            connection.execute(
                f"UPDATE integrations SET first_seen_at = COALESCE(first_seen_at, ?), "
                f"last_seen_at = ?, {phase_column} = ?, request_count = request_count + 1, "
                "error_count = error_count + ?, last_error_at = CASE WHEN ? THEN ? "
                "ELSE last_error_at END, updated_at = ? WHERE id = ?",
                (
                    now,
                    now,
                    now,
                    int(not success),
                    int(not success),
                    now,
                    now,
                    integration_id,
                ),
            )
            connection.commit()

    # Evidence and system summary

    def activities(self, limit: int = 100) -> tuple[DecisionEvent, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, created_at, kind, outcome, guardrail_id, assignment_id, "
                "risk, detail, integration_id FROM evidence_events "
                "ORDER BY created_at DESC, id DESC LIMIT ?",
                (max(1, min(limit, 500)),),
            ).fetchall()
        return tuple(
            DecisionEvent(
                id=str(row[0]),
                created_at=str(row[1]),
                kind=str(row[2]),
                outcome=str(row[3]),
                guardrail_id=str(row[4]) if row[4] else None,
                assignment_id=str(row[5]) if row[5] else None,
                risk=str(row[6]) if row[6] else None,
                detail=str(row[7]),
                integration_id=str(row[8]) if row[8] else None,
            )
            for row in rows
        )

    def runtime_metrics(
        self,
        *,
        since: str,
    ) -> tuple[RuntimeMetricEvent, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, created_at, guardrail_id, guardrail_version,
                       assignment_id, integration_id, protocol, phase,
                       outcome, action, risk, latency_ms, timed_out,
                       module_invocations, evaluator_invocations,
                       rail_invocations, action_invocations, model_invocations,
                       queue_latency_ms, cache_hits, cache_misses,
                       runtime_engine, config_checksum, fail_closed,
                       active_concurrency, provider_latency_ms, slo_breached
                FROM runtime_metric_events
                WHERE created_at >= ?
                ORDER BY created_at DESC, id DESC
                """,
                (since,),
            ).fetchall()
        return tuple(
            RuntimeMetricEvent(
                id=str(row[0]),
                created_at=str(row[1]),
                guardrail_id=str(row[2]) if row[2] else None,
                guardrail_version=int(row[3]) if row[3] is not None else None,
                assignment_id=str(row[4]) if row[4] else None,
                integration_id=str(row[5]) if row[5] else None,
                protocol=str(row[6]),
                phase=str(row[7]),
                outcome=str(row[8]),
                action=str(row[9]),
                risk=str(row[10]) if row[10] else None,
                latency_ms=int(row[11]),
                timed_out=bool(row[12]),
                module_invocations=int(row[13]),
                evaluator_invocations=int(row[14]),
                rail_invocations=int(row[15]),
                action_invocations=int(row[16]),
                model_invocations=int(row[17]),
                queue_latency_ms=int(row[18]),
                cache_hits=int(row[19]),
                cache_misses=int(row[20]),
                runtime_engine=str(row[21]),
                config_checksum=str(row[22]),
                fail_closed=bool(row[23]),
                active_concurrency=int(row[24]),
                provider_latency_ms=int(row[25]),
                slo_breached=bool(row[26]),
            )
            for row in rows
        )

    def runtime_step_metrics(
        self,
        *,
        since: str,
    ) -> tuple[RuntimeStepMetricEvent, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, created_at, guardrail_id, guardrail_version, "
                "assignment_id, integration_id, protocol, phase, kind, name, "
                "risk, stage, outcome, latency_ms, timed_out, runtime_engine, "
                "config_checksum, control_id, control_version, rail_type, "
                "flow_name, action_name, action_version, parallel_group, "
                "timeout_ms, provider_latency_ms FROM runtime_step_metric_events "
                "WHERE created_at >= ? ORDER BY created_at DESC, id DESC",
                (since,),
            ).fetchall()
        return tuple(
            RuntimeStepMetricEvent(
                id=str(row[0]),
                created_at=str(row[1]),
                guardrail_id=str(row[2]),
                guardrail_version=int(row[3]),
                assignment_id=str(row[4]) if row[4] else None,
                integration_id=str(row[5]) if row[5] else None,
                protocol=str(row[6]),
                phase=str(row[7]),
                kind=str(row[8]),
                name=str(row[9]),
                risk=str(row[10]) if row[10] else None,
                stage=str(row[11]) if row[11] else None,
                outcome=str(row[12]),
                latency_ms=int(row[13]),
                timed_out=bool(row[14]),
                runtime_engine=str(row[15]),
                config_checksum=str(row[16]),
                control_id=str(row[17]) if row[17] else None,
                control_version=int(row[18]) if row[18] is not None else None,
                rail_type=str(row[19]) if row[19] else None,
                flow_name=str(row[20]) if row[20] else None,
                action_name=str(row[21]) if row[21] else None,
                action_version=str(row[22]) if row[22] else None,
                parallel_group=str(row[23]) if row[23] else None,
                timeout_ms=int(row[24]) if row[24] is not None else None,
                provider_latency_ms=int(row[25]),
            )
            for row in rows
        )

    def record_runtime_steps(
        self,
        *,
        guardrail_id: str | None,
        guardrail_version: int | None,
        assignment_id: str | None,
        integration_id: str | None,
        protocol: str,
        phase: str,
        trace: tuple[EvaluationTraceStep, ...],
        runtime_engine: str,
        config_checksum: str,
    ) -> None:
        if guardrail_id is None or guardrail_version is None:
            return
        rows: list[tuple[object, ...]] = []
        now = _now()
        for step in trace:
            kind = (
                "rail"
                if step.kind == "rail" and step.id.startswith("nemo:rail:")
                else "action"
                if step.id.startswith("nemo:action:")
                else None
            )
            if kind is None:
                continue
            rows.append(
                (
                    f"step-metric-{uuid.uuid4().hex[:12]}",
                    now,
                    guardrail_id,
                    guardrail_version,
                    assignment_id,
                    integration_id,
                    protocol,
                    phase,
                    kind,
                    step.name[:256],
                    step.risk,
                    step.stage,
                    step.status,
                    max(0, step.duration_ms),
                    int(step.timed_out),
                    step.engine or runtime_engine,
                    step.config_checksum or config_checksum,
                    step.control_id,
                    step.control_version,
                    step.rail_type,
                    step.flow_name,
                    step.action_name,
                    step.action_version,
                    step.parallel_group,
                    step.timeout_ms,
                    max(0, step.provider_latency_ms),
                )
            )
        if not rows:
            return
        with self._write_lock, self._connect() as connection:
            connection.executemany(
                "INSERT INTO runtime_step_metric_events "
                "(id, created_at, guardrail_id, guardrail_version, assignment_id, "
                "integration_id, protocol, phase, kind, name, risk, stage, outcome, "
                "latency_ms, timed_out, runtime_engine, config_checksum, control_id, "
                "control_version, rail_type, flow_name, action_name, action_version, "
                "parallel_group, timeout_ms, provider_latency_ms) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            connection.commit()

    def record_decision(
        self,
        *,
        outcome: str,
        guardrail_id: str | None,
        assignment_id: str | None,
        risk: str | None,
        detail: str,
        guardrail_version: int | None = None,
        integration_id: str | None = None,
        protocol: str = "unknown",
        phase: str = "unknown",
        action: str = "unknown",
        latency_ms: int = 0,
        timed_out: bool = False,
        module_invocations: int = 0,
        evaluator_invocations: int = 0,
        rail_invocations: int = 0,
        action_invocations: int = 0,
        model_invocations: int = 0,
        queue_latency_ms: int = 0,
        cache_hits: int = 0,
        cache_misses: int = 0,
        runtime_engine: str = "",
        config_checksum: str = "",
        fail_closed: bool = False,
        active_concurrency: int = 0,
        provider_latency_ms: int = 0,
    ) -> None:
        now = _now()
        with self._write_lock, self._connect() as connection:
            self._insert_activity(
                connection,
                kind="interaction.decision",
                outcome=outcome,
                guardrail_id=guardrail_id,
                assignment_id=assignment_id,
                integration_id=integration_id,
                risk=risk,
                detail=detail,
            )
            connection.execute(
                """
                INSERT INTO runtime_metric_events
                    (id, created_at, guardrail_id, guardrail_version,
                     assignment_id, integration_id, protocol, phase,
                     outcome, action, risk, latency_ms, timed_out,
                     module_invocations, evaluator_invocations,
                     rail_invocations, action_invocations, model_invocations,
                     queue_latency_ms, cache_hits, cache_misses,
                     runtime_engine, config_checksum, fail_closed,
                     active_concurrency, provider_latency_ms, slo_breached)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"metric-{uuid.uuid4().hex[:12]}",
                    now,
                    guardrail_id,
                    guardrail_version,
                    assignment_id,
                    integration_id,
                    protocol,
                    phase,
                    outcome,
                    action,
                    risk,
                    max(0, latency_ms),
                    int(timed_out),
                    max(0, module_invocations),
                    max(0, evaluator_invocations),
                    max(0, rail_invocations),
                    max(0, action_invocations),
                    max(0, model_invocations),
                    max(0, queue_latency_ms),
                    max(0, cache_hits),
                    max(0, cache_misses),
                    runtime_engine,
                    config_checksum,
                    int(fail_closed),
                    max(0, active_concurrency),
                    max(0, provider_latency_ms),
                    int(latency_ms > self._runtime_p99_budget_ms),
                ),
            )
            connection.commit()

    def summary(self) -> dict[str, object]:
        integrations = self.integrations()
        active = [item for item in self._assignments if item.enabled]
        degraded = any(item.runtime_status == "degraded" for item in integrations)
        configured_capabilities = {
            "deterministic": True,
            "fast_semantic": self._fast_semantic_configured,
            "deep_judge": self._deep_judge_configured,
            "automated_reasoning": self._automated_reasoning_configured,
        }
        return {
            "status": "degraded" if degraded else "healthy",
            "status_reason": "integration_degraded" if degraded else "runtime_ready",
            "active_assignments": len(active),
            "enabled_integrations": sum(item.enabled for item in integrations),
            "total_integrations": len(integrations),
            "capabilities": configured_capabilities,
            "latency_budget": {
                "p95_ms": self._runtime_p95_budget_ms,
                "p99_ms": self._runtime_p99_budget_ms,
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
                has_existing_tables = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' LIMIT 1"
                ).fetchone()
                if has_existing_tables:
                    raise ControlPlaneError(
                        "This database is incompatible with the current TaskLattice Guard schema; initialize a new database."
                    )
                self._create_schema(connection)
                self._seed(connection)
            else:
                row = connection.execute(
                    "SELECT value FROM control_plane_meta WHERE key='schema_version'"
                ).fetchone()
                version = str(row[0]) if row else ""
                if version != SCHEMA_VERSION:
                    raise ControlPlaneError(
                        "This database is incompatible with the current TaskLattice Guard schema; initialize a new database."
                    )
            self._ensure_builtin_controls(connection)
            # Released system Controls must be visible to the snapshot compiler,
            # which resolves them through the same read path as normal requests.
            connection.commit()
            self._ensure_product_defaults(connection)
            connection.commit()
        self._reload_runtime()

    @staticmethod
    def _create_schema(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE control_plane_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE guardrails (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                purpose TEXT NOT NULL,
                allowed_topics_json TEXT NOT NULL,
                restricted_topics_json TEXT NOT NULL,
                controls_json TEXT NOT NULL,
                safety_level TEXT NOT NULL,
                output_delivery TEXT NOT NULL,
                source_pack_id TEXT,
                parameters_json TEXT NOT NULL,
                control_configurations_json TEXT NOT NULL DEFAULT '[]',
                control_bindings_json TEXT NOT NULL DEFAULT '[]',
                draft_version INTEGER NOT NULL,
                active_version INTEGER,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE guardrail_versions (
                guardrail_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                source_draft_version INTEGER NOT NULL,
                guardrail_json TEXT NOT NULL,
                plan_json TEXT NOT NULL,
                nemo_config_json TEXT,
                compiler_version TEXT NOT NULL,
                plan_checksum TEXT NOT NULL,
                runtime_engine TEXT NOT NULL DEFAULT 'nemo',
                config_checksum TEXT,
                execution_mode TEXT NOT NULL DEFAULT 'nemo_only',
                created_at TEXT NOT NULL,
                PRIMARY KEY (guardrail_id, version),
                FOREIGN KEY (guardrail_id) REFERENCES guardrails(id) ON DELETE CASCADE
            );
            CREATE TABLE control_packages (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                source TEXT NOT NULL,
                owner TEXT NOT NULL,
                draft_json TEXT NOT NULL,
                draft_revision INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE control_versions (
                control_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                version_json TEXT NOT NULL,
                checksum TEXT NOT NULL,
                published_at TEXT NOT NULL,
                PRIMARY KEY (control_id, version),
                FOREIGN KEY (control_id) REFERENCES control_packages(id) ON DELETE CASCADE
            );
            CREATE TABLE control_test_runs (
                id TEXT PRIMARY KEY,
                control_id TEXT NOT NULL,
                draft_revision INTEGER NOT NULL,
                status TEXT NOT NULL,
                results_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (control_id) REFERENCES control_packages(id) ON DELETE CASCADE
            );
            CREATE TABLE integrations (
                id TEXT PRIMARY KEY,
                adapter_id TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                enabled INTEGER NOT NULL,
                first_seen_at TEXT,
                last_seen_at TEXT,
                input_seen_at TEXT,
                output_seen_at TEXT,
                request_count INTEGER NOT NULL,
                error_count INTEGER NOT NULL,
                last_error_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE integration_credentials (
                id TEXT PRIMARY KEY,
                integration_id TEXT NOT NULL,
                secret_hash TEXT NOT NULL UNIQUE,
                key_hint TEXT NOT NULL,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL,
                revoked_at TEXT,
                FOREIGN KEY (integration_id) REFERENCES integrations(id) ON DELETE CASCADE
            );
            CREATE TABLE assignments (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                guardrail_id TEXT NOT NULL,
                guardrail_version INTEGER NOT NULL,
                traffic_scope_json TEXT NOT NULL,
                enabled INTEGER NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (guardrail_id, guardrail_version)
                    REFERENCES guardrail_versions(guardrail_id, version)
            );
            CREATE TABLE test_runs (
                id TEXT PRIMARY KEY,
                guardrail_id TEXT NOT NULL,
                guardrail_version INTEGER,
                source_draft_version INTEGER NOT NULL,
                status TEXT NOT NULL,
                metrics_json TEXT NOT NULL,
                results_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (guardrail_id) REFERENCES guardrails(id) ON DELETE CASCADE
            );
            CREATE TABLE test_cases (
                id TEXT NOT NULL,
                guardrail_id TEXT NOT NULL,
                name TEXT NOT NULL,
                risk TEXT NOT NULL,
                phase TEXT NOT NULL,
                content TEXT NOT NULL,
                trusted_instruction TEXT NOT NULL,
                target_source TEXT NOT NULL,
                expected_decision TEXT NOT NULL,
                query_content TEXT NOT NULL,
                grounding_sources_json TEXT NOT NULL,
                expected_reasoning_result TEXT,
                case_type TEXT NOT NULL DEFAULT 'unit',
                required INTEGER NOT NULL DEFAULT 1,
                expected_failure TEXT,
                concurrency_group TEXT,
                origin TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (guardrail_id, id),
                FOREIGN KEY (guardrail_id) REFERENCES guardrails(id) ON DELETE CASCADE
            );
            CREATE TABLE evidence_events (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                kind TEXT NOT NULL,
                outcome TEXT NOT NULL,
                guardrail_id TEXT,
                assignment_id TEXT,
                risk TEXT,
                detail TEXT NOT NULL,
                integration_id TEXT
            );
            CREATE TABLE runtime_metric_events (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                guardrail_id TEXT,
                guardrail_version INTEGER,
                assignment_id TEXT,
                integration_id TEXT,
                protocol TEXT NOT NULL,
                phase TEXT NOT NULL,
                outcome TEXT NOT NULL,
                action TEXT NOT NULL,
                risk TEXT,
                latency_ms INTEGER NOT NULL,
                timed_out INTEGER NOT NULL,
                module_invocations INTEGER NOT NULL,
                evaluator_invocations INTEGER NOT NULL,
                rail_invocations INTEGER NOT NULL DEFAULT 0,
                action_invocations INTEGER NOT NULL DEFAULT 0,
                model_invocations INTEGER NOT NULL DEFAULT 0,
                queue_latency_ms INTEGER NOT NULL DEFAULT 0,
                cache_hits INTEGER NOT NULL DEFAULT 0,
                cache_misses INTEGER NOT NULL DEFAULT 0,
                runtime_engine TEXT NOT NULL DEFAULT '',
                config_checksum TEXT NOT NULL DEFAULT '',
                fail_closed INTEGER NOT NULL DEFAULT 0,
                active_concurrency INTEGER NOT NULL DEFAULT 0,
                provider_latency_ms INTEGER NOT NULL DEFAULT 0,
                slo_breached INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX runtime_metric_events_created_at_idx
                ON runtime_metric_events(created_at);
            CREATE INDEX runtime_metric_events_guardrail_created_at_idx
                ON runtime_metric_events(guardrail_id, created_at);
            CREATE TABLE runtime_step_metric_events (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                guardrail_id TEXT NOT NULL,
                guardrail_version INTEGER NOT NULL,
                assignment_id TEXT,
                integration_id TEXT,
                protocol TEXT NOT NULL,
                phase TEXT NOT NULL,
                kind TEXT NOT NULL,
                name TEXT NOT NULL,
                risk TEXT,
                stage TEXT,
                outcome TEXT NOT NULL,
                latency_ms INTEGER NOT NULL,
                timed_out INTEGER NOT NULL,
                runtime_engine TEXT NOT NULL,
                config_checksum TEXT NOT NULL,
                control_id TEXT,
                control_version INTEGER,
                rail_type TEXT,
                flow_name TEXT,
                action_name TEXT,
                action_version TEXT,
                parallel_group TEXT,
                timeout_ms INTEGER,
                provider_latency_ms INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX runtime_step_metric_events_created_at_idx
                ON runtime_step_metric_events(created_at);
            CREATE INDEX runtime_step_metric_events_guardrail_created_at_idx
                ON runtime_step_metric_events(guardrail_id, created_at);
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

    def _seed(self, connection: sqlite3.Connection) -> None:
        self._insert_activity(
            connection,
            kind="system.seeded",
            outcome="success",
            detail="Initialized the standalone TaskLattice control plane.",
        )

    def _ensure_builtin_controls(self, connection: sqlite3.Connection) -> None:
        """Expose every existing built-in detector as an immutable Control Version."""
        published_at = "2000-01-01T00:00:00+00:00"
        for definition in CONTROL_DEFINITIONS:
            control_id = f"builtin-{definition.id.replace('_', '-')}"
            rails = tuple(
                RailBinding(
                    rail_type=phase,
                    flow_name=f"builtin_{definition.id}_{phase}",
                    execution_mode=(
                        "mutate"
                        if definition.default_action in {"redact", "rewrite"}
                        else "detect"
                    ),
                    on_unsafe=definition.default_action,
                    priority=(
                        100
                        if definition.default_action in {"redact", "rewrite"}
                        else None
                    ),
                )
                for phase in definition.default_phases
            )
            sources = tuple(
                ControlSourceFile(
                    path=f"{definition.id}.co",
                    content="\n\n".join(
                        f"flow {item.flow_name} $text\n  pass" for item in rails
                    ),
                )
                for _ in (0,)
            )
            draft = ControlDraft(
                colang_version="2.x",
                sources=sources,
                parameter_schema=(),
                rail_bindings=rails,
                action_references=tuple(
                    ActionReference(name=name, version="1.0.0")
                    for name in dict.fromkeys(
                        action_name_for(definition.id, stage)
                        for stage in definition.available_stages
                    )
                    if self._action_catalog.contains(name, "1.0.0")
                ),
                execution_contract=(("native_risk", definition.id),),
            )
            package_payload = _json(asdict(draft))
            version_payload = {
                "control_id": control_id,
                "version": 1,
                "name": definition.display_name,
                "description": definition.description,
                "source": "built-in",
                "owner": "TaskLattice",
                **asdict(draft),
                "published_at": published_at,
            }
            checksum = hashlib.sha256(
                json.dumps(
                    version_payload, sort_keys=True, separators=(",", ":")
                ).encode()
            ).hexdigest()
            connection.execute(
                """
                INSERT INTO control_packages
                    (id, name, description, source, owner, draft_json,
                     draft_revision, updated_at)
                VALUES (?, ?, ?, 'built-in', 'TaskLattice', ?, 1, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    description = excluded.description,
                    source = 'built-in',
                    owner = 'TaskLattice',
                    draft_json = excluded.draft_json,
                    updated_at = excluded.updated_at
                """,
                (
                    control_id,
                    definition.display_name,
                    definition.description,
                    package_payload,
                    published_at,
                ),
            )
            connection.execute(
                """
                INSERT INTO control_versions
                    (control_id, version, version_json, checksum, published_at)
                VALUES (?, 1, ?, ?, ?)
                ON CONFLICT(control_id, version) DO NOTHING
                """,
                (control_id, _json(version_payload), checksum, published_at),
            )

    def _ensure_product_defaults(self, connection: sqlite3.Connection) -> None:
        guardrail_row = connection.execute(
            "SELECT id FROM guardrails WHERE id = ?", (DEFAULT_GUARDRAIL_ID,)
        ).fetchone()
        created_guardrail = guardrail_row is None
        if created_guardrail:
            now = _now()
            controls = (
                GuardrailControl("secrets", "reject"),
                GuardrailControl("pii", "redact"),
                GuardrailControl("builtin_content_filter", "reject"),
            )
            control_bindings = _native_control_bindings(controls, ())
            guardrail = Guardrail(
                id=DEFAULT_GUARDRAIL_ID,
                name=DEFAULT_GUARDRAIL_NAME,
                purpose=DEFAULT_GUARDRAIL_PURPOSE,
                allowed_topics=(),
                restricted_topics=(),
                controls=controls,
                safety_level="balanced",
                output_delivery="window_buffered",
                source_pack_id=DEFAULT_GUARDRAIL_PACK_ID,
                parameters=(),
                draft_version=1,
                active_version=DEFAULT_GUARDRAIL_VERSION,
                updated_at=now,
                control_bindings=control_bindings,
            )
            plan = self._compile_guardrail(
                guardrail,
                DEFAULT_GUARDRAIL_VERSION,
            )
            if not plan.steps or any(step.stage != "deterministic" for step in plan.steps):
                raise ControlPlaneError(
                    "The Default Guardrail must compile to local deterministic stages only."
                )
            nemo_config = self._nemo_compiler.compile(plan)
            nemo_checksum = self._nemo_compiler.checksum(nemo_config)
            connection.execute(
                """
                INSERT INTO guardrails
                    (id, name, purpose, allowed_topics_json, restricted_topics_json,
                     controls_json, safety_level, output_delivery, source_pack_id,
                     parameters_json, control_configurations_json,
                     control_bindings_json, draft_version, active_version, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', ?, 1, ?, ?)
                """,
                (
                    guardrail.id,
                    guardrail.name,
                    guardrail.purpose,
                    _json(guardrail.allowed_topics),
                    _json(guardrail.restricted_topics),
                    _controls_json(guardrail.controls),
                    guardrail.safety_level,
                    guardrail.output_delivery,
                    guardrail.source_pack_id,
                    _json({}),
                    _json([asdict(item) for item in control_bindings]),
                    DEFAULT_GUARDRAIL_VERSION,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO guardrail_versions
                    (guardrail_id, version, source_draft_version, guardrail_json,
                     plan_json, nemo_config_json, compiler_version, plan_checksum,
                     runtime_engine, config_checksum, created_at)
                VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    guardrail.id,
                    DEFAULT_GUARDRAIL_VERSION,
                    _json(asdict(guardrail)),
                    _json(asdict(plan)),
                    _json(asdict(nemo_config)),
                    nemo_config.compiler_version,
                    nemo_checksum,
                    nemo_config.runtime_engine,
                    nemo_checksum,
                    now,
                ),
            )
            self._insert_activity(
                connection,
                kind="guardrail.default.created",
                outcome="success",
                guardrail_id=DEFAULT_GUARDRAIL_ID,
                detail="Installed the local-only Default Guardrail.",
            )

        assignment_row = connection.execute(
            "SELECT id FROM assignments WHERE id = ?", (DEFAULT_ASSIGNMENT_ID,)
        ).fetchone()
        if assignment_row is None:
            now = _now()
            connection.execute(
                """
                INSERT INTO assignments
                    (id, name, guardrail_id, guardrail_version, traffic_scope_json, enabled, updated_at)
                VALUES (?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    DEFAULT_ASSIGNMENT_ID,
                    DEFAULT_ASSIGNMENT_NAME,
                    DEFAULT_GUARDRAIL_ID,
                    DEFAULT_GUARDRAIL_VERSION,
                    _json({"combinator": "and", "rules": []}),
                    now,
                ),
            )
            self._insert_activity(
                connection,
                kind="assignment.default.created",
                outcome="success",
                guardrail_id=DEFAULT_GUARDRAIL_ID,
                assignment_id=DEFAULT_ASSIGNMENT_ID,
                detail="Enabled the Default Assignment for unmatched traffic.",
            )

    def _insert_credential(
        self,
        connection: sqlite3.Connection,
        integration_id: str,
        source: str,
    ) -> IntegrationCredentialSecret:
        credential_id = str(uuid.uuid4())
        credential = _new_credential()
        key_hint = _key_hint(credential)
        created_at = _now()
        connection.execute(
            """
            INSERT INTO integration_credentials
                (id, integration_id, secret_hash, key_hint, source, created_at, revoked_at)
            VALUES (?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                credential_id,
                integration_id,
                _hash(credential),
                key_hint,
                source,
                created_at,
            ),
        )
        return IntegrationCredentialSecret(
            id=credential_id,
            value=credential,
            key_hint=key_hint,
            created_at=created_at,
        )

    @staticmethod
    def _insert_activity(
        connection: sqlite3.Connection,
        *,
        kind: str,
        outcome: str,
        detail: str,
        guardrail_id: str | None = None,
        assignment_id: str | None = None,
        integration_id: str | None = None,
        risk: str | None = None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO evidence_events
                (id, created_at, kind, outcome, guardrail_id, assignment_id, risk, detail, integration_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"evidence-{uuid.uuid4().hex[:12]}",
                _now(),
                kind,
                outcome,
                guardrail_id,
                assignment_id,
                risk,
                detail,
                integration_id,
            ),
        )

    def _reload_runtime(self) -> None:
        plans: dict[tuple[str, int], GuardrailPlanSnapshot] = {}
        nemo_configs: dict[tuple[str, int], NeMoConfigSnapshot] = {}
        credentials: dict[str, str] = {}
        with self._connect() as connection:
            for row in connection.execute(
                "SELECT guardrail_id, version, plan_json, nemo_config_json "
                "FROM guardrail_versions"
            ).fetchall():
                key = (str(row[0]), int(row[1]))
                plans[key] = _plan_from_payload(
                    json.loads(str(row[2]))
                )
                if row[3] is not None:
                    nemo_configs[key] = _nemo_config_from_payload(
                        json.loads(str(row[3]))
                    )
            for row in connection.execute(
                "SELECT secret_hash, integration_id FROM integration_credentials WHERE revoked_at IS NULL"
            ).fetchall():
                credentials[str(row[0])] = str(row[1])
        self._plans = plans
        self._nemo_configs = nemo_configs
        self._assignments = self.assignments()
        self._credential_index = credentials

    def _integration_from_row(
        self, connection: sqlite3.Connection, row: sqlite3.Row
    ) -> Integration:
        adapter = adapter_definition(str(row["adapter_id"]))
        if adapter is None:
            raise ControlPlaneError("Stored Integration adapter is not registered.")
        credentials = tuple(
            IntegrationCredential(
                id=str(item["id"]),
                key_hint=str(item["key_hint"]),
                created_at=str(item["created_at"]),
            )
            for item in connection.execute(
                "SELECT id, key_hint, created_at FROM integration_credentials "
                "WHERE integration_id = ? AND revoked_at IS NULL "
                "ORDER BY created_at DESC, id DESC",
                (str(row["id"]),),
            ).fetchall()
        )
        enabled = bool(row["enabled"])
        first_seen_at = str(row["first_seen_at"]) if row["first_seen_at"] else None
        last_seen_at = str(row["last_seen_at"]) if row["last_seen_at"] else None
        input_seen_at = str(row["input_seen_at"]) if row["input_seen_at"] else None
        output_seen_at = str(row["output_seen_at"]) if row["output_seen_at"] else None
        last_error_at = str(row["last_error_at"]) if row["last_error_at"] else None
        setup_status = (
            "disabled"
            if not enabled
            else "awaiting_input"
            if input_seen_at is None
            else "awaiting_output"
            if output_seen_at is None
            else "verified"
        )
        runtime_status = (
            "disabled"
            if not enabled
            else "waiting"
            if last_seen_at is None
            else "degraded"
            if last_error_at == last_seen_at
            else "healthy"
        )
        return Integration(
            id=str(row["id"]),
            adapter_id=adapter.id,
            protocol=adapter.protocol,
            name=str(row["name"]),
            description=str(row["description"]),
            enabled=enabled,
            key_hint=credentials[0].key_hint if credentials else "",
            credentials=credentials,
            setup_status=setup_status,
            runtime_status=runtime_status,
            first_seen_at=first_seen_at,
            last_seen_at=last_seen_at,
            input_seen_at=input_seen_at,
            output_seen_at=output_seen_at,
            request_count=int(row["request_count"]),
            error_count=int(row["error_count"]),
            last_error_at=last_error_at,
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def _validate_control_draft(
        self,
        control_id: str,
        draft: ControlDraft,
        *,
        validate_dependencies: bool,
    ) -> None:
        if draft.colang_version not in {"1.0", "2.x"}:
            raise ValidationError("Control Colang version must be 1.0 or 2.x.")
        if not draft.sources or any(
            not item.path.strip() or not item.content.strip() for item in draft.sources
        ):
            raise ValidationError("A Control requires at least one named Colang source.")
        if len({item.path for item in draft.sources}) != len(draft.sources):
            raise ValidationError("Control source paths must be unique.")
        if not draft.rail_bindings:
            raise ValidationError("A Control requires at least one Rail binding.")
        if len({(item.rail_type, item.flow_name) for item in draft.rail_bindings}) != len(
            draft.rail_bindings
        ):
            raise ValidationError("Control Rail bindings must be unique.")
        for binding in draft.rail_bindings:
            if binding.rail_type not in {
                "input", "output", "retrieval", "dialog", "execution"
            }:
                raise ValidationError("Unsupported Control rail type.")
            if binding.timeout_ms <= 0:
                raise ValidationError("Control rail timeouts must be positive.")
            if binding.execution_mode == "mutate" and binding.priority is None:
                raise ValidationError(
                    f"Mutating flow {binding.flow_name!r} requires an explicit priority."
                )
        mutating_groups: dict[tuple[str, str | None], list[RailBinding]] = {}
        for binding in draft.rail_bindings:
            if binding.execution_mode == "mutate":
                mutating_groups.setdefault(
                    (binding.rail_type, binding.parallel_group), []
                ).append(binding)
        for (rail, group), bindings in mutating_groups.items():
            if group is not None and len(bindings) > 1:
                raise ValidationError(
                    f"Mutating {rail} flows cannot share parallel group {group!r}."
                )
        for rail in {item.rail_type for item in draft.rail_bindings}:
            priorities = tuple(
                item.priority
                for item in draft.rail_bindings
                if item.rail_type == rail and item.execution_mode == "mutate"
            )
            if len(set(priorities)) != len(priorities):
                raise ValidationError(
                    f"Mutating {rail} flows require distinct priorities."
                )
        if not validate_dependencies:
            return
        for reference in draft.action_references:
            if not self._action_catalog.contains(reference.name, reference.version):
                raise ValidationError(
                    f"Control {control_id!r} references unregistered Action "
                    f"{reference.name}@{reference.version}."
                )
            definition = self._action_catalog.get(reference.name, reference.version)
            if not definition.provider_ready:
                raise ValidationError(
                    f"Action provider {reference.name}@{reference.version} is not ready."
                )
        missing_models = tuple(
            item
            for item in draft.model_dependencies
            if not self._nemo_compiler.has_model_dependency(item)
        )
        if missing_models:
            raise ValidationError(
                f"Control {control_id!r} references unregistered Models: "
                + ", ".join(missing_models)
                + "."
            )
        missing_prompts = tuple(
            item
            for item in draft.prompt_dependencies
            if not self._nemo_compiler.has_prompt_dependency(item)
        )
        if missing_prompts:
            raise ValidationError(
                f"Control {control_id!r} references unregistered Prompts: "
                + ", ".join(missing_prompts)
                + "."
            )

    def _validate_guardrail_control_bindings(
        self,
        bindings: tuple[GuardrailControlBinding, ...],
    ) -> None:
        keys = tuple((item.control_id, item.control_version) for item in bindings)
        if len(set(keys)) != len(keys):
            raise ValidationError("A Control Version may only be bound once.")
        for binding in bindings:
            version = self.control_version(binding.control_id, binding.control_version)
            definitions = {item.name: item for item in version.parameter_schema}
            supplied = dict(binding.parameter_values)
            missing = tuple(
                item.name
                for item in definitions.values()
                if item.required and item.default is None and not supplied.get(item.name)
            )
            if missing:
                raise ValidationError(
                    f"Control {binding.control_id}@{binding.control_version} requires "
                    + ", ".join(missing)
                    + "."
                )
            unknown = set(supplied) - set(definitions)
            if unknown:
                raise ValidationError(
                    f"Unknown parameters for Control {binding.control_id}: "
                    + ", ".join(sorted(unknown))
                    + "."
                )
            available_rails = {item.rail_type for item in version.rail_bindings}
            if not set(binding.enabled_rails) <= available_rails:
                raise ValidationError(
                    f"Control {binding.control_id}@{binding.control_version} does not "
                    "provide every enabled rail."
                )

    @staticmethod
    def _validate_guardrail_fields(
        purpose: str,
        controls: tuple[GuardrailControl, ...],
        safety_level: str,
        output_delivery: str,
        control_configurations: tuple[GuardrailControlConfig, ...] = (),
        control_bindings: tuple[GuardrailControlBinding, ...] = (),
    ) -> None:
        if not purpose.strip():
            raise ValidationError("Describe what this AI is allowed to do.")
        if safety_level not in {"balanced", "strict"}:
            raise ValidationError("Enforcement mode must be balanced or strict.")
        if output_delivery not in {"interruptible", "window_buffered", "full_buffered"}:
            raise ValidationError("Unsupported output delivery mode.")
        known = {item.id: item for item in CONTROL_DEFINITIONS}
        if not controls and not control_bindings:
            raise ValidationError("Select at least one Control to protect.")
        if len({item.risk for item in controls}) != len(controls):
            raise ValidationError("A risk may only be configured once.")
        for risk in controls:
            definition = known.get(risk.risk)
            if definition is None:
                raise ValidationError(f"Unknown risk {risk.risk!r}.")
            if risk.action not in definition.allowed_actions:
                raise ValidationError(f"Unsupported action for {risk.risk}.")
            if risk.risk == "automated_reasoning":
                binding = risk.reasoning_policy
                if binding is None:
                    raise ValidationError(
                        "Automated reasoning requires a deployed policy binding."
                    )
                if not binding.policy_id.strip() or not binding.policy_version.strip():
                    raise ValidationError(
                        "Automated reasoning policy ID and version are required."
                    )
                if not 0 <= binding.confidence_threshold <= 1:
                    raise ValidationError(
                        "Automated reasoning confidence threshold must be between 0 and 1."
                    )
                if output_delivery != "full_buffered":
                    raise ValidationError(
                        "Automated reasoning requires full-buffered output delivery."
                    )
            elif risk.reasoning_policy is not None:
                raise ValidationError(
                    "Only automated reasoning may bind a reasoning policy."
                )
        configured_runtime_risks = {
            item.runtime_risk for item in control_configurations
        }
        missing_runtime_controls = configured_runtime_risks - {
            item.risk for item in controls
        }
        if missing_runtime_controls:
            raise ValidationError(
                "Configured Controls must be included in the Guardrail runtime plan: "
                + ", ".join(sorted(missing_runtime_controls))
                + "."
            )
        ControlPlaneService._validate_control_configurations(control_configurations)

    @staticmethod
    def _validate_control_configurations(
        configurations: tuple[GuardrailControlConfig, ...],
    ) -> None:
        if len({item.id for item in configurations}) != len(configurations):
            raise ValidationError("A Control may only be configured once.")
        known_risks = {item.id for item in CONTROL_DEFINITIONS}
        for configuration in configurations:
            if configuration.runtime_risk not in known_risks:
                raise ValidationError(
                    f"Unknown runtime Control {configuration.runtime_risk!r}."
                )
            if not configuration.rules or not any(
                rule.enabled for rule in configuration.rules
            ):
                raise ValidationError(
                    f"Control {configuration.name!r} must enable at least one Rule."
                )
            if len({rule.id for rule in configuration.rules}) != len(
                configuration.rules
            ):
                raise ValidationError(
                    f"Control {configuration.name!r} contains duplicate Rules."
                )
            if configuration.kind == "built_in":
                built_in = library_control(configuration.control_id or "")
                if built_in is None:
                    raise ValidationError("Unknown built-in Control.")
                if configuration.control_version != built_in.version:
                    raise ValidationError(
                        f"Control {built_in.id!r} must pin version {built_in.version}."
                    )
                available = {rule.id for rule in built_in.rules}
                if any(rule.id not in available for rule in configuration.rules):
                    raise ValidationError(
                        f"Control {configuration.name!r} references an unknown Rule."
                    )
            elif configuration.kind == "custom":
                if (
                    configuration.control_id is not None
                    or configuration.control_version is not None
                ):
                    raise ValidationError(
                        "A custom Control cannot reference a built-in Control version."
                    )
            else:
                raise ValidationError(
                    f"Unsupported Control kind {configuration.kind!r}."
                )
            for rule in configuration.rules:
                if not rule.phases or any(
                    phase not in {"input", "output"} for phase in rule.phases
                ):
                    raise ValidationError(
                        f"Rule {rule.name!r} requires a supported model boundary."
                    )
                if rule.detector == "regex" and configuration.kind == "custom":
                    if not (rule.expression or "").strip():
                        raise ValidationError(
                            f"Custom Regex Rule {rule.name!r} requires an expression."
                        )
                    try:
                        re.compile(rule.expression or "")
                    except re.error as error:
                        raise ValidationError(
                            f"Custom Regex Rule {rule.name!r} is invalid."
                        ) from error
                if rule.detector == "keyword" and configuration.kind == "custom":
                    if not any(keyword.strip() for keyword in rule.keywords):
                        raise ValidationError(
                            f"Custom Keyword Rule {rule.name!r} requires a keyword."
                        )
                if (
                    configuration.kind == "built_in"
                    and rule.enabled
                    and rule.id.startswith("dynamic-")
                    and (
                        not any(keyword.strip() for keyword in rule.keywords)
                        or any("{{" in keyword for keyword in rule.keywords)
                    )
                ):
                    raise ValidationError(
                        f"Parameterized Rule {rule.name!r} requires reviewed values."
                    )

    @staticmethod
    def _validate_test_case(
        guardrail: Guardrail,
        name: str,
        risk: str,
        phase: str,
        content: str,
        expected_decision: str,
        target_source: str = "user_input",
        query: str = "",
        grounding_sources: tuple[str, ...] = (),
        expected_reasoning_result: str | None = None,
    ) -> None:
        if not name.strip() or not content.strip():
            raise ValidationError("Test case name and model content are required.")
        if risk not in {
            *(item.risk for item in guardrail.controls),
            *(item.control_id for item in guardrail.control_bindings),
        }:
            raise ValidationError("Test case risk must be enabled in this Guardrail.")
        if phase not in {"input", "output"}:
            raise ValidationError("Test case phase must be input or output.")
        if expected_decision not in {"allow", "block", "transform", "intervene"}:
            raise ValidationError("Unsupported expected test decision.")
        if target_source not in {
            "user_input",
            "retrieved_content",
            "tool_output",
            "model_output",
        }:
            raise ValidationError("Unsupported test target source.")
        clean_sources = tuple(item.strip() for item in grounding_sources if item.strip())
        if risk == "contextual_grounding":
            if expected_reasoning_result is not None:
                raise ValidationError(
                    "Only automated reasoning tests may expect a reasoning result."
                )
            if phase != "output":
                raise ValidationError("Contextual grounding tests must target model output.")
            if not query.strip() or not clean_sources:
                raise ValidationError(
                    "Contextual grounding tests require a query and at least one grounding source."
                )
            if len(query) > 1_000 or sum(len(item) for item in clean_sources) > 100_000:
                raise ValidationError("Contextual grounding test context exceeds runtime limits.")
            if len(content) > 5_000:
                raise ValidationError("Contextual grounding test output exceeds 5,000 characters.")
        elif risk == "automated_reasoning":
            if phase != "output" or target_source != "model_output":
                raise ValidationError(
                    "Automated reasoning tests must target complete model output."
                )
            if clean_sources:
                raise ValidationError(
                    "Automated reasoning tests do not accept grounding sources."
                )
            if expected_reasoning_result not in {
                "valid",
                "invalid",
                "satisfiable",
                "impossible",
                "translation_ambiguous",
                "too_complex",
                "no_translations",
            }:
                raise ValidationError(
                    "Automated reasoning tests require an expected logical result."
                )
        elif query.strip() or clean_sources:
            raise ValidationError(
                "Query context is only supported by response-assurance tests."
            )
        elif expected_reasoning_result is not None:
            raise ValidationError(
                "Only automated reasoning tests may expect a reasoning result."
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection


def _control_draft_from_payload(payload: dict[str, object]) -> ControlDraft:
    return ControlDraft(
        colang_version=str(payload["colang_version"]),
        sources=tuple(ControlSourceFile(**item) for item in payload.get("sources", ())),
        parameter_schema=tuple(
            ControlParameterDefinition(**item)
            for item in payload.get("parameter_schema", ())
        ),
        rail_bindings=tuple(
            RailBinding(**item) for item in payload.get("rail_bindings", ())
        ),
        action_references=tuple(
            ActionReference(**item) for item in payload.get("action_references", ())
        ),
        model_dependencies=tuple(payload.get("model_dependencies", ())),
        prompt_dependencies=tuple(payload.get("prompt_dependencies", ())),
        execution_contract=tuple(
            tuple(item) for item in payload.get("execution_contract", ())
        ),
        tests=tuple(
            ControlTestDefinition(**item) for item in payload.get("tests", ())
        ),
    )


def _control_package_from_row(row: sqlite3.Row) -> ControlPackage:
    return ControlPackage(
        id=str(row["id"]),
        name=str(row["name"]),
        description=str(row["description"]),
        source=str(row["source"]),
        owner=str(row["owner"]),
        draft=_control_draft_from_payload(json.loads(str(row["draft_json"]))),
        draft_revision=int(row["draft_revision"]),
        updated_at=str(row["updated_at"]),
    )


def _control_version_from_row(row: sqlite3.Row) -> ControlVersion:
    payload = json.loads(str(row["version_json"]))
    draft = _control_draft_from_payload(payload)
    return ControlVersion(
        control_id=str(payload["control_id"]),
        version=int(payload["version"]),
        name=str(payload["name"]),
        description=str(payload["description"]),
        source=str(payload["source"]),
        owner=str(payload["owner"]),
        colang_version=draft.colang_version,
        sources=draft.sources,
        parameter_schema=draft.parameter_schema,
        rail_bindings=draft.rail_bindings,
        action_references=draft.action_references,
        model_dependencies=draft.model_dependencies,
        prompt_dependencies=draft.prompt_dependencies,
        execution_contract=draft.execution_contract,
        tests=draft.tests,
        checksum=str(row["checksum"]),
        published_at=str(row["published_at"]),
    )


def _control_version_snapshot(version: ControlVersion) -> ControlVersionSnapshot:
    return ControlVersionSnapshot(
        control_id=version.control_id,
        version=version.version,
        name=version.name,
        source=version.source,
        colang_version=version.colang_version,
        sources=tuple(
            ControlSourceSnapshot(path=item.path, content=item.content)
            for item in version.sources
        ),
        parameter_schema=tuple(
            (item.name, item.kind) for item in version.parameter_schema
        ),
        rail_bindings=tuple(
            ControlRailBindingSnapshot(**asdict(item))
            for item in version.rail_bindings
        ),
        action_references=tuple(
            ControlActionReferenceSnapshot(item.name, item.version)
            for item in version.action_references
        ),
        model_dependencies=version.model_dependencies,
        prompt_dependencies=version.prompt_dependencies,
        execution_contract=version.execution_contract,
        tests=tuple(
            (item.name, item.expected_decision) for item in version.tests
        ),
        checksum=version.checksum,
    )


def _guardrail_from_row(row: sqlite3.Row) -> Guardrail:
    raw_controls = json.loads(str(row["controls_json"]))
    raw_configurations = json.loads(str(row["control_configurations_json"]))
    raw_bindings = json.loads(str(row["control_bindings_json"]))
    return Guardrail(
        id=str(row["id"]),
        name=str(row["name"]),
        purpose=str(row["purpose"]),
        allowed_topics=tuple(json.loads(str(row["allowed_topics_json"]))),
        restricted_topics=tuple(json.loads(str(row["restricted_topics_json"]))),
        controls=tuple(
            GuardrailControl(
                str(item["risk"]),
                str(item["action"]),
                _reasoning_binding(item["reasoning_policy"]),
            )
            for item in raw_controls
        ),
        safety_level=str(row["safety_level"]),
        output_delivery=str(row["output_delivery"]),
        source_pack_id=(
            str(row["source_pack_id"]) if row["source_pack_id"] else None
        ),
        parameters=tuple(
            sorted(json.loads(str(row["parameters_json"])).items())
        ),
        draft_version=int(row["draft_version"]),
        active_version=(
            int(row["active_version"]) if row["active_version"] is not None else None
        ),
        updated_at=str(row["updated_at"]),
        control_configurations=tuple(
            GuardrailControlConfig(
                id=str(item["id"]),
                name=str(item["name"]),
                kind=str(item["kind"]),
                runtime_risk=str(item["runtime_risk"]),
                control_id=(
                    str(item["control_id"]) if item.get("control_id") else None
                ),
                control_version=(
                    str(item["control_version"])
                    if item.get("control_version")
                    else None
                ),
                rules=tuple(
                    GuardrailRuleConfig(
                        id=str(rule["id"]),
                        name=str(rule["name"]),
                        detector=str(rule["detector"]),
                        action=str(rule["action"]),
                        phases=tuple(rule["phases"]),
                        enabled=bool(rule.get("enabled", True)),
                        description=str(rule.get("description", "")),
                        expression=(
                            str(rule["expression"])
                            if rule.get("expression") is not None
                            else None
                        ),
                        keywords=tuple(rule.get("keywords", ())),
                    )
                    for rule in item["rules"]
                ),
            )
            for item in raw_configurations
        ),
        control_bindings=tuple(
            GuardrailControlBinding(
                control_id=str(item["control_id"]),
                control_version=int(item["control_version"]),
                parameter_values=tuple(
                    tuple(value) for value in item.get("parameter_values", ())
                ),
                enabled_rails=tuple(item.get("enabled_rails", ("input", "output"))),
            )
            for item in raw_bindings
        ),
    )


def _plan_from_payload(payload: dict[str, object]) -> GuardrailPlanSnapshot:
    modules = tuple(
        GuardrailPlanModule(
            id=str(item["id"]),
            module=str(item["module"]),
            phase=str(item["phase"]),
            step_ids=tuple(item["step_ids"]),
            depends_on=tuple(item["depends_on"]),
            input_view=str(item["input_view"]),
            required_for_release=bool(item["required_for_release"]),
            timeout_ms=int(item["timeout_ms"]),
            failure_mode=str(item["failure_mode"]),
        )
        for item in payload["modules"]
    )
    return GuardrailPlanSnapshot(
        guardrail_id=str(payload["guardrail_id"]),
        guardrail_version=int(payload["guardrail_version"]),
        compiler_version=str(payload["compiler_version"]),
        safety_level=str(payload["safety_level"]),
        output_delivery=str(payload["output_delivery"]),
        steps=tuple(
            GuardrailPlanStep(
                **{
                    **item,
                    "phases": tuple(item["phases"]),
                    "parameters": tuple(tuple(value) for value in item["parameters"]),
                }
            )
            for item in payload["steps"]
        ),
        modules=modules,
        reasoning_policies=tuple(
            AutomatedReasoningPolicySnapshot(**item)
            for item in payload.get("reasoning_policies", ())
        ),
        control_versions=tuple(
            ControlVersionSnapshot(
                control_id=str(item["control_id"]),
                version=int(item["version"]),
                name=str(item["name"]),
                source=str(item["source"]),
                colang_version=str(item["colang_version"]),
                sources=tuple(
                    ControlSourceSnapshot(**source) for source in item.get("sources", ())
                ),
                parameter_schema=tuple(
                    tuple(value) for value in item.get("parameter_schema", ())
                ),
                rail_bindings=tuple(
                    ControlRailBindingSnapshot(**binding)
                    for binding in item.get("rail_bindings", ())
                ),
                action_references=tuple(
                    ControlActionReferenceSnapshot(**reference)
                    for reference in item.get("action_references", ())
                ),
                model_dependencies=tuple(item.get("model_dependencies", ())),
                prompt_dependencies=tuple(item.get("prompt_dependencies", ())),
                execution_contract=tuple(
                    tuple(value) for value in item.get("execution_contract", ())
                ),
                tests=tuple(tuple(value) for value in item.get("tests", ())),
                checksum=str(item["checksum"]),
            )
            for item in payload.get("control_versions", ())
        ),
        control_bindings=tuple(
            GuardrailControlBindingSnapshot(
                control_id=str(item["control_id"]),
                control_version=int(item["control_version"]),
                parameter_values=tuple(
                    tuple(value) for value in item.get("parameter_values", ())
                ),
                enabled_rails=tuple(item.get("enabled_rails", ("input", "output"))),
            )
            for item in payload.get("control_bindings", ())
        ),
    )


def _nemo_config_from_payload(payload: dict[str, object]) -> NeMoConfigSnapshot:
    compiler_version = str(payload.get("compiler_version", ""))
    compiler_generation = _nemo_compiler_generation(compiler_version)
    if compiler_generation is not None and compiler_generation >= 6 and not payload.get(
        "runtime_profile"
    ):
        raise ControlPlaneError(
            "Stored NeMo v6 artifact is missing its explicit runtime_profile."
        )
    return NeMoConfigSnapshot(
        guardrail_id=str(payload["guardrail_id"]),
        guardrail_version=int(payload["guardrail_version"]),
        compiler_version=compiler_version,
        output_delivery=str(payload["output_delivery"]),
        config_yaml=str(payload["config_yaml"]),
        colang_content=str(payload["colang_content"]),
        prompts_yaml=str(payload.get("prompts_yaml", "")),
        action_bindings=tuple(
            NeMoActionBinding(
                id=str(item["id"]),
                risk=str(item["risk"]),
                stage=str(item["stage"]),
                phases=tuple(item["phases"]),
                on_unsafe=str(item["on_unsafe"]),
                escalation=str(item.get("escalation", "never")),
                timeout_ms=int(item.get("timeout_ms", 2_000)),
                parameters=tuple(
                    tuple(value) for value in item.get("parameters", ())
                ),
                control_id=(
                    str(item["control_id"]) if item.get("control_id") else None
                ),
                control_version=(
                    int(item["control_version"])
                    if item.get("control_version") is not None
                    else None
                ),
                flow_name=(
                    str(item["flow_name"]) if item.get("flow_name") else None
                ),
                action_name=(
                    str(item["action_name"])
                    if item["action_name"] is not None
                    else None
                ),
                action_version=(
                    str(item["action_version"])
                    if item["action_version"] is not None
                    else None
                ),
                parallel_group=(
                    str(item["parallel_group"])
                    if item.get("parallel_group")
                    else None
                ),
                execution_mode=str(item.get("execution_mode", "detect")),
                failure_mode=str(item.get("failure_mode", "fail_closed")),
                depends_on=tuple(item.get("depends_on", ())),
                result_var=(
                    str(item["result_var"])
                    if item.get("result_var")
                    else None
                ),
            )
            for item in payload.get("action_bindings", ())
        ),
        required_models=tuple(payload.get("required_models", ())),
        required_features=tuple(payload.get("required_features", ())),
        runtime_engine=str(payload.get("runtime_engine", "llmrails")),
        colang_version=str(payload.get("colang_version", "2.x")),
        runtime_profile=str(
            payload.get("runtime_profile")
            or _legacy_runtime_profile(payload)
        ),
        rail_flows=tuple(
            tuple(item) for item in payload.get("rail_flows", ())
        ),
        dependency_manifest=tuple(
            tuple(item) for item in payload.get("dependency_manifest", ())
        ),
        estimated_critical_path_ms=int(
            payload.get("estimated_critical_path_ms", 0)
        ),
    )


def _legacy_runtime_profile(payload: dict[str, object]) -> str:
    """Read pre-v6 immutable artifacts without re-compiling them."""
    engine = str(payload.get("runtime_engine", "llmrails"))
    colang_version = str(payload.get("colang_version", "2.x"))
    if engine == "iorails":
        return "iorails_native"
    if colang_version in {"1.0", "1"}:
        return "llmrails_colang1_standard"
    return "llmrails_colang2_programmable"


def _stored_runtime_profile(value: object) -> str:
    if value is None:
        return ""
    try:
        payload = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    return _nemo_config_from_payload(payload).runtime_profile


def _nemo_compiler_generation(value: str) -> int | None:
    match = re.fullmatch(r"tasklattice-nemo-config-v(\d+)", value)
    return int(match.group(1)) if match else None


def _reasoning_binding(value: object) -> AutomatedReasoningPolicyBinding | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ControlPlaneError("Stored Guardrail control has an invalid reasoning policy.")
    return AutomatedReasoningPolicyBinding(
        policy_id=str(value["policy_id"]),
        policy_version=str(value["policy_version"]),
        confidence_threshold=float(value["confidence_threshold"]),
    )


def _assignment_from_row(row: sqlite3.Row) -> GuardrailAssignment:
    return GuardrailAssignment(
        id=str(row["id"]),
        name=str(row["name"]),
        guardrail_id=str(row["guardrail_id"]),
        guardrail_version=int(row["guardrail_version"]),
        traffic_scope=traffic_scope_from_payload(
            json.loads(str(row["traffic_scope_json"]))
        ),
        enabled=bool(row["enabled"]),
        updated_at=str(row["updated_at"]),
    )


def _evaluation_from_row(row: sqlite3.Row) -> EvaluationRun:
    return EvaluationRun(
        id=str(row["id"]),
        guardrail_id=str(row["guardrail_id"]),
        guardrail_version=(
            int(row["guardrail_version"]) if row["guardrail_version"] is not None else None
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
    values = dict(payload)
    values["grounding_sources"] = tuple(values["grounding_sources"])
    values["findings"] = tuple(values["findings"])
    values["trace"] = tuple(values["trace"])
    return EvaluationCaseResult(**values)


def _test_case_from_row(row: sqlite3.Row) -> GuardrailTestCase:
    return GuardrailTestCase(
        id=str(row["id"]),
        guardrail_id=str(row["guardrail_id"]),
        name=str(row["name"]),
        risk=str(row["risk"]),
        phase=str(row["phase"]),
        content=str(row["content"]),
        expected_decision=str(row["expected_decision"]),
        origin=str(row["origin"]),
        updated_at=str(row["updated_at"]),
        trusted_instruction=str(row["trusted_instruction"]),
        target_source=str(row["target_source"]),
        query=str(row["query_content"]),
        grounding_sources=tuple(json.loads(str(row["grounding_sources_json"]))),
        expected_reasoning_result=(
            str(row["expected_reasoning_result"])
            if row["expected_reasoning_result"] is not None
            else None
        ),
        case_type=str(row["case_type"]),
        required=bool(row["required"]),
        expected_failure=(
            str(row["expected_failure"])
            if row["expected_failure"] is not None
            else None
        ),
        concurrency_group=(
            str(row["concurrency_group"])
            if row["concurrency_group"] is not None
            else None
        ),
    )


def _resolution_step(kind: str, name: str, detail: str):
    from ..runtime.contracts import EvaluationTraceStep

    return EvaluationTraceStep(
        id=f"resolution:{kind}", kind=kind, name=name, status="selected", detail=detail
    )


def _controls_json(controls: tuple[GuardrailControl, ...]) -> str:
    return _json([asdict(item) for item in controls])


def _control_configurations_json(
    configurations: tuple[GuardrailControlConfig, ...],
) -> str:
    return _json([asdict(item) for item in configurations])


def _native_control_bindings(
    controls: tuple[GuardrailControl, ...],
    existing: tuple[GuardrailControlBinding, ...],
) -> tuple[GuardrailControlBinding, ...]:
    """Attach every built-in policy choice to its immutable Control Version."""
    expected_builtin_ids = {
        f"builtin-{item.risk.replace('_', '-')}" for item in controls
    }
    bindings = [
        item
        for item in existing
        if not controls
        or not item.control_id.startswith("builtin-")
        or item.control_id in expected_builtin_ids
    ]
    selected = {(item.control_id, item.control_version) for item in bindings}
    for configured in controls:
        control_id = f"builtin-{configured.risk.replace('_', '-')}"
        key = (control_id, 1)
        if key in selected:
            continue
        definition = control(configured.risk)
        bindings.append(
            GuardrailControlBinding(
                control_id=control_id,
                control_version=1,
                enabled_rails=definition.default_phases,
            )
        )
        selected.add(key)
    return tuple(bindings)


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _new_credential() -> str:
    return "tali_integration_" + secrets.token_urlsafe(30)


def _key_hint(credential: str) -> str:
    return f"••••{credential[-6:]}"


def _now() -> str:
    return datetime.now(UTC).isoformat()
