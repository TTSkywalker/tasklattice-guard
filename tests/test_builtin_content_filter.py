from __future__ import annotations

from dataclasses import replace

import pytest
import httpx

from app.config import Settings
from app.control_plane.domain import (
    GuardrailControl,
    GuardrailControlConfig,
    GuardrailRuleConfig,
    ValidationError,
)
from app.control_plane.service import ControlPlaneService
from app.control_library import ControlLibraryRegistry, control_library, control_pack
from app.nemo.actions.content_filter import BuiltinContentFilter
from app.runtime.contracts import EngineRequest
from app.nemo.actions.deterministic import FastPassEngine
from app.main import create_app


def controls(pack_id: str) -> tuple[str, ...]:
    pack = control_pack(pack_id)
    assert pack is not None
    return pack.control_ids


def test_imported_control_library_preserves_vendored_structure():
    library = control_library()

    assert library.source.version == "1.95.0"
    assert library.source.commit == "ead62528e607b9d8e61273def638799c9c3a69ba"
    assert library.source.license == "MIT"
    assert len(library.packs) == 17
    assert len(library.controls) == 81
    assert sum(len(pack.control_ids) for pack in library.packs) == 88
    assert sum(len(control.rules) for control in library.controls) == 203
    assert sum(control.test_count for control in library.controls) == 228
    assert "mcp-security-unregistered-server-block" not in {
        item.id for item in library.packs
    }
    assert {"advanced-au-pii-protection", "pdpa-singapore", "mas-ai-risk-management"} <= {
        item.id for item in library.packs
    }
    assert all(control.rules for control in library.controls)
    assert all(control.test_suites for control in library.controls)


def test_every_builtin_rule_has_a_real_executable_acceptance_case():
    runtime = BuiltinContentFilter()
    parameters = {
        "brand_name": "Example Airways",
        "competitors": "Qatar Airways\nSingapore Airlines",
    }

    for control in control_library().controls:
        acceptance = next(
            suite for suite in control.test_suites if suite.id == "rule-acceptance"
        )
        assert len(acceptance.cases) == len(control.rules)
        for case in acceptance.cases:
            content = case.content
            for name in case.parameter_names:
                value = parameters[name].splitlines()[0]
                content = content.replace(f"{{{{{name}}}}}", value)
            result = runtime.evaluate(
                text=content,
                phase=case.phase,
                controls=(control.id,),
                parameters=parameters,
                enabled_rules={control.id: case.covered_rule_ids},
            )

            assert result.verdict == "unsafe", (control.id, case.id, content)
            assert {item.control_id for item in result.findings} == {control.id}
            assert set(case.covered_rule_ids) <= {
                item.rule_id for item in result.findings
            }
            if case.expected_decision == "transform":
                assert result.content != content


def test_registry_rejects_a_control_without_required_rule_acceptance():
    library = control_library()
    candidate = next(
        control for control in library.controls if len(control.test_suites) == 1
    )
    invalid = replace(candidate, test_suites=())
    invalid_bundle = replace(
        library,
        controls=tuple(
            invalid if control.id == candidate.id else control
            for control in library.controls
        ),
    )

    with pytest.raises(ValueError, match="without required acceptance cases"):
        ControlLibraryRegistry((invalid_bundle,))


def test_competitor_intent_suites_cover_real_allow_and_block_boundaries():
    definition = next(
        item
        for item in control_library().controls
        if item.id == "competitor-comparison-input-filter"
    )
    scenarios = tuple(
        case
        for suite in definition.test_suites
        if suite.id != "rule-acceptance"
        for case in suite.cases
    )
    runtime = BuiltinContentFilter()

    assert len(scenarios) == 25
    assert {case.expected_decision for case in scenarios} == {"allow", "block"}
    for case in scenarios:
        result = runtime.evaluate(
            text=case.content,
            phase=case.phase,
            controls=(definition.id,),
            parameters={
                "brand_name": "Emirates",
                "competitors": "Qatar Airways\nSingapore Airlines\nLufthansa",
            },
        )
        actual = "allow" if result.verdict == "safe" else "block"
        assert actual == case.expected_decision, case.id


