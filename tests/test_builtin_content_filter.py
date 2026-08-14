from __future__ import annotations

from dataclasses import replace

import httpx
import pytest

from app.config import Settings
from app.control_plane.domain import GuardrailPolicyBinding
from app.control_plane.service import ControlPlaneService
from app.main import create_app
from app.nemo.actions import local_action_providers
from app.nemo.actions.content_filter import BuiltinContentFilter
from app.policy_library import policies, policy
from app.policy_library.materialization import materialize_test_content
from app.policy_library.registry import PolicyLibraryRegistry
from app.runtime.contracts import EngineRequest
from tests.nemo_helpers import nemo_engine


_REVIEWED_PARAMETERS = {
    "brand_name": "Example Airways",
    "competitors": "Qatar Airways\nSingapore Airlines",
}


def test_canonical_policy_catalog_owns_rules_and_real_test_cases():
    items = policies()

    assert len(items) == 17
    assert sum(len(item.rules) for item in items) == 222
    assert sum(item.test_count for item in items) == 272
    assert all(item.rules for item in items)
    assert all(item.test_cases for item in items)
    assert all(
        case.covered_rule_ids
        for item in items
        for case in item.test_cases
    )


def test_every_policy_rule_has_an_executable_acceptance_case():
    runtime = BuiltinContentFilter()

    for item in policies():
        acceptance = tuple(
            case for case in item.test_cases if case.group == "Rule acceptance"
        )
        assert len(acceptance) == len(item.rules)
        for case in acceptance:
            content = materialize_test_content(case, _REVIEWED_PARAMETERS)
            result = runtime.evaluate(
                text=content,
                phase=case.stage,
                policies=(item.id,),
                parameters=_REVIEWED_PARAMETERS,
                enabled_rules={item.id: case.covered_rule_ids},
            )

            assert result.verdict == "unsafe", (item.id, case.id, content)
            assert {finding.policy_id for finding in result.findings} == {item.id}
            assert set(case.covered_rule_ids) <= {
                finding.rule_id for finding in result.findings
            }
            if case.expected_decision == "transform":
                assert result.content != content


def test_policy_registry_rejects_rules_without_required_acceptance_tests():
    items = policies()
    candidate = items[0]
    invalid = replace(candidate, test_cases=())

    with pytest.raises(ValueError, match="contains no Test Cases"):
        PolicyLibraryRegistry(
            tuple(invalid if item.id == candidate.id else item for item in items)
        )


def test_competitor_policy_scenarios_cover_allow_and_intervention_boundaries():
    definition = policy("competitor-mention-detection")
    assert definition is not None
    scenarios = tuple(
        case
        for case in definition.test_cases
        if case.group != "Rule acceptance"
    )
    runtime = BuiltinContentFilter()

    assert len(scenarios) == 25
    assert {case.expected_decision for case in scenarios} == {"allow", "block"}
    for case in scenarios:
        result = runtime.evaluate(
            text=case.content,
            phase=case.stage,
            policies=(definition.id,),
            parameters={
                "brand_name": "Emirates",
                "competitors": "Qatar Airways\nSingapore Airlines\nLufthansa",
            },
        )
        actual = "allow" if result.verdict == "safe" else "block"
        assert actual == case.expected_decision, case.id


@pytest.mark.asyncio
async def test_guardrail_executes_only_selected_policy_rules(tmp_path):
    service = ControlPlaneService(tmp_path / "policy-rules.db")
    rule_id = "sg-pdpa-contact-information/sg_postal_code"
    guardrail = service.create_guardrail(
        name="Singapore postal code",
        purpose="Mask reviewed Singapore postal codes.",
        policy_bindings=(
            GuardrailPolicyBinding(
                policy_id="pdpa-singapore",
                policy_version="1.95.0",
                enabled_rule_ids=(rule_id,),
            ),
        ),
    )
    plan = service.compile_draft(guardrail.id)
    engine = nemo_engine(plan, *local_action_providers())

    email = await engine.evaluate(
        EngineRequest("input", "Contact alice@example.com", plan)
    )
    postal = await engine.evaluate(
        EngineRequest("input", "The postal code is 018989", plan)
    )

    assert email.decision == "allow"
    assert postal.decision == "transform"
    assert postal.texts == ("The postal code is [sg_postal_code_REDACTED]",)
    assert {finding.rule_id for finding in postal.findings} == {rule_id}
    await engine.shutdown()


@pytest.mark.asyncio
async def test_parameterized_policy_uses_reviewed_guardrail_values(tmp_path):
    service = ControlPlaneService(tmp_path / "parameterized-policy.db")
    guardrail = service.create_guardrail(
        name="Reviewed competitor terms",
        purpose="Apply reviewed competitor comparison boundaries.",
        policy_bindings=(
            GuardrailPolicyBinding(
                policy_id="competitor-mention-detection",
                policy_version="1.95.0",
                parameter_values=(
                    ("brand_name", "Acme Bank"),
                    ("competitors", "Example Bank\nRival Finance"),
                ),
            ),
        ),
    )
    plan = service.compile_draft(guardrail.id)
    engine = nemo_engine(plan, *local_action_providers())
    result = await engine.evaluate(
        EngineRequest("input", "You should switch to Example Bank", plan)
    )

    assert result.decision == "block"
    assert any(
        finding.policy_id == "competitor-mention-detection"
        for finding in result.findings
    )
    await engine.shutdown()


@pytest.mark.asyncio
async def test_policy_guardrail_materializes_and_runs_owned_test_cases(tmp_path):
    app = create_app(
        settings=Settings(
            database_path=tmp_path / "policy-validation.db",
            ui_dist_path=tmp_path / "missing-ui",
        )
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        await client.post(
            "/api/v1/session", json={"email": "admin", "password": "admin"}
        )
        created = await client.post(
            "/api/v1/guardrails",
            json={
                "name": "Aviation acceptance",
                "purpose": "Protect reviewed aviation operations and brand content.",
                "policy_bindings": [
                    {
                        "policy_id": "aviation-operations-security",
                        "policy_version": "1.95.0",
                        "parameter_values": {
                            "brand_name": "Emirates",
                            "competitors": (
                                "Qatar Airways\nSingapore Airlines\n"
                                "Turkish Airlines\nLufthansa"
                            ),
                        },
                    }
                ],
            },
        )
        guardrail_id = created.json()["id"]
        cases_response = await client.get(
            "/api/v1/test-cases", params={"guardrail_id": guardrail_id}
        )
        run = await client.post(
            "/api/v1/validation-runs", json={"guardrail_id": guardrail_id}
        )

    assert created.status_code == 201
    cases = cases_response.json()["items"]
    assert len(cases) == 51
    assert {item["case_type"] for item in cases} == {
        "rule_acceptance",
        "scenario",
    }
    assert all(item["policy_id"] == "aviation-operations-security" for item in cases)
    assert all(item["source_policy_id"] for item in cases)
    assert all(item["source_case_id"] for item in cases)
    assert all(item["covered_rule_ids"] for item in cases)
    assert all("{{" not in item["name"] for item in cases)
    assert all("{{" not in item["content"] for item in cases)
    assert run.status_code == 201
    assert run.json()["status"] == "passed"
    scenario = next(
        item
        for item in run.json()["results"]
        if item["source_case_id"]
        == "competitor-comparison-input-filter/competitor-comparison-002"
    )
    assert scenario["covered_rule_ids"] == [
        "competitor-comparison-input-filter/competitor-comparison-intent"
    ]
    assert (
        "competitor-comparison-input-filter/competitor-comparison-intent"
        in scenario["matched_rule_ids"]
    )
