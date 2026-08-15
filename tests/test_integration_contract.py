from __future__ import annotations

import json
import uuid
from pathlib import Path

import httpx
import pytest
import yaml

from app.adapters.litellm import LiteLLMAdapter, LiteLLMGuardrailRequest
from app.config import Settings
from app.control_plane.catalog import builtin_policy_id
from app.control_plane.domain import (
    TestCaseResult,
    ValidationMetrics,
    GuardrailPolicyBinding,
    TrafficScopeExpression,
    TrafficCondition,
)
from app.integrations import (
    A2A_GUARD_ADAPTER_ID,
    GENERIC_HTTP_GUARD_ADAPTER_ID,
    LITELLM_GENERIC_GUARDRAIL_ADAPTER_ID,
)
from app.main import create_app
from app.runtime.contracts import ProtectionDecision


PUBLIC_RUNTIME_BASE_URL = "https://guard.example.com"


def policy_binding(risk: str, action: str) -> GuardrailPolicyBinding:
    return GuardrailPolicyBinding(
        policy_id=builtin_policy_id(risk),
        policy_version="1",
        action=action,
    )


def integration_settings(tmp_path: Path) -> Settings:
    return Settings(
        database_path=tmp_path / "tasklattice-guard-policy-schema-v3.db",
        ui_dist_path=tmp_path / "missing-ui",
        public_runtime_base_url=PUBLIC_RUNTIME_BASE_URL,
    )


async def login(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/v1/session",
        json={"email": "admin", "password": "admin"},
    )
    assert response.status_code == 200, response.text


async def create_integration(
    client: httpx.AsyncClient,
    *,
    name: str,
    adapter_id: str = LITELLM_GENERIC_GUARDRAIL_ADAPTER_ID,
) -> dict[str, object]:
    response = await client.post(
        "/api/v1/integrations",
        json={"name": name, "adapter_id": adapter_id},
    )
    assert response.status_code == 201, response.text
    return response.json()


def runtime_path(integration_id: str, suffix: str) -> str:
    return f"/runtime/v1/integrations/{integration_id}/{suffix}"


def litellm_path(integration_id: str) -> str:
    return runtime_path(integration_id, "beta/litellm_basic_guardrail_api")


def litellm_verify_path(integration_id: str) -> str:
    return runtime_path(integration_id, "verify")


def http_path(integration_id: str) -> str:
    return runtime_path(integration_id, "guardrails/evaluate")


def litellm_payload(
    *, input_type: str = "request", call_id: str = "call-1", text: str = "hello"
) -> dict[str, object]:
    return {
        "input_type": input_type,
        "litellm_call_id": call_id,
        "texts": [text],
    }


class RecordingEngine:
    name = "integration-contract"
    supported_phases = frozenset({"input", "output"})

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int]] = []
        self.requests = []

    async def evaluate(self, request):
        self.requests.append(request)
        self.calls.append(
            (
                request.phase,
                request.plan.guardrail_id,
                request.plan.guardrail_version,
            )
        )
        return ProtectionDecision(
            decision="allow",
            action="pass",
            reason="Allowed by the Integration contract test.",
            guardrail_id=request.plan.guardrail_id,
            guardrail_version=request.plan.guardrail_version,
            output_delivery=request.plan.output_delivery,
        )


@pytest.mark.asyncio
async def test_http_adapter_propagates_source_provenance_and_trusted_sink_context(tmp_path):
    engine = RecordingEngine()
    app = create_app(settings=integration_settings(tmp_path), engine=engine)
    registration = app.state.control_plane.create_integration(
        name="Structured context ingress",
        description="Phase-two trusted context contract",
        adapter_id=GENERIC_HTTP_GUARD_ADAPTER_ID,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            http_path(registration.integration.id),
            headers={"x-api-key": registration.credential.value},
            json={
                "protocol": "http",
                "content": [
                    {
                        "id": "retrieval-42",
                        "role": "retrieved_content",
                        "text": "Approved quarterly report.",
                        "source_id": "document-42",
                        "source_type": "document",
                        "retrieval_index": 3,
                        "provenance_id": "ingestion-7",
                        "mime_type": "application/pdf",
                        "origin_hash": "sha256:0123456789abcdef",
                    }
                ],
                "jwt_claims": {"department": "finance"},
                "output_sink": "json",
                "content_type": "application/json",
                "schema_id": "finance-summary-v2",
                "target_environment": "production",
            },
        )

    assert response.status_code == 200
    request = engine.requests[0]
    assert request.request_context is not None
    assert request.request_context.value("jwt_claim", "department") == "finance"
    assert request.request_context.value("field", "auth.claim_source") == (
        "integration_asserted"
    )
    assert request.request_context.value("field", "output.sink") == "json"
    assert request.request_context.value("field", "output.schema_id") == (
        "finance-summary-v2"
    )
    active = request.content_view.active_block
    assert active.metadata_value("source_id") == "document-42"
    assert active.metadata_value("retrieval_index") == "3"
    assert active.metadata_value("provenance_id") == "ingestion-7"


