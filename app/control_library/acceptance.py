from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path
from re import _constants as regex_constants
from re import _parser as regex_parser
from typing import Any

from .domain import (
    ControlSpec,
    ControlTestCaseSpec,
    ControlTestSuiteSpec,
    RuleSpec,
)


_CATEGORY_SAMPLES = {
    regex_constants.CATEGORY_DIGIT: "1",
    regex_constants.CATEGORY_NOT_DIGIT: "a",
    regex_constants.CATEGORY_SPACE: " ",
    regex_constants.CATEGORY_NOT_SPACE: "a",
    regex_constants.CATEGORY_WORD: "a",
    regex_constants.CATEGORY_NOT_WORD: "-",
    regex_constants.CATEGORY_LINEBREAK: "\n",
    regex_constants.CATEGORY_NOT_LINEBREAK: "a",
}


def attach_test_suites(
    controls: dict[str, ControlSpec],
    *,
    asset_path: Path,
) -> dict[str, ControlSpec]:
    """Attach TaskLattice test contracts without coupling runtime execution to assets."""

    scenario_suites = _load_scenario_suites(asset_path)
    unknown = sorted(set(scenario_suites).difference(controls))
    if unknown:
        raise RuntimeError(
            "Built-in Control tests reference unknown Controls: " + ", ".join(unknown)
        )

    return {
        control_id: replace(
            control,
            test_suites=(
                _rule_acceptance_suite(control),
                *scenario_suites.get(control_id, ()),
            ),
        )
        for control_id, control in controls.items()
    }


def materialize_test_content(
    case: ControlTestCaseSpec,
    parameters: dict[str, str],
) -> str:
    return materialize_test_text(case.content, case.parameter_names, parameters)


def materialize_test_text(
    value: str,
    parameter_names: tuple[str, ...],
    parameters: dict[str, str],
) -> str:
    rendered = value
    for name in parameter_names:
        parameter_value = parameters.get(name, "").strip()
        if "\n" in parameter_value:
            parameter_value = next(
                (
                    item.strip()
                    for item in parameter_value.splitlines()
                    if item.strip()
                ),
                "",
            )
        rendered = rendered.replace(f"{{{{{name}}}}}", parameter_value)
    return rendered.strip()


def _rule_acceptance_suite(control: ControlSpec) -> ControlTestSuiteSpec:
    cases = tuple(_rule_acceptance_case(rule) for rule in control.rules)
    return ControlTestSuiteSpec(
        id="rule-acceptance",
        name="Rule acceptance",
        description=(
            "Required implementation-level checks proving that each published Rule "
            "can produce its declared enforcement action."
        ),
        cases=cases,
    )


def _rule_acceptance_case(rule: RuleSpec) -> ControlTestCaseSpec:
    content, parameters = _acceptance_content(rule)
    return ControlTestCaseSpec(
        id=f"rule-{rule.id}-acceptance",
        name=f"Trigger {rule.name}",
        description=(
            f"Proves that the published {rule.detector} implementation for "
            f"{rule.name} activates this Rule."
        ),
        phase=rule.phases[0],
        content=content,
        expected_decision="transform" if rule.action == "MASK" else "block",
        covered_rule_ids=(rule.id,),
        kind="rule_acceptance",
        required=True,
        parameter_names=parameters,
    )


def _acceptance_content(rule: RuleSpec) -> tuple[str, tuple[str, ...]]:
    if rule.detector == "regex":
        sample = _regex_sample(rule.expression or "")
        if rule.context_expression:
            sample = f"{_regex_sample(rule.context_expression)} {sample}"
        return f"Acceptance sample: {sample}", ()

    if rule.detector == "keyword":
        value = rule.keywords[0].value
        if value == "{{competitors_blocked_words}}":
            return "Review the services offered by {{competitors}}.", ("competitors",)
        if value == "{{competitor_recommendation_words}}":
            return "I recommend {{competitors}} for this trip.", ("competitors",)
        if value == "{{competitor_comparison_words}}":
            return (
                "{{competitors}} is better than {{brand_name}}.",
                ("competitors", "brand_name"),
            )
        parameters = tuple(sorted(set(re.findall(r"\{\{([^{}]+)\}\}", value))))
        return f"Acceptance sample: {value}", parameters

    if rule.always_block:
        return f"Acceptance sample: {rule.always_block[0].value}", ()
    if rule.identifiers and rule.conditions:
        return f"Acceptance sample: {rule.identifiers[0]} {rule.conditions[0]}", ()
    if rule.keywords:
        return f"Acceptance sample: {rule.keywords[0].value}", ()
    if rule.phrase_patterns:
        return f"Acceptance sample: {_regex_sample(rule.phrase_patterns[0])}", ()
    raise RuntimeError(f"Rule {rule.id!r} has no executable acceptance sample.")


