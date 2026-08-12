from __future__ import annotations

import json
import re
import unicodedata

from .content_filter import BuiltinContentFilter
from ...runtime.contracts import (
    EngineRequest,
    GuardrailPlanStep,
    RiskFinding,
    StageResult,
)


SECRET_PATTERN = re.compile(
    r"(?:api[-_ ]?key|access[-_ ]?token)\s*[:=]\s*[A-Za-z0-9_\-]{16,}"
    r"|(?:authorization\s*:\s*bearer|bearer)\s+[A-Za-z0-9._~+\-/]+=*"
    r"|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    r"|tasklattice-test-block",
    re.IGNORECASE,
)
PII_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE), "email address"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "US social security number"),
    (re.compile(r"\b(?:\d[ -]*?){13,19}\b"), "payment card-like number"),
    (re.compile(r"身份证号(?:码)?|护照号|社会安全号码|银行卡号", re.IGNORECASE), "personal-data label"),
)


class FastPassEngine:
    name = "deterministic"
    stage = "deterministic"
    supported_phases = frozenset({"input", "output"})
    supported_risks: frozenset[str] = frozenset()

    def __init__(self, content_filter: BuiltinContentFilter | None = None) -> None:
        self._content_filter = content_filter or BuiltinContentFilter()

    async def evaluate(
        self,
        request: EngineRequest,
        steps: tuple[GuardrailPlanStep, ...],
    ) -> StageResult:
        content = request.text
        findings: list[RiskFinding] = []
        by_risk = {step.risk: step for step in steps}

        builtin_step = by_risk.get("builtin_content_filter")
        if builtin_step:
            controls = tuple(
                item.strip()
                for item in (builtin_step.parameter("control_ids") or "").splitlines()
                if item.strip()
            )
            parameters = {
                key.removeprefix("parameter."): value
                for key, value in builtin_step.parameters
                if key.startswith("parameter.")
            }
            enabled_rules = json.loads(
                builtin_step.parameter("enabled_rules_json") or "{}"
            )
            rule_actions = json.loads(
                builtin_step.parameter("rule_actions_json") or "{}"
            )
            custom_rules = json.loads(
                builtin_step.parameter("custom_rules_json") or "[]"
            )
            filtered = self._content_filter.evaluate(
                text=content,
                phase=request.phase,
                controls=controls,
                parameters=parameters,
                enabled_rules=enabled_rules,
                rule_actions=rule_actions,
                custom_rules=custom_rules,
            )
            if filtered.verdict == "error":
                return filtered
            content = filtered.content
            findings.extend(filtered.findings)

        secret_step = by_risk.get("secrets")
        if secret_step:
            matches = list(SECRET_PATTERN.finditer(content))
            if matches:
                content = self._redact(content, matches, "[SECRET_REDACTED]")
                findings.append(
                    RiskFinding(
                        risk="secrets",
                        verdict="unsafe",
                        confidence=0.99,
                        evidence="High-confidence credential pattern detected.",
                        recommended_action=secret_step.on_unsafe,
                        replacement="[SECRET_REDACTED]",
                    )
                )

        pii_step = by_risk.get("pii")
        if pii_step:
            pii_matches: list[re.Match[str]] = []
            evidence: list[str] = []
            for pattern, label in PII_PATTERNS:
                found = list(pattern.finditer(content))
                if found:
                    pii_matches.extend(found)
                    evidence.append(label)
            if pii_matches:
                content = self._redact(content, pii_matches, "[PII_REDACTED]")
                findings.append(
                    RiskFinding(
                        risk="pii",
                        verdict="unsafe",
                        confidence=0.97,
                        evidence=f"Detected {', '.join(sorted(set(evidence)))}.",
                        recommended_action=pii_step.on_unsafe,
                        replacement="[PII_REDACTED]",
                    )
                )

        topic_uncertainty: StageResult | None = None
        topic_step = by_risk.get("topic_control")
        if topic_step:
            topic_result = self._evaluate_topic_boundary(request, topic_step)
            if topic_result.verdict == "unsafe":
                findings.extend(topic_result.findings)
            elif topic_result.verdict == "uncertain":
                topic_uncertainty = topic_result

        if findings:
            return StageResult(
                verdict="unsafe",
                content=content,
                findings=tuple(findings),
                reason="A deterministic Control matched high-confidence sensitive content.",
            )
        if topic_uncertainty is not None:
            return topic_uncertainty
        return StageResult(
            verdict="safe",
            content=request.text,
            reason="No configured deterministic Control matched.",
        )

    @staticmethod
    def _evaluate_topic_boundary(
        request: EngineRequest,
        step: GuardrailPlanStep,
    ) -> StageResult:
        parameters = dict(step.parameters)
        allowed = _policy_lines(parameters.get("allowed_topics", ""))
        restricted = _policy_lines(parameters.get("restricted_topics", ""))
        content = _normalize_topic(request.text)
        allowed_matches = tuple(item for item in allowed if item in content)
        restricted_matches = tuple(item for item in restricted if item in content)

        if restricted_matches and not allowed_matches:
            evidence = ", ".join(restricted_matches[:3])
            return StageResult(
                verdict="unsafe",
                content=request.text,
                findings=(
                    RiskFinding(
                        risk="topic_control",
                        verdict="unsafe",
                        confidence=0.98,
                        evidence=f"Matched an explicitly restricted topic: {evidence}.",
                        recommended_action=step.on_unsafe,
                    ),
                ),
                reason="The request directly matched an explicitly restricted topic.",
            )
        if allowed_matches and not restricted_matches:
            return StageResult(
                verdict="safe",
                content=request.text,
                reason="The request directly matched an explicitly allowed topic.",
            )

        reason = (
            "The request matched both allowed and restricted topic language; primary intent needs deeper review."
            if allowed_matches and restricted_matches
            else "The request did not directly match an explicit topic boundary; primary intent needs deeper review."
        )
        return StageResult(
            verdict="uncertain",
            content=request.text,
            findings=(
                RiskFinding(
                    risk="topic_control",
                    verdict="uncertain",
                    confidence=0.5,
                    evidence=reason,
                    recommended_action=step.on_unsafe,
                ),
            ),
            reason=reason,
        )

    @staticmethod
    def _redact(
        content: str,
        matches: list[re.Match[str]],
        replacement: str,
    ) -> str:
        output = content
        for match in sorted(matches, key=lambda item: item.start(), reverse=True):
            output = output[: match.start()] + replacement + output[match.end() :]
        return output


def _policy_lines(value: str) -> tuple[str, ...]:
    return tuple(
        normalized
        for item in value.splitlines()
        if (normalized := _normalize_topic(item))
    )


def _normalize_topic(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.sub(r"[^\w\u3400-\u9fff]+", " ", normalized).split())