class ToggleEngine(RecordingEngine):
    def __init__(self) -> None:
        super().__init__()
        self.fail_next = True

    async def evaluate(self, request):
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("Simulated transient runtime failure.")
        return await super().evaluate(request)


def publish_guardrail(control_plane, name: str) -> str:
    guardrail = control_plane.create_guardrail(
        name=name,
        purpose=f"Protect traffic for {name}.",
        policy_bindings=(policy_binding("secrets", "reject"),),
    )
    control_plane.save_validation_run(
        guardrail_id=guardrail.id,
        guardrail_version=None,
        source_draft_version=guardrail.draft_version,
        status="passed",
        metrics=ValidationMetrics(1, 1, 100, 0, 0, 0, 1),
        results=(
            TestCaseResult(
                "case",
                "case",
                "secrets",
                "allow",
                "allow",
                True,
                "deterministic",
                1,
                "allowed",
            ),
        ),
    )
    control_plane.activate_tested_version(guardrail.id)
    return guardrail.id


def integration_scope(integration_id: str) -> TrafficScopeExpression:
    return TrafficScopeExpression(
        combinator="and",
        conditions=(
            TrafficCondition(
                field="integration.id",
                operator="equals",
                value=integration_id,
            ),
        ),
    )


@pytest.mark.asyncio
async def test_create_uses_adapter_uuid_and_returns_litellm_setup(tmp_path):
    app = create_app(settings=integration_settings(tmp_path), engine=RecordingEngine())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        await login(client)
        created = await create_integration(client, name="Gateway A")
        obsolete_protocol = await client.post(
            "/api/v1/integrations",
            json={"name": "Legacy payload", "protocol": "litellm"},
        )
        fetched = await client.get(
            f"/api/v1/integrations/{created['integration']['id']}"
        )

    integration = created["integration"]
    credential = created["credential"]
    integration_id = integration["id"]
    parsed_id = uuid.UUID(integration_id)

    assert str(parsed_id) == integration_id
    assert parsed_id.version == 4
    assert obsolete_protocol.status_code == 422
    assert integration["adapter_id"] == LITELLM_GENERIC_GUARDRAIL_ADAPTER_ID
    assert integration["protocol"] == "litellm"
    assert integration["setup_status"] == "awaiting_callback"
    assert integration["credentials"] == [
        {
            "id": credential["id"],
            "key_hint": credential["key_hint"],
            "created_at": credential["created_at"],
        }
    ]
    assert credential["value"].startswith("tali_integration_")
    assert credential["value"] not in json.dumps(integration)
    assert credential["value"] not in fetched.text
    assert "value" not in fetched.json()["credentials"][0]

    setup = integration["setup"]
    expected_base = f"{PUBLIC_RUNTIME_BASE_URL}/runtime/v1/integrations/{integration_id}"
    expected_callback = f"{expected_base}/beta/litellm_basic_guardrail_api"
    assert setup["api_base_url"] == expected_base
    assert setup["callback_url"] == expected_callback
    assert setup["callback_url"].count("/beta/litellm_basic_guardrail_api") == 1
    assert setup["auth_header"] == "x-api-key"
    assert setup["api_base_env_var"] == "TASKLATTICE_GUARD_API_BASE"
    assert setup["credential_env_var"] == "TASKLATTICE_GUARD_API_KEY"
    assert setup["recommended_modes"] == ["pre_call", "post_call"]
    assert setup["default_on"] is True
    assert setup["unreachable_fallback"] == "fail_closed"
    assert setup["fail_on_error"] is True

    config = yaml.safe_load(setup["yaml_template"])
    params = config["litellm_settings"]["guardrails"][0]["litellm_params"]
    assert params == {
        "guardrail": "tasklattice_guard",
        "mode": ["pre_call", "post_call"],
        "api_base": "os.environ/TASKLATTICE_GUARD_API_BASE",
        "api_key": "os.environ/TASKLATTICE_GUARD_API_KEY",
        "default_on": True,
        "unreachable_fallback": "fail_closed",
        "fail_on_error": True,
    }
    assert "environment" not in setup
    assert "environment" not in integration
    assert "/beta/litellm_basic_guardrail_api" not in setup["api_base_url"]


