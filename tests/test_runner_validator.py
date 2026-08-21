from __future__ import annotations

import json

import pytest

from runner.compiler import DefaultRunnerCompiler
from runner.generated import runner_control_pb2 as protocol
from runner.validator import DefaultRunnerValidator


@pytest.mark.asyncio
async def test_default_runner_validates_cases_through_the_real_nemo_runtime() -> None:
    plan = {
        "guardrail_id": "guardrail-1",
        "guardrail_version": 1,
        "compiler_version": "tasklattice-controller-plan-v2",
        "safety_level": "balanced",
        "output_delivery": "full_buffered",
        "steps": [{
            "id": "secrets:deterministic",
            "risk": "secrets",
            "stage": "deterministic",
            "phases": ["input", "output"],
            "on_unsafe": "reject",
            "escalation": "never",
            "parameters": [],
        }],
        "modules": [{
            "id": "data_protection:input",
            "module": "data_protection",
            "phase": "input",
            "step_ids": ["secrets:deterministic"],
            "depends_on": [],
            "input_view": "original",
            "required_for_release": True,
            "timeout_ms": 750,
            "failure_mode": "fail_closed",
        }, {
            "id": "data_protection:output",
            "module": "data_protection",
            "phase": "output",
            "step_ids": ["secrets:deterministic"],
            "depends_on": [],
            "input_view": "original",
            "required_for_release": True,
            "timeout_ms": 750,
            "failure_mode": "fail_closed",
        }],
        "reasoning_policies": [],
        "policy_versions": [],
        "policy_bindings": [],
    }
    cases = [{
        "id": "safe",
        "name": "Safe prompt",
        "policyId": "builtin-secrets",
        "phase": "input",
        "content": "Summarize the quarterly report.",
        "expectedDecision": "allow",
        "required": True,
        "coveredRuleIds": [],
    }, {
        "id": "blocked",
        "name": "Credential prompt",
        "policyId": "builtin-secrets",
        "phase": "input",
        "content": "api_key=abcdefghijklmnop",
        "expectedDecision": "block",
        "required": True,
        "coveredRuleIds": [],
    }]

    status, metrics, results = await DefaultRunnerValidator(DefaultRunnerCompiler()).validate(
        protocol.ValidationRequest(
            run_id="validation-1",
            guardrail_id="guardrail-1",
            candidate_version=1,
            source_draft_revision=1,
            plan_json=json.dumps(plan),
            runtime_profile="auto",
            test_cases_json=json.dumps(cases),
        )
    )

    assert status == "passed"
    assert metrics["total"] == 2
    assert metrics["passed"] == 2
    assert metrics["complianceRate"] == 100
    assert [(item["caseId"], item["actualDecision"], item["passed"]) for item in results] == [
        ("safe", "allow", True),
        ("blocked", "block", True),
    ]
    assert results[1]["findings"][0]["risk"] == "secrets"