def _regex_sample(expression: str) -> str:
    groups: dict[int, str] = {}
    sample = _render_tokens(regex_parser.parse(expression), groups)
    if not re.search(expression, sample, re.IGNORECASE):
        raise RuntimeError(
            f"Could not derive a matching acceptance sample for regex {expression!r}."
        )
    return sample


def _render_tokens(tokens, groups: dict[int, str]) -> str:
    output = ""
    for operator, argument in tokens:
        if operator is regex_constants.LITERAL:
            output += chr(argument)
        elif operator is regex_constants.NOT_LITERAL:
            output += "a" if argument != ord("a") else "b"
        elif operator is regex_constants.ANY:
            output += "a"
        elif operator is regex_constants.IN:
            output += _render_character_class(argument)
        elif operator in {
            regex_constants.MAX_REPEAT,
            regex_constants.MIN_REPEAT,
            regex_constants.POSSESSIVE_REPEAT,
        }:
            minimum, _maximum, child = argument
            output += _render_tokens(child, groups) * max(1, minimum)
        elif operator is regex_constants.SUBPATTERN:
            group, _add_flags, _delete_flags, child = argument
            value = _render_tokens(child, groups)
            output += value
            if group:
                groups[group] = value
        elif operator is regex_constants.BRANCH:
            output += _render_tokens(argument[1][0], groups)
        elif operator is regex_constants.CATEGORY:
            output += _CATEGORY_SAMPLES.get(argument, "a")
        elif operator is regex_constants.GROUPREF:
            output += groups.get(argument, "a")
        elif operator is regex_constants.GROUPREF_EXISTS:
            group, yes_branch, no_branch = argument
            output += _render_tokens(
                yes_branch if group in groups else no_branch or (), groups
            )
        elif operator in {
            regex_constants.AT,
            regex_constants.ASSERT,
            regex_constants.ASSERT_NOT,
        }:
            continue
        else:  # pragma: no cover - protected by the shipped pattern corpus test
            raise RuntimeError(f"Unsupported regex token {operator!r}.")
    return output


def _render_character_class(tokens) -> str:
    negated = False
    candidates: list[str] = []
    for operator, argument in tokens:
        if operator is regex_constants.NEGATE:
            negated = True
        elif operator is regex_constants.LITERAL:
            candidates.append(chr(argument))
        elif operator is regex_constants.RANGE:
            candidates.append(chr(argument[0]))
        elif operator is regex_constants.CATEGORY:
            candidates.append(_CATEGORY_SAMPLES.get(argument, "a"))
    value = candidates[0] if candidates else "a"
    return "b" if negated and value == "a" else value


def _load_scenario_suites(path: Path) -> dict[str, tuple[ControlTestSuiteSpec, ...]]:
    payload: list[dict[str, Any]] = json.loads(path.read_text())
    suites: dict[str, list[ControlTestSuiteSpec]] = {}
    for raw_suite in payload:
        control_id = str(raw_suite["control_id"])
        cases = tuple(
            ControlTestCaseSpec(
                id=str(raw_case["id"]),
                name=str(raw_case["name"]),
                description=str(raw_case["description"]),
                phase=str(raw_case["phase"]),
                content=str(raw_case["content"]),
                expected_decision=str(raw_case["expected_decision"]),
                covered_rule_ids=tuple(raw_case["covered_rule_ids"]),
                kind="scenario",
                required=bool(raw_case.get("required", True)),
                parameter_names=tuple(raw_case.get("parameter_names", ())),
            )
            for raw_case in raw_suite["cases"]
        )
        suites.setdefault(control_id, []).append(
            ControlTestSuiteSpec(
                id=str(raw_suite["id"]),
                name=str(raw_suite["name"]),
                description=str(raw_suite["description"]),
                cases=cases,
            )
        )
    return {control_id: tuple(items) for control_id, items in suites.items()}