@pytest.mark.asyncio
async def test_litellm_verify_authenticates_without_recording_activity_or_setup(tmp_path):
    app = create_app(settings=integration_settings(tmp_path), engine=RecordingEngine())
    control_plane = app.state.control_plane
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        await login(client)
        gateway = await create_integration(client, name="Gateway verify")
        integration_id = gateway["integration"]["id"]
        credential = gateway["credential"]["value"]
        before = control_plane.integration(integration_id)
        evidence_before = control_plane.evidence_records()

        verified = await client.post(
            litellm_verify_path(integration_id), headers={"x-api-key": credential}
        )

        after = control_plane.integration(integration_id)
        evidence_after = control_plane.evidence_records()

    assert verified.status_code == 200
    assert verified.json() == {
        "ready": True,
        "adapter_id": LITELLM_GENERIC_GUARDRAIL_ADAPTER_ID,
        "protocol": "litellm",
        "integration_id": integration_id,
    }
    assert after == before
    assert after.setup_status == "awaiting_callback"
    assert after.request_count == 0
    assert after.first_seen_at is None
    assert after.input_seen_at is None
    assert after.output_seen_at is None
    assert evidence_after == evidence_before


@pytest.mark.asyncio
async def test_litellm_verify_rejects_wrong_secret_adapter_and_disabled_integration(
    tmp_path,
):
    app = create_app(settings=integration_settings(tmp_path), engine=RecordingEngine())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        await login(client)
        litellm = await create_integration(client, name="LiteLLM")
        http = await create_integration(
            client,
            name="HTTP",
            adapter_id=GENERIC_HTTP_GUARD_ADAPTER_ID,
        )
        integration_id = litellm["integration"]["id"]
        credential = litellm["credential"]["value"]

        missing = await client.post(litellm_verify_path(integration_id))
        wrong_secret = await client.post(
            litellm_verify_path(integration_id),
            headers={"x-api-key": http["credential"]["value"]},
        )
        wrong_adapter = await client.post(
            litellm_verify_path(http["integration"]["id"]),
            headers={"x-api-key": http["credential"]["value"]},
        )
        disabled = await client.patch(
            f"/api/v1/integrations/{integration_id}", json={"enabled": False}
        )
        disabled_verify = await client.post(
            litellm_verify_path(integration_id), headers={"x-api-key": credential}
        )

    assert missing.status_code == 401
    assert wrong_secret.status_code == 401
    assert wrong_adapter.status_code == 401
    assert disabled.status_code == 200
    assert disabled_verify.status_code == 401


@pytest.mark.asyncio
async def test_litellm_runtime_url_binds_uuid_and_key_and_removes_shared_route(tmp_path):
    app = create_app(settings=integration_settings(tmp_path), engine=RecordingEngine())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        await login(client)
        gateway_a = await create_integration(client, name="Gateway A")
        gateway_b = await create_integration(client, name="Gateway B")
        id_a = gateway_a["integration"]["id"]
        id_b = gateway_b["integration"]["id"]
        key_a = gateway_a["credential"]["value"]
        key_b = gateway_b["credential"]["value"]

        a_with_a = await client.post(
            litellm_path(id_a),
            headers={"x-api-key": key_a},
            json=litellm_payload(call_id="a-valid"),
        )
        a_with_b = await client.post(
            litellm_path(id_a),
            headers={"x-api-key": key_b},
            json=litellm_payload(call_id="a-wrong"),
        )
        b_with_a = await client.post(
            litellm_path(id_b),
            headers={"x-api-key": key_a},
            json=litellm_payload(call_id="b-wrong"),
        )
        shared_route = await client.post(
            "/beta/litellm_basic_guardrail_api",
            headers={"x-api-key": key_a},
            json=litellm_payload(call_id="legacy"),
        )

        disabled = await client.patch(
            f"/api/v1/integrations/{id_a}", json={"enabled": False}
        )
        disabled_call = await client.post(
            litellm_path(id_a),
            headers={"x-api-key": key_a},
            json=litellm_payload(call_id="disabled"),
        )
        system_status = await client.get("/api/v1/system-status")

    assert a_with_a.status_code == 200
    assert a_with_a.json() == {"action": "NONE"}
    assert a_with_b.status_code == 401
    assert b_with_a.status_code == 401
    assert shared_route.status_code == 404
    assert disabled.status_code == 200
    assert disabled.json()["setup_status"] == "disabled"
    assert disabled_call.status_code == 401
    assert system_status.json()["enabled_integrations"] == 1
    assert system_status.json()["total_integrations"] == 2
    assert "online_integrations" not in system_status.json()


