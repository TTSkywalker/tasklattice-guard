from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import httpx
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.config import Settings
from app.control_plane.defaults import DEFAULT_GUARDRAIL_ID, DEFAULT_GUARDRAIL_VERSION
from app.control_plane.domain import ValidationError
from app.control_plane.service import ControlPlaneService
from app.main import create_app
from app.persistence.models import RuntimeLogEntryModel, RuntimeLogInteractionModel


def _service(tmp_path) -> ControlPlaneService:
    return ControlPlaneService(
        tmp_path / "runtime-logs.db",
        runtime_log_encryption_key=Fernet.generate_key().decode(),
        runtime_log_retention_days=7,
    )


def _record(
    service: ControlPlaneService,
    *,
    trace_id: str,
    call_id: str | None,
    phase: str,
    outcome: str,
    text: str,
    transformed: str | None = None,
) -> None:
    service.record_runtime_log(
        trace_id=trace_id,
        call_id=call_id,
        guardrail_id=DEFAULT_GUARDRAIL_ID,
        guardrail_version=DEFAULT_GUARDRAIL_VERSION,
        deployment_id="deployment-default",
        integration_id=None,
        protocol="test",
        phase=phase,
        outcome=outcome,
        action="pass" if outcome == "allow" else outcome,
        risk="secrets" if outcome == "block" else None,
        latency_ms=7,
        timed_out=False,
        fail_closed=False,
        detail=f"{phase} {outcome}",
        content_before=(
            {"id": trace_id, "role": "user", "source": "user_input", "text": text},
        ),
        content_after=(
            ({"id": f"{trace_id}-after", "role": "user", "source": "user_input", "text": transformed},)
            if transformed is not None
            else ()
        ),
    )


def test_info_is_default_and_elevated_levels_require_key_and_acknowledgement(tmp_path):
    without_key = ControlPlaneService(tmp_path / "without-key.db")
    settings = without_key.guardrail_logging_settings(DEFAULT_GUARDRAIL_ID)

    assert settings.level == "info"
    assert settings.retention_days == 7
    assert settings.content_capture_enabled is False
    with pytest.raises(ValidationError, match="acknowledgement"):
        without_key.update_guardrail_logging_settings(
            DEFAULT_GUARDRAIL_ID,
            level="debug",
            actor_id="admin-1",
        )
    with pytest.raises(ValidationError, match="ENCRYPTION_KEY"):
        without_key.update_guardrail_logging_settings(
            DEFAULT_GUARDRAIL_ID,
            level="debug",
            actor_id="admin-1",
            acknowledge_cost=True,
        )


def test_info_correlates_an_allowed_input_when_the_output_is_blocked_and_encrypts_content(tmp_path):
    service = _service(tmp_path)
    input_text = "customer secret 12345"
    output_text = "blocked model answer"

    _record(service, trace_id="trace-input", call_id="call-1", phase="input", outcome="allow", text=input_text)
    assert service.runtime_log_interactions(include_content=True)[0] == ()

    _record(service, trace_id="trace-output", call_id="call-1", phase="output", outcome="block", text=output_text)
    items, cursor = service.runtime_log_interactions(include_content=True)

    assert cursor is None
    assert len(items) == 1
    assert items[0].outcome == "block"
    assert [entry.phase for entry in items[0].entries] == ["input", "output"]
    assert items[0].entries[0].content_before is not None
    assert items[0].entries[0].content_before[0].text == input_text
    assert items[0].entries[1].content_before is not None
    assert items[0].entries[1].content_before[0].text == output_text

    redacted_items, _ = service.runtime_log_interactions(include_content=False)
    assert redacted_items[0].entries[0].content_before is None
    assert redacted_items[0].entries[0].content_available is True

    with service.database.session() as session:
        rows = session.scalars(select(RuntimeLogEntryModel)).all()
        ciphertext = " ".join(row.content_before_ciphertext or "" for row in rows)
    assert input_text not in ciphertext
    assert output_text not in ciphertext


