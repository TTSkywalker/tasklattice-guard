from __future__ import annotations

import re

from ...runtime.contracts import RiskFinding
from .contracts import ActionRequest, ActionResult, action_result
from .names import ACTION_PII


PII_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
        "email address",
    ),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "US social security number"),
    (re.compile(r"\b(?:\d[ -]*?){13,19}\b"), "payment card-like number"),
    (
        re.compile(
            r"身份证号(?:码)?|护照号|社会安全号码|银行卡号",
            re.IGNORECASE,
        ),
        "personal-data label",
    ),
)


class PiiActionProvider:
    """Detect and redact common PII patterns for the NeMo PII Action."""

    name = ACTION_PII
    version = "1.0.0"
    risks = frozenset({"pii"})
    rails = frozenset({"input", "output"})

    async def execute(self, request: ActionRequest) -> ActionResult:
        matches: list[re.Match[str]] = []
        evidence: list[str] = []
        for pattern, label in PII_PATTERNS:
            found = list(pattern.finditer(request.content))
            if found:
                matches.extend(found)
                evidence.append(label)
        if not matches:
            return action_result(
                request,
                "safe",
                request.content,
                reason="No PII pattern matched.",
            )
        return action_result(
            request,
            "unsafe",
            _redact(request.content, matches, "[PII_REDACTED]"),
            findings=(
                RiskFinding(
                    risk="pii",
                    verdict="unsafe",
                    confidence=0.97,
                    evidence=f"Detected {', '.join(sorted(set(evidence)))}.",
                    recommended_action=request.proposed_action,
                    replacement="[PII_REDACTED]",
                ),
            ),
            reason="A high-confidence PII pattern was detected.",
        )


def _redact(
    content: str,
    matches: list[re.Match[str]],
    replacement: str,
) -> str:
    output = content
    for match in sorted(matches, key=lambda item: item.start(), reverse=True):
        output = output[: match.start()] + replacement + output[match.end() :]
    return output