@pytest.mark.asyncio
async def test_same_litellm_call_id_is_isolated_and_integration_scope_selects_deployment(
    tmp_path,
):
    engine = RecordingEngine()
    app = create_app(settings=integration_settings(tmp_path), engine=engine)
    control_plane = app.state.control_plane
    gateway_a = control_plane.create_integration(
        name="Gateway A",
        description="",
        adapter_id=LITELLM_GENERIC_GUARDRAIL_ADAPTER_ID,
    )
    gateway_b = control_plane.create_integration(
        name="Gateway B",
        description="",
        adapter_id=LITELLM_GENERIC_GUARDRAIL_ADAPTER_ID,
    )
    guardrail_a = publish_guardrail(control_plane, "Gateway A Guardrail")
    guardrail_b = publish_guardrail(control_plane, "Gateway B Guardrail")
    deployment_a = control_plane.create_deployment(
        name="Gateway A deployment",
        guardrail_id=guardrail_a,
        traffic_scope=integration_scope(gateway_a.integration.id),
    )
    deployment_b = control_plane.create_deployment(
        name="Gateway B deployment",
        guardrail_id=guardrail_b,
        traffic_scope=integration_scope(gateway_b.integration.id),
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        responses = []
        for registration, input_type in (
            (gateway_a, "request"),
            (gateway_b, "request"),
            (gateway_a, "response"),
            (gateway_b, "response"),
        ):
            responses.append(
                await client.post(
                    litellm_path(registration.integration.id),
                    headers={"x-api-key": registration.credential.value},
                    json=litellm_payload(
                        input_type=input_type,
                        call_id="same-upstream-call-id",
                    ),
                )
            )

    assert all(response.status_code == 200 for response in responses)
    assert [call[:2] for call in engine.calls] == [
        ("input", guardrail_a),
        ("input", guardrail_b),
        ("output", guardrail_a),
        ("output", guardrail_b),
    ]
    assert deployment_a.id != deployment_b.id
    normalized_a = LiteLLMAdapter._to_engine_request(
        LiteLLMGuardrailRequest(**litellm_payload(call_id="same-upstream-call-id")),
        gateway_a.integration,
    )
    normalized_b = LiteLLMAdapter._to_engine_request(
        LiteLLMGuardrailRequest(**litellm_payload(call_id="same-upstream-call-id")),
        gateway_b.integration,
    )
    assert normalized_a.call_id == (
        f"{gateway_a.integration.id}:same-upstream-call-id"
    )
    assert normalized_b.call_id == (
        f"{gateway_b.integration.id}:same-upstream-call-id"
    )
    assert normalized_a.call_id != normalized_b.call_id
    normalized_sink = LiteLLMAdapter._to_engine_request(
        LiteLLMGuardrailRequest(
            input_type="response",
            texts=["result"],
            request_data={
                "output_sink": "json",
                "content_type": "application/json",
                "schema_id": "finance-summary-v2",
                "tool_name": "publish_summary",
                "target_environment": "production",
            },
        ),
        gateway_a.integration,
    )
    assert normalized_sink.context.value("field", "output.sink") == "json"
    assert normalized_sink.context.value("field", "output.schema_id") == (
        "finance-summary-v2"
    )
    assert normalized_sink.context.value("field", "tool.name") == "publish_summary"
    runtime_events = control_plane.runtime_metrics(
        since="1970-01-01T00:00:00+00:00"
    )
    assert {
        (event.integration_id, event.deployment_id, event.guardrail_id)
        for event in runtime_events
    } == {
        (gateway_a.integration.id, deployment_a.id, guardrail_a),
        (gateway_b.integration.id, deployment_b.id, guardrail_b),
    }


@pytest.mark.asyncio
async def test_first_callback_verifies_setup_and_survives_restart(tmp_path):
    configured = integration_settings(tmp_path)
    app = create_app(settings=configured, engine=RecordingEngine())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        await login(client)
        created = await create_integration(client, name="Persistent Gateway")
        integration_id = created["integration"]["id"]
        credential = created["credential"]["value"]
        input_result = await client.post(
            litellm_path(integration_id),
            headers={"x-api-key": credential},
            json=litellm_payload(input_type="request", call_id="persistent-call"),
        )
        verified_after_input = await client.get(
            f"/api/v1/integrations/{integration_id}"
        )
        output_result = await client.post(
            litellm_path(integration_id),
            headers={"x-api-key": credential},
            json=litellm_payload(input_type="response", call_id="persistent-call"),
        )
        verified = await client.get(f"/api/v1/integrations/{integration_id}")

    assert input_result.status_code == 200
    assert verified_after_input.json()["setup_status"] == "verified"
    assert verified_after_input.json()["input_seen_at"] is not None
    assert verified_after_input.json()["output_seen_at"] is None
    assert output_result.status_code == 200
    assert verified.json()["setup_status"] == "verified"
    assert verified.json()["first_seen_at"] is not None
    assert verified.json()["input_seen_at"] is not None
    assert verified.json()["output_seen_at"] is not None

    restarted = create_app(settings=configured, engine=RecordingEngine())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=restarted), base_url="http://test"
    ) as client:
        await login(client)
        after_restart = await client.get(f"/api/v1/integrations/{integration_id}")

    assert after_restart.status_code == 200
    assert after_restart.json()["setup_status"] == "verified"
    for field in (
        "first_seen_at",
        "last_seen_at",
        "input_seen_at",
        "output_seen_at",
        "request_count",
    ):
        assert after_restart.json()[field] == verified.json()[field]
    assert credential not in after_restart.text


