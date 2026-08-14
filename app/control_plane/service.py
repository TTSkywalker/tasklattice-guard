from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime

from sqlalchemy import case, delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..integrations import adapter_definition
from ..nemo.action_registry import (
    BUILTIN_ACTION_CATALOG,
    ActionCatalog,
    action_name_for,
)
from ..persistence import Database, DatabaseLocator
from ..persistence.models import (
    DeploymentModel,
    EvidenceRecordModel,
    GuardrailModel,
    GuardrailVersionModel,
    IntegrationCredentialModel,
    IntegrationModel,
    PolicyRecordModel,
    PolicyValidationRunModel,
    PolicyVersionModel,
    RuntimeMetricEventModel,
    RuntimeStepMetricEventModel,
    TestCaseModel,
    ValidationRunModel,
)
from ..policy_library import policies as library_policies
from ..policy_library import policy as library_policy
from ..runtime.contracts import (
    ENFORCEMENT_ACTIONS,
    AutomatedReasoningPolicySnapshot,
    GuardrailPlanModule,
    GuardrailPlanSnapshot,
    GuardrailPlanStep,
    GuardrailPolicyBindingSnapshot,
    NeMoActionBinding,
    NeMoConfigSnapshot,
    PlanResolution,
    PolicyActionReferenceSnapshot,
    PolicyRailBindingSnapshot,
    PolicySourceSnapshot,
    PolicyVersionSnapshot,
    RequestContext,
    RuntimeTraceStep,
    flow_rule_id,
)
from .catalog import BUILTIN_POLICY_CAPABILITIES, runtime_capability
from .compiler import GuardrailCompiler
from .defaults import (
    DEFAULT_DEPLOYMENT_ID,
    DEFAULT_DEPLOYMENT_NAME,
    DEFAULT_GUARDRAIL_ID,
    DEFAULT_GUARDRAIL_NAME,
    DEFAULT_GUARDRAIL_POLICY_ID,
    DEFAULT_GUARDRAIL_PURPOSE,
    DEFAULT_GUARDRAIL_VERSION,
    is_default_deployment,
    is_default_guardrail,
)
from .domain import (
    ActionReference,
    AutomatedReasoningPolicyBinding,
    ConflictError,
    ControlPlaneError,
    Deployment,
    EvidenceRecord,
    Guardrail,
    GuardrailPolicyBinding,
    GuardrailTestCase,
    GuardrailTestCaseSpec,
    GuardrailVersion,
    Integration,
    IntegrationAuthenticationError,
    IntegrationCredential,
    IntegrationCredentialSecret,
    IntegrationRegistration,
    NotFoundError,
    PolicyDraft,
    PolicyParameterDefinition,
    PolicyRecord,
    PolicySourceFile,
    PolicyTestCaseDefinition,
    PolicyVersion,
    RailBinding,
    ResolvedPolicyCapability,
    RuntimeMetricEvent,
    RuntimeStepMetricEvent,
    TestCaseResult,
    TestedGuardrailVersion,
    TrafficScopeExpression,
    ValidationError,
    ValidationMetrics,
    ValidationRun,
)
from .filtering import (
    normalize_traffic_scope,
    traffic_condition_count,
    traffic_scope_from_payload,
    traffic_scope_matches,
    traffic_scope_signature,
    traffic_scope_specificity,
)
from .nemo_compiler import NeMoConfigCompiler
from .policy_tests import tests_for_builtin_policy


