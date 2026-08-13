from __future__ import annotations

import httpx
import pytest

from app.policy_library import policies, policy, policy_catalog


def test_policy_library_loads_canonical_product_policies():
    items = policies()

    assert len(items) == 17
    # Reused implementation rules are intentionally materialized in each
    # Policy that owns them; the product contract is Policy-scoped.
    assert sum(len(item.rules) for item in items) == 222
    assert sum(item.test_count for item in items) == 272
    assert all(item.rules for item in items)
    assert all(item.test_cases for item in items)
    assert all(item.parameters is not None for item in items)


def test_policy_rule_ids_are_unique_and_every_test_references_policy_rules():
    for item in policies():
        rule_ids = {rule.id for rule in item.rules}
        assert len(rule_ids) == len(item.rules), item.id
        for case in item.test_cases:
            assert case.covered_rule_ids
            assert set(case.covered_rule_ids) <= rule_ids


def test_policy_metadata_is_non_exclusive_and_includes_runtime_provenance():
    item = policy("mas-ai-risk-management")

    assert item is not None
    assert {
        "capability:regulatory-governance",
        "domain:financial-services",
        "framework:mas-ai-risk",
        "engine:nemo-guardrails",
        "stage:input",
    } <= {tag.id for tag in item.tags}


def test_public_policy_payload_is_policy_rule_test_not_control_pack_control():
    item = next(
        candidate
        for candidate in policy_catalog()
        if candidate["id"] == "aviation-operations-security"
    )

    assert item["implementation"] == "rules"
    assert len(item["rules"]) == 26
    assert item["test_count"] == 51
    assert "policy_ids" not in item
    assert "packs" not in item
    assert all("implementation" in rule for rule in item["rules"])


@pytest.mark.asyncio
async def test_policy_api_is_the_single_product_catalog(tmp_path, monkeypatch):
    monkeypatch.setenv("NVAPI_API_KEY", "test-key")
    monkeypatch.setenv(
        "MODEL_GUARDRAILS_DATABASE_PATH", str(tmp_path / "module-default.db")
    )
    from app.config import Settings
    from app.main import create_app

    app = create_app(
        settings=Settings(
            database_path=tmp_path / "policy-library.db",
            ui_dist_path=tmp_path / "missing-ui",
        )
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        await client.post(
            "/api/v1/session", json={"email": "admin", "password": "admin"}
        )
        response = await client.get("/api/v1/policies")
        detail = await client.get("/api/v1/policies/mas-ai-risk-management")
        programmable = await client.get("/api/v1/policies/builtin-secrets")

    assert response.status_code == 200
    assert response.json()["count"] == 26
    assert all(item["rules"] for item in response.json()["items"])
    assert all(item["test_cases"] for item in response.json()["items"])
    assert all(item["test_count"] > 0 for item in response.json()["items"])
    assert detail.status_code == 200
    assert detail.json()["name"].startswith("Singapore MAS")
    assert detail.json()["rules"]
    assert detail.json()["test_cases"]
    assert programmable.status_code == 200
    assert programmable.json()["test_count"] == 4
    assert {
        case["stage"] for case in programmable.json()["test_cases"]
    } == {"input", "output"}