@pytest.mark.asyncio
async def test_transient_runtime_error_recovers_health_and_counters_survive_restart(
    tmp_path,
):
    configured = integration_settings(tmp_path)
    app = create_app(settings=configured, engine=ToggleEngine())
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await login(client)
        created = await create_integration(client, name="Recovering Gateway")
        integration_id = created["integration"]["id"]
        credential = created["credential"]["value"]

        failed = await client.post(
            litellm_path(integration_id),
            headers={"x-api-key": credential},
            json=litellm_payload(call_id="transient-failure"),
        )
        degraded = await client.get(f"/api/v1/integrations/{integration_id}")
        degraded_system = await client.get("/api/v1/system-status")
        recovered_call = await client.post(
            litellm_path(integration_id),
            headers={"x-api-key": credential},
            json=litellm_payload(call_id="successful-retry"),
        )
        recovered = await client.get(f"/api/v1/integrations/{integration_id}")
        recovered_system = await client.get("/api/v1/system-status")

    assert failed.status_code == 500
    assert degraded.json()["runtime_status"] == "degraded"
    assert degraded.json()["request_count"] == 1
    assert degraded.json()["error_count"] == 1
    assert degraded.json()["last_error_at"] == degraded.json()["last_seen_at"]
    assert degraded_system.json()["status"] == "degraded"
    assert degraded_system.json()["enabled_integrations"] == 1

    assert recovered_call.status_code == 200
    assert recovered.json()["runtime_status"] == "healthy"
    assert recovered.json()["request_count"] == 2
    assert recovered.json()["error_count"] == 1
    assert recovered.json()["last_error_at"] == degraded.json()["last_error_at"]
    assert recovered.json()["last_seen_at"] != recovered.json()["last_error_at"]
    assert recovered_system.json()["status"] == "healthy"
    assert recovered_system.json()["enabled_integrations"] == 1

    restarted = create_app(settings=configured, engine=RecordingEngine())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=restarted), base_url="http://test"
    ) as client:
        await login(client)
        after_restart = await client.get(f"/api/v1/integrations/{integration_id}")

    assert after_restart.status_code == 200
    for field in (
        "runtime_status",
        "first_seen_at",
        "last_seen_at",
        "input_seen_at",
        "request_count",
        "error_count",
        "last_error_at",
    ):
        assert after_restart.json()[field] == recovered.json()[field]


