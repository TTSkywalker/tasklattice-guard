from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.integrations import GENERIC_HTTP_GUARD_ADAPTER_ID
from app.main import create_app


CUSTOMER_DATA_COLANG = """\
flow check_customer_identifier_input $text
  $result = await TaskLatticeCustomerIdentifierAction(text=$text)
  if $result["detected"]
    $recorded = await TaskLatticeRecordPolicyAction(flow_name="check_customer_identifier_input", safe=False, text=$text, replacement=$result["redacted"])
  else
    $recorded = await TaskLatticeRecordPolicyAction(flow_name="check_customer_identifier_input", safe=True, text=$text)

flow check_customer_identifier_output $text
  $result = await TaskLatticeCustomerIdentifierAction(text=$text)
  if $result["detected"]
    $recorded = await TaskLatticeRecordPolicyAction(flow_name="check_customer_identifier_output", safe=False, text=$text, replacement=$result["redacted"])
  else
    $recorded = await TaskLatticeRecordPolicyAction(flow_name="check_customer_identifier_output", safe=True, text=$text)
"""


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        database_path=tmp_path / "native.db",
        ui_dist_path=tmp_path / "no-ui",
    )


async def _login(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/v1/session", json={"email": "admin", "password": "admin"}
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_customer_data_policy_runs_create_to_real_http_on_one_version(tmp_path):
    app = create_app(settings=_settings(tmp_path))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        await _login(client)
        created = await client.post(
            "/api/v1/policies",
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
                            "name": "TaskLatticeRecordPolicyAction",
                            "version": "1.0.0",
                        },
                    ],
                    "test_cases": [
                        {
                            "name": "Block customer identifier on input",
                            "rail_type": "input",
                            "content": "Contact alice@example.com",
                            "expected_decision": "block",
                            "covered_rule_ids": [
                                "flow/input/check_customer_identifier_input"
                            ],
                        },
                        {
                            "name": "Redact customer identifier on output",
                            "rail_type": "output",
                            "content": "Contact alice@example.com",
                            "expected_decision": "transform",
                            "covered_rule_ids": [
                                "flow/output/check_customer_identifier_output"
                            ],
                        },
                    ],
                },
            },
        )
        assert created.status_code == 201, created.text
        policy_id = created.json()["id"]

        validated = await client.post(f"/api/v1/policies/{policy_id}/validate")
        tested = await client.post(
            f"/api/v1/policies/{policy_id}/validation-runs"
        )
        published = await client.post(f"/api/v1/policies/{policy_id}/publish")
        assert validated.json()["valid"] is True
        assert tested.status_code == 201, tested.text
        assert tested.json()["status"] == "passed"
        assert [
            item["covered_rule_ids"] for item in tested.json()["results"]
        ] == [
            ["flow/input/check_customer_identifier_input"],
            ["flow/output/check_customer_identifier_output"],
        ]
        assert [
            item["matched_rule_ids"] for item in tested.json()["results"]
        ] == [
            ["flow/input/check_customer_identifier_input"],
            ["flow/output/check_customer_identifier_output"],
        ]
        assert published.status_code == 201, published.text
        policy_version = published.json()["version"]

        guardrail_response = await client.post(
            "/api/v1/guardrails",
            json={
                "name": "Customer Data Boundary",
                "purpose": "Keep customer identifiers inside the trusted service boundary.",
                "policy_bindings": [
                    {
                        "policy_id": policy_id,
                        "policy_version": str(policy_version),
                        "enabled_rails": ["input", "output"],
                    }
                ],
            },
        )
        assert guardrail_response.status_code == 201, guardrail_response.text
        guardrail_id = guardrail_response.json()["id"]

        preview = await client.get(
            f"/api/v1/guardrails/{guardrail_id}/compile-preview"
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["engine"] == "llmrails"
        assert preview.json()["colang_version"] == "2.x"
        assert preview.json()["dependency_manifest"]

        validation_run = await client.post(
            "/api/v1/validation-runs", json={"guardrail_id": guardrail_id}
        )
        assert validation_run.status_code == 201, validation_run.text
        assert validation_run.json()["status"] == "passed"
        assert [
            item["covered_rule_ids"]
            for item in validation_run.json()["results"]
        ] == [
            ["flow/input/check_customer_identifier_input"],
            ["flow/output/check_customer_identifier_output"],
        ]
        assert [
            item["matched_rule_ids"]
            for item in validation_run.json()["results"]
        ] == [
            ["flow/input/check_customer_identifier_input"],
            ["flow/output/check_customer_identifier_output"],
        ]
        guardrail_version = validation_run.json()["guardrail_version"]

        deployment = await client.post(
            "/api/v1/deployments",
            json={
                "name": "Customer API",
                "guardrail_id": guardrail_id,
                "traffic_scope": {
                    "combinator": "and",
                    "conditions": [
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
                "adapter_id": GENERIC_HTTP_GUARD_ADAPTER_ID,
            },
        )
        assert deployment.status_code == 201, deployment.text
        assert integration.status_code == 201, integration.text
        integration_id = integration.json()["integration"]["id"]
        credential = integration.json()["credential"]["value"]

        headers = {"x-api-key": credential, "x-app-id": "customer-api"}
        input_response = await client.post(
            f"/runtime/v1/integrations/{integration_id}/guardrails/evaluate",
            headers=headers,
            json={
                "input_type": "request",
                "texts": ["Contact alice@example.com"],
                "call_id": "customer-call-1",
                "output_scope": "full",
            },
        )
        output_response = await client.post(
            f"/runtime/v1/integrations/{integration_id}/guardrails/evaluate",
            headers=headers,
            json={
                "input_type": "response",
                "texts": ["Contact alice@example.com"],
                "call_id": "customer-call-1",
                "output_scope": "full",
            },
        )
        metrics_response = await client.get("/api/v1/metrics")

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
        "runtime", "policy", "rail", "action"
    } <= {item["kind"] for item in output_payload["trace"]}
    action_steps = [
        item for item in output_payload["trace"] if item["kind"] == "action"
    ]
    assert any(
        item["policy_id"] == policy_id
        and item["policy_version"] == str(policy_version)
        and item["rail_type"] == "output"
        and item["flow_name"] == "check_customer_identifier_output"
        and item["action_name"] == "TaskLatticeCustomerIdentifierAction"
        and item["action_version"] == "1.0.0"
        and item["engine"] == "llmrails"
        and item["config_checksum"]
        and item["provider_latency_ms"] >= 0
        for item in action_steps
    )
    assert any(
        item["kind"] == "action"
        and item["parallel_group"] == "customer-data-detection"
        for item in input_payload["trace"]
    )
    trace_contract = {
        "guardrail_id",
        "guardrail_version",
        "policy_id",
        "policy_version",
        "rail_type",
        "flow_name",
        "action_name",
        "action_version",
        "outcome",
        "duration_ms",
        "timed_out",
        "parallel_group",
        "engine",
        "config_checksum",
    }
    validation_trace = tested.json()["results"][0]["trace"]
    assert validation_trace and output_payload["trace"]
    assert all(trace_contract <= item.keys() for item in validation_trace)
    assert all(trace_contract <= item.keys() for item in output_payload["trace"])

    assert metrics_response.status_code == 200, metrics_response.text
    runtime_metrics = metrics_response.json()
    assert runtime_metrics["peak_active_concurrency"] >= 1
    assert runtime_metrics["provider_p95_ms"] >= 0
    assert any(
        item["guardrail_id"] == guardrail_id
        and item["guardrail_version"] == guardrail_version
        and item["requests"] == 2
        for item in runtime_metrics["version_distribution"]
    )
    assert any(
        item["policy_id"] == policy_id
        and item["policy_version"] == str(policy_version)
        and item["invocations"] >= 2
        for item in runtime_metrics["policy_distribution"]
    )
    assert "alice@example.com" not in metrics_response.text

    service = app.state.control_plane
    config = service.nemo_config(guardrail_id, guardrail_version)
    assert config.runtime_engine == "llmrails"
    assert config.guardrail_version == guardrail_version
    assert "tl." + policy_id + ".v1.check_customer_identifier_input" in {
        item.id for item in config.action_bindings
    }


def test_mutating_flows_cannot_share_an_unordered_parallel_group(tmp_path):
    app = create_app(settings=_settings(tmp_path))
    service = app.state.control_plane
    from app.control_plane.domain import (
        ActionReference,
        PolicyDraft,
        PolicySourceFile,
        RailBinding,
        ValidationError,
    )

    with pytest.raises(ValidationError, match="cannot share parallel group"):
        service.create_policy(
            name="Conflicting mutations",
            description="Invalid by design.",
            owner="test",
            draft=PolicyDraft(
                colang_version="2.x",
                sources=(PolicySourceFile("main.co", CUSTOMER_DATA_COLANG),),
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
