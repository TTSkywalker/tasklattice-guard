from __future__ import annotations

from dataclasses import asdict, dataclass
import fnmatch
from typing import Any

from ..runtime.contracts import RequestContext
from .domain import (
    ValidationError,
    TrafficScopeExpression,
    TrafficCondition,
)


MAX_TRAFFIC_SCOPE_DEPTH = 3
MAX_TRAFFIC_CONDITIONS = 16
TRAFFIC_SCOPE_COMBINATORS = frozenset({"and", "or"})


@dataclass(frozen=True, slots=True)
class TrafficScopeFieldDefinition:
    id: str
    group: str
    source: str
    key: str
    operators: tuple[str, ...]
    values: tuple[str, ...] = ()
    custom_key: bool = False


TRAFFIC_SCOPE_FIELDS = (
    TrafficScopeFieldDefinition("protocol", "request", "field", "protocol", ("equals",), ("http", "litellm", "a2a")),
    TrafficScopeFieldDefinition("output.sink", "request", "field", "output.sink", ("equals",), ("display", "markdown", "html", "sql", "shell", "url", "json", "tool_argument")),
    TrafficScopeFieldDefinition("output.content_type", "request", "field", "output.content_type", ("equals", "glob")),
    TrafficScopeFieldDefinition("output.schema_id", "request", "field", "output.schema_id", ("equals", "glob")),
    TrafficScopeFieldDefinition("tool.name", "request", "field", "tool.name", ("equals", "glob")),
    TrafficScopeFieldDefinition("target.environment", "request", "field", "target.environment", ("equals", "glob")),
    TrafficScopeFieldDefinition("auth.principal", "authentication", "field", "auth.principal", ("equals", "glob")),
    TrafficScopeFieldDefinition("integration.id", "authentication", "field", "integration.id", ("equals",)),
    TrafficScopeFieldDefinition("http.method", "http", "field", "http.method", ("equals",), ("GET", "POST", "PUT", "PATCH", "DELETE")),
    TrafficScopeFieldDefinition("http.host", "http", "field", "http.host", ("equals", "glob")),
    TrafficScopeFieldDefinition("http.path", "http", "field", "http.path", ("equals", "starts_with", "glob")),
    TrafficScopeFieldDefinition("http.header", "http", "header", "", ("equals", "contains", "starts_with", "glob"), custom_key=True),
    TrafficScopeFieldDefinition("auth.jwt_claim", "authentication", "jwt_claim", "", ("equals", "contains", "glob"), custom_key=True),
    TrafficScopeFieldDefinition("model", "model", "field", "model", ("equals", "starts_with", "glob")),
    TrafficScopeFieldDefinition("litellm.api_key_alias", "litellm", "field", "litellm.api_key_alias", ("equals", "glob")),
    TrafficScopeFieldDefinition("litellm.team_id", "litellm", "field", "litellm.team_id", ("equals", "glob")),
    TrafficScopeFieldDefinition("litellm.user_id", "litellm", "field", "litellm.user_id", ("equals", "glob")),
    TrafficScopeFieldDefinition("a2a.version", "a2a", "field", "a2a.version", ("equals",), ("0.3", "1.0")),
    TrafficScopeFieldDefinition("a2a.extensions", "a2a", "field", "a2a.extensions", ("contains", "glob")),
    TrafficScopeFieldDefinition("a2a.operation", "a2a", "field", "a2a.operation", ("equals", "glob")),
    TrafficScopeFieldDefinition("a2a.context_id", "a2a", "field", "a2a.context_id", ("equals", "glob")),
    TrafficScopeFieldDefinition("a2a.task_id", "a2a", "field", "a2a.task_id", ("equals", "glob")),
    TrafficScopeFieldDefinition("adapter.field", "request", "field", "", ("equals", "contains", "starts_with", "glob"), custom_key=True),
)

_FIELD_BY_ID = {item.id: item for item in TRAFFIC_SCOPE_FIELDS}
_OPERATOR_WEIGHT = {"equals": 4, "starts_with": 3, "contains": 2, "glob": 1}


def traffic_scope_field_payloads() -> list[dict[str, object]]:
    return [asdict(item) for item in TRAFFIC_SCOPE_FIELDS]


def normalize_traffic_scope(
    expression: TrafficScopeExpression,
) -> TrafficScopeExpression:
    counter = [0]
    return _normalize_group(expression, depth=1, root=True, counter=counter)


def traffic_scope_from_payload(payload: dict[str, Any]) -> TrafficScopeExpression:
    return TrafficScopeExpression(
        combinator=str(payload["combinator"]),
        conditions=tuple(
            traffic_scope_from_payload(item)
            if "conditions" in item
            else TrafficCondition(
                field=str(item["field"]),
                operator=str(item["operator"]),
                value=str(item["value"]),
                key=str(item["key"]),
            )
            for item in payload["conditions"]
        ),
    )