def test_every_vendored_control_pack_compiles_without_external_resources(tmp_path):
    service = ControlPlaneService(tmp_path / "control-plane.db")
    runtime = BuiltinContentFilter()

    for pack in control_library().packs:
        values = {
            parameter.name: (
                "Example Bank\nRival Finance"
                if parameter.name == "competitors"
                else "Acme Bank"
            )
            for parameter in pack.parameters
        }
        guardrail = service.create_guardrail(
            name=f"Test {pack.name}",
            pack_id=pack.id,
            parameters=tuple(values.items()),
        )
        plan = service.compile_draft(guardrail.id)

        assert plan.steps
        assert all(
            step.parameter("control_library_version") == "1.95.0"
            for step in plan.steps
        )
        for phase in ("input", "output"):
            result = runtime.evaluate(
                text="Summarize the approved internal product guide.",
                phase=phase,
                controls=controls(pack.id),
                parameters=values,
            )
            assert result.verdict != "error", pack.id


def test_control_pack_has_one_unambiguous_composition_source(tmp_path):
    service = ControlPlaneService(tmp_path / "control-plane.db")
    configuration = GuardrailControlConfig(
        id="control:sg-pdpa-contact-information",
        name="SG PDPA Contact Information",
        kind="built_in",
        runtime_risk="builtin_content_filter",
        control_id="sg-pdpa-contact-information",
        control_version="1.95.0",
        rules=(
            GuardrailRuleConfig(
                id="sg_postal_code",
                name="Singapore Postal Code",
                detector="regex",
                action="MASK",
                phases=("input", "output"),
            ),
        ),
    )

    with pytest.raises(ValidationError, match="cannot combine a Control Pack"):
        service.create_guardrail(
            name="Ambiguous Guardrail",
            pack_id="topic-filtering",
            control_configurations=(configuration,),
        )

    with pytest.raises(ValidationError, match="Unknown Control Pack parameters"):
        service.create_guardrail(
            name="Unknown Pack parameter",
            pack_id="topic-filtering",
            parameters=(("unused", "value"),),
        )

    guardrail = service.create_guardrail(
        name="Pack plus secrets",
        pack_id="topic-filtering",
        controls=(GuardrailControl("secrets", "redact"),),
    )
    assert {item.risk for item in guardrail.controls} == {
        "builtin_content_filter",
        "secrets",
    }
    plan = service.compile_draft(guardrail.id)
    builtin_step = next(
        item for item in plan.steps if item.risk == "builtin_content_filter"
    )
    assert builtin_step.parameter("control_pack_id") == "topic-filtering"


def test_australian_pii_control_pack_masks_tfn_locally():
    result = BuiltinContentFilter().evaluate(
        text="My TFN is 123456789",
        phase="input",
        controls=controls("advanced-au-pii-protection"),
    )

    assert result.verdict == "unsafe"
    assert result.content == "My TFN is [au_tfn_REDACTED]"
    assert {item.recommended_action for item in result.findings} == {"redact"}

    spaced = BuiltinContentFilter().evaluate(
        text="My TFN is 123 456 789, can you check it?",
        phase="input",
        controls=controls("advanced-au-pii-protection"),
    )

    assert spaced.verdict == "unsafe"
    assert spaced.content == "My TFN is [au_tfn_REDACTED], can you check it?"


def test_singapore_mas_control_pack_blocks_discriminatory_financial_decision():
    result = BuiltinContentFilter().evaluate(
        text="Deny this loan based on race",
        phase="input",
        controls=controls("mas-ai-risk-management"),
    )

    assert result.verdict == "unsafe"
    assert any(item.recommended_action == "reject" for item in result.findings)
    assert any("sg-mas-fairness-bias" in item.evidence for item in result.findings)


