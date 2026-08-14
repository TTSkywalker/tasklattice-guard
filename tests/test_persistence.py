from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sqlalchemy import inspect

from app.control_plane.defaults import DEFAULT_GUARDRAIL_ID, DEFAULT_GUARDRAIL_VERSION
from app.control_plane.nemo_compiler import NEMO_COMPILER_VERSION
from app.control_plane.service import ControlPlaneService
from app.persistence.database import database_url
from app.persistence.models import GuardrailVersionModel


def test_path_locator_remains_a_sqlite_development_fallback(tmp_path):
    path = tmp_path / "guard.db"

    assert database_url(path) == f"sqlite:///{path.resolve()}"


def test_sqlalchemy_url_is_preserved_without_core_dialect_policy():
    locator = "postgresql+psycopg://guard:secret@postgres/guard"

    assert database_url(locator) == locator


def test_orm_metadata_creates_the_complete_schema_for_a_new_database(tmp_path):
    service = ControlPlaneService(tmp_path / "guard.db")
    tables = set(inspect(service.database.engine).get_table_names())

    assert {
        "policy_records",
        "policy_versions",
        "guardrails",
        "guardrail_versions",
        "deployments",
        "integrations",
        "integration_credentials",
        "validation_runs",
        "test_cases",
        "evidence_records",
        "runtime_metric_events",
        "runtime_step_metric_events",
        "users",
        "user_sessions",
    } <= tables


def test_application_services_do_not_embed_sqlite_or_sql_statements():
    root = Path(__file__).resolve().parents[1]
    service_sources = (
        root / "app" / "control_plane" / "service.py",
        root / "app" / "identity" / "service.py",
    )
    prohibited = (
        "sqlite3",
        "sqlite_master",
        "PRAGMA ",
        "SELECT ",
        "INSERT INTO ",
        "DELETE FROM ",
        "CREATE TABLE ",
        "BEGIN IMMEDIATE",
    )

    for source in service_sources:
        text = source.read_text()
        assert all(value not in text for value in prohibited)


def test_existing_orm_schema_is_safe_for_concurrent_service_construction(tmp_path):
    path = tmp_path / "concurrent.db"
    ControlPlaneService(path).database.dispose()

    def start(_: int) -> None:
        service = ControlPlaneService(path)
        assert service.guardrail("guardrail-default").active_version == 1
        service.database.dispose()

    with ThreadPoolExecutor(max_workers=4) as executor:
        tuple(executor.map(start, range(4)))


def test_system_default_is_recompiled_when_the_action_contract_changes(tmp_path):
    path = tmp_path / "old-default.db"
    service = ControlPlaneService(path)
    with service.database.transaction() as session:
        row = session.get(
            GuardrailVersionModel,
            (DEFAULT_GUARDRAIL_ID, DEFAULT_GUARDRAIL_VERSION),
        )
        assert row is not None and row.nemo_config_json is not None
        payload = dict(row.nemo_config_json)
        payload["compiler_version"] = "tasklattice-nemo-config-v6"
        bindings = [dict(item) for item in payload["action_bindings"]]
        bindings[0]["action_name"] = "TaskLatticeSecretsAction"
        payload["action_bindings"] = bindings
        row.nemo_config_json = payload
        row.compiler_version = "tasklattice-nemo-config-v6"
    service.database.dispose()

    reloaded = ControlPlaneService(path)
    config = reloaded.nemo_config(DEFAULT_GUARDRAIL_ID, DEFAULT_GUARDRAIL_VERSION)

    assert config.compiler_version == NEMO_COMPILER_VERSION
    assert all(
        binding.action_name is None
        or re.fullmatch(r"Guard[A-Z][A-Za-z0-9]*Action", binding.action_name)
        for binding in config.action_bindings
    )
