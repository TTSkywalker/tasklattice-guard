from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class GuardrailModel(Base):
    __tablename__ = "guardrails"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    allowed_topics_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    restricted_topics_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    safety_level: Mapped[str] = mapped_column(String, nullable=False)
    output_delivery: Mapped[str] = mapped_column(String, nullable=False)
    policy_bindings_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    excluded_test_case_ids_json: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    draft_version: Mapped[int] = mapped_column(Integer, nullable=False)
    active_version: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GuardrailLoggingSettingsModel(Base):
    __tablename__ = "guardrail_logging_settings"

    guardrail_id: Mapped[str] = mapped_column(
        ForeignKey("guardrails.id", ondelete="CASCADE"), primary_key=True
    )
    level: Mapped[str] = mapped_column(String, nullable=False, default="info")
    updated_by: Mapped[str | None] = mapped_column(String)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GuardrailVersionModel(Base):
    __tablename__ = "guardrail_versions"

    guardrail_id: Mapped[str] = mapped_column(
        ForeignKey("guardrails.id", ondelete="CASCADE"), primary_key=True
    )
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_draft_version: Mapped[int] = mapped_column(Integer, nullable=False)
    guardrail_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    plan_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    nemo_config_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    compiler_version: Mapped[str] = mapped_column(String, nullable=False)
    plan_checksum: Mapped[str] = mapped_column(String, nullable=False)
    runtime_engine: Mapped[str] = mapped_column(String, nullable=False, default="nemo")
    config_checksum: Mapped[str | None] = mapped_column(String)
    execution_mode: Mapped[str] = mapped_column(
        String, nullable=False, default="nemo_only"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PolicyRecordModel(Base):
    __tablename__ = "policy_records"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    owner: Mapped[str] = mapped_column(String, nullable=False)
    draft_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    draft_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PolicyVersionModel(Base):
    __tablename__ = "policy_versions"

    policy_id: Mapped[str] = mapped_column(
        ForeignKey("policy_records.id", ondelete="CASCADE"), primary_key=True
    )
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    checksum: Mapped[str] = mapped_column(String, nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PolicyValidationRunModel(Base):
    __tablename__ = "policy_validation_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    policy_id: Mapped[str] = mapped_column(
        ForeignKey("policy_records.id", ondelete="CASCADE"), nullable=False
    )
    draft_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    results_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IntegrationModel(Base):
    __tablename__ = "integrations"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    adapter_id: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    input_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    output_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IntegrationCredentialModel(Base):
    __tablename__ = "integration_credentials"
    __table_args__ = (UniqueConstraint("secret_hash"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    integration_id: Mapped[str] = mapped_column(
        ForeignKey("integrations.id", ondelete="CASCADE"), nullable=False
    )
    secret_hash: Mapped[str] = mapped_column(String, nullable=False)
    key_hint: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DeploymentModel(Base):
    __tablename__ = "deployments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["guardrail_id", "guardrail_version"],
            ["guardrail_versions.guardrail_id", "guardrail_versions.version"],
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    guardrail_id: Mapped[str] = mapped_column(String, nullable=False)
    guardrail_version: Mapped[int] = mapped_column(Integer, nullable=False)
    integration_id: Mapped[str | None] = mapped_column(
        ForeignKey("integrations.id", ondelete="CASCADE"), nullable=True
    )
    route_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=100, server_default="100"
    )
    traffic_scope_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ValidationRunModel(Base):
    __tablename__ = "validation_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    guardrail_id: Mapped[str] = mapped_column(
        ForeignKey("guardrails.id", ondelete="CASCADE"), nullable=False
    )
    guardrail_version: Mapped[int | None] = mapped_column(Integer)
    source_draft_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    metrics_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    results_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    excluded_case_ids_json: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TestCaseModel(Base):
    __tablename__ = "test_cases"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    guardrail_id: Mapped[str] = mapped_column(
        ForeignKey("guardrails.id", ondelete="CASCADE"), primary_key=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    policy_id: Mapped[str] = mapped_column(String, nullable=False)
    phase: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    trusted_instruction: Mapped[str] = mapped_column(Text, nullable=False)
    target_source: Mapped[str] = mapped_column(String, nullable=False)
    expected_decision: Mapped[str] = mapped_column(String, nullable=False)
    query_content: Mapped[str] = mapped_column(Text, nullable=False)
    grounding_sources_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    expected_reasoning_result: Mapped[str | None] = mapped_column(String)
    case_type: Mapped[str] = mapped_column(String, nullable=False, default="unit")
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    expected_failure: Mapped[str | None] = mapped_column(Text)
    concurrency_group: Mapped[str | None] = mapped_column(String)
    source_policy_id: Mapped[str | None] = mapped_column(String)
    source_policy_version: Mapped[str | None] = mapped_column(String)
    source_case_id: Mapped[str | None] = mapped_column(String)
    covered_rule_ids_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    origin: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EvidenceRecordModel(Base):
    __tablename__ = "evidence_records"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    outcome: Mapped[str] = mapped_column(String, nullable=False)
    guardrail_id: Mapped[str | None] = mapped_column(String)
    deployment_id: Mapped[str | None] = mapped_column(String)
    risk: Mapped[str | None] = mapped_column(String)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    integration_id: Mapped[str | None] = mapped_column(String)
    actor_id: Mapped[str | None] = mapped_column(String)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class RuntimeMetricEventModel(Base):
    __tablename__ = "runtime_metric_events"
    __table_args__ = (
        Index("runtime_metric_events_created_at_idx", "created_at"),
        Index("runtime_metric_events_trace_id_idx", "trace_id"),
        Index(
            "runtime_metric_events_guardrail_created_at_idx",
            "guardrail_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    trace_id: Mapped[str] = mapped_column(String, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    guardrail_id: Mapped[str | None] = mapped_column(String)
    guardrail_version: Mapped[int | None] = mapped_column(Integer)
    deployment_id: Mapped[str | None] = mapped_column(String)
    integration_id: Mapped[str | None] = mapped_column(String)
    protocol: Mapped[str] = mapped_column(String, nullable=False)
    phase: Mapped[str] = mapped_column(String, nullable=False)
    outcome: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    risk: Mapped[str | None] = mapped_column(String)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    timed_out: Mapped[bool] = mapped_column(Boolean, nullable=False)
    module_invocations: Mapped[int] = mapped_column(Integer, nullable=False)
    evaluator_invocations: Mapped[int] = mapped_column(Integer, nullable=False)
    rail_invocations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    action_invocations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    model_invocations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    queue_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_hits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_misses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    runtime_engine: Mapped[str] = mapped_column(String, nullable=False, default="")
    config_checksum: Mapped[str] = mapped_column(String, nullable=False, default="")
    fail_closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active_concurrency: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    provider_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    slo_breached: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")


class RuntimeStepMetricEventModel(Base):
    __tablename__ = "runtime_step_metric_events"
    __table_args__ = (
        Index("runtime_step_metric_events_created_at_idx", "created_at"),
        Index(
            "runtime_step_metric_events_guardrail_created_at_idx",
            "guardrail_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    trace_id: Mapped[str] = mapped_column(String, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    guardrail_id: Mapped[str] = mapped_column(String, nullable=False)
    guardrail_version: Mapped[int] = mapped_column(Integer, nullable=False)
    deployment_id: Mapped[str | None] = mapped_column(String)
    integration_id: Mapped[str | None] = mapped_column(String)
    protocol: Mapped[str] = mapped_column(String, nullable=False)
    phase: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    risk: Mapped[str | None] = mapped_column(String)
    stage: Mapped[str | None] = mapped_column(String)
    outcome: Mapped[str] = mapped_column(String, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    timed_out: Mapped[bool] = mapped_column(Boolean, nullable=False)
    runtime_engine: Mapped[str] = mapped_column(String, nullable=False)
    config_checksum: Mapped[str] = mapped_column(String, nullable=False)
    policy_id: Mapped[str | None] = mapped_column(String)
    policy_version: Mapped[str | None] = mapped_column(String)
    rail_type: Mapped[str | None] = mapped_column(String)
    flow_name: Mapped[str | None] = mapped_column(String)
    action_name: Mapped[str | None] = mapped_column(String)
    action_version: Mapped[str | None] = mapped_column(String)
    parallel_group: Mapped[str | None] = mapped_column(String)
    timeout_ms: Mapped[int | None] = mapped_column(Integer)
    provider_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class RuntimeFindingEventModel(Base):
    """Privacy-safe finding metadata correlated to one runtime decision trace."""

    __tablename__ = "runtime_finding_events"
    __table_args__ = (
        Index("runtime_finding_events_trace_id_idx", "trace_id"),
        Index(
            "runtime_finding_events_guardrail_created_at_idx",
            "guardrail_id",
            "created_at",
        ),
        Index(
            "runtime_finding_events_deployment_created_at_idx",
            "deployment_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    trace_id: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    guardrail_id: Mapped[str | None] = mapped_column(String)
    guardrail_version: Mapped[int | None] = mapped_column(Integer)
    deployment_id: Mapped[str | None] = mapped_column(String)
    integration_id: Mapped[str | None] = mapped_column(String)
    phase: Mapped[str] = mapped_column(String, nullable=False)
    severity: Mapped[str] = mapped_column(String, nullable=False)
    risk: Mapped[str] = mapped_column(String, nullable=False)
    verdict: Mapped[str] = mapped_column(String, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    recommended_action: Mapped[str] = mapped_column(String, nullable=False)
    policy_id: Mapped[str | None] = mapped_column(String)
    rule_id: Mapped[str | None] = mapped_column(String)
    detail: Mapped[str] = mapped_column(Text, nullable=False)


class RuntimeLogInteractionModel(Base):
    """One correlated input/output interaction selected by a Guardrail log level."""

    __tablename__ = "runtime_log_interactions"
    __table_args__ = (
        Index(
            "runtime_log_interactions_guardrail_created_at_idx",
            "guardrail_id",
            "created_at",
        ),
        Index(
            "runtime_log_interactions_correlation_idx",
            "correlation_hash",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    correlation_hash: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    guardrail_id: Mapped[str] = mapped_column(
        ForeignKey("guardrails.id", ondelete="CASCADE"), nullable=False
    )
    guardrail_version: Mapped[int | None] = mapped_column(Integer)
    deployment_id: Mapped[str | None] = mapped_column(String)
    integration_id: Mapped[str | None] = mapped_column(String)
    protocol: Mapped[str] = mapped_column(String, nullable=False)
    outcome: Mapped[str] = mapped_column(String, nullable=False)
    capture_level: Mapped[str] = mapped_column(String, nullable=False)


class RuntimeLogEntryModel(Base):
    """One encrypted inbound or outbound checkpoint in a runtime interaction."""

    __tablename__ = "runtime_log_entries"
    __table_args__ = (
        Index("runtime_log_entries_interaction_idx", "interaction_id", "created_at"),
        Index("runtime_log_entries_trace_id_idx", "trace_id"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    interaction_id: Mapped[str] = mapped_column(
        ForeignKey("runtime_log_interactions.id", ondelete="CASCADE"), nullable=False
    )
    trace_id: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    phase: Mapped[str] = mapped_column(String, nullable=False)
    outcome: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    risk: Mapped[str | None] = mapped_column(String)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    timed_out: Mapped[bool] = mapped_column(Boolean, nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    content_before_ciphertext: Mapped[str | None] = mapped_column(Text)
    content_after_ciphertext: Mapped[str | None] = mapped_column(Text)


class UserModel(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    password_salt: Mapped[str] = mapped_column(String, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    preferred_language: Mapped[str] = mapped_column(String, nullable=False, default="en")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UserSessionModel(Base):
    __tablename__ = "user_sessions"

    token_hash: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
