from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Mapping

from ..policy_packs.litellm import (
    BlockedWordRule,
    CategoryRule,
    ContentControlDefinition,
    control_definition,
    keyword_expression,
)
from .contracts import GuardrailPhase, RiskFinding, StageResult


@dataclass(frozen=True, slots=True)
class _Detection:
    control: str
    kind: str
    rule: str
    action: str


class BuiltinContentFilter:
    """Execute the vendored LiteLLM content-filter policy definitions locally."""

    def evaluate(
        self,
        *,
        text: str,
        phase: GuardrailPhase,
        controls: Iterable[str],
        parameters: Mapping[str, str] | None = None,
    ) -> StageResult:
        configured = parameters or {}
        content = text
        detections: list[_Detection] = []
        for name in controls:
            definition = control_definition(name)
            if definition is None:
                return StageResult(
                    verdict="error",
                    content=text,
                    reason=f"Built-in content-filter control {name!r} is unavailable.",
                )
            if definition.phase != phase:
                continue
            content, matches = self._apply_control(
                definition,
                content,
                configured,
            )
            detections.extend(matches)

        if not detections:
            return StageResult(
                verdict="safe",
                content=text,
                reason="No built-in content-filter rule matched.",
            )

        findings = tuple(
            RiskFinding(
                risk="builtin_content_filter",
                verdict="unsafe",
                confidence=0.99,
                evidence=(
                    f"Built-in control {item.control} matched "
                    f"{item.kind} rule {item.rule}."
                ),
                recommended_action=("redact" if item.action == "MASK" else "reject"),
                replacement="[REDACTED]" if item.action == "MASK" else None,
            )
            for item in detections
        )
        blocked = any(item.action == "BLOCK" for item in detections)
        return StageResult(
            verdict="unsafe",
            content=content,
            findings=findings,
            reason=(
                "A built-in content-filter policy blocked the interaction."
                if blocked
                else "Built-in content-filter policy masked sensitive content."
            ),
        )

    def _apply_control(
        self,
        definition: ContentControlDefinition,
        text: str,
        parameters: Mapping[str, str],
    ) -> tuple[str, list[_Detection]]:
        content = text
        detections: list[_Detection] = []
        category_match = self._category_match(definition.categories, content)
        if category_match:
            rule, action = category_match
            detections.append(_Detection(definition.name, "category", rule, action))
            if action == "MASK":
                content = self._mask_keyword(content, rule)

        for pattern in definition.patterns:
            expression = self._render(pattern.expression, parameters)
            keyword = (
                self._render(pattern.keyword_expression, parameters)
                if pattern.keyword_expression
                else None
            )
            if keyword and not re.search(keyword, content, re.IGNORECASE):
                continue
            matches = list(re.finditer(expression, content, re.IGNORECASE))
            if not matches:
                continue
            detections.append(
                _Detection(definition.name, "pattern", pattern.name, pattern.action)
            )
            if pattern.action == "MASK":
                content = self._mask_spans(content, matches, pattern.redaction)

        for blocked in self._blocked_words(definition.blocked_words, parameters):
            rendered = self._render(blocked.keyword, parameters).strip()
            if not rendered:
                continue
            expression = keyword_expression(rendered)
            if not re.search(expression, content, re.IGNORECASE):
                continue
            detections.append(
                _Detection(definition.name, "blocked word", rendered, blocked.action)
            )
            if blocked.action == "MASK":
                content = re.sub(expression, "[REDACTED]", content, flags=re.IGNORECASE)
        return content, detections

    def _category_match(
        self,
        categories: tuple[CategoryRule, ...],
        text: str,
    ) -> tuple[str, str] | None:
        lowered = text.lower()
        if any(exception in lowered for item in categories for exception in item.exceptions):
            return None
        for item in categories:
            for expression in item.phrase_patterns:
                if re.search(expression, text, re.IGNORECASE):
                    return (item.name, item.action)
            if item.identifiers and item.conditional_words:
                for sentence in re.split(r"[.!?]+", lowered):
                    identifier = next(
                        (value for value in item.identifiers if value in sentence),
                        None,
                    )
                    conditional = next(
                        (
                            value
                            for value in item.conditional_words
                            if self._keyword_matches(value, sentence)
                        ),
                        None,
                    )
                    if identifier and conditional:
                        return (f"{identifier} + {conditional}", item.action)
            for keyword, _severity in (*item.always_block, *item.keywords):
                if self._keyword_matches(keyword, lowered):
                    return (keyword, item.action)
        return None

    @staticmethod
    def _blocked_words(
        configured: tuple[BlockedWordRule, ...] | str,
        parameters: Mapping[str, str],
    ) -> tuple[BlockedWordRule, ...]:
        if isinstance(configured, tuple):
            return configured
        competitors = tuple(
            item.strip()
            for item in parameters.get("competitors", "").splitlines()
            if item.strip()
        )
        brand = parameters.get("brand_name", "").strip()
        if configured == "{{competitors_blocked_words}}":
            values = competitors
        elif configured == "{{competitor_recommendation_words}}":
            values = tuple(
                phrase
                for competitor in competitors
                for phrase in (
                    f"recommend {competitor}",
                    f"try {competitor}",
                    f"switch to {competitor}",
                )
            )
        elif configured == "{{competitor_comparison_words}}":
            values = tuple(
                phrase
                for competitor in competitors
                for phrase in (
                    f"{competitor} is better",
                    f"{competitor} vs {brand}" if brand else f"{competitor} vs",
                    f"better than {brand}" if brand else f"better than {competitor}",
                )
            )
        else:
            values = ()
        return tuple(BlockedWordRule(value, "BLOCK", "Reviewed competitor policy") for value in values)

    @staticmethod
    def _keyword_matches(keyword: str, text: str) -> bool:
        expression = keyword_expression(keyword)
        return bool(re.search(expression, text, re.IGNORECASE))

    @staticmethod
    def _mask_keyword(text: str, keyword: str) -> str:
        return re.sub(keyword_expression(keyword), "[REDACTED]", text, flags=re.IGNORECASE)

    @staticmethod
    def _mask_spans(text: str, matches: list[re.Match[str]], replacement: str) -> str:
        output = text
        for match in reversed(matches):
            output = output[: match.start()] + replacement + output[match.end() :]
        return output

    @staticmethod
    def _render(value: str, parameters: Mapping[str, str]) -> str:
        rendered = value
        for key, replacement in parameters.items():
            rendered = rendered.replace(f"{{{{{key}}}}}", replacement)
        return rendered
