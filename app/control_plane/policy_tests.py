from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from ..runtime.contracts import flow_rule_id
from .catalog import capability_id_for_policy
from .domain import PolicyTestCaseDefinition


_ASSET_PATH = Path(__file__).resolve().parent / "assets" / "builtin_policy_tests.json"
_SUPPORTED_RAIL_TYPES = frozenset({"input", "output"})
_SUPPORTED_DECISIONS = frozenset({"allow", "intervene"})
_SUPPORTED_EXPANSIONS = frozenset({"allowed_topics", "restricted_topics"})


@lru_cache(maxsize=1)
def builtin_policy_tests() -> dict[str, tuple[PolicyTestCaseDefinition, ...]]:
    """Load the reviewed Test Cases owned by built-in programmable Policies."""

    raw_policies = json.loads(_ASSET_PATH.read_text())
    if not isinstance(raw_policies, list):
        raise RuntimeError("Built-in Policy Test Cases must be a JSON list.")

    result: dict[str, tuple[PolicyTestCaseDefinition, ...]] = {}
    case_ids: set[str] = set()
    for raw_policy in raw_policies:
        policy_id = _required_string(raw_policy, "policy_id")
        capability_id = capability_id_for_policy(policy_id)
        if policy_id in result:
            raise RuntimeError(f"Built-in Policy tests repeat {policy_id!r}.")
        raw_cases = raw_policy.get("cases")
        if not isinstance(raw_cases, list) or not raw_cases:
            raise RuntimeError(f"Built-in Policy {policy_id!r} has no Test Cases.")

        cases: list[PolicyTestCaseDefinition] = []
        for raw_case in raw_cases:
            case_id = _required_string(raw_case, "id")
            if case_id in case_ids:
                raise RuntimeError(f"Built-in Policy Test Case {case_id!r} is repeated.")
            case_ids.add(case_id)
            rail_type = _required_string(raw_case, "rail_type")
            expected_decision = _required_string(raw_case, "expected_decision")
            for_each = raw_case.get("for_each")
            if rail_type not in _SUPPORTED_RAIL_TYPES:
                raise RuntimeError(f"Test Case {case_id!r} has an unsupported Rail.")
            if expected_decision not in _SUPPORTED_DECISIONS:
                raise RuntimeError(f"Test Case {case_id!r} has an unsupported expectation.")
            if for_each is not None and for_each not in _SUPPORTED_EXPANSIONS:
                raise RuntimeError(f"Test Case {case_id!r} has an unsupported expansion.")

            cases.append(
                PolicyTestCaseDefinition(
                    id=case_id,
                    name=_required_string(raw_case, "name"),
                    description=_required_string(raw_case, "description"),
                    rail_type=rail_type,
                    content=_required_string(raw_case, "content"),
                    expected_decision=expected_decision,
                    covered_rule_ids=(
                        flow_rule_id(
                            rail_type,
                            f"builtin_{capability_id}_{rail_type}",
                        ),
                    ),
                    case_type="scenario",
                    trusted_instruction=str(raw_case.get("trusted_instruction", "")),
                    use_guardrail_instruction=bool(
                        raw_case.get("use_guardrail_instruction", False)
                    ),
                    for_each=for_each,
                    target_source=str(raw_case.get("target_source", "user_input")),
                    query=str(raw_case.get("query", "")),
                    grounding_sources=tuple(raw_case.get("grounding_sources", ())),
                    expected_reasoning_result=raw_case.get(
                        "expected_reasoning_result"
                    ),
                )
            )
        result[policy_id] = tuple(cases)
    return result


def tests_for_builtin_policy(policy_id: str) -> tuple[PolicyTestCaseDefinition, ...]:
    try:
        return builtin_policy_tests()[policy_id]
    except KeyError as error:
        raise RuntimeError(
            f"Built-in Policy {policy_id!r} does not own reviewed Test Cases."
        ) from error


def _required_string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"Built-in Policy Test Case field {key!r} is required.")
    return value.strip()
