from __future__ import annotations

from dataclasses import asdict

from .domain import ControlPackSpec, ControlSpec, RuleSpec
from .registry import control_packs, controls


def control_catalog() -> tuple[dict[str, object], ...]:
    """Return the public, implementation-discriminated rule Control catalog."""
    packs = control_packs()
    memberships: dict[str, list[dict[str, str]]] = {
        item.id: [] for item in controls()
    }
    for pack in packs:
        reference = {"id": pack.id, "name": pack.name}
        for control_id in pack.control_ids:
            memberships[control_id].append(reference)

    return tuple(
        _control_payload(
            item,
            tuple(
                sorted(
                    memberships[item.id],
                    key=lambda reference: reference["name"].casefold(),
                )
            ),
        )
        for item in controls()
    )


def control_pack_catalog() -> tuple[dict[str, object], ...]:
    return tuple(_control_pack_payload(item) for item in control_packs())


def _control_payload(
    item: ControlSpec,
    packs: tuple[dict[str, str], ...],
) -> dict[str, object]:
    return {
        "implementation": "rules",
        "id": item.id,
        "name": item.name,
        "description": item.description,
        "source": item.source,
        "version": item.version,
        "phases": item.phases,
        "default_action": item.default_action,
        "allowed_actions": item.allowed_actions,
        "detector_types": item.detector_types,
        "rules": tuple(_rule_payload(rule) for rule in item.rules),
        "packs": packs,
    }


def _rule_payload(item: RuleSpec) -> dict[str, object]:
    return {
        "id": item.id,
        "name": item.name,
        "detector": item.detector,
        "action": item.action,
        "phases": item.phases,
        "description": item.description,
        "expression": item.expression,
        "context_expression": item.context_expression,
        "redaction": item.redaction,
        "severity_threshold": item.severity_threshold,
        "identifiers": item.identifiers,
        "conditions": item.conditions,
        "keywords": tuple(asdict(keyword) for keyword in item.keywords),
        "always_block": tuple(asdict(keyword) for keyword in item.always_block),
        "exceptions": item.exceptions,
        "phrase_patterns": item.phrase_patterns,
    }


def _control_pack_payload(item: ControlPackSpec) -> dict[str, object]:
    return asdict(item)