class ControlPlaneService:
    """Persist Policies, Guardrail versions, Deployments, and audit Evidence."""

    def __init__(
        self,
        database: Database | DatabaseLocator,
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
        self._database = database if isinstance(database, Database) else Database(database)
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
        self._plans: dict[tuple[str, int], GuardrailPlanSnapshot] = {}
        self._nemo_configs: dict[tuple[str, int], NeMoConfigSnapshot] = {}
        self._deployments: tuple[Deployment, ...] = ()
        self._credential_index: dict[str, str] = {}
        self._initialize()

    @property
    def database(self) -> Database:
        return self._database

    # Creation resources. These support the Guardrail workflow but are not
    # first-class navigation objects.

    def library_policies(self):
        return library_policies()

    def actions(self):
        return self._action_catalog.definitions()

    # Programmable Policies

    def policies(self) -> tuple[PolicyRecord, ...]:
        with self._database.session() as session:
            rows = session.scalars(
                select(PolicyRecordModel).order_by(
                    func.lower(PolicyRecordModel.name), PolicyRecordModel.id
                )
            ).all()
            return tuple(_policy_record_from_model(row) for row in rows)

    def policy_record(self, policy_id: str) -> PolicyRecord:
        with self._database.session() as session:
            row = session.get(PolicyRecordModel, policy_id)
            if row is None:
                raise NotFoundError(f"Policy {policy_id!r} was not found.")
            return _policy_record_from_model(row)

    def create_policy(
        self,
        *,
        name: str,
        description: str,
        owner: str,
        draft: PolicyDraft,
        source: str = "custom",
    ) -> PolicyRecord:
        clean_name = name.strip()
        if not clean_name:
            raise ValidationError("Policy name is required.")
        if source not in {"built-in", "custom"}:
            raise ValidationError("Policy source must be built-in or custom.")
        policy_id = f"policy-{uuid.uuid4().hex[:12]}"
        now = _now()
        self._validate_policy_draft(policy_id, draft, validate_dependencies=False)
        with self._database.transaction() as session:
            session.add(
                PolicyRecordModel(
                    id=policy_id,
                    name=clean_name,
                    description=description.strip(),
                    source=source,
                    owner=owner.strip() or "unknown",
                    draft_json=asdict(draft),
                    draft_revision=1,
                    updated_at=_datetime(now),
                )
            )
            self._insert_evidence_record(
                session,
                kind="policy.created",
                outcome="success",
                detail=f"Created Policy {clean_name}.",
            )
        return self.policy_record(policy_id)

    def update_policy_draft(
        self,
        policy_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        owner: str | None = None,
        draft: PolicyDraft | None = None,
    ) -> PolicyRecord:
        current = self.policy_record(policy_id)
        next_draft = current.draft if draft is None else draft
        if current.source == "built-in":
            raise ValidationError("Built-in Policies are system managed.")
        self._validate_policy_draft(
            policy_id, next_draft, validate_dependencies=False
        )
        next_name = current.name if name is None else name.strip()
        if not next_name:
            raise ValidationError("Policy name is required.")
        with self._database.transaction() as session:
            row = session.scalar(
                select(PolicyRecordModel)
                .where(PolicyRecordModel.id == policy_id)
                .with_for_update()
            )
            if row is None:
                raise NotFoundError(f"Policy {policy_id!r} was not found.")
            row.name = next_name
            row.description = (
                current.description if description is None else description.strip()
            )
            row.owner = current.owner if owner is None else owner.strip() or "unknown"
            row.draft_json = asdict(next_draft)
            row.draft_revision += 1
            row.updated_at = _utcnow()
        return self.policy_record(policy_id)

    def validate_policy(self, policy_id: str) -> dict[str, object]:
        record = self.policy_record(policy_id)
        self._validate_policy_draft(
            policy_id, record.draft, validate_dependencies=True
        )
        self._nemo_compiler.validate_policy(policy_id, record.draft)
        return {
            "valid": True,
            "policy_id": policy_id,
            "draft_revision": record.draft_revision,
            "colang_version": record.draft.colang_version,
            "rails": tuple(item.rail_type for item in record.draft.rail_bindings),
        }

    def publish_policy(self, policy_id: str) -> PolicyVersion:
        record = self.policy_record(policy_id)
        self.validate_policy(policy_id)
        if record.source == "custom" and record.draft.test_cases:
            latest = self.latest_policy_validation_run(policy_id)
            if (
                latest is None
                or int(latest["draft_revision"]) != record.draft_revision
                or latest["status"] != "passed"
            ):
                raise ValidationError(
                    "The current Policy draft must pass validation before publishing."
                )
        published_at = _now()
        with self._database.transaction() as session:
            locked_record = session.scalar(
                select(PolicyRecordModel)
                .where(PolicyRecordModel.id == policy_id)
                .with_for_update()
            )
            if locked_record is None:
                raise NotFoundError(f"Policy {policy_id!r} was not found.")
            latest = session.scalar(
                select(func.max(PolicyVersionModel.version)).where(
                    PolicyVersionModel.policy_id == policy_id
                )
            )
            version_number = int(latest or 0) + 1
            version_payload = {
                "policy_id": record.id,
                "version": version_number,
                "name": record.name,
                "description": record.description,
                "source": record.source,
                "owner": record.owner,
                **asdict(record.draft),
                "published_at": published_at,
            }
            checksum = hashlib.sha256(
                json.dumps(
                    version_payload, sort_keys=True, separators=(",", ":")
                ).encode()
            ).hexdigest()
            session.add(
                PolicyVersionModel(
                    policy_id=policy_id,
                    version=version_number,
                    version_json=version_payload,
                    checksum=checksum,
                    published_at=_datetime(published_at),
                )
            )
            self._insert_evidence_record(
                session,
                kind="policy.version.published",
                outcome="success",
                detail=f"Published Policy {record.name} version {version_number}.",
            )
        return self.policy_version(policy_id, version_number)

    def compile_policy_draft(
        self, policy_id: str
    ) -> tuple[GuardrailPlanSnapshot, NeMoConfigSnapshot]:
        """Compile one Policy draft through the production NeMo compiler for validation."""
        record = self.policy_record(policy_id)
        self.validate_policy(policy_id)
        revision = record.draft_revision
        draft = record.draft
        checksum_payload = {
            "policy_id": record.id,
            "draft_revision": revision,
            **asdict(draft),
        }
        checksum = hashlib.sha256(
            json.dumps(
                checksum_payload, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        candidate = PolicyVersion(
            policy_id=record.id,
            version=revision,
            name=record.name,
            description=record.description,
            source=record.source,
            owner=record.owner,
            colang_version=draft.colang_version,
            sources=draft.sources,
            parameter_schema=draft.parameter_schema,
            rail_bindings=draft.rail_bindings,
            action_references=draft.action_references,
            model_dependencies=draft.model_dependencies,
            prompt_dependencies=draft.prompt_dependencies,
            execution_contract=draft.execution_contract,
            test_cases=draft.test_cases,
            checksum=checksum,
            published_at="",
        )
        binding = GuardrailPolicyBindingSnapshot(
            policy_id=record.id,
            policy_version=str(revision),
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
            id=f"policy-preview-{record.id}",
            name=record.name,
            purpose=record.description or f"Evaluate {record.name}.",
            allowed_topics=(),
            restricted_topics=(),
            safety_level="balanced",
            output_delivery="window_buffered",
            draft_version=revision,
            active_version=None,
            updated_at=record.updated_at,
            policy_bindings=(
                GuardrailPolicyBinding(
                    policy_id=record.id,
                    policy_version=str(revision),
                    enabled_rails=binding.enabled_rails,
                ),
            ),
        )
        plan = self._compiler.compile(
            guardrail,
            revision,
            resolved_policies=tuple(
                ResolvedPolicyCapability(
                    native_risk,
                    next(
                        (
                            rail.on_unsafe
                            for rail in draft.rail_bindings
                            if rail.rail_type in binding.enabled_rails
                        ),
                        "reject",
                    ),
                )
                for native_risk in (
                    dict(draft.execution_contract).get("native_risk"),
                )
                if native_risk
            ),
            policy_versions=(_policy_version_snapshot(candidate),),
            policy_bindings=(binding,),
        )
        config = self._nemo_compiler.compile(plan)
        self._nemo_configs[(plan.guardrail_id, plan.guardrail_version)] = config
        return plan, config

    def save_policy_validation_run(
        self,
        *,
        policy_id: str,
        draft_revision: int,
        status: str,
        results: tuple[dict[str, object], ...],
    ) -> dict[str, object]:
        run_id = f"policy-test-{uuid.uuid4().hex[:12]}"
        created_at = _now()
        with self._database.transaction() as session:
            session.add(
                PolicyValidationRunModel(
                    id=run_id,
                    policy_id=policy_id,
                    draft_revision=draft_revision,
                    status=status,
                    results_json=list(results),
                    created_at=_datetime(created_at),
                ),
            )
        return {
            "id": run_id,
            "policy_id": policy_id,
            "draft_revision": draft_revision,
            "status": status,
            "results": list(results),
            "created_at": created_at,
        }

    def latest_policy_validation_run(
        self, policy_id: str
    ) -> dict[str, object] | None:
        self.policy_record(policy_id)
        with self._database.session() as session:
            row = session.scalar(
                select(PolicyValidationRunModel)
                .where(PolicyValidationRunModel.policy_id == policy_id)
                .order_by(
                    PolicyValidationRunModel.created_at.desc(),
                    PolicyValidationRunModel.id.desc(),
                )
                .limit(1)
            )
            if row is None:
                return None
            return {
                "id": row.id,
                "policy_id": row.policy_id,
                "draft_revision": row.draft_revision,
                "status": row.status,
                "results": row.results_json,
                "created_at": _iso(row.created_at),
            }

    def policy_versions(self, policy_id: str) -> tuple[PolicyVersion, ...]:
        self.policy_record(policy_id)
        with self._database.session() as session:
            rows = session.scalars(
                select(PolicyVersionModel)
                .where(PolicyVersionModel.policy_id == policy_id)
                .order_by(PolicyVersionModel.version.desc())
            ).all()
            return tuple(_policy_version_from_model(row) for row in rows)

    def policy_version(self, policy_id: str, version: int) -> PolicyVersion:
        with self._database.session() as session:
            row = session.get(PolicyVersionModel, (policy_id, version))
            if row is None:
                raise NotFoundError(
                    f"Policy Version {policy_id}@{version} was not found."
                )
            return _policy_version_from_model(row)

    # Guardrails

    def guardrails(self) -> tuple[Guardrail, ...]:
        with self._database.session() as session:
            rows = session.scalars(
                select(GuardrailModel).order_by(
                    func.lower(GuardrailModel.name), GuardrailModel.id
                )
            ).all()
            return tuple(_guardrail_from_model(row) for row in rows)

    def guardrail(self, guardrail_id: str) -> Guardrail:
        with self._database.session() as session:
            row = session.get(GuardrailModel, guardrail_id)
            if row is None:
                raise NotFoundError(f"Guardrail {guardrail_id!r} was not found.")
            return _guardrail_from_model(row)

    def create_guardrail(
        self,
        *,
        name: str,
        purpose: str | None = None,
        allowed_topics: tuple[str, ...] = (),
        restricted_topics: tuple[str, ...] = (),
        policy_bindings: tuple[GuardrailPolicyBinding, ...] = (),
        safety_level: str = "balanced",
        output_delivery: str = "window_buffered",
    ) -> Guardrail:
        clean_name = name.strip()
        if not clean_name:
            raise ValidationError("Guardrail name is required.")
        self._validate_guardrail_fields(
            purpose or "",
            safety_level,
            output_delivery,
            policy_bindings,
        )
        self._validate_guardrail_policy_bindings(policy_bindings)
        guardrail_id = f"guardrail-{uuid.uuid4().hex[:12]}"
        now = _now()
        with self._database.transaction() as session:
            session.add(
                GuardrailModel(
                    id=guardrail_id,
                    name=clean_name,
                    purpose=(purpose or "").strip(),
                    allowed_topics_json=list(allowed_topics),
                    restricted_topics_json=list(restricted_topics),
                    safety_level=safety_level,
                    output_delivery=output_delivery,
                    policy_bindings_json=[asdict(item) for item in policy_bindings],
                    draft_version=1,
                    active_version=None,
                    updated_at=_datetime(now),
                )
            )
            self._insert_evidence_record(
                session,
                kind="guardrail.created",
                outcome="success",
                guardrail_id=guardrail_id,
                detail=f"Created Guardrail {clean_name}.",
            )
        return self.guardrail(guardrail_id)

    def update_guardrail(
        self,
        guardrail_id: str,
        *,
        name: str | None = None,
        purpose: str | None = None,
        allowed_topics: tuple[str, ...] | None = None,
        restricted_topics: tuple[str, ...] | None = None,
        policy_bindings: tuple[GuardrailPolicyBinding, ...] | None = None,
        safety_level: str | None = None,
        output_delivery: str | None = None,
    ) -> Guardrail:
        if is_default_guardrail(guardrail_id):
            raise ValidationError("The Default Guardrail is managed by TaskLattice.")
        current = self.guardrail(guardrail_id)
        next_name = current.name if name is None else name.strip()
        next_purpose = current.purpose if purpose is None else purpose.strip()
        next_policy_bindings = (
            current.policy_bindings if policy_bindings is None else policy_bindings
        )
        next_level = current.safety_level if safety_level is None else safety_level
        next_delivery = current.output_delivery if output_delivery is None else output_delivery
        if not next_name:
            raise ValidationError("Guardrail name is required.")
        self._validate_guardrail_fields(
            next_purpose,
            next_level,
            next_delivery,
            next_policy_bindings,
        )
        self._validate_guardrail_policy_bindings(next_policy_bindings)
        with self._database.transaction() as session:
            row = session.scalar(
                select(GuardrailModel)
                .where(GuardrailModel.id == guardrail_id)
                .with_for_update()
            )
            if row is None:
                raise NotFoundError(f"Guardrail {guardrail_id!r} was not found.")
            row.name = next_name
            row.purpose = next_purpose
            row.allowed_topics_json = list(
                current.allowed_topics if allowed_topics is None else allowed_topics
            )
            row.restricted_topics_json = list(
                current.restricted_topics
                if restricted_topics is None
                else restricted_topics
            )
            row.safety_level = next_level
            row.output_delivery = next_delivery
            row.policy_bindings_json = [asdict(item) for item in next_policy_bindings]
            row.draft_version += 1
            row.updated_at = _utcnow()
            self._insert_evidence_record(
                session,
                kind="guardrail.updated",
                outcome="success",
                guardrail_id=guardrail_id,
                detail=f"Updated safety intent for {next_name}; tests are now stale.",
            )
        return self.guardrail(guardrail_id)

    def _compile_guardrail(
        self,
        guardrail: Guardrail,
        version: int,
    ) -> GuardrailPlanSnapshot:
        resolved_versions: list[PolicyVersionSnapshot] = []
        resolved_bindings: list[GuardrailPolicyBindingSnapshot] = []
        resolved_policies: list[ResolvedPolicyCapability] = []
        for binding in guardrail.policy_bindings:
            static_policy = library_policy(binding.policy_id)
            if static_policy is not None:
                if binding.policy_version != static_policy.version:
                    raise ValidationError(
                        f"Policy {binding.policy_id!r} must pin version "
                        f"{static_policy.version}."
                    )
                enabled_rails = binding.enabled_rails or static_policy.stages
                if not any(item.risk == "builtin_content_filter" for item in resolved_policies):
                    resolved_policies.append(
                        ResolvedPolicyCapability(
                            "builtin_content_filter",
                            binding.action or "reject",
                        )
                    )
                resolved_bindings.append(
                    GuardrailPolicyBindingSnapshot(
                        policy_id=binding.policy_id,
                        policy_version=binding.policy_version,
                        action=binding.action,
                        parameter_values=binding.parameter_values,
                        enabled_rule_ids=binding.enabled_rule_ids,
                        rule_actions=binding.rule_actions,
                        enabled_rails=enabled_rails,
                    )
                )
                continue

            try:
                stored_version = int(binding.policy_version)
            except ValueError as error:
                raise ValidationError(
                    f"Policy {binding.policy_id!r} requires a numeric published version."
                ) from error
            policy_version = self.policy_version(binding.policy_id, stored_version)
            enabled_rails = binding.enabled_rails or tuple(
                dict.fromkeys(item.rail_type for item in policy_version.rail_bindings)
            )
            resolved_versions.append(_policy_version_snapshot(policy_version))
            native_risk = dict(policy_version.execution_contract).get("native_risk")
            if native_risk and native_risk not in {
                item.risk for item in resolved_policies
            }:
                action = binding.action or next(
                    (
                        item.on_unsafe
                        for item in policy_version.rail_bindings
                        if item.rail_type in enabled_rails
                    ),
                    "reject",
                )
                resolved_policies.append(
                    ResolvedPolicyCapability(
                        native_risk,
                        action,
                        binding.reasoning_policy,
                    )
                )
            resolved_parameters = {
                item.name: item.default
                for item in policy_version.parameter_schema
                if item.default is not None
            }
            resolved_parameters.update(dict(binding.parameter_values))
            resolved_bindings.append(
                GuardrailPolicyBindingSnapshot(
                    policy_id=binding.policy_id,
                    policy_version=binding.policy_version,
                    action=binding.action,
                    parameter_values=tuple(sorted(resolved_parameters.items())),
                    enabled_rule_ids=binding.enabled_rule_ids,
                    rule_actions=binding.rule_actions,
                    enabled_rails=enabled_rails,
                )
            )
        return self._compiler.compile(
            guardrail,
            version,
            resolved_policies=tuple(resolved_policies),
            policy_versions=tuple(resolved_versions),
            policy_bindings=tuple(resolved_bindings),
        )

    def compile_draft(self, guardrail_id: str) -> GuardrailPlanSnapshot:
        guardrail = self.guardrail(guardrail_id)
        plan = self._compile_guardrail(
            guardrail, self._next_guardrail_version(guardrail_id)
        )
        # Draft validation uses the same compiler/runtime as released traffic,
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
        policy_bindings: tuple[GuardrailPolicyBinding, ...] = (),
        safety_level: str = "balanced",
        output_delivery: str = "window_buffered",
    ) -> tuple[GuardrailPlanSnapshot, NeMoConfigSnapshot, str]:
        """Compile a creation-flow candidate without persisting a Guardrail."""
        self._validate_guardrail_fields(
            purpose,
            safety_level,
            output_delivery,
            policy_bindings,
        )
        self._validate_guardrail_policy_bindings(policy_bindings)
        guardrail = Guardrail(
            id="guardrail-candidate-preview",
            name=name.strip() or "Guardrail candidate",
            purpose=purpose.strip(),
            allowed_topics=allowed_topics,
            restricted_topics=restricted_topics,
            safety_level=safety_level,
            output_delivery=output_delivery,
            draft_version=1,
            active_version=None,
            updated_at=_now(),
            policy_bindings=policy_bindings,
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
        """Create the immutable deployable snapshot after a passing Validation Run."""
        guardrail = self.guardrail(guardrail_id)
        latest = self.latest_validation_run(guardrail_id)
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
                with self._database.transaction() as session:
                    run = session.get(ValidationRunModel, latest.id)
                    if run is not None:
                        run.guardrail_version = existing.version
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
        with self._database.transaction() as session:
            locked_guardrail = session.scalar(
                select(GuardrailModel)
                .where(GuardrailModel.id == guardrail_id)
                .with_for_update()
            )
            if locked_guardrail is None:
                raise NotFoundError(f"Guardrail {guardrail_id!r} was not found.")
            current_max = session.scalar(
                select(func.max(GuardrailVersionModel.version)).where(
                    GuardrailVersionModel.guardrail_id == guardrail_id
                )
            )
            if int(current_max or 0) + 1 != next_version:
                raise ConflictError(
                    "Guardrail changed while the tested version was being activated."
                )
            session.add(
                GuardrailVersionModel(
                    guardrail_id=guardrail_id,
                    version=next_version,
                    source_draft_version=guardrail.draft_version,
                    guardrail_json=asdict(guardrail),
                    plan_json=asdict(plan),
                    nemo_config_json=asdict(nemo_config),
                    compiler_version=nemo_config.compiler_version,
                    plan_checksum=checksum,
                    runtime_engine=nemo_config.runtime_engine,
                    config_checksum=checksum,
                    execution_mode="nemo_only",
                    created_at=_datetime(created_at),
                )
            )
            session.flush()
            locked_guardrail.active_version = next_version
            locked_guardrail.updated_at = _datetime(created_at)
            session.execute(
                update(DeploymentModel)
                .where(DeploymentModel.guardrail_id == guardrail_id)
                .values(
                    guardrail_version=next_version,
                    updated_at=_datetime(created_at),
                )
            )
            run = session.get(ValidationRunModel, latest.id)
            if run is not None:
                run.guardrail_version = next_version
            self._insert_evidence_record(
                session,
                kind="guardrail.version.created",
                outcome="passed",
                guardrail_id=guardrail_id,
                detail=f"Tests passed; created a new immutable version of {guardrail.name}.",
            )
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
        with self._database.session() as session:
            rows = session.scalars(
                select(GuardrailVersionModel)
                .where(GuardrailVersionModel.guardrail_id == guardrail_id)
                .order_by(GuardrailVersionModel.version.desc())
            ).all()
            return tuple(
                GuardrailVersion(
                    guardrail_id=row.guardrail_id,
                    version=row.version,
                    source_draft_version=row.source_draft_version,
                    compiler_version=row.compiler_version,
                    plan_checksum=row.plan_checksum,
                    created_at=_iso(row.created_at),
                    active=row.version == guardrail.active_version,
                    runtime_engine=row.runtime_engine or "nemo",
                    runtime_profile=_stored_runtime_profile(row.nemo_config_json),
                    config_checksum=row.config_checksum or row.plan_checksum,
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
        with self._database.transaction() as session:
            row = session.scalar(
                select(GuardrailModel)
                .where(GuardrailModel.id == guardrail_id)
                .with_for_update()
            )
            if row is None:
                raise NotFoundError(f"Guardrail {guardrail_id!r} was not found.")
            row.active_version = version
            row.updated_at = _datetime(now)
            session.execute(
                update(DeploymentModel)
                .where(DeploymentModel.guardrail_id == guardrail_id)
                .values(guardrail_version=version, updated_at=_datetime(now))
            )
            self._insert_evidence_record(
                session,
                kind="guardrail.version.rolled_back",
                outcome="success",
                guardrail_id=guardrail_id,
                detail=f"Rolled {guardrail.name} back to immutable version {version}.",
            )
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
        with self._database.session() as session:
            row = session.get(GuardrailVersionModel, (guardrail_id, version))
            if row is None:
                raise NotFoundError("Guardrail Version was not found.")
            return _plan_from_payload(row.plan_json)

    def nemo_config(self, guardrail_id: str, version: int) -> NeMoConfigSnapshot:
        config = self._nemo_configs.get((guardrail_id, version))
        if config is not None:
            return config
        with self._database.session() as session:
            row = session.get(GuardrailVersionModel, (guardrail_id, version))
            if row is None or row.nemo_config_json is None:
                raise NotFoundError("Guardrail Version NeMo configuration was not found.")
            return _nemo_config_from_payload(row.nemo_config_json)

    def active_plan_keys(self) -> tuple[tuple[str, int], ...]:
        return tuple(
            dict.fromkeys(
                (item.guardrail_id, item.guardrail_version)
                for item in self._deployments
                if item.enabled
            )
        )

    # Test evidence

    def save_validation_run(
        self,
        *,
        guardrail_id: str,
        guardrail_version: int | None,
        source_draft_version: int,
        status: str,
        metrics: ValidationMetrics,
        results: tuple[TestCaseResult, ...],
    ) -> ValidationRun:
        run_id = f"validation-{uuid.uuid4().hex[:12]}"
        created_at = _now()
        with self._database.transaction() as session:
            session.add(
                ValidationRunModel(
                    id=run_id,
                    guardrail_id=guardrail_id,
                    guardrail_version=guardrail_version,
                    source_draft_version=source_draft_version,
                    status=status,
                    metrics_json=asdict(metrics),
                    results_json=[asdict(item) for item in results],
                    created_at=_datetime(created_at),
                ),
            )
            self._insert_evidence_record(
                session,
                kind="guardrail.validation.completed",
                outcome=status,
                guardrail_id=guardrail_id,
                detail=f"Guardrail validation completed with {metrics.compliance_rate:.1f}% compliance.",
            )
        return self.validation_run(run_id)

    def validation_runs(self, guardrail_id: str | None = None) -> tuple[ValidationRun, ...]:
        query = select(ValidationRunModel)
        if guardrail_id:
            query = query.where(ValidationRunModel.guardrail_id == guardrail_id)
        query = query.order_by(
            ValidationRunModel.created_at.desc(), ValidationRunModel.id.desc()
        )
        with self._database.session() as session:
            rows = session.scalars(query).all()
            return tuple(_validation_run_from_model(row) for row in rows)

    def validation_run(self, run_id: str) -> ValidationRun:
        with self._database.session() as session:
            row = session.get(ValidationRunModel, run_id)
            if row is None:
                raise NotFoundError("Validation Run was not found.")
            return _validation_run_from_model(row)

    def latest_validation_run(self, guardrail_id: str) -> ValidationRun | None:
        runs = self.validation_runs(guardrail_id)
        return runs[0] if runs else None

    def test_cases(self, guardrail_id: str) -> tuple[GuardrailTestCase, ...]:
        self.guardrail(guardrail_id)
        with self._database.session() as session:
            rows = session.scalars(
                select(TestCaseModel)
                .where(TestCaseModel.guardrail_id == guardrail_id)
                .order_by(
                    case((TestCaseModel.origin == "generated", 0), else_=1),
                    func.lower(TestCaseModel.name),
                    TestCaseModel.id,
                )
            ).all()
            return tuple(_test_case_from_model(row) for row in rows)

    def sync_generated_test_cases(
        self,
        guardrail_id: str,
        cases: tuple[GuardrailTestCaseSpec, ...],
    ) -> tuple[GuardrailTestCase, ...]:
        """Refresh generated cases while keeping reviewed custom cases intact."""
        guardrail = self.guardrail(guardrail_id)
        now = _now()
        with self._database.transaction() as session:
            session.execute(
                delete(TestCaseModel).where(
                    TestCaseModel.guardrail_id == guardrail_id,
                    TestCaseModel.origin == "generated",
                )
            )
            for case in cases:
                self._validate_test_case(
                    guardrail,
                    str(case.name),
                    str(case.policy_id),
                    str(case.phase),
                    str(case.content),
                    str(case.expected_decision),
                    case.target_source,
                    case.query,
                    case.grounding_sources,
                    case.expected_reasoning_result,
                )
                session.add(
                    TestCaseModel(
                        id=str(case.id),
                        guardrail_id=guardrail_id,
                        name=str(case.name),
                        policy_id=str(case.policy_id),
                        phase=str(case.phase),
                        content=str(case.content),
                        trusted_instruction=case.trusted_instruction,
                        target_source=case.target_source,
                        expected_decision=str(case.expected_decision),
                        query_content=case.query,
                        grounding_sources_json=list(case.grounding_sources),
                        expected_reasoning_result=case.expected_reasoning_result,
                        case_type=case.case_type,
                        required=case.required,
                        expected_failure=case.expected_failure,
                        concurrency_group=case.concurrency_group,
                        source_policy_id=case.source_policy_id,
                        source_policy_version=case.source_policy_version,
                        source_case_id=case.source_case_id,
                        covered_rule_ids_json=list(case.covered_rule_ids),
                        origin="generated",
                        updated_at=_datetime(now),
                    )
                )
        return self.test_cases(guardrail_id)

    def create_test_case(
        self,
        guardrail_id: str,
        *,
        name: str,
        policy_id: str,
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
            policy_id,
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
        with self._database.transaction() as session:
            session.add(
                TestCaseModel(
                    id=case_id,
                    guardrail_id=guardrail_id,
                    name=name.strip(),
                    policy_id=policy_id,
                    phase=phase,
                    content=content.strip(),
                    trusted_instruction=trusted_instruction.strip(),
                    target_source=target_source,
                    expected_decision=expected_decision,
                    query_content=query.strip(),
                    grounding_sources_json=[
                        item.strip() for item in grounding_sources if item.strip()
                    ],
                    expected_reasoning_result=expected_reasoning_result,
                    case_type="unit",
                    required=True,
                    expected_failure=None,
                    concurrency_group=None,
                    source_policy_id=None,
                    source_policy_version=None,
                    source_case_id=None,
                    covered_rule_ids_json=[],
                    origin="custom",
                    updated_at=_datetime(now),
                )
            )
            guardrail_row = session.scalar(
                select(GuardrailModel)
                .where(GuardrailModel.id == guardrail_id)
                .with_for_update()
            )
            assert guardrail_row is not None
            guardrail_row.draft_version += 1
            guardrail_row.updated_at = _datetime(now)
            self._insert_evidence_record(
                session,
                kind="guardrail.test_case.created",
                outcome="success",
                guardrail_id=guardrail_id,
                detail=(
                    f"Added reviewed Test Case {name.strip()} for Policy {policy_id}."
                ),
            )
        return next(item for item in self.test_cases(guardrail_id) if item.id == case_id)

    def delete_test_case(self, guardrail_id: str, case_id: str) -> None:
        self.guardrail(guardrail_id)
        with self._database.transaction() as session:
            row = session.get(TestCaseModel, (case_id, guardrail_id))
            if row is None:
                raise NotFoundError("Guardrail test case was not found.")
            name = row.name
            session.delete(row)
            guardrail_row = session.scalar(
                select(GuardrailModel)
                .where(GuardrailModel.id == guardrail_id)
                .with_for_update()
            )
            assert guardrail_row is not None
            guardrail_row.draft_version += 1
            guardrail_row.updated_at = _utcnow()
            self._insert_evidence_record(
                session,
                kind="guardrail.test_case.deleted",
                outcome="success",
                guardrail_id=guardrail_id,
                detail=f"Removed test case {name}.",
            )

    # Deployments

    def deployments(self) -> tuple[Deployment, ...]:
        with self._database.session() as session:
            rows = session.scalars(
                select(DeploymentModel).order_by(
                    func.lower(DeploymentModel.name), DeploymentModel.id
                )
            ).all()
            return tuple(_deployment_from_model(row) for row in rows)

    def deployment(self, deployment_id: str) -> Deployment:
        item = next((item for item in self.deployments() if item.id == deployment_id), None)
        if item is None:
            raise NotFoundError("Deployment was not found.")
        return item

    def create_deployment(
        self,
        *,
        name: str,
        guardrail_id: str,
        traffic_scope: TrafficScopeExpression,
        enabled: bool = True,
    ) -> Deployment:
        guardrail = self.guardrail(guardrail_id)
        if is_default_guardrail(guardrail_id):
            raise ValidationError(
                "The Default Guardrail is reserved for the Default Deployment."
            )
        tested_current = any(
            item.source_draft_version == guardrail.draft_version
            for item in self.versions(guardrail_id)
        )
        if guardrail.active_version is None or not tested_current:
            raise ValidationError("Validate the current Guardrail before creating a Deployment.")
        if not name.strip():
            raise ValidationError("Deployment name is required.")
        normalized = normalize_traffic_scope(traffic_scope)
        if not normalized.conditions:
            raise ValidationError(
                "Unmatched traffic is already covered by the Default Deployment."
            )
        signature = traffic_scope_signature(normalized)
        duplicate = next(
            (
                item
                for item in self.deployments()
                if traffic_scope_signature(item.traffic_scope) == signature
            ),
            None,
        )
        if duplicate is not None:
            raise ValidationError(
                f"This Traffic Scope is already used by Deployment {duplicate.name}."
            )

        deployment_id = f"deployment-{uuid.uuid4().hex[:12]}"
        now = _now()
        with self._database.transaction() as session:
            session.add(
                DeploymentModel(
                    id=deployment_id,
                    name=name.strip(),
                    guardrail_id=guardrail_id,
                    guardrail_version=guardrail.active_version,
                    traffic_scope_json=asdict(normalized),
                    enabled=enabled,
                    updated_at=_datetime(now),
                )
            )
            self._insert_evidence_record(
                session,
                kind="deployment.created",
                outcome="success",
                guardrail_id=guardrail_id,
                deployment_id=deployment_id,
                detail=f"Created Deployment {name.strip()}.",
            )
        self._reload_runtime()
        return self.deployment(deployment_id)

    def set_deployment_enabled(self, deployment_id: str, enabled: bool) -> Deployment:
        current = self.deployment(deployment_id)
        if is_default_deployment(deployment_id):
            if not enabled:
                raise ValidationError("The Default Deployment is always enabled.")
            return current
        with self._database.transaction() as session:
            row = session.get(DeploymentModel, deployment_id)
            assert row is not None
            row.enabled = enabled
            row.updated_at = _utcnow()
            self._insert_evidence_record(
                session,
                kind="deployment.updated",
                outcome="success",
                guardrail_id=current.guardrail_id,
                deployment_id=deployment_id,
                detail=f"Deployment {current.name} {'enabled' if enabled else 'paused'}.",
            )
        self._reload_runtime()
        return self.deployment(deployment_id)

    # Runtime resolution

    def resolve(self, context: RequestContext) -> PlanResolution:
        integration = self.integration(context.integration_id) if context.integration_id else None
        candidates = [
            item
            for item in self._deployments
            if item.enabled
            and traffic_scope_matches(item.traffic_scope, context)
            and (item.guardrail_id, item.guardrail_version) in self._plans
        ]
        if not candidates:
            raise ControlPlaneError("No Deployment matches this model interaction.")
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
        selected_default = is_default_deployment(selected.id)
        trace.extend((
            _resolution_step(
                "deployment",
                selected.name,
                (
                    "No explicit Deployment matched; selected the system-managed baseline."
                    if selected_default
                    else f"Matched {len(candidates)} Deployment Traffic Scope(s); selected "
                    f"{traffic_condition_count(selected.traffic_scope)} condition(s) by specificity."
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
            deployment_id=selected.id,
            integration_id=integration.id if integration else None,
            trace=tuple(trace),
        )

    # Integrations

    def integrations(self) -> tuple[Integration, ...]:
        with self._database.session() as session:
            rows = session.scalars(
                select(IntegrationModel).order_by(
                    func.lower(IntegrationModel.name), IntegrationModel.id
                )
            ).all()
            return tuple(self._integration_from_model(session, row) for row in rows)

    def integration(self, integration_id: str) -> Integration:
        with self._database.session() as session:
            row = session.get(IntegrationModel, integration_id)
            if row is None:
                raise NotFoundError("Integration was not found.")
            return self._integration_from_model(session, row)

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
        with self._database.transaction() as session:
            session.add(
                IntegrationModel(
                    id=integration_id,
                    adapter_id=adapter.id,
                    name=name.strip(),
                    description=description.strip(),
                    enabled=True,
                    first_seen_at=None,
                    last_seen_at=None,
                    input_seen_at=None,
                    output_seen_at=None,
                    request_count=0,
                    error_count=0,
                    last_error_at=None,
                    created_at=_datetime(now),
                    updated_at=_datetime(now),
                )
            )
            session.flush()
            credential = self._insert_credential(session, integration_id, "generated")
            self._insert_evidence_record(
                session,
                kind="integration.registered",
                outcome="success",
                integration_id=integration_id,
                detail=f"Registered {adapter.name} Integration {name.strip()}.",
            )
        self._reload_runtime()
        return IntegrationRegistration(self.integration(integration_id), credential)

    def set_integration_enabled(
        self, integration_id: str, enabled: bool
    ) -> Integration:
        current = self.integration(integration_id)
        with self._database.transaction() as session:
            row = session.get(IntegrationModel, integration_id)
            assert row is not None
            row.enabled = enabled
            row.updated_at = _utcnow()
            self._insert_evidence_record(
                session,
                kind="integration.updated",
                outcome="success",
                integration_id=integration_id,
                detail=f"Integration {current.name} {'enabled' if enabled else 'disabled'}.",
            )
        return self.integration(integration_id)

    def rotate_integration_credential(
        self, integration_id: str
    ) -> IntegrationRegistration:
        self.integration(integration_id)
        with self._database.transaction() as session:
            credential = self._insert_credential(
                session, integration_id, "rotated"
            )
            self._insert_evidence_record(
                session,
                kind="integration.credential.rotated",
                outcome="success",
                integration_id=integration_id,
                detail="Created a new Integration credential.",
            )
        self._reload_runtime()
        return IntegrationRegistration(self.integration(integration_id), credential)

    def revoke_integration_credential(
        self, integration_id: str, credential_id: str
    ) -> None:
        self.integration(integration_id)
        with self._database.transaction() as session:
            row = session.scalar(
                select(IntegrationCredentialModel)
                .where(
                    IntegrationCredentialModel.id == credential_id,
                    IntegrationCredentialModel.integration_id == integration_id,
                    IntegrationCredentialModel.revoked_at.is_(None),
                )
                .with_for_update()
            )
            if row is None:
                raise NotFoundError("Integration credential was not found.")
            active_count = session.scalar(
                select(func.count())
                .select_from(IntegrationCredentialModel)
                .where(
                    IntegrationCredentialModel.integration_id == integration_id,
                    IntegrationCredentialModel.revoked_at.is_(None),
                )
            )
            if int(active_count or 0) <= 1:
                raise ConflictError(
                    "An Integration must keep at least one active credential."
                )
            row.revoked_at = _utcnow()
            self._insert_evidence_record(
                session,
                kind="integration.credential.revoked",
                outcome="success",
                integration_id=integration_id,
                detail="Revoked an Integration credential.",
            )
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
        now = _utcnow()
        with self._database.transaction() as session:
            row = session.scalar(
                select(IntegrationModel)
                .where(IntegrationModel.id == integration_id)
                .with_for_update()
            )
            if row is None:
                raise NotFoundError("Integration was not found.")
            row.first_seen_at = row.first_seen_at or now
            row.last_seen_at = now
            if phase == "input":
                row.input_seen_at = now
            else:
                row.output_seen_at = now
            row.request_count += 1
            if not success:
                row.error_count += 1
                row.last_error_at = now
            row.updated_at = now

    # Evidence and system summary

    def evidence_records(self, limit: int = 100) -> tuple[EvidenceRecord, ...]:
        with self._database.session() as session:
            rows = session.scalars(
                select(EvidenceRecordModel)
                .order_by(
                    EvidenceRecordModel.created_at.desc(),
                    EvidenceRecordModel.id.desc(),
                )
                .limit(max(1, min(limit, 500)))
            ).all()
            return tuple(
                EvidenceRecord(
                    id=row.id,
                    created_at=_iso(row.created_at),
                    kind=row.kind,
                    outcome=row.outcome,
                    guardrail_id=row.guardrail_id,
                    deployment_id=row.deployment_id,
                    risk=row.risk,
                    detail=row.detail,
                    integration_id=row.integration_id,
                )
                for row in rows
            )

    def runtime_metrics(
        self,
        *,
        since: str,
    ) -> tuple[RuntimeMetricEvent, ...]:
        with self._database.session() as session:
            rows = session.scalars(
                select(RuntimeMetricEventModel)
                .where(RuntimeMetricEventModel.created_at >= _datetime(since))
                .order_by(
                    RuntimeMetricEventModel.created_at.desc(),
                    RuntimeMetricEventModel.id.desc(),
                )
            ).all()
            return tuple(
                RuntimeMetricEvent(
                    id=row.id,
                    created_at=_iso(row.created_at),
                    guardrail_id=row.guardrail_id,
                    guardrail_version=row.guardrail_version,
                    deployment_id=row.deployment_id,
                    integration_id=row.integration_id,
                    protocol=row.protocol,
                    phase=row.phase,
                    outcome=row.outcome,
                    action=row.action,
                    risk=row.risk,
                    latency_ms=row.latency_ms,
                    timed_out=row.timed_out,
                    module_invocations=row.module_invocations,
                    evaluator_invocations=row.evaluator_invocations,
                    rail_invocations=row.rail_invocations,
                    action_invocations=row.action_invocations,
                    model_invocations=row.model_invocations,
                    queue_latency_ms=row.queue_latency_ms,
                    cache_hits=row.cache_hits,
                    cache_misses=row.cache_misses,
                    runtime_engine=row.runtime_engine,
                    config_checksum=row.config_checksum,
                    fail_closed=row.fail_closed,
                    active_concurrency=row.active_concurrency,
                    provider_latency_ms=row.provider_latency_ms,
                    slo_breached=row.slo_breached,
                )
                for row in rows
            )

    def runtime_step_metrics(
        self,
        *,
        since: str,
    ) -> tuple[RuntimeStepMetricEvent, ...]:
        with self._database.session() as session:
            rows = session.scalars(
                select(RuntimeStepMetricEventModel)
                .where(RuntimeStepMetricEventModel.created_at >= _datetime(since))
                .order_by(
                    RuntimeStepMetricEventModel.created_at.desc(),
                    RuntimeStepMetricEventModel.id.desc(),
                )
            ).all()
            return tuple(
                RuntimeStepMetricEvent(
                    id=row.id,
                    created_at=_iso(row.created_at),
                    guardrail_id=row.guardrail_id,
                    guardrail_version=row.guardrail_version,
                    deployment_id=row.deployment_id,
                    integration_id=row.integration_id,
                    protocol=row.protocol,
                    phase=row.phase,
                    kind=row.kind,
                    name=row.name,
                    risk=row.risk,
                    stage=row.stage,
                    outcome=row.outcome,
                    latency_ms=row.latency_ms,
                    timed_out=row.timed_out,
                    runtime_engine=row.runtime_engine,
                    config_checksum=row.config_checksum,
                    policy_id=row.policy_id,
                    policy_version=row.policy_version,
                    rail_type=row.rail_type,
                    flow_name=row.flow_name,
                    action_name=row.action_name,
                    action_version=row.action_version,
                    parallel_group=row.parallel_group,
                    timeout_ms=row.timeout_ms,
                    provider_latency_ms=row.provider_latency_ms,
                )
                for row in rows
            )

    def record_runtime_steps(
        self,
        *,
        guardrail_id: str | None,
        guardrail_version: int | None,
        deployment_id: str | None,
        integration_id: str | None,
        protocol: str,
        phase: str,
        trace: tuple[RuntimeTraceStep, ...],
        runtime_engine: str,
        config_checksum: str,
    ) -> None:
        if guardrail_id is None or guardrail_version is None:
            return
        rows: list[RuntimeStepMetricEventModel] = []
        now = _utcnow()
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
                RuntimeStepMetricEventModel(
                    id=f"step-metric-{uuid.uuid4().hex[:12]}",
                    created_at=now,
                    guardrail_id=guardrail_id,
                    guardrail_version=guardrail_version,
                    deployment_id=deployment_id,
                    integration_id=integration_id,
                    protocol=protocol,
                    phase=phase,
                    kind=kind,
                    name=step.name[:256],
                    risk=step.risk,
                    stage=step.stage,
                    outcome=step.status,
                    latency_ms=max(0, step.duration_ms),
                    timed_out=step.timed_out,
                    runtime_engine=step.engine or runtime_engine,
                    config_checksum=step.config_checksum or config_checksum,
                    policy_id=step.policy_id,
                    policy_version=step.policy_version,
                    rail_type=step.rail_type,
                    flow_name=step.flow_name,
                    action_name=step.action_name,
                    action_version=step.action_version,
                    parallel_group=step.parallel_group,
                    timeout_ms=step.timeout_ms,
                    provider_latency_ms=max(0, step.provider_latency_ms),
                )
            )
        if not rows:
            return
        with self._database.transaction() as session:
            session.add_all(rows)

    def record_decision(
        self,
        *,
        outcome: str,
        guardrail_id: str | None,
        deployment_id: str | None,
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
        now = _utcnow()
        with self._database.transaction() as session:
            self._insert_evidence_record(
                session,
                kind="interaction.decision",
                outcome=outcome,
                guardrail_id=guardrail_id,
                deployment_id=deployment_id,
                integration_id=integration_id,
                risk=risk,
                detail=detail,
            )
            session.add(
                RuntimeMetricEventModel(
                    id=f"metric-{uuid.uuid4().hex[:12]}",
                    created_at=now,
                    guardrail_id=guardrail_id,
                    guardrail_version=guardrail_version,
                    deployment_id=deployment_id,
                    integration_id=integration_id,
                    protocol=protocol,
                    phase=phase,
                    outcome=outcome,
                    action=action,
                    risk=risk,
                    latency_ms=max(0, latency_ms),
                    timed_out=timed_out,
                    module_invocations=max(0, module_invocations),
                    evaluator_invocations=max(0, evaluator_invocations),
                    rail_invocations=max(0, rail_invocations),
                    action_invocations=max(0, action_invocations),
                    model_invocations=max(0, model_invocations),
                    queue_latency_ms=max(0, queue_latency_ms),
                    cache_hits=max(0, cache_hits),
                    cache_misses=max(0, cache_misses),
                    runtime_engine=runtime_engine,
                    config_checksum=config_checksum,
                    fail_closed=fail_closed,
                    active_concurrency=max(0, active_concurrency),
                    provider_latency_ms=max(0, provider_latency_ms),
                    slo_breached=latency_ms > self._runtime_p99_budget_ms,
                ),
            )

    def summary(self) -> dict[str, object]:
        integrations = self.integrations()
        active = [item for item in self._deployments if item.enabled]
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
            "active_deployments": len(active),
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
        self._database.create_schema()
        try:
            with self._database.transaction() as session:
                has_evidence = session.scalar(
                    select(EvidenceRecordModel.id).limit(1)
                )
                if has_evidence is None:
                    self._seed(session)
                self._ensure_builtin_policies(session)
        except IntegrityError as error:
            # Another replica completed the idempotent product seed first.
            with self._database.session() as session:
                seeded = all(
                    session.get(PolicyVersionModel, (item.policy_id, 1)) is not None
                    for item in BUILTIN_POLICY_CAPABILITIES
                    if item.policy_id is not None
                )
            if not seeded:
                raise ControlPlaneError(
                    "The built-in Policy seed could not be initialized."
                ) from error
        # The default Guardrail compiler reads released built-ins through a new
        # Session, so seed them in a preceding transaction.
        try:
            with self._database.transaction() as session:
                self._ensure_product_defaults(session)
        except IntegrityError as error:
            # The schema bootstrap or another replica installed the defaults.
            with self._database.session() as session:
                seeded = (
                    session.get(GuardrailModel, DEFAULT_GUARDRAIL_ID) is not None
                    and session.get(
                        GuardrailVersionModel,
                        (DEFAULT_GUARDRAIL_ID, DEFAULT_GUARDRAIL_VERSION),
                    )
                    is not None
                    and session.get(DeploymentModel, DEFAULT_DEPLOYMENT_ID) is not None
                )
            if not seeded:
                raise ControlPlaneError(
                    "The Default Guardrail seed could not be initialized."
                ) from error
        self._reload_runtime()

    def _seed(self, session: Session) -> None:
        self._insert_evidence_record(
            session,
            kind="system.seeded",
            outcome="success",
            detail="Initialized the standalone TaskLattice control plane.",
        )

    def _ensure_builtin_policies(self, session: Session) -> None:
        """Expose every existing built-in detector as an immutable Policy Version."""
        published_at = "2000-01-01T00:00:00+00:00"
        for definition in BUILTIN_POLICY_CAPABILITIES:
            assert definition.policy_id is not None
            policy_id = definition.policy_id
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
                PolicySourceFile(
                    path=f"{definition.id}.co",
                    content="\n\n".join(
                        f"flow {item.flow_name} $text\n  pass" for item in rails
                    ),
                )
                for _ in (0,)
            )
            draft = PolicyDraft(
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
                test_cases=tests_for_builtin_policy(policy_id),
            )
            package_payload = asdict(draft)
            version_payload = {
                "policy_id": policy_id,
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
            record = session.get(PolicyRecordModel, policy_id)
            if record is None:
                record = PolicyRecordModel(
                    id=policy_id,
                    name=definition.display_name,
                    description=definition.description,
                    source="built-in",
                    owner="TaskLattice",
                    draft_json=package_payload,
                    draft_revision=1,
                    updated_at=_datetime(published_at),
                )
                session.add(record)
            else:
                record.name = definition.display_name
                record.description = definition.description
                record.source = "built-in"
                record.owner = "TaskLattice"
                record.draft_json = package_payload
                record.updated_at = _datetime(published_at)
            if session.get(PolicyVersionModel, (policy_id, 1)) is None:
                session.add(
                    PolicyVersionModel(
                        policy_id=policy_id,
                        version=1,
                        version_json=version_payload,
                        checksum=checksum,
                        published_at=_datetime(published_at),
                    )
                )

    def _ensure_product_defaults(self, session: Session) -> None:
        guardrail_row = session.get(GuardrailModel, DEFAULT_GUARDRAIL_ID)
        created_guardrail = guardrail_row is None
        if created_guardrail:
            now = _now()
            policy_bindings = (
                GuardrailPolicyBinding("builtin-secrets", "1", action="reject"),
                GuardrailPolicyBinding("builtin-pii", "1", action="redact"),
                GuardrailPolicyBinding(
                    DEFAULT_GUARDRAIL_POLICY_ID,
                    library_policy(DEFAULT_GUARDRAIL_POLICY_ID).version,
                    action="reject",
                    enabled_rails=("input",),
                ),
            )
            guardrail = Guardrail(
                id=DEFAULT_GUARDRAIL_ID,
                name=DEFAULT_GUARDRAIL_NAME,
                purpose=DEFAULT_GUARDRAIL_PURPOSE,
                allowed_topics=(),
                restricted_topics=(),
                safety_level="balanced",
                output_delivery="window_buffered",
                draft_version=1,
                active_version=DEFAULT_GUARDRAIL_VERSION,
                updated_at=now,
                policy_bindings=policy_bindings,
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
            session.add(
                GuardrailModel(
                    id=guardrail.id,
                    name=guardrail.name,
                    purpose=guardrail.purpose,
                    allowed_topics_json=list(guardrail.allowed_topics),
                    restricted_topics_json=list(guardrail.restricted_topics),
                    safety_level=guardrail.safety_level,
                    output_delivery=guardrail.output_delivery,
                    policy_bindings_json=[asdict(item) for item in policy_bindings],
                    draft_version=1,
                    active_version=DEFAULT_GUARDRAIL_VERSION,
                    updated_at=_datetime(now),
                )
            )
            session.add(
                GuardrailVersionModel(
                    guardrail_id=guardrail.id,
                    version=DEFAULT_GUARDRAIL_VERSION,
                    source_draft_version=1,
                    guardrail_json=asdict(guardrail),
                    plan_json=asdict(plan),
                    nemo_config_json=asdict(nemo_config),
                    compiler_version=nemo_config.compiler_version,
                    plan_checksum=nemo_checksum,
                    runtime_engine=nemo_config.runtime_engine,
                    config_checksum=nemo_checksum,
                    execution_mode="nemo_only",
                    created_at=_datetime(now),
                )
            )
            self._insert_evidence_record(
                session,
                kind="guardrail.default.created",
                outcome="success",
                guardrail_id=DEFAULT_GUARDRAIL_ID,
                detail="Installed the local-only Default Guardrail.",
            )

        session.flush()
        deployment_row = session.get(DeploymentModel, DEFAULT_DEPLOYMENT_ID)
        if deployment_row is None:
            now = _now()
            session.add(
                DeploymentModel(
                    id=DEFAULT_DEPLOYMENT_ID,
                    name=DEFAULT_DEPLOYMENT_NAME,
                    guardrail_id=DEFAULT_GUARDRAIL_ID,
                    guardrail_version=DEFAULT_GUARDRAIL_VERSION,
                    traffic_scope_json={"combinator": "and", "conditions": []},
                    enabled=True,
                    updated_at=_datetime(now),
                )
            )
            self._insert_evidence_record(
                session,
                kind="deployment.default.created",
                outcome="success",
                guardrail_id=DEFAULT_GUARDRAIL_ID,
                deployment_id=DEFAULT_DEPLOYMENT_ID,
                detail="Enabled the Default Deployment for unmatched traffic.",
            )

    def _insert_credential(
        self,
        session: Session,
        integration_id: str,
        source: str,
    ) -> IntegrationCredentialSecret:
        credential_id = str(uuid.uuid4())
        credential = _new_credential()
        key_hint = _key_hint(credential)
        created_at = _now()
        session.add(
            IntegrationCredentialModel(
                id=credential_id,
                integration_id=integration_id,
                secret_hash=_hash(credential),
                key_hint=key_hint,
                source=source,
                created_at=_datetime(created_at),
                revoked_at=None,
            )
        )
        return IntegrationCredentialSecret(
            id=credential_id,
            value=credential,
            key_hint=key_hint,
            created_at=created_at,
        )

    @staticmethod
    def _insert_evidence_record(
        session: Session,
        *,
        kind: str,
        outcome: str,
        detail: str,
        guardrail_id: str | None = None,
        deployment_id: str | None = None,
        integration_id: str | None = None,
        risk: str | None = None,
    ) -> None:
        session.add(
            EvidenceRecordModel(
                id=f"evidence-{uuid.uuid4().hex[:12]}",
                created_at=_utcnow(),
                kind=kind,
                outcome=outcome,
                guardrail_id=guardrail_id,
                deployment_id=deployment_id,
                risk=risk,
                detail=detail,
                integration_id=integration_id,
            )
        )

    def _reload_runtime(self) -> None:
        plans: dict[tuple[str, int], GuardrailPlanSnapshot] = {}
        nemo_configs: dict[tuple[str, int], NeMoConfigSnapshot] = {}
        credentials: dict[str, str] = {}
        with self._database.session() as session:
            for row in session.scalars(select(GuardrailVersionModel)).all():
                key = (row.guardrail_id, row.version)
                plans[key] = _plan_from_payload(row.plan_json)
                if row.nemo_config_json is not None:
                    nemo_configs[key] = _nemo_config_from_payload(
                        row.nemo_config_json
                    )
            credential_rows = session.scalars(
                select(IntegrationCredentialModel).where(
                    IntegrationCredentialModel.revoked_at.is_(None)
                )
            ).all()
            for row in credential_rows:
                credentials[row.secret_hash] = row.integration_id
        self._plans = plans
        self._nemo_configs = nemo_configs
        self._deployments = self.deployments()
        self._credential_index = credentials

    def _integration_from_model(
        self, session: Session, row: IntegrationModel
    ) -> Integration:
        adapter = adapter_definition(row.adapter_id)
        if adapter is None:
            raise ControlPlaneError("Stored Integration adapter is not registered.")
        credentials = tuple(
            IntegrationCredential(
                id=item.id,
                key_hint=item.key_hint,
                created_at=_iso(item.created_at),
            )
            for item in session.scalars(
                select(IntegrationCredentialModel)
                .where(
                    IntegrationCredentialModel.integration_id == row.id,
                    IntegrationCredentialModel.revoked_at.is_(None),
                )
                .order_by(
                    IntegrationCredentialModel.created_at.desc(),
                    IntegrationCredentialModel.id.desc(),
                )
            ).all()
        )
        enabled = row.enabled
        first_seen_at = _iso(row.first_seen_at) if row.first_seen_at else None
        last_seen_at = _iso(row.last_seen_at) if row.last_seen_at else None
        input_seen_at = _iso(row.input_seen_at) if row.input_seen_at else None
        output_seen_at = _iso(row.output_seen_at) if row.output_seen_at else None
        last_error_at = _iso(row.last_error_at) if row.last_error_at else None
        setup_status = (
            "disabled"
            if not enabled
            else "awaiting_callback"
            if first_seen_at is None
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
            id=row.id,
            adapter_id=adapter.id,
            protocol=adapter.protocol,
            name=row.name,
            description=row.description,
            enabled=enabled,
            key_hint=credentials[0].key_hint if credentials else "",
            credentials=credentials,
            setup_status=setup_status,
            runtime_status=runtime_status,
            first_seen_at=first_seen_at,
            last_seen_at=last_seen_at,
            input_seen_at=input_seen_at,
            output_seen_at=output_seen_at,
            request_count=row.request_count,
            error_count=row.error_count,
            last_error_at=last_error_at,
            created_at=_iso(row.created_at),
            updated_at=_iso(row.updated_at),
        )

    def _validate_policy_draft(
        self,
        policy_id: str,
        draft: PolicyDraft,
        *,
        validate_dependencies: bool,
    ) -> None:
        if draft.colang_version not in {"1.0", "2.x"}:
            raise ValidationError("Policy Colang version must be 1.0 or 2.x.")
        if not draft.sources or any(
            not item.path.strip() or not item.content.strip() for item in draft.sources
        ):
            raise ValidationError("A Policy requires at least one named Colang source.")
        if len({item.path for item in draft.sources}) != len(draft.sources):
            raise ValidationError("Policy source paths must be unique.")
        if not draft.rail_bindings:
            raise ValidationError("A Policy requires at least one Rail binding.")
        if len({(item.rail_type, item.flow_name) for item in draft.rail_bindings}) != len(
            draft.rail_bindings
        ):
            raise ValidationError("Policy Rail bindings must be unique.")
        for binding in draft.rail_bindings:
            if binding.rail_type not in {"input", "output"}:
                raise ValidationError("Unsupported Policy rail type.")
            if binding.timeout_ms <= 0:
                raise ValidationError("Policy rail timeouts must be positive.")
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
        rules = {
            flow_rule_id(binding.rail_type, binding.flow_name): binding
            for binding in draft.rail_bindings
        }
        accepted_rules: set[str] = set()
        for test in draft.test_cases:
            if not test.covered_rule_ids:
                raise ValidationError(
                    f"Policy Test Case {test.name!r} must cover at least one Rule."
                )
            unknown_rules = set(test.covered_rule_ids).difference(rules)
            if unknown_rules:
                raise ValidationError(
                    f"Policy Test Case {test.name!r} references unknown Rules: "
                    + ", ".join(sorted(unknown_rules))
                    + "."
                )
            mismatched_rules = sorted(
                rule_id
                for rule_id in test.covered_rule_ids
                if rules[rule_id].rail_type != test.rail_type
            )
            if mismatched_rules:
                raise ValidationError(
                    f"Policy Test Case {test.name!r} must run on the same Rail as its Rules: "
                    + ", ".join(mismatched_rules)
                    + "."
                )
            if test.required:
                accepted_rules.update(test.covered_rule_ids)
        missing_test_rules = sorted(set(rules).difference(accepted_rules))
        if missing_test_rules:
            raise ValidationError(
                "Every Policy Rule requires a reviewed Test Case; missing "
                + ", ".join(missing_test_rules)
                + "."
            )
        case_ids = [item.id for item in draft.test_cases if item.id]
        if len(case_ids) != len(set(case_ids)):
            raise ValidationError("Policy Test Case IDs must be unique.")
        for reference in draft.action_references:
            if not self._action_catalog.contains(reference.name, reference.version):
                raise ValidationError(
                    f"Policy {policy_id!r} references unregistered Action "
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
                f"Policy {policy_id!r} references unregistered Models: "
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
                f"Policy {policy_id!r} references unregistered Prompts: "
                + ", ".join(missing_prompts)
                + "."
            )

    def _validate_guardrail_policy_bindings(
        self,
        bindings: tuple[GuardrailPolicyBinding, ...],
    ) -> None:
        keys = tuple((item.policy_id, item.policy_version) for item in bindings)
        if len(set(keys)) != len(keys):
            raise ValidationError("A Policy Version may only be bound once.")
        for binding in bindings:
            configured_actions = dict(binding.rule_actions)
            invalid_actions = {
                action
                for action in (binding.action, *configured_actions.values())
                if action is not None and action not in ENFORCEMENT_ACTIONS
            }
            if invalid_actions:
                raise ValidationError(
                    f"Policy {binding.policy_id!r} uses unsupported Rule actions: "
                    + ", ".join(sorted(invalid_actions))
                    + "."
                )
            static_policy = library_policy(binding.policy_id)
            if static_policy is not None:
                if binding.policy_version != static_policy.version:
                    raise ValidationError(
                        f"Policy {binding.policy_id!r} must pin version "
                        f"{static_policy.version}."
                    )
                supported_parameters = {item.name: item for item in static_policy.parameters}
                supplied = dict(binding.parameter_values)
                missing = tuple(
                    item.name
                    for item in supported_parameters.values()
                    if item.required and not supplied.get(item.name)
                )
                if missing:
                    raise ValidationError(
                        f"Policy {binding.policy_id!r} requires "
                        + ", ".join(missing)
                        + "."
                    )
                unknown = set(supplied).difference(supported_parameters)
                if unknown:
                    raise ValidationError(
                        f"Unknown parameters for Policy {binding.policy_id!r}: "
                        + ", ".join(sorted(unknown))
                        + "."
                    )
                available_rules = {item.id for item in static_policy.rules}
                if set(binding.enabled_rule_ids).difference(available_rules):
                    raise ValidationError(
                        f"Policy {binding.policy_id!r} enables an unknown Rule."
                    )
                if {item[0] for item in binding.rule_actions}.difference(available_rules):
                    raise ValidationError(
                        f"Policy {binding.policy_id!r} configures an unknown Rule."
                    )
                enabled_rails = set(binding.enabled_rails or static_policy.stages)
                if not enabled_rails <= set(static_policy.stages):
                    raise ValidationError(
                        f"Policy {binding.policy_id!r} does not provide every enabled Rail."
                    )
                if binding.enabled_rule_ids:
                    rules_by_id = {item.id: item for item in static_policy.rules}
                    outside_enabled_rails = {
                        rule_id
                        for rule_id in binding.enabled_rule_ids
                        if enabled_rails.isdisjoint(rules_by_id[rule_id].stages)
                    }
                    if outside_enabled_rails:
                        raise ValidationError(
                            f"Policy {binding.policy_id!r} enables Rules outside its enabled Rails."
                        )
                if configured_actions and binding.enabled_rule_ids:
                    disabled_overrides = set(configured_actions).difference(
                        binding.enabled_rule_ids
                    )
                    if disabled_overrides:
                        raise ValidationError(
                            f"Policy {binding.policy_id!r} configures actions for disabled Rules."
                        )
                continue
            try:
                stored_version = int(binding.policy_version)
            except ValueError as error:
                raise ValidationError(
                    f"Policy {binding.policy_id!r} requires a numeric published version."
                ) from error
            version = self.policy_version(binding.policy_id, stored_version)
            native_risk = dict(version.execution_contract).get("native_risk")
            if native_risk:
                definition = runtime_capability(native_risk)
                enabled_rails = binding.enabled_rails or tuple(
                    dict.fromkeys(item.rail_type for item in version.rail_bindings)
                )
                action = binding.action or next(
                    (
                        rail.on_unsafe
                        for rail in version.rail_bindings
                        if rail.rail_type in enabled_rails
                    ),
                    definition.default_action,
                )
                if action not in definition.allowed_actions:
                    raise ValidationError(
                        f"Policy {binding.policy_id!r} does not support action {action!r}."
                    )
                if native_risk == "automated_reasoning":
                    reasoning = binding.reasoning_policy
                    if reasoning is None:
                        raise ValidationError(
                            "Automated reasoning requires a deployed reasoning Policy."
                        )
                    if not 0 <= reasoning.confidence_threshold <= 1:
                        raise ValidationError(
                            "Automated reasoning confidence threshold must be between 0 and 1."
                        )
                elif binding.reasoning_policy is not None:
                    raise ValidationError(
                        "Only automated reasoning may bind a reasoning Policy."
                    )
            definitions = {item.name: item for item in version.parameter_schema}
            supplied = dict(binding.parameter_values)
            missing = tuple(
                item.name
                for item in definitions.values()
                if item.required and item.default is None and not supplied.get(item.name)
            )
            if missing:
                raise ValidationError(
                    f"Policy {binding.policy_id}@{binding.policy_version} requires "
                    + ", ".join(missing)
                    + "."
                )
            unknown = set(supplied) - set(definitions)
            if unknown:
                raise ValidationError(
                    f"Unknown parameters for Policy {binding.policy_id}: "
                    + ", ".join(sorted(unknown))
                    + "."
                )
            available_rails = {item.rail_type for item in version.rail_bindings}
            enabled_rails = set(binding.enabled_rails or available_rails)
            if not enabled_rails <= available_rails:
                raise ValidationError(
                    f"Policy {binding.policy_id}@{binding.policy_version} does not "
                    "provide every enabled rail."
                )
            rules = {
                flow_rule_id(item.rail_type, item.flow_name): item
                for item in version.rail_bindings
            }
            unknown_enabled_rules = set(binding.enabled_rule_ids).difference(rules)
            if unknown_enabled_rules:
                raise ValidationError(
                    f"Policy {binding.policy_id}@{binding.policy_version} enables unknown Rules: "
                    + ", ".join(sorted(unknown_enabled_rules))
                    + "."
                )
            unknown_rule_actions = set(configured_actions).difference(rules)
            if unknown_rule_actions:
                raise ValidationError(
                    f"Policy {binding.policy_id}@{binding.policy_version} configures unknown Rules: "
                    + ", ".join(sorted(unknown_rule_actions))
                    + "."
                )
            if binding.enabled_rule_ids:
                outside_enabled_rails = {
                    rule_id
                    for rule_id in binding.enabled_rule_ids
                    if rules[rule_id].rail_type not in enabled_rails
                }
                if outside_enabled_rails:
                    raise ValidationError(
                        f"Policy {binding.policy_id}@{binding.policy_version} enables Rules "
                        "outside its enabled Rails."
                    )
                disabled_overrides = set(configured_actions).difference(
                    binding.enabled_rule_ids
                )
                if disabled_overrides:
                    raise ValidationError(
                        f"Policy {binding.policy_id}@{binding.policy_version} configures "
                        "actions for disabled Rules."
                    )

    @staticmethod
    def _validate_guardrail_fields(
        purpose: str,
        safety_level: str,
        output_delivery: str,
        policy_bindings: tuple[GuardrailPolicyBinding, ...] = (),
    ) -> None:
        if not purpose.strip():
            raise ValidationError("Describe what this AI is allowed to do.")
        if safety_level not in {"balanced", "strict"}:
            raise ValidationError("Enforcement mode must be balanced or strict.")
        if output_delivery not in {"interruptible", "window_buffered", "full_buffered"}:
            raise ValidationError("Unsupported output delivery mode.")
        if not policy_bindings:
            raise ValidationError("Select at least one Policy to protect.")

    @staticmethod
    def _validate_test_case(
        guardrail: Guardrail,
        name: str,
        policy_id: str,
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
        if policy_id not in {
            *(item.policy_id for item in guardrail.policy_bindings),
        }:
            raise ValidationError("Test case Policy must be enabled in this Guardrail.")
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
        if policy_id == "builtin-contextual-grounding":
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
        elif policy_id == "builtin-automated-reasoning":
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

def _policy_draft_from_payload(payload: dict[str, object]) -> PolicyDraft:
    return PolicyDraft(
        colang_version=str(payload["colang_version"]),
        sources=tuple(PolicySourceFile(**item) for item in payload.get("sources", ())),
        parameter_schema=tuple(
            PolicyParameterDefinition(**item)
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
        test_cases=tuple(
            PolicyTestCaseDefinition(**item) for item in payload.get("test_cases", ())
        ),
    )


def _policy_record_from_model(row: PolicyRecordModel) -> PolicyRecord:
    return PolicyRecord(
        id=row.id,
        name=row.name,
        description=row.description,
        source=row.source,
        owner=row.owner,
        draft=_policy_draft_from_payload(row.draft_json),
        draft_revision=row.draft_revision,
        updated_at=_iso(row.updated_at),
    )


def _policy_version_from_model(row: PolicyVersionModel) -> PolicyVersion:
    payload = row.version_json
    draft = _policy_draft_from_payload(payload)
    return PolicyVersion(
        policy_id=str(payload["policy_id"]),
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
        test_cases=draft.test_cases,
        checksum=row.checksum,
        published_at=_iso(row.published_at),
    )


def _policy_version_snapshot(version: PolicyVersion) -> PolicyVersionSnapshot:
    return PolicyVersionSnapshot(
        policy_id=version.policy_id,
        version=str(version.version),
        name=version.name,
        source=version.source,
        colang_version=version.colang_version,
        sources=tuple(
            PolicySourceSnapshot(path=item.path, content=item.content)
            for item in version.sources
        ),
        parameter_schema=tuple(
            (item.name, item.kind) for item in version.parameter_schema
        ),
        rail_bindings=tuple(
            PolicyRailBindingSnapshot(**asdict(item))
            for item in version.rail_bindings
        ),
        action_references=tuple(
            PolicyActionReferenceSnapshot(item.name, item.version)
            for item in version.action_references
        ),
        model_dependencies=version.model_dependencies,
        prompt_dependencies=version.prompt_dependencies,
        execution_contract=version.execution_contract,
        test_cases=tuple(
            (item.name, item.expected_decision) for item in version.test_cases
        ),
        checksum=version.checksum,
    )


def _guardrail_from_model(row: GuardrailModel) -> Guardrail:
    raw_bindings = row.policy_bindings_json
    return Guardrail(
        id=row.id,
        name=row.name,
        purpose=row.purpose,
        allowed_topics=tuple(row.allowed_topics_json),
        restricted_topics=tuple(row.restricted_topics_json),
        safety_level=row.safety_level,
        output_delivery=row.output_delivery,
        draft_version=row.draft_version,
        active_version=row.active_version,
        updated_at=_iso(row.updated_at),
        policy_bindings=tuple(
            GuardrailPolicyBinding(
                policy_id=str(item["policy_id"]),
                policy_version=str(item["policy_version"]),
                action=(str(item["action"]) if item.get("action") else None),
                parameter_values=tuple(
                    tuple(value) for value in item.get("parameter_values", ())
                ),
                enabled_rule_ids=tuple(item.get("enabled_rule_ids", ())),
                rule_actions=tuple(
                    tuple(value) for value in item.get("rule_actions", ())
                ),
                enabled_rails=tuple(item.get("enabled_rails", ("input", "output"))),
                reasoning_policy=(
                    _reasoning_binding(item["reasoning_policy"])
                    if item.get("reasoning_policy")
                    else None
                ),
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
        policy_versions=tuple(
            PolicyVersionSnapshot(
                policy_id=str(item["policy_id"]),
                version=str(item["version"]),
                name=str(item["name"]),
                source=str(item["source"]),
                colang_version=str(item["colang_version"]),
                sources=tuple(
                    PolicySourceSnapshot(**source) for source in item.get("sources", ())
                ),
                parameter_schema=tuple(
                    tuple(value) for value in item.get("parameter_schema", ())
                ),
                rail_bindings=tuple(
                    PolicyRailBindingSnapshot(**binding)
                    for binding in item.get("rail_bindings", ())
                ),
                action_references=tuple(
                    PolicyActionReferenceSnapshot(**reference)
                    for reference in item.get("action_references", ())
                ),
                model_dependencies=tuple(item.get("model_dependencies", ())),
                prompt_dependencies=tuple(item.get("prompt_dependencies", ())),
                execution_contract=tuple(
                    tuple(value) for value in item.get("execution_contract", ())
                ),
                test_cases=tuple(tuple(value) for value in item.get("test_cases", ())),
                checksum=str(item["checksum"]),
            )
            for item in payload.get("policy_versions", ())
        ),
        policy_bindings=tuple(
            GuardrailPolicyBindingSnapshot(
                policy_id=str(item["policy_id"]),
                policy_version=str(item["policy_version"]),
                action=(str(item["action"]) if item.get("action") else None),
                parameter_values=tuple(
                    tuple(value) for value in item.get("parameter_values", ())
                ),
                enabled_rule_ids=tuple(item.get("enabled_rule_ids", ())),
                rule_actions=tuple(
                    tuple(value) for value in item.get("rule_actions", ())
                ),
                enabled_rails=tuple(item.get("enabled_rails", ("input", "output"))),
            )
            for item in payload.get("policy_bindings", ())
        ),
    )


def _nemo_config_from_payload(payload: dict[str, object]) -> NeMoConfigSnapshot:
    compiler_version = str(payload.get("compiler_version", ""))
    runtime_profile = payload.get("runtime_profile")
    if not isinstance(runtime_profile, str) or not runtime_profile.strip():
        raise ControlPlaneError(
            "Stored NeMo artifact is missing its explicit runtime_profile."
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
                policy_id=(
                    str(item["policy_id"]) if item.get("policy_id") else None
                ),
                policy_version=(
                    str(item["policy_version"])
                    if item.get("policy_version") is not None
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
        runtime_profile=runtime_profile,
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


def _stored_runtime_profile(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        payload = value
    else:
        try:
            payload = json.loads(str(value))
        except (TypeError, ValueError, json.JSONDecodeError):
            return ""
    if not isinstance(payload, dict):
        return ""
    return _nemo_config_from_payload(payload).runtime_profile


def _reasoning_binding(value: object) -> AutomatedReasoningPolicyBinding | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ControlPlaneError("Stored Guardrail Policy binding has an invalid reasoning policy.")
    return AutomatedReasoningPolicyBinding(
        policy_id=str(value["policy_id"]),
        policy_version=str(value["policy_version"]),
        confidence_threshold=float(value["confidence_threshold"]),
    )


def _deployment_from_model(row: DeploymentModel) -> Deployment:
    return Deployment(
        id=row.id,
        name=row.name,
        guardrail_id=row.guardrail_id,
        guardrail_version=row.guardrail_version,
        traffic_scope=traffic_scope_from_payload(row.traffic_scope_json),
        enabled=row.enabled,
        updated_at=_iso(row.updated_at),
    )


def _validation_run_from_model(row: ValidationRunModel) -> ValidationRun:
    return ValidationRun(
        id=row.id,
        guardrail_id=row.guardrail_id,
        guardrail_version=row.guardrail_version,
        source_draft_version=row.source_draft_version,
        status=row.status,
        metrics=ValidationMetrics(**row.metrics_json),
        results=tuple(
            _test_case_result_from_payload(item)
            for item in row.results_json
        ),
        created_at=_iso(row.created_at),
    )


def _test_case_result_from_payload(payload: dict[str, object]) -> TestCaseResult:
    values = dict(payload)
    values["grounding_sources"] = tuple(values["grounding_sources"])
    values["findings"] = tuple(values["findings"])
    values["trace"] = tuple(values["trace"])
    return TestCaseResult(**values)


def _test_case_from_model(row: TestCaseModel) -> GuardrailTestCase:
    return GuardrailTestCase(
        id=row.id,
        guardrail_id=row.guardrail_id,
        name=row.name,
        policy_id=row.policy_id,
        phase=row.phase,
        content=row.content,
        expected_decision=row.expected_decision,
        origin=row.origin,
        updated_at=_iso(row.updated_at),
        trusted_instruction=row.trusted_instruction,
        target_source=row.target_source,
        query=row.query_content,
        grounding_sources=tuple(row.grounding_sources_json),
        expected_reasoning_result=row.expected_reasoning_result,
        case_type=row.case_type,
        required=row.required,
        expected_failure=row.expected_failure,
        concurrency_group=row.concurrency_group,
        source_policy_id=row.source_policy_id,
        source_policy_version=row.source_policy_version,
        source_case_id=row.source_case_id,
        covered_rule_ids=tuple(row.covered_rule_ids_json),
    )


def _resolution_step(kind: str, name: str, detail: str):
    from ..runtime.contracts import RuntimeTraceStep

    return RuntimeTraceStep(
        id=f"resolution:{kind}", kind=kind, name=name, status="selected", detail=detail
    )


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _new_credential() -> str:
    return "tali_integration_" + secrets.token_urlsafe(30)


def _key_hint(credential: str) -> str:
    return f"••••{credential[-6:]}"


def _now() -> str:
    return _utcnow().isoformat()


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _datetime(value: str | datetime) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(value)


def _iso(value: datetime) -> str:
    normalized = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return normalized.isoformat()
