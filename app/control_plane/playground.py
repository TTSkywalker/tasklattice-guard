from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any

from ..runtime.contracts import EvaluationDecision, EvaluationTraceStep, GuardrailPlanSnapshot
from .catalog import control
from .domain import Guardrail, GuardrailControlConfig, GuardrailRuleConfig


def playground_probe_payload(
    *,
    probe_id: str,
    guardrail: Guardrail,
    plan: GuardrailPlanSnapshot,
    phase: str,
    content: str,
    decision: EvaluationDecision,
    latency_ms: int,
    runtime: str,
) -> dict[str, Any]:
    controls, rules_by_control = _evaluated_controls(
        guardrail=guardrail,
        plan=plan,
        phase=phase,
        content=content,
        decision=decision,
    )
    triggered_control = next(
        (
            {"id": item["id"], "name": item["name"]}
            for item in controls
            if item["status"] == "matched"
        ),
        None,
    )
    triggered_rule = (
        rules_by_control.get(triggered_control["id"])
        if triggered_control is not None
        else None
    )
    findings = [
        _finding_payload(
            probe_id=probe_id,
            index=index,
            finding=finding,
            controls=controls,
            rules_by_control=rules_by_control,
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
        "probe_id": probe_id,
        "trace_id": probe_id,
        "evidence_id": None,
        "guardrail": {
            "id": guardrail.id,
            "name": guardrail.name,
            "draft_version": guardrail.draft_version,
            "compiler_version": plan.compiler_version,
        },
        "phase": phase,
        "content": content,
        "decision": decision.decision,
        "action": decision.action,
        "output_content": output_content,
        "latency_ms": latency_ms,
        "reason": decision.reason or "",
        "runtime": runtime,
        "triggered_control": triggered_control,
        "triggered_rule": triggered_rule,
        "controls": controls,
        "findings": findings,
        "trace_summary": {
            "steps": len(decision.trace),
            "matched_steps": matched_steps,
        },
        "trace": [asdict(item) for item in decision.trace],
    }


def _evaluated_controls(
    *,
    guardrail: Guardrail,
    plan: GuardrailPlanSnapshot,
    phase: str,
    content: str,
    decision: EvaluationDecision,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, str]]]:
    result: list[dict[str, Any]] = []
    rules_by_control: dict[str, dict[str, str]] = {}
    configurations_by_risk = {
        risk: tuple(
            item
            for item in guardrail.control_configurations
            if item.runtime_risk == risk and _configuration_applies(item, phase)
        )
        for risk in {item.runtime_risk for item in guardrail.control_configurations}
    }
    versions = {(item.control_id, item.version): item for item in plan.control_versions}
    native_risks = {
        (binding.control_id, binding.control_version): dict(version.execution_contract).get(
            "native_risk"
        )
        for binding in plan.control_bindings
        if (version := versions.get((binding.control_id, binding.control_version)))
        is not None
    }

    for configuration in guardrail.control_configurations:
        if not _configuration_applies(configuration, phase):
            continue
        rule = _matched_configuration_rule(
            configuration,
            phase=phase,
            content=content,
            findings=decision.findings,
        )
        relevant_findings = tuple(
            item for item in decision.findings if item.risk == configuration.runtime_risk
        )
        matched = rule is not None or (
            bool(relevant_findings)
            and len(configurations_by_risk.get(configuration.runtime_risk, ())) == 1
        )
        steps = _trace_steps(decision.trace, risk=configuration.runtime_risk)
        status = _control_status(steps, matched=matched)
        result.append(
            {
                "id": configuration.id,
                "name": configuration.name,
                "risk": configuration.runtime_risk,
                "status": status,
                "duration_ms": _step_duration(steps),
            }
        )
        if rule is not None:
            rules_by_control[configuration.id] = {"id": rule.id, "name": rule.name}

    configured_risks = set(configurations_by_risk)
    for configured in guardrail.controls:
        if configured.risk in configured_risks:
            continue
        if configured.risk in native_risks.values():
            continue
        steps = _trace_steps(decision.trace, risk=configured.risk)
        applicable_steps = tuple(item for item in plan.steps_for(phase) if item.risk == configured.risk)
        if not applicable_steps:
            continue
        matched = _risk_matched(configured.risk, decision, steps)
        definition = control(configured.risk)
        control_id = configured.risk
        result.append(
            {
                "id": control_id,
                "name": definition.display_name,
                "risk": configured.risk,
                "status": _control_status(steps, matched=matched),
                "duration_ms": _step_duration(steps),
            }
        )
        if matched:
            matched_step = next(
                (
                    item
                    for item in steps
                    if item.verdict == "unsafe"
                    or item.status in {"blocked", "unsafe", "matched"}
                ),
                None,
            )
            plan_step = next(
                (item for item in applicable_steps if item.stage == getattr(matched_step, "stage", None)),
                applicable_steps[0],
            )
            rules_by_control[control_id] = {
                "id": plan_step.id,
                "name": _plan_rule_name(definition.display_name, plan_step.stage),
            }

    for binding in plan.control_bindings:
        if phase not in binding.enabled_rails:
            continue
        version = versions.get((binding.control_id, binding.control_version))
        if native_risks.get((binding.control_id, binding.control_version)) in configured_risks:
            continue
        steps = _trace_steps(decision.trace, control_id=binding.control_id)
        matched = any(
            item.verdict == "unsafe" or item.status in {"blocked", "unsafe", "matched"}
            for item in steps
        )
        result.append(
            {
                "id": binding.control_id,
                "name": version.name if version is not None else binding.control_id,
                "risk": native_risks.get(
                    (binding.control_id, binding.control_version)
                )
                or next((item.risk for item in steps if item.risk), binding.control_id),
                "status": _control_status(steps, matched=matched),
                "duration_ms": _step_duration(steps),
            }
        )
        matched_step = next(
            (
                item
                for item in steps
                if item.kind == "action"
                and (item.verdict == "unsafe" or item.status in {"blocked", "unsafe", "matched"})
            ),
            None,
        )
        if matched_step is not None:
            rule_id = matched_step.action_name or matched_step.id
            rules_by_control[binding.control_id] = {
                "id": rule_id,
                "name": matched_step.action_name or matched_step.name,
            }

    if decision.decision != "allow" and not any(item["status"] == "matched" for item in result):
        candidates = [item for item in result if item["status"] != "error"]
        if len(candidates) == 1:
            candidates[0]["status"] = "matched"
    return result, rules_by_control


