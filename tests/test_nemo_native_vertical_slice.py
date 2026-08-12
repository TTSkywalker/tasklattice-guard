from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.main import create_app


CUSTOMER_DATA_COLANG = """\
flow check_customer_identifier_input $text
  $result = await TaskLatticeCustomerIdentifierAction(text=$text)
  if $result["detected"]
    $recorded = await TaskLatticeRecordControlAction(flow_name="check_customer_identifier_input", safe=False, text=$text, replacement=$result["redacted"])
  else
    $recorded = await TaskLatticeRecordControlAction(flow_name="check_customer_identifier_input", safe=True, text=$text)

flow check_customer_identifier_output $text
  $result = await TaskLatticeCustomerIdentifierAction(text=$text)
  if $result["detected"]
    $recorded = await TaskLatticeRecordControlAction(flow_name="check_customer_identifier_output", safe=False, text=$text, replacement=$result["redacted"])
  else
    $recorded = await TaskLatticeRecordControlAction(flow_name="check_customer_identifier_output", safe=True, text=$text)
"""


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        nemo_config_path=tmp_path / "no-profile",
        database_path=tmp_path / "native.db",
        ui_dist_path=tmp_path / "no-ui",
    )


async def _login(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/v1/session", json={"email": "admin", "password": "admin"}
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_customer_data_control_runs_create_to_real_http_on_one_version(tmp_path):
    app = create_app(settings=_settings(tmp_path))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        await _login(client)
        created = await client.post(
            "/api/v1/controls",
            json={
                "name": "Customer Data Protection",
                "description": "Block customer identifiers on input and redact them on output.",
                "owner": "security-platform",
                "draft": {
                    "colang_version": "2.x",
                    "sources": [
                        {"path": "customer_data.co", "content": CUSTOMER_DATA_COLANG}
                    ],
                    "rail_bindings": [
                        {
                            "rail_type": "input",
                            "flow_name": "check_customer_identifier_input",
                            "execution_mode": "detect",
                            "on_unsafe": "reject",
                            "parallel_group": "customer-data-detection",
                            "timeout_ms": 500,
                        },
                        {
                            "rail_type": "output",
                            "flow_name": "check_customer_identifier_output",
                            "execution_mode": "mutate",
                            "on_unsafe": "redact",
                            "priority": 100,
                            "timeout_ms": 500,
                        },
                    ],
                    "action_references": [
                        {
                            "name": "TaskLatticeCustomerIdentifierAction",
                            "version": "1.0.0",
                        },
                        {
                            "name": "TaskLatticeRecordControlAction",
                            "version": "1.0.0",
                        },
                    ],
                    "tests": [
                        {
                            "name": "Block customer identifier on input",
                            "rail_type": "input",
                            "content": "Contact alice@example.com",
                            "expected_decision": "block",
                        },
                        {
                            "name": "Redact customer identifier on output",
                            "rail_type": "output",
                            "content": "Contact alice@example.com",
                            "expected_decision": "transform",
                        },
                    ],
                },
            },
        )
        assert created.status_code == 201, created.text
        control_id = created.json()["id"]

        validated = await client.post(f"/api/v1/controls/{control_id}/validate")
        published = await client.post(f"/api/v1/controls/{control_id}/publish")
        assert validated.json()["valid"] is True
        assert published.status_code == 201, published.text
        control_version = published.json()["version"]

        guardrail_response = await client.post(
            "/api/v1/guardrails",
            json={
                "name": "Customer Data Boundary",
                "purpose": "Keep customer identifiers inside the trusted service boundary.",
                "control_bindings": [
                    {
                        "control_id": control_id,
                        "control_version": control_version,
                        "enabled_rails": ["input", "output"],
                    }
                ],
            },
        )
        assert guardrail_response.status_code == 201, guardrail_response.text
        guardrail_id = guardrail_response.json()["id"]

        evaluation = await client.post(
            "/api/v1/test-runs", json={"guardrail_id": guardrail_id}
        )
        assert evaluation.status_code == 201, evaluation.text
        assert evaluation.json()["status"] == "passed"
        guardrail_version = evaluation.json()["guardrail_version"]

        assignment = await client.post(
            "/api/v1/assignments",
            json={
                "name": "Customer API",
                "guardrail_id": guardrail_id,
                "traffic_scope": {
                    "combinator": "and",
                    "rules": [
                        {
                            "field": "http.header",
                            "key": "x-app-id",
                            "operator": "equals",
                            "value": "customer-api",
                        }
                    ],
                },
            },
        )
        integration = await client.post(
            "/api/v1/integrations",
            json={
                "name": "Customer HTTP ingress",
                "environment": "test",
                "protocol": "http",
            },
        )
        assert assignment.status_code == 201, assignment.text
        assert integration.status_code == 201, integration.text
        credential = integration.json()["credential"]

        headers = {"x-api-key": credential, "x-app-id": "customer-api"}
        input_response = await client.post(
            "/v1/guardrails/evaluate",
            headers=headers,
            json={
                "input_type": "request",
                "texts": ["Contact alice@example.com"],
                "call_id": "customer-call-1",
                "output_scope": "full",
            },
        )
        output_response = await client.post(
            "/v1/guardrails/evaluate",
            headers=headers,
            json={
                "input_type": "response",
                "texts": ["Contact alice@example.com"],
                "call_id": "customer-call-1",
                "output_scope": "full",
            },
        )

    assert input_response.status_code == 200, input_response.text
    assert output_response.status_code == 200, output_response.text
    input_payload = input_response.json()
    output_payload = output_response.json()
    assert (input_payload["decision"], input_payload["action"]) == ("block", "reject")
    assert (output_payload["decision"], output_payload["action"]) == (
        "transform",
        "redact",
    )
    assert "alice@example.com" not in output_payload["texts"][0]
    assert input_payload["guardrail_version"] == guardrail_version
    assert output_payload["guardrail_version"] == guardrail_version
    assert {
        "runtime", "control", "rail", "evaluator"
    } <= {item["kind"] for item in output_payload["trace"]}
    assert any(
        "TaskLatticeCustomerIdentifierAction@1.0.0" in item["detail"]
        and "check_customer_identifier_output" in item["detail"]
        for item in output_payload["trace"]
    )

    service = app.state.control_plane
    config = service.nemo_config(guardrail_id, guardrail_version)
    assert config.runtime_engine == "llmrails"
    assert config.guardrail_version == guardrail_version
    assert "tl." + control_id + ".v1.check_customer_identifier_input" in {
        item.id for item in config.action_bindings
    }


def test_mutating_flows_cannot_share_an_unordered_parallel_group(tmp_path):
    app = create_app(settings=_settings(tmp_path))
    service = app.state.control_plane
    from app.control_plane.domain import (
        ActionReference,
        ControlDraft,
        ControlSourceFile,
        RailBinding,
        ValidationError,
    )

    with pytest.raises(ValidationError, match="cannot share parallel group"):
        service.create_control(
            name="Conflicting mutations",
            description="Invalid by design.",
            owner="test",
            draft=ControlDraft(
                colang_version="2.x",
                sources=(ControlSourceFile("main.co", CUSTOMER_DATA_COLANG),),
                parameter_schema=(),
                rail_bindings=(
                    RailBinding(
                        "output", "check_customer_identifier_input", "mutate",
                        "redact", parallel_group="unordered", priority=10,
                    ),
                    RailBinding(
                        "output", "check_customer_identifier_output", "mutate",
                        "rewrite", parallel_group="unordered", priority=20,
                    ),
                ),
                action_references=(
                    ActionReference("TaskLatticeCustomerIdentifierAction", "1.0.0"),
                ),
            ),
        )
