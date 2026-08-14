from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ..runtime.contracts import ProtectionDecision, GuardrailPlanSnapshot
from ..policy_library import policy as library_policy
from ..policy_library.materialization import materialize_test_text
from .domain import Guardrail


def playground_check_payload(
    *,
    check_id: str,
    guardrail: Guardrail,
    plan: GuardrailPlanSnapshot,
    published_at: str,
    phase: str,
    content: str,
    decision: ProtectionDecision,
    latency_ms: int,
    runtime: str,
) -> dict[str, Any]:
    policies, rules_by_policy = _evaluated_policies(
        guardrail=guardrail,
        plan=plan,
        phase=phase,
        content=content,
        decision=decision,
    )
    triggered_policy = next(
        (
            {"id": item["id"], "name": item["name"]}
            for item in policies
            if item["status"] == "matched"
        ),
        None,
    )
    triggered_rule = (
        rules_by_policy.get(triggered_policy["id"])
        if triggered_policy is not None
        else None
    )
    findings = [
        _finding_payload(
            probe_id=check_id,
            index=index,
            finding=finding,
            policies=policies,
            rules_by_policy=rules_by_policy,
        )
        for index, finding in enumerate(decision.findings)
    ]
    output_content = (
        decision.texts[0]
        if decision.texts
        else "" if decision.decision == "block" else content
    )
    matched_steps = sum(
        1
        for step in decision.trace
        if step.verdict == "unsafe" or step.status in {"blocked", "unsafe", "matched"}
    )
    return {
        "check_id": check_id,
        "trace_id": check_id,
        "evidence_id": None,
        "guardrail": {
            "id": guardrail.id,
            "name": guardrail.name,
            "version": plan.guardrail_version,
            "published_at": published_at,
            "compiler_version": plan.compiler_version,
        },
        "phase": phase,
        "decision": decision.decision,
        "action": decision.action,
        "output_content": output_content,
        "latency_ms": latency_ms,
        "reason": decision.reason or "",
        "runtime": runtime,
        "triggered_policy": triggered_policy,
        "triggered_rule": triggered_rule,
        "policies": policies,
        "findings": findings,
        "trace_summary": {
            "steps": len(decision.trace),
            "matched_steps": matched_steps,
        },
        "trace": [asdict(item) for item in decision.trace],
    }


def _evaluated_policies(
    *,
    guardrail: Guardrail,
    plan: GuardrailPlanSnapshot,
    phase: str,
    content: str,
    decision: ProtectionDecision,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, str]]]:
    del content
    result: list[dict[str, Any]] = []
    rules_by_policy: dict[str, dict[str, str]] = {}
    versions = {(item.policy_id, item.version): item for item in plan.policy_versions}

    for binding in plan.policy_bindings:
        version = versions.get((binding.policy_id, binding.policy_version))
        declared = library_policy(binding.policy_id)
        enabled_rails = binding.enabled_rails or (
            declared.stages
            if declared is not None
            else tuple(
                dict.fromkeys(item.rail_type for item in version.rail_bindings)
            )
            if version is not None
            else ()
        )
        if phase not in enabled_rails:
            continue

        risk = (
            dict(version.execution_contract).get("native_risk")
            if version is not None
            else "builtin_content_filter"
            if declared is not None
            else binding.policy_id
        )
        steps = tuple(
            item
            for item in decision.trace
            if item.kind in {"action", "policy", "rail"}
            and (
                item.policy_id == binding.policy_id
                or (risk is not None and item.risk == risk)
            )
        )
        findings = tuple(
            item
            for item in decision.findings
            if item.policy_id == binding.policy_id
            or (risk is not None and item.risk == risk)
        )
        matched = bool(findings) or any(
            item.verdict == "unsafe"
            or item.status in {"blocked", "unsafe", "matched"}
            for item in steps
        )
        result.append(
            {
                "id": binding.policy_id,
                "name": (
                    declared.name
                    if declared is not None
                    else version.name
                    if version is not None
                    else binding.policy_id
                ),
                "risk": risk or binding.policy_id,
                "status": _policy_status(steps, matched=matched),
                "duration_ms": _step_duration(steps),
            }
        )

        rule_id = next(
            (item.rule_id for item in findings if item.rule_id),
            None,
        )
        if rule_id:
            declared_rule = next(
                (
                    item
                    for item in declared.rules
                    if item.id == rule_id
                ),
                None,
            ) if declared is not None else None
            rules_by_policy[binding.policy_id] = {
                "id": rule_id,
                "name": (
                    materialize_test_text(
                        declared_rule.name,
                        tuple(dict(binding.parameter_values)),
                        dict(binding.parameter_values),
                    )
                    if declared_rule is not None
                    else rule_id
                ),
            }
            continue
        matched_step = next(
            (
                item
                for item in steps
                if item.kind == "action"
                and (
                    item.verdict == "unsafe"
                    or item.status in {"blocked", "unsafe", "matched"}
                )
            ),
            None,
        )
        if matched_step is not None:
            rule_id = matched_step.flow_name or matched_step.action_name or matched_step.id
            rules_by_policy[binding.policy_id] = {
                "id": rule_id,
                "name": matched_step.flow_name or matched_step.action_name or matched_step.name,
            }

    if decision.decision != "allow" and not any(
        item["status"] == "matched" for item in result
    ):
        candidates = [item for item in result if item["status"] != "error"]
        if len(candidates) == 1:
            candidates[0]["status"] = "matched"
    return result, rules_by_policy

def _policy_status(steps: tuple, *, matched: bool) -> str:
    if any(item.verdict == "error" or item.status == "error" for item in steps):
        return "error"
    return "matched" if matched else "not_matched"


def _step_duration(steps: tuple) -> int:
    actions = tuple(item for item in steps if item.kind == "action")
    selected = actions or tuple(item for item in steps if item.kind == "policy") or steps
    return sum(max(0, item.duration_ms) for item in selected)


def _finding_payload(
    *,
    probe_id: str,
    index: int,
    finding,
    policies: list[dict[str, Any]],
    rules_by_policy: dict[str, dict[str, str]],
) -> dict[str, Any]:
    evidence = finding.evidence.casefold()
    policy_summary = next(
        (
            item
            for item in policies
            if item["status"] == "matched"
            and item["risk"] == finding.risk
            and (
                item["id"].casefold() in evidence
                or item["name"].casefold() in evidence
                or (
                    (rule := rules_by_policy.get(item["id"])) is not None
                    and (
                        rule["id"].casefold() in evidence
                        or rule["name"].casefold() in evidence
                    )
                )
            )
        ),
        next(
            (
                item
                for item in policies
                if item["status"] == "matched" and item["risk"] == finding.risk
            ),
            next((item for item in policies if item["status"] == "matched"), None),
        ),
    )
    rule = rules_by_policy.get(policy_summary["id"]) if policy_summary else None
    confidence = max(0.0, min(1.0, finding.confidence))
    severity = (
        "high"
        if finding.verdict in {"unsafe", "error"} and confidence >= 0.85
        else "medium"
        if finding.verdict in {"unsafe", "uncertain", "error"}
        else "low"
    )
    return {
        "id": f"{probe_id}:finding:{index + 1}",
        "severity": severity,
        "title": rule["name"] if rule else (policy_summary["name"] if policy_summary else finding.risk.replace("_", " ").title()),
        "detail": finding.evidence,
        "confidence": confidence,
        "recommended_action": finding.recommended_action,
        "policy_id": policy_summary["id"] if policy_summary else None,
        "rule_id": rule["id"] if rule else None,
    }