def test_debug_records_transformations_and_trace_records_approved_traffic(tmp_path):
    service = _service(tmp_path)
    service.update_guardrail_logging_settings(
        DEFAULT_GUARDRAIL_ID,
        level="debug",
        actor_id="admin-debug",
        acknowledge_cost=True,
    )

    _record(service, trace_id="debug-allow", call_id=None, phase="input", outcome="allow", text="ordinary")
    _record(
        service,
        trace_id="debug-transform",
        call_id=None,
        phase="input",
        outcome="transform",
        text="my email is me@example.com",
        transformed="my email is [REDACTED]",
    )
    debug_items, _ = service.runtime_log_interactions(include_content=True)
    assert len(debug_items) == 1
    assert debug_items[0].capture_level == "debug"
    assert debug_items[0].entries[0].content_after is not None
    assert debug_items[0].entries[0].content_after[0].text.endswith("[REDACTED]")

    service.update_guardrail_logging_settings(
        DEFAULT_GUARDRAIL_ID,
        level="trace",
        actor_id="admin-trace",
        acknowledge_cost=True,
    )
    _record(service, trace_id="trace-allow-in", call_id="call-trace", phase="input", outcome="allow", text="hello")
    _record(service, trace_id="trace-allow-out", call_id="call-trace", phase="output", outcome="allow", text="hello back")

    trace_items, _ = service.runtime_log_interactions(outcome="allow", include_content=True)
    assert len(trace_items) == 1
    assert trace_items[0].capture_level == "trace"
    assert [entry.phase for entry in trace_items[0].entries] == ["input", "output"]


def test_logging_changes_remain_content_free_evidence_and_retention_deletes_old_interactions(tmp_path):
    service = _service(tmp_path)
    service.update_guardrail_logging_settings(
        DEFAULT_GUARDRAIL_ID,
        level="trace",
        actor_id="admin-audit",
        acknowledge_cost=True,
    )
    _record(service, trace_id="old-trace", call_id=None, phase="input", outcome="allow", text="expired content")

    evidence = service.evidence_records()
    event = next(
        item
        for item in evidence
        if item.kind == "guardrail.logging_level.updated"
        and item.guardrail_id == DEFAULT_GUARDRAIL_ID
    )
    assert event.actor_id == "admin-audit"
    assert dict(event.metadata) == {"level": "trace", "previous_level": "info"}
    assert "expired content" not in event.detail

    with service.database.transaction() as session:
        row = session.scalar(select(RuntimeLogInteractionModel).where(RuntimeLogInteractionModel.guardrail_id == DEFAULT_GUARDRAIL_ID))
        assert row is not None
        row.created_at = datetime.now(UTC) - timedelta(days=8)
    assert service.cleanup_runtime_logs() == 1
    assert service.runtime_log_interactions(include_content=True)[0] == ()


@pytest.mark.asyncio
async def test_runtime_log_api_restricts_configuration_and_decryption_to_admins(tmp_path, monkeypatch):
    encryption_key = Fernet.generate_key().decode()
    monkeypatch.setenv("TEST_RUNTIME_LOG_KEY", encryption_key)
    app = create_app(
        settings=Settings(
            database_path=tmp_path / "runtime-log-api.db",
            ui_dist_path=tmp_path / "missing-ui",
            runtime_log_encryption_key_env_var="TEST_RUNTIME_LOG_KEY",
        )
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        login = await client.post(
            "/api/v1/session", json={"email": "admin", "password": "admin"}
        )
        assert login.status_code == 200
        configured = await client.patch(
            f"/api/v1/guardrails/{DEFAULT_GUARDRAIL_ID}/logging",
            json={"level": "trace", "acknowledge_cost": True},
        )
        assert configured.status_code == 200

        _record(
            app.state.control_plane,
            trace_id="api-trace",
            call_id=None,
            phase="input",
            outcome="allow",
            text="administrator-visible content",
        )
        admin_logs = await client.get("/api/v1/runtime-logs")
        assert admin_logs.status_code == 200
        assert admin_logs.json()["items"][0]["entries"][0]["content_before"][0]["text"] == "administrator-visible content"
        control_plane_audit = await client.get("/api/v1/audit-logs")
        assert control_plane_audit.status_code == 404

        created = await client.post(
            "/api/v1/users",
            json={
                "display_name": "Log Reviewer",
                "email": "reviewer@example.com",
                "password": "reviewer-password",
                "role": "member",
                "preferred_language": "en",
            },
        )
        assert created.status_code == 201
        await client.delete("/api/v1/session")
        member_login = await client.post(
            "/api/v1/session",
            json={"email": "reviewer@example.com", "password": "reviewer-password"},
        )
        assert member_login.status_code == 200
        member_logs = await client.get("/api/v1/runtime-logs")
        forbidden = await client.patch(
            f"/api/v1/guardrails/{DEFAULT_GUARDRAIL_ID}/logging",
            json={"level": "info", "acknowledge_cost": False},
        )

    entry = member_logs.json()["items"][0]["entries"][0]
    assert entry["content_available"] is True
    assert entry["content_before"] is None
    assert forbidden.status_code == 403