def _configuration_applies(configuration: GuardrailControlConfig, phase: str) -> bool:
    return any(rule.enabled and phase in rule.phases for rule in configuration.rules)


def _matched_configuration_rule(
    configuration: GuardrailControlConfig,
    *,
    phase: str,
    content: str,
    findings: tuple,
) -> GuardrailRuleConfig | None:
    candidates = tuple(
        rule for rule in configuration.rules if rule.enabled and phase in rule.phases
    )
    relevant = tuple(item for item in findings if item.risk == configuration.runtime_risk)
    if not relevant:
        return None
    evidence = " ".join(item.evidence for item in relevant).casefold()
    template_matches = not configuration.template_id or configuration.template_id.casefold() in evidence
    for rule in candidates:
        if rule.id.casefold() in evidence or rule.name.casefold() in evidence:
            return rule
    for rule in candidates:
        if _rule_matches_content(rule, content):
            return rule
    if template_matches and len(candidates) == 1:
        return candidates[0]
    return None


def _rule_matches_content(rule: GuardrailRuleConfig, content: str) -> bool:
    if rule.detector == "regex" and rule.expression:
        try:
            return re.search(rule.expression, content, re.IGNORECASE) is not None
        except re.error:
            return False
    if rule.detector == "keyword":
        lowered = content.casefold()
        return any(keyword.strip().casefold() in lowered for keyword in rule.keywords if keyword.strip())
    return False


def _trace_steps(
    trace: tuple[EvaluationTraceStep, ...],
    *,
    risk: str | None = None,
    control_id: str | None = None,
) -> tuple[EvaluationTraceStep, ...]:
    return tuple(
        item
        for item in trace
        if (risk is None or item.risk == risk)
        and (control_id is None or item.control_id == control_id)
        and item.kind in {"action", "control", "rail"}
    )


def _risk_matched(
    risk: str,
    decision: EvaluationDecision,
    steps: tuple[EvaluationTraceStep, ...],
) -> bool:
    return any(item.risk == risk and item.verdict == "unsafe" for item in decision.findings) or any(
        item.verdict == "unsafe" or item.status in {"blocked", "unsafe", "matched"}
        for item in steps
    )


def _control_status(steps: tuple[EvaluationTraceStep, ...], *, matched: bool) -> str:
    if any(item.verdict == "error" or item.status == "error" for item in steps):
        return "error"
    return "matched" if matched else "not_matched"


def _step_duration(steps: tuple[EvaluationTraceStep, ...]) -> int:
    actions = tuple(item for item in steps if item.kind == "action")
    selected = actions or tuple(item for item in steps if item.kind == "control") or steps
    return sum(max(0, item.duration_ms) for item in selected)


def _plan_rule_name(control_name: str, stage: str) -> str:
    stage_name = {
        "deterministic": "deterministic check",
        "fast_semantic": "semantic classifier",
        "deep_judge": "deep policy judge",
    }.get(stage, stage.replace("_", " "))
    return f"{control_name} · {stage_name}"


def _finding_payload(
    *,
    probe_id: str,
    index: int,
    finding,
    controls: list[dict[str, Any]],
    rules_by_control: dict[str, dict[str, str]],
) -> dict[str, Any]:
    evidence = finding.evidence.casefold()
    control_summary = next(
        (
            item
            for item in controls
            if item["status"] == "matched"
            and item["risk"] == finding.risk
            and (
                item["id"].casefold() in evidence
                or item["name"].casefold() in evidence
                or (
                    (rule := rules_by_control.get(item["id"])) is not None
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
                for item in controls
                if item["status"] == "matched" and item["risk"] == finding.risk
            ),
            next((item for item in controls if item["status"] == "matched"), None),
        ),
    )
    rule = rules_by_control.get(control_summary["id"]) if control_summary else None
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
        "title": rule["name"] if rule else (control_summary["name"] if control_summary else finding.risk.replace("_", " ").title()),
        "detail": finding.evidence,
        "confidence": confidence,
        "recommended_action": finding.recommended_action,
        "control_id": control_summary["id"] if control_summary else None,
        "rule_id": rule["id"] if rule else None,
    }
