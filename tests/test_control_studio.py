from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.main import create_app
from app.runtime.contracts import EvaluationDecision


PASS_THROUGH_COLANG = """\
flow allow_input $text
  pass
"""


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        database_path=tmp_path / "studio.db",
        ui_dist_path=tmp_path / "no-ui",
    )


@asynccontextmanager
async def _client(tmp_path: Path, *, engine=None):
    app = create_app(settings=_settings(tmp_path), engine=engine)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        await client.post(
            "/api/v1/session", json={"email": "admin", "password": "admin"}
        )
        yield client


class _ConcurrentEvaluationEngine:
    name = "evaluation-concurrency-probe"
    supported_phases = frozenset({"input", "output"})

    def __init__(self):
        self.active = 0
        self.maximum = 0

    async def evaluate(self, request):
        self.active += 1
        self.maximum = max(self.maximum, self.active)
        try:
            await asyncio.sleep(0.03)
            return EvaluationDecision(
                decision="allow",
                action="pass",
                reason="Concurrency probe completed.",
                guardrail_id=request.plan.guardrail_id,
                guardrail_version=request.plan.guardrail_version,
                output_delivery=request.plan.output_delivery,
            )
        finally:
            self.active -= 1


@pytest.mark.asyncio
async def test_failed_current_draft_evaluation_blocks_control_publish(tmp_path):
    async with _client(tmp_path) as client:
        created = await client.post(
            "/api/v1/controls",
            json={
                "name": "Evaluation gated Control",
                "description": "Prove that failed Evaluation blocks publication.",
                "owner": "security-platform",
                "draft": {
                    "colang_version": "2.x",
                    "sources": [
                        {"path": "main.co", "content": PASS_THROUGH_COLANG}
                    ],
                    "rail_bindings": [
                        {
                            "rail_type": "input",
                            "flow_name": "allow_input",
                            "execution_mode": "detect",
                            "on_unsafe": "reject",
                            "timeout_ms": 250,
                        }
                    ],
                    "tests": [
                        {
                            "name": "Expect an intentionally wrong block",
                            "rail_type": "input",
                            "content": "ordinary safe content",
                            "expected_decision": "block",
                        }
                    ],
                },
            },
        )
        assert created.status_code == 201, created.text
        control_id = created.json()["id"]

        evaluated = await client.post(
            f"/api/v1/controls/{control_id}/test-runs"
        )
        published = await client.post(f"/api/v1/controls/{control_id}/publish")

        assert evaluated.status_code == 201, evaluated.text
        assert evaluated.json()["status"] == "failed"
        assert published.status_code == 422
        assert "must pass Evaluation" in published.json()["detail"]


@pytest.mark.asyncio
async def test_guardrail_creation_preview_compiles_pinned_native_version(tmp_path):
    async with _client(tmp_path) as client:
        controls = await client.get("/api/v1/controls")
        built_in = next(
            item
            for item in controls.json()["items"]
            if item["id"] == "builtin-secrets"
        )
        assert built_in["versions"][0]["version"] == 1

        preview = await client.post(
            "/api/v1/guardrail-compile-previews",
            json={
                "name": "Native candidate",
                "purpose": "Review the exact NeMo runtime before saving.",
                "control_bindings": [
                    {
                        "control_id": "builtin-secrets",
                        "control_version": 1,
                        "enabled_rails": ["input", "output"],
                    }
                ],
            },
        )

        assert preview.status_code == 200, preview.text
        payload = preview.json()
        assert payload["engine"] == "llmrails"
        assert payload["colang_version"] == "2.x"
        assert payload["checksum"]
        assert payload["dependency_manifest"]
        assert payload["estimated_critical_path_ms"] > 0


@pytest.mark.asyncio
async def test_evaluation_runs_concurrency_groups_and_only_required_cases_gate(tmp_path):
    engine = _ConcurrentEvaluationEngine()
    async with _client(tmp_path, engine=engine) as client:
        created = await client.post(
            "/api/v1/controls",
            json={
                "name": "Concurrent Evaluation Control",
                "description": "Exercise grouped Evaluation cases.",
                "owner": "security-platform",
                "draft": {
                    "colang_version": "2.x",
                    "sources": [
                        {"path": "main.co", "content": PASS_THROUGH_COLANG}
                    ],
                    "rail_bindings": [
                        {
                            "rail_type": "input",
                            "flow_name": "allow_input",
                            "execution_mode": "detect",
                            "on_unsafe": "reject",
                            "timeout_ms": 250,
                        }
                    ],
                    "tests": [
                        {
                            "name": "Concurrent A",
                            "rail_type": "input",
                            "content": "safe-a",
                            "expected_decision": "allow",
                            "case_type": "concurrency",
                            "concurrency_group": "burst-a",
                        },
                        {
                            "name": "Concurrent B",
                            "rail_type": "input",
                            "content": "safe-b",
                            "expected_decision": "allow",
                            "case_type": "concurrency",
                            "concurrency_group": "burst-a",
                        },
                        {
                            "name": "Optional negative probe",
                            "rail_type": "input",
                            "content": "safe-c",
                            "expected_decision": "block",
                            "required": False,
                        },
                    ],
                },
            },
        )
        assert created.status_code == 201, created.text

        evaluated = await client.post(
            f"/api/v1/controls/{created.json()['id']}/test-runs"
        )

    assert evaluated.status_code == 201, evaluated.text
    payload = evaluated.json()
    assert payload["status"] == "passed"
    assert engine.maximum == 2
    assert [item["concurrency_group"] for item in payload["results"][:2]] == [
        "burst-a",
        "burst-a",
    ]
    assert payload["results"][2]["required"] is False
    assert payload["results"][2]["passed"] is False