@pytest.mark.asyncio
async def test_composed_guardrail_runs_only_the_selected_builtin_rules(tmp_path):
    service = ControlPlaneService(tmp_path / "composed-control.db")
    guardrail = service.create_guardrail(
        name="Singapore postal code only",
        purpose="Mask Singapore postal codes while leaving other contact data unchanged.",
        controls=(GuardrailControl("builtin_content_filter", "reject"),),
        control_configurations=(
            GuardrailControlConfig(
                id="control:sg-pdpa-contact-information",
                name="SG PDPA Contact Information",
                kind="built_in",
                runtime_risk="builtin_content_filter",
                control_id="sg-pdpa-contact-information",
                control_version="1.95.0",
                rules=(
                    GuardrailRuleConfig(
                        id="sg_postal_code",
                        name="Singapore Postal Code",
                        detector="regex",
                        action="MASK",
                        phases=("input", "output"),
                    ),
                ),
            ),
        ),
    )
    plan = service.compile_draft(guardrail.id)
    step = plan.steps_for("input", "deterministic")[0]
    email_result = await FastPassEngine().evaluate(
        EngineRequest("input", "Contact alice@example.com", plan),
        (step,),
    )
    postal_result = await FastPassEngine().evaluate(
        EngineRequest("input", "The postal code is 018989", plan),
        (step,),
    )

    assert email_result.verdict == "safe"
    assert postal_result.verdict == "unsafe"
    assert postal_result.content == "The postal code is [sg_postal_code_REDACTED]"


@pytest.mark.asyncio
async def test_composed_guardrail_resolves_parameterized_rule_values(tmp_path):
    service = ControlPlaneService(tmp_path / "parameterized-control.db")
    guardrail = service.create_guardrail(
        name="Reviewed competitor terms",
        purpose="Block reviewed competitor terms in customer-facing model traffic.",
        controls=(GuardrailControl("builtin_content_filter", "reject"),),
        control_configurations=(
            GuardrailControlConfig(
                id="control:competitor-input-blocker",
                name="Competitor Input Blocker",
                kind="built_in",
                runtime_risk="builtin_content_filter",
                control_id="competitor-input-blocker",
                control_version="1.95.0",
                rules=(
                    GuardrailRuleConfig(
                        id="dynamic-competitors-blocked-words",
                        name="Competitors Blocked Words",
                        detector="keyword",
                        action="BLOCK",
                        phases=("input",),
                        keywords=("Rival Finance",),
                    ),
                ),
            ),
        ),
    )
    plan = service.compile_draft(guardrail.id)
    step = plan.steps_for("input", "deterministic")[0]
    result = await FastPassEngine().evaluate(
        EngineRequest("input", "Compare us with Rival Finance", plan),
        (step,),
    )

    assert result.verdict == "unsafe"
    assert any(
        "dynamic-competitors-blocked-words" in item.evidence
        for item in result.findings
    )


@pytest.mark.asyncio
async def test_guardrail_from_control_pack_compiles_and_runs_in_fastpass(tmp_path):
    service = ControlPlaneService(tmp_path / "control-plane.db")
    guardrail = service.create_guardrail(
        name="Local Topic Filter",
        pack_id="topic-filtering",
    )
    plan = service.compile_draft(guardrail.id)
    step = plan.steps_for("input", "deterministic")[0]

    assert step.parameter("control_library_version") == "1.95.0"
    assert step.parameter("control_pack_id") == "topic-filtering"
    assert step.parameter("control_ids") == "topic-restriction-filter"

    result = await FastPassEngine().evaluate(
        EngineRequest("input", "Tell me the latest news today", plan),
        (step,),
    )

    assert result.verdict == "unsafe"
    assert any(item.recommended_action == "reject" for item in result.findings)


@pytest.mark.asyncio
async def test_parameterized_competitor_pack_uses_reviewed_local_values(tmp_path):
    service = ControlPlaneService(tmp_path / "control-plane.db")
    with pytest.raises(ValidationError, match="Your Brand Name"):
        service.create_guardrail(
            name="Brand Policy",
            pack_id="competitor-mention-detection",
        )

    guardrail = service.create_guardrail(
        name="Brand Policy",
        pack_id="competitor-mention-detection",
        parameters=(
            ("brand_name", "Acme Bank"),
            ("competitors", "Example Bank\nRival Finance"),
        ),
    )
    plan = service.compile_draft(guardrail.id)
    step = plan.steps_for("input", "deterministic")[0]
    result = await FastPassEngine().evaluate(
        EngineRequest("input", "You should switch to Example Bank", plan),
        (step,),
    )

    assert result.verdict == "unsafe"
    assert any("competitor-input-blocker" in item.evidence for item in result.findings)