def traffic_scope_signature(expression: TrafficScopeExpression) -> tuple[object, ...]:
    children = []
    for item in expression.conditions:
        if isinstance(item, TrafficScopeExpression):
            children.append(traffic_scope_signature(item))
        else:
            children.append(("condition", item.field, item.key, item.operator, item.value))
    return ("group", expression.combinator, *sorted(children, key=repr))


def traffic_scope_matches(
    expression: TrafficScopeExpression,
    context: RequestContext,
) -> bool:
    if not expression.conditions:
        return True
    matches = (
        traffic_scope_matches(item, context)
        if isinstance(item, TrafficScopeExpression)
        else _condition_matches(item, context)
        for item in expression.conditions
    )
    return all(matches) if expression.combinator == "and" else any(matches)


def traffic_scope_specificity(
    expression: TrafficScopeExpression,
) -> tuple[int, int]:
    if not expression.conditions:
        return (0, 0)
    children = [
        traffic_scope_specificity(item)
        if isinstance(item, TrafficScopeExpression)
        else (1, _OPERATOR_WEIGHT[item.operator])
        for item in expression.conditions
    ]
    if expression.combinator == "and":
        return (sum(item[0] for item in children), sum(item[1] for item in children))
    return min(children)


def traffic_condition_count(expression: TrafficScopeExpression) -> int:
    return sum(
        traffic_condition_count(item) if isinstance(item, TrafficScopeExpression) else 1
        for item in expression.conditions
    )


def _normalize_group(
    expression: TrafficScopeExpression,
    *,
    depth: int,
    root: bool,
    counter: list[int],
) -> TrafficScopeExpression:
    if depth > MAX_TRAFFIC_SCOPE_DEPTH:
        raise ValidationError(
            f"Traffic Scopes support at most {MAX_TRAFFIC_SCOPE_DEPTH} nested levels."
        )
    combinator = expression.combinator.strip().lower()
    if combinator not in TRAFFIC_SCOPE_COMBINATORS:
        raise ValidationError("Traffic Scope groups must use AND or OR.")
    if not expression.conditions:
        if not root:
            raise ValidationError("Nested Traffic Scope groups cannot be empty.")
        return TrafficScopeExpression(combinator="and", conditions=())

    conditions: list[TrafficCondition | TrafficScopeExpression] = []
    for item in expression.conditions:
        if isinstance(item, TrafficScopeExpression):
            conditions.append(
                _normalize_group(item, depth=depth + 1, root=False, counter=counter)
            )
            continue
        counter[0] += 1
        if counter[0] > MAX_TRAFFIC_CONDITIONS:
            raise ValidationError(
                f"A Deployment can contain at most {MAX_TRAFFIC_CONDITIONS} Traffic Conditions."
            )
        conditions.append(_normalize_condition(item))

    if combinator == "and":
        equalities: dict[tuple[str, str], set[str]] = {}
        for item in conditions:
            if isinstance(item, TrafficScopeExpression) or item.operator != "equals":
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
        traffic_scope_signature(item)
        if isinstance(item, TrafficScopeExpression)
        else ("condition", item.field, item.key, item.operator, item.value)
        for item in conditions
    ]
    if len(signatures) != len(set(signatures)):
        raise ValidationError("A Traffic Scope group cannot contain duplicate conditions.")
    return TrafficScopeExpression(combinator=combinator, conditions=tuple(conditions))


def _normalize_condition(condition: TrafficCondition) -> TrafficCondition:
    field = condition.field.strip()
    definition = _FIELD_BY_ID.get(field)
    if definition is None:
        raise ValidationError("Unsupported Traffic Scope field.")
    operator = condition.operator.strip()
    if operator not in definition.operators:
        raise ValidationError("Unsupported operator for this Traffic Scope field.")
    value = condition.value.strip()
    if not value or len(value) > 500:
        raise ValidationError(
            "Traffic Scope values are required and limited to 500 characters."
        )
    key = condition.key.strip() if definition.custom_key else ""
    if definition.custom_key and (
        not key or len(key) > 120 or any(character.isspace() for character in key)
    ):
        raise ValidationError(
            "Custom Traffic Scope fields require a compact attribute name."
        )
    if definition.source == "header":
        key = key.lower()
    return TrafficCondition(field=field, key=key, operator=operator, value=value)


def _condition_matches(condition: TrafficCondition, context: RequestContext) -> bool:
    definition = _FIELD_BY_ID[condition.field]
    actual = context.value(
        definition.source,
        condition.key if definition.custom_key else definition.key,
    )
    if actual is None:
        return False
    if condition.operator == "equals":
        return actual == condition.value
    if condition.operator == "contains":
        return condition.value in actual
    if condition.operator == "starts_with":
        return actual.startswith(condition.value)
    return fnmatch.fnmatchcase(actual, condition.value)
