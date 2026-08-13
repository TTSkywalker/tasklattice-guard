from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from ...policy_library import PolicyRuleSpec, PolicySpec, policy
from ...policy_library.matching import keyword_expression, severity_applies
from ...runtime.contracts import GuardrailPhase, RiskFinding, StageResult


@dataclass(frozen=True, slots=True)
class _Detection:
    policy: str
    kind: str
    rule: str
    action: str
    evidence: str


class BuiltinContentFilter:
    """Execute the selected Policy Rules through a NeMo Python Action."""

    def evaluate(
        self,
        *,
        text: str,
        phase: GuardrailPhase,
        policies: Iterable[str],
        parameters: Mapping[str, str] | None = None,
        enabled_rules: Mapping[str, Iterable[str]] | None = None,
        rule_actions: Mapping[str, str] | None = None,
        custom_rules: Iterable[Mapping[str, Any]] = (),
    ) -> StageResult:
        configured = parameters or {}
        selected_rules = {
            name: frozenset(rule_ids)
            for name, rule_ids in (enabled_rules or {}).items()
        }
        configured_actions = rule_actions or {}
        content = text
        detections: list[_Detection] = []
        for name in policies:
            definition = policy(name)
            if definition is None:
                return StageResult(
                    verdict="error",
                    content=text,
                    reason=f"Built-in Policy {name!r} is unavailable.",
                )
            if phase not in definition.stages:
                continue
            content, matches = self._apply_policy(
                definition,
                content,
                phase,
                configured,
                selected_rules.get(name),
                configured_actions,
            )
            detections.extend(matches)

        try:
            content, custom_detections = self._apply_custom_rules(
                tuple(custom_rules), content, phase
            )
        except re.error as error:
            return StageResult(
                verdict="error",
                content=text,
                reason=f"Custom content-filter Rule is invalid: {error}.",
            )
        detections.extend(custom_detections)

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
                    f"Policy {item.policy} matched "
                    f"{item.kind} rule {item.rule}: {item.evidence}."
                ),
                recommended_action=("redact" if item.action == "MASK" else "reject"),
                replacement="[REDACTED]" if item.action == "MASK" else None,
                policy_id=item.policy,
                rule_id=item.rule,
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

    def _apply_policy(
        self,
        definition: PolicySpec,
        text: str,
        phase: GuardrailPhase,
        parameters: Mapping[str, str],
        enabled_rules: frozenset[str] | None,
        rule_actions: Mapping[str, str],
    ) -> tuple[str, list[_Detection]]:
        content = text
        detections: list[_Detection] = []
        categories = tuple(
            item
            for item in definition.rules
            if item.form == "category"
            and phase in item.stages
            and (enabled_rules is None or item.id in enabled_rules)
        )
        category_match = self._category_match(categories, content)
        if category_match:
            rule_id, evidence, default_action = category_match
            action = rule_actions.get(
                rule_id, default_action
            )
            detections.append(
                _Detection(definition.id, "category", rule_id, action, evidence)
            )
            if action == "MASK":
                content = self._mask_keyword(content, evidence)

        for rule in definition.rules:
            if rule.form != "regex" or phase not in rule.stages:
                continue
            if enabled_rules is not None and rule.id not in enabled_rules:
                continue
            expression = self._render(rule.expression or "", parameters)
            keyword = (
                self._render(rule.context_expression, parameters)
                if rule.context_expression
                else None
            )
            if keyword and not re.search(keyword, content, re.IGNORECASE):
                continue
            matches = list(re.finditer(expression, content, re.IGNORECASE))
            if not matches:
                continue
            action = rule_actions.get(
                rule.id, _source_action(rule.effect)
            )
            detections.append(
                _Detection(
                    definition.id,
                    "pattern",
                    rule.id,
                    action,
                    matches[0].group(0),
                )
            )
            if action == "MASK":
                content = self._mask_spans(
                    content,
                    matches,
                    rule.redaction or "[REDACTED]",
                )

        for rule in definition.rules:
            if rule.form != "keyword" or phase not in rule.stages:
                continue
            if enabled_rules is not None and rule.id not in enabled_rules:
                continue
            for keyword in self._resolved_keywords(rule, parameters):
                rendered = self._render(keyword, parameters).strip()
                if not rendered:
                    continue
                expression = keyword_expression(rendered)
                if not re.search(expression, content, re.IGNORECASE):
                    continue
                action = rule_actions.get(
                    rule.id, _source_action(rule.effect)
                )
                detections.append(
                    _Detection(
                        definition.id,
                        "blocked word",
                        rule.id,
                        action,
                        rendered,
                    )
                )
                if action == "MASK":
                    content = re.sub(
                        expression,
                        "[REDACTED]",
                        content,
                        flags=re.IGNORECASE,
                    )
                break
        return content, detections

    def _apply_custom_rules(
        self,
        rules: tuple[Mapping[str, Any], ...],
        text: str,
        phase: GuardrailPhase,
    ) -> tuple[str, list[_Detection]]:
        content = text
        detections: list[_Detection] = []
        for rule in rules:
            if phase not in tuple(rule.get("phases", ())):
                continue
            rule_id = str(rule.get("id", "custom-rule"))
            action = str(rule.get("action", "BLOCK")).upper()
            detector = str(rule.get("detector", "keyword"))
            if detector == "regex":
                expression = str(rule.get("expression") or "")
                matches = list(re.finditer(expression, content, re.IGNORECASE))
                if not matches:
                    continue
                detections.append(
                    _Detection("custom", "pattern", rule_id, action, matches[0].group(0))
                )
                if action == "MASK":
                    content = self._mask_spans(content, matches, "[REDACTED]")
                continue
            if detector == "keyword":
                for keyword in tuple(rule.get("keywords", ())):
                    rendered = str(keyword).strip()
                    if not rendered:
                        continue
                    expression = keyword_expression(rendered)
                    if not re.search(expression, content, re.IGNORECASE):
                        continue
                    detections.append(
                        _Detection("custom", "keyword", rule_id, action, rendered)
                    )
                    if action == "MASK":
                        content = re.sub(
                            expression, "[REDACTED]", content, flags=re.IGNORECASE
                        )
                    break
        return content, detections

    def _category_match(
        self,
        categories: tuple[PolicyRuleSpec, ...],
        text: str,
    ) -> tuple[str, str, str] | None:
        lowered = text.lower()
        for item in categories:
            if any(exception in lowered for exception in item.exceptions):
                continue
            for expression in item.phrase_patterns:
                if re.search(expression, text, re.IGNORECASE):
                    return (item.id, item.id, _source_action(item.effect))
            if item.identifiers and item.conditions:
                for sentence in re.split(r"[.!?]+", lowered):
                    identifier = next(
                        (value for value in item.identifiers if value in sentence),
                        None,
                    )
                    conditional = next(
                        (
                            value
                            for value in item.conditions
                            if self._keyword_matches(value, sentence)
                        ),
                        None,
                    )
                    if identifier and conditional:
                        return (
                            item.id,
                            f"{identifier} + {conditional}",
                            _source_action(item.effect),
                        )
            for keyword in item.always_block:
                if self._keyword_matches(keyword[0], lowered):
                    return (item.id, keyword[0], _source_action(item.effect))
            for keyword in item.keywords:
                if severity_applies(
                    keyword[1],
                    item.severity_threshold or "medium",
                ) and self._keyword_matches(keyword[0], lowered):
                    return (item.id, keyword[0], _source_action(item.effect))
        return None

    @staticmethod
    def _resolved_keywords(
        rule: PolicyRuleSpec,
        parameters: Mapping[str, str],
    ) -> tuple[str, ...]:
        if len(rule.keywords) != 1:
            return tuple(value for value, _severity in rule.keywords)
        configured = rule.keywords[0][0]
        if not (configured.startswith("{{") and configured.endswith("}}")):
            return (configured,)
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
        return values

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


def _source_action(effect: str) -> str:
    if effect == "redact":
        return "MASK"
    if effect == "reject":
        return "BLOCK"
    return effect.upper()