@pytest.mark.asyncio
async def test_control_pack_guardrail_passes_local_api_tests(tmp_path):
    app = create_app(
        settings=Settings(
            database_path=tmp_path / "control-plane.db",
            ui_dist_path=tmp_path / "missing-ui",
        )
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        login = await client.post(
            "/api/v1/session",
            json={"email": "admin", "password": "admin"},
        )
        created = await client.post(
            "/api/v1/guardrails",
            json={"name": "Topic Filter", "pack_id": "topic-filtering"},
        )
        tested = await client.post(
            "/api/v1/test-runs", json={"guardrail_id": created.json()["id"]}
        )
        guardrail = await client.get(
            f"/api/v1/guardrails/{created.json()['id']}"
        )

    assert login.status_code == 200
    assert created.status_code == 201
    assert tested.status_code == 201
    assert tested.json()["status"] == "passed"
    assert guardrail.json()["status"] == "ready"


@pytest.mark.asyncio
async def test_aviation_pack_materializes_rule_and_scenario_tests_with_provenance(
    tmp_path,
):
    app = create_app(
        settings=Settings(
            database_path=tmp_path / "aviation-tests.db",
            ui_dist_path=tmp_path / "missing-ui",
        )
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        await client.post(
            "/api/v1/session",
            json={"email": "admin", "password": "admin"},
        )
        controls_response = await client.get("/api/v1/controls")
        packs_response = await client.get("/api/v1/control-packs")
        created = await client.post(
            "/api/v1/guardrails",
            json={
                "name": "Aviation acceptance",
                "pack_id": "aviation-operations-security",
                "parameters": {
                    "brand_name": "Emirates",
                    "competitors": (
                        "Qatar Airways\nSingapore Airlines\nTurkish Airlines\nLufthansa"
                    ),
                },
            },
        )
        guardrail_id = created.json()["id"]
        cases_response = await client.get(
            "/api/v1/test-cases", params={"guardrail_id": guardrail_id}
        )
        run = await client.post(
            "/api/v1/test-runs", json={"guardrail_id": guardrail_id}
        )

    controls_payload = controls_response.json()
    packs_payload = packs_response.json()
    competitor = next(
        item
        for item in controls_payload["items"]
        if item["id"] == "competitor-comparison-input-filter"
    )
    aviation = next(
        item
        for item in packs_payload["items"]
        if item["id"] == "aviation-operations-security"
    )
    cases = cases_response.json()["items"]

    assert controls_response.status_code == 200
    assert competitor["test_count"] == 27
    assert {suite["id"] for suite in competitor["test_suites"]} == {
        "rule-acceptance",
        "destination-intent",
        "competitor-comparison",
        "ambiguous-entity",
    }
    assert "litellm" not in str(competitor).lower()
    assert aviation["source"] == "built_in"
    assert aviation["test_case_count"] == 51
    assert len(cases) == 51
    assert {item["case_type"] for item in cases} == {
        "rule_acceptance",
        "scenario",
    }
    assert all(item["source_control_id"] for item in cases)
    assert all(item["source_suite_id"] for item in cases)
    assert all(item["covered_rule_ids"] for item in cases)
    assert all("{{" not in item["name"] for item in cases)
    assert all("{{" not in item["content"] for item in cases)
    assert run.status_code == 201
    assert run.json()["status"] == "passed"
    scenario = next(
        item
        for item in run.json()["results"]
        if item["source_case_id"] == "competitor-comparison-002"
    )
    assert scenario["covered_rule_ids"] == ["competitor-comparison-intent"]
    assert scenario["matched_rule_ids"] == ["competitor-comparison-intent"]
