from __future__ import annotations

import json
from pathlib import Path

from .domain import (
    PolicyImplementationRef,
    PolicyParameterSpec,
    PolicyRuleSpec,
    PolicySpec,
    PolicyTag,
    PolicyTestCaseSpec,
)


_ASSET_PATH = Path(__file__).resolve().parent / "assets" / "builtin_policies.json"


def load_builtin_policies() -> tuple[PolicySpec, ...]:
    """Load TaskLattice's canonical, versioned built-in Policy catalog."""

    payload = json.loads(_ASSET_PATH.read_text())
    if not isinstance(payload, list):
        raise RuntimeError("The built-in Policy catalog must be a JSON list.")
    return tuple(_policy(item) for item in payload)


def _policy(payload: dict[str, object]) -> PolicySpec:
    return PolicySpec(
        id=str(payload["id"]),
        name=str(payload["name"]),
        description=str(payload["description"]),
        source=str(payload["source"]),
        version=str(payload["version"]),
        tags=tuple(PolicyTag(**item) for item in payload.get("tags", ())),
        parameters=tuple(
            PolicyParameterSpec(**item) for item in payload.get("parameters", ())
        ),
        rules=tuple(_rule(item) for item in payload.get("rules", ())),
        test_cases=tuple(_test_case(item) for item in payload.get("test_cases", ())),
        safety_level=str(payload.get("safety_level", "balanced")),
        output_delivery=str(payload.get("output_delivery", "window_buffered")),
    )


def _rule(payload: dict[str, object]) -> PolicyRuleSpec:
    values = dict(payload)
    values["stages"] = tuple(values.get("stages", ()))
    values["implementation"] = PolicyImplementationRef(
        **values["implementation"]
    )
    for field in (
        "identifiers",
        "conditions",
        "keywords",
        "always_block",
        "exceptions",
        "phrase_patterns",
    ):
        values[field] = tuple(
            tuple(item) if isinstance(item, list) else item
            for item in values.get(field, ())
        )
    return PolicyRuleSpec(**values)


def _test_case(payload: dict[str, object]) -> PolicyTestCaseSpec:
    values = dict(payload)
    values["covered_rule_ids"] = tuple(values.get("covered_rule_ids", ()))
    values["parameter_names"] = tuple(values.get("parameter_names", ()))
    return PolicyTestCaseSpec(**values)
