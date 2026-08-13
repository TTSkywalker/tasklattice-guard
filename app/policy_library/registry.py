from __future__ import annotations

from functools import lru_cache

from .domain import PolicySpec
from .loader import load_builtin_policies


_SUPPORTED_STAGES = frozenset(
    {"input", "retrieval", "dialog", "execution", "output"}
)
_SUPPORTED_TEST_DECISIONS = frozenset(
    {"allow", "block", "transform", "intervene"}
)


class PolicyLibraryRegistry:
    """Validated and indexed access to all Policies available to Guardrails."""

    def __init__(self, items: tuple[PolicySpec, ...]) -> None:
        if not items:
            raise ValueError("The Policy Library requires at least one Policy.")

        index: dict[str, PolicySpec] = {}
        for item in items:
            self._validate_policy(item)
            if item.id in index:
                raise ValueError(f"Duplicate Policy ID {item.id!r}.")
            index[item.id] = item

        self._items = tuple(
            sorted(index.values(), key=lambda item: (item.name.casefold(), item.id))
        )
        self._index = index

    @property
    def policies(self) -> tuple[PolicySpec, ...]:
        return self._items

    def policy(self, policy_id: str) -> PolicySpec | None:
        return self._index.get(policy_id)

    @staticmethod
    def _validate_policy(item: PolicySpec) -> None:
        _required(item.id, "Policy ID")
        _required(item.name, f"Policy {item.id!r} name")
        _required(item.description, f"Policy {item.id!r} description")
        _required(item.version, f"Policy {item.id!r} version")
        if not item.rules:
            raise ValueError(f"Policy {item.id!r} contains no Rules.")
        if not item.test_cases:
            raise ValueError(f"Policy {item.id!r} contains no Test Cases.")

        parameter_names = [parameter.name for parameter in item.parameters]
        if len(parameter_names) != len(set(parameter_names)):
            raise ValueError(f"Policy {item.id!r} repeats a parameter name.")

        rule_ids: set[str] = set()
        for rule in item.rules:
            _required(rule.id, f"Policy {item.id!r} Rule ID")
            _required(rule.name, f"Policy {item.id!r} Rule {rule.id!r} name")
            if rule.id in rule_ids:
                raise ValueError(
                    f"Policy {item.id!r} contains duplicate Rule {rule.id!r}."
                )
            rule_ids.add(rule.id)
            if not rule.stages or any(
                stage not in _SUPPORTED_STAGES for stage in rule.stages
            ):
                raise ValueError(
                    f"Policy {item.id!r} Rule {rule.id!r} has invalid stages."
                )

        case_ids: set[str] = set()
        accepted_rules: set[str] = set()
        available_parameters = set(parameter_names)
        for case in item.test_cases:
            _required(case.id, f"Policy {item.id!r} Test Case ID")
            _required(case.name, f"Policy {item.id!r} Test Case {case.id!r} name")
            _required(case.group, f"Policy {item.id!r} Test Case {case.id!r} group")
            _required(
                case.content,
                f"Policy {item.id!r} Test Case {case.id!r} content",
            )
            if case.id in case_ids:
                raise ValueError(
                    f"Policy {item.id!r} repeats Test Case {case.id!r}."
                )
            case_ids.add(case.id)
            if case.stage not in _SUPPORTED_STAGES:
                raise ValueError(
                    f"Policy {item.id!r} Test Case {case.id!r} has an invalid stage."
                )
            if case.expected_decision not in _SUPPORTED_TEST_DECISIONS:
                raise ValueError(
                    f"Policy {item.id!r} Test Case {case.id!r} has an invalid expectation."
                )
            unknown_rules = set(case.covered_rule_ids).difference(rule_ids)
            if unknown_rules:
                raise ValueError(
                    f"Policy {item.id!r} Test Case {case.id!r} references unknown "
                    f"Rules: {', '.join(sorted(unknown_rules))}."
                )
            unknown_parameters = set(case.parameter_names).difference(
                available_parameters
            )
            if unknown_parameters:
                raise ValueError(
                    f"Policy {item.id!r} Test Case {case.id!r} references unknown "
                    f"parameters: {', '.join(sorted(unknown_parameters))}."
                )
            if case.required and case.kind == "rule_acceptance":
                accepted_rules.update(case.covered_rule_ids)

        uncovered = sorted(rule_ids.difference(accepted_rules))
        if uncovered:
            raise ValueError(
                f"Policy {item.id!r} Rules lack required acceptance tests: "
                + ", ".join(uncovered)
                + "."
            )


def _required(value: str, label: str) -> None:
    if not value.strip():
        raise ValueError(f"{label} is required.")


@lru_cache(maxsize=1)
def registry() -> PolicyLibraryRegistry:
    return PolicyLibraryRegistry(load_builtin_policies())


def policies() -> tuple[PolicySpec, ...]:
    return registry().policies


def policy(policy_id: str) -> PolicySpec | None:
    return registry().policy(policy_id)