@pytest.mark.asyncio
async def test_credential_rotation_and_revocation_lifecycle(tmp_path):
    configured = integration_settings(tmp_path)
    app = create_app(settings=configured, engine=RecordingEngine())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        await login(client)
        created = await create_integration(client, name="Rotating Gateway")
        integration_id = created["integration"]["id"]
        old_credential = created["credential"]

        rotated_response = await client.post(
            f"/api/v1/integrations/{integration_id}/credentials"
        )
        assert rotated_response.status_code == 201, rotated_response.text
        rotated = rotated_response.json()
        new_credential = rotated["credential"]
        both_active = await client.get(f"/api/v1/integrations/{integration_id}")
        old_call = await client.post(
            litellm_path(integration_id),
            headers={"x-api-key": old_credential["value"]},
            json=litellm_payload(call_id="old-active"),
        )
        new_call = await client.post(
            litellm_path(integration_id),
            headers={"x-api-key": new_credential["value"]},
            json=litellm_payload(call_id="new-active"),
        )
        revoked = await client.delete(
            f"/api/v1/integrations/{integration_id}/credentials/{old_credential['id']}"
        )
        old_after_revoke = await client.post(
            litellm_path(integration_id),
            headers={"x-api-key": old_credential["value"]},
            json=litellm_payload(call_id="old-revoked"),
        )
        new_after_revoke = await client.post(
            litellm_path(integration_id),
            headers={"x-api-key": new_credential["value"]},
            json=litellm_payload(call_id="new-after-revoke"),
        )
        fetched = await client.get(f"/api/v1/integrations/{integration_id}")
        last_active = await client.delete(
            f"/api/v1/integrations/{integration_id}/credentials/{new_credential['id']}"
        )

    assert new_credential["id"] != old_credential["id"]
    assert new_credential["value"] != old_credential["value"]
    assert {item["id"] for item in both_active.json()["credentials"]} == {
        old_credential["id"],
        new_credential["id"],
    }
    assert old_call.status_code == new_call.status_code == 200
    assert revoked.status_code == 204
    assert old_after_revoke.status_code == 401
    assert new_after_revoke.status_code == 200
    assert [item["id"] for item in fetched.json()["credentials"]] == [
        new_credential["id"]
    ]
    assert old_credential["value"] not in fetched.text
    assert new_credential["value"] not in fetched.text
    assert last_active.status_code == 409

    restarted = create_app(settings=configured, engine=RecordingEngine())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=restarted), base_url="http://test"
    ) as client:
        old_after_restart = await client.post(
            litellm_path(integration_id),
            headers={"x-api-key": old_credential["value"]},
            json=litellm_payload(call_id="old-restarted"),
        )
        new_after_restart = await client.post(
            litellm_path(integration_id),
            headers={"x-api-key": new_credential["value"]},
            json=litellm_payload(call_id="new-restarted"),
        )

    assert old_after_restart.status_code == 401
    assert new_after_restart.status_code == 200


@pytest.mark.asyncio
async def test_http_and_a2a_use_instance_urls_and_enforce_adapter_protocol(tmp_path):
    app = create_app(settings=integration_settings(tmp_path), engine=RecordingEngine())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        await login(client)
        http_integration = await create_integration(
            client,
            name="HTTP Gateway",
            adapter_id=GENERIC_HTTP_GUARD_ADAPTER_ID,
        )
        a2a_integration = await create_integration(
            client,
            name="A2A Gateway",
            adapter_id=A2A_GUARD_ADAPTER_ID,
        )
        http_id = http_integration["integration"]["id"]
        a2a_id = a2a_integration["integration"]["id"]
        http_key = http_integration["credential"]["value"]
        a2a_key = a2a_integration["credential"]["value"]

        http_result = await client.post(
            http_path(http_id),
            headers={"x-api-key": http_key},
            json={"protocol": "http", "texts": ["hello"], "call_id": "http-1"},
        )
        a2a_result = await client.post(
            http_path(a2a_id),
            headers={"x-api-key": a2a_key},
            json={
                "protocol": "a2a",
                "texts": ["hello"],
                "a2a_operation": "SendMessage",
                "a2a_task_id": "task-1",
            },
        )
        wrong_http_protocol = await client.post(
            http_path(http_id),
            headers={"x-api-key": http_key},
            json={"protocol": "a2a", "texts": ["hello"]},
        )
        wrong_a2a_protocol = await client.post(
            http_path(a2a_id),
            headers={"x-api-key": a2a_key},
            json={"protocol": "http", "texts": ["hello"]},
        )
        old_shared_route = await client.post(
            "/v1/guardrails/evaluate",
            headers={"x-api-key": http_key},
            json={"protocol": "http", "texts": ["hello"]},
        )

    assert http_integration["integration"]["protocol"] == "http"
    assert a2a_integration["integration"]["protocol"] == "a2a"
    assert http_result.status_code == 200
    assert http_result.json()["decision"] == "allow"
    assert a2a_result.status_code == 200
    assert a2a_result.json()["decision"] == "allow"
    assert wrong_http_protocol.status_code == 401
    assert wrong_a2a_protocol.status_code == 401
    assert old_shared_route.status_code == 404
