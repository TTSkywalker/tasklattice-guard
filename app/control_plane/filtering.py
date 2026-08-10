from __future__ import annotations

from dataclasses import asdict, dataclass
import fnmatch
from typing import Any

from ..engine.contracts import RequestContext
from .domain import (
    ValidationError,
    WorkloadFilterExpression,
    WorkloadFilterRule,
)


MAX_FILTER_DEPTH = 3
MAX_FILTER_RULES = 16
FILTER_COMBINATORS = frozenset({"and", "or"})


@dataclass(frozen=True, slots=True)
class WorkloadFilterFieldDefinition:
    id: str
    group: str
    source: str
    key: str
    operators: tuple[str, ...]
    values: tuple[str, ...] = ()
    custom_key: bool = False


WORKLOAD_FILTER_FIELDS = (
    WorkloadFilterFieldDefinition("protocol", "request", "field", "protocol", ("equals",), ("http", "litellm", "a2a")),
    WorkloadFilterFieldDefinition("auth.principal", "authentication", "field", "auth.principal", ("equals", "glob")),
    WorkloadFilterFieldDefinition("integration.id", "authentication", "field", "integration.id", ("equals",)),
    WorkloadFilterFieldDefinition("http.method", "http", "field", "http.method", ("equals",), ("GET", "POST", "PUT", "PATCH", "DELETE")),
    WorkloadFilterFieldDefinition("http.host", "http", "field", "http.host", ("equals", "glob")),
    WorkloadFilterFieldDefinition("http.path", "http", "field", "http.path", ("equals", "starts_with", "glob")),
    WorkloadFilterFieldDefinition("http.header", "http", "header", "", ("equals", "contains", "starts_with", "glob"), custom_key=True),
    WorkloadFilterFieldDefinition("auth.jwt_claim", "authentication", "jwt_claim", "", ("equals", "contains", "glob"), custom_key=True),
    WorkloadFilterFieldDefinition("model", "model", "field", "model", ("equals", "starts_with", "glob")),
    WorkloadFilterFieldDefinition("litellm.api_key_alias", "litellm", "field", "litellm.api_key_alias", ("equals", "glob")),
    WorkloadFilterFieldDefinition("litellm.team_id", "litellm", "field", "litellm.team_id", ("equals", "glob")),
    WorkloadFilterFieldDefinition("litellm.user_id", "litellm", "field", "litellm.user_id", ("equals", "glob")),
    WorkloadFilterFieldDefinition("a2a.version", "a2a", "field", "a2a.version", ("equals",), ("0.3", "1.0")),
    WorkloadFilterFieldDefinition("a2a.extensions", "a2a", "field", "a2a.extensions", ("contains", "glob")),
    WorkloadFilterFieldDefinition("a2a.operation", "a2a", "field", "a2a.operation", ("equals", "glob")),
    WorkloadFilterFieldDefinition("a2a.context_id", "a2a", "field", "a2a.context_id", ("equals", "glob")),
    WorkloadFilterFieldDefinition("a2a.task_id", "a2a", "field", "a2a.task_id", ("equals", "glob")),
    WorkloadFilterFieldDefinition("adapter.field", "request", "field", "", ("equals", "contains", "starts_with", "glob"), custom_key=True),
)

_FIELD_BY_ID = {item.id: item for item in WORKLOAD_FILTER_FIELDS}
_OPERATOR_WEIGHT = {"equals": 4, "starts_with": 3, "contains": 2, "glob": 1}


def workload_filter_field_payloads() -> list[dict[str, object]]:
    return [asdict(item) for item in WORKLOAD_FILTER_FIELDS]


def normalize_filter_expression(
    expression: WorkloadFilterExpression,
) -> WorkloadFilterExpression:
    counter = [0]
    return _normalize_group(expression, depth=1, root=True, counter=counter)


def filter_expression_from_payload(payload: dict[str, Any]) -> WorkloadFilterExpression:
    return WorkloadFilterExpression(
        combinator=str(payload["combinator"]),
        rules=tuple(
            filter_expression_from_payload(item)
            if "rules" in item
            else WorkloadFilterRule(
                field=str(item["field"]),
                operator=str(item["operator"]),
                value=str(item["value"]),
                key=str(item.get("key", "")),
            )
            for item in payload["rules"]
        ),
    )


def filter_expression_signature(expression: WorkloadFilterExpression) -> tuple[object, ...]:
    children = []
    for item in expression.rules:
        if isinstance(item, WorkloadFilterExpression):
            children.append(filter_expression_signature(item))
        else:
            children.append(("rule", item.field, item.key, item.operator, item.value))
    return ("group", expression.combinator, *sorted(children, key=repr))


def filter_expression_matches(
    expression: WorkloadFilterExpression,
    context: RequestContext,
) -> bool:
    if not expression.rules:
        return True
    matches = (
        filter_expression_matches(item, context)
        if isinstance(item, WorkloadFilterExpression)
        else _rule_matches(item, context)
        for item in expression.rules
    )
    return all(matches) if expression.combinator == "and" else any(matches)


def filter_expression_specificity(
    expression: WorkloadFilterExpression,
) -> tuple[int, int]:
    if not expression.rules:
        return (0, 0)
    children = [
        filter_expression_specificity(item)
        if isinstance(item, WorkloadFilterExpression)
        else (1, _OPERATOR_WEIGHT[item.operator])
        for item in expression.rules
    ]
    if expression.combinator == "and":
        return (sum(item[0] for item in children), sum(item[1] for item in children))
    return min(children)


def filter_rule_count(expression: WorkloadFilterExpression) -> int:
    return sum(
        filter_rule_count(item) if isinstance(item, WorkloadFilterExpression) else 1
        for item in expression.rules
    )


def _normalize_group(
    expression: WorkloadFilterExpression,
    *,
    depth: int,
    root: bool,
    counter: list[int],
) -> WorkloadFilterExpression:
    if depth > MAX_FILTER_DEPTH:
        raise ValidationError(
            f"Workload filters support at most {MAX_FILTER_DEPTH} nested levels."
        )
    combinator = expression.combinator.strip().lower()
    if combinator not in FILTER_COMBINATORS:
        raise ValidationError("Workload filter groups must use AND or OR.")
    if not expression.rules:
        if not root:
            raise ValidationError("Nested Workload filter groups cannot be empty.")
        return WorkloadFilterExpression(combinator="and", rules=())

    rules: list[WorkloadFilterRule | WorkloadFilterExpression] = []
    for item in expression.rules:
        if isinstance(item, WorkloadFilterExpression):
            rules.append(
                _normalize_group(item, depth=depth + 1, root=False, counter=counter)
            )
            continue
        counter[0] += 1
        if counter[0] > MAX_FILTER_RULES:
            raise ValidationError(
                f"A Workload can contain at most {MAX_FILTER_RULES} traffic rules."
            )
        rules.append(_normalize_rule(item))

    if combinator == "and":
        equalities: dict[tuple[str, str], set[str]] = {}
        for item in rules:
            if isinstance(item, WorkloadFilterExpression) or item.operator != "equals":
                continue
            equalities.setdefault((item.field, item.key), set()).add(item.value)
        conflict = next(
            (
                (field, key, values)
                for (field, key), values in equalities.items()
                if len(values) > 1
            ),
            None,
        )
        if conflict is not None:
            field, key, values = conflict
            attribute = f"{field}:{key}" if key else field
            raise ValidationError(
                f"{attribute} cannot equal {', '.join(sorted(values))} at the same time; "
                "use an OR group for alternatives."
            )

    signatures = [
        filter_expression_signature(item)
        if isinstance(item, WorkloadFilterExpression)
        else ("rule", item.field, item.key, item.operator, item.value)
        for item in rules
    ]
    if len(signatures) != len(set(signatures)):
        raise ValidationError("A Workload filter group cannot contain duplicate rules.")
    return WorkloadFilterExpression(combinator=combinator, rules=tuple(rules))


def _normalize_rule(rule: WorkloadFilterRule) -> WorkloadFilterRule:
    field = rule.field.strip()
    definition = _FIELD_BY_ID.get(field)
    if definition is None:
        raise ValidationError("Unsupported Workload filter field.")
    operator = rule.operator.strip()
    if operator not in definition.operators:
        raise ValidationError("Unsupported operator for this Workload filter field.")
    value = rule.value.strip()
    if not value or len(value) > 500:
        raise ValidationError(
            "Workload filter values are required and limited to 500 characters."
        )
    key = rule.key.strip() if definition.custom_key else ""
    if definition.custom_key and (
        not key or len(key) > 120 or any(character.isspace() for character in key)
    ):
        raise ValidationError(
            "Custom Workload filter fields require a compact attribute name."
        )
    if definition.source == "header":
        key = key.lower()
    return WorkloadFilterRule(field=field, key=key, operator=operator, value=value)


def _rule_matches(rule: WorkloadFilterRule, context: RequestContext) -> bool:
    definition = _FIELD_BY_ID[rule.field]
    actual = context.value(
        definition.source,
        rule.key if definition.custom_key else definition.key,
    )
    if actual is None:
        return False
    if rule.operator == "equals":
        return actual == rule.value
    if rule.operator == "contains":
        return rule.value in actual
    if rule.operator == "starts_with":
        return actual.startswith(rule.value)
    return fnmatch.fnmatchcase(actual, rule.value)
