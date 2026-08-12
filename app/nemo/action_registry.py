from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..runtime.contracts import RailType


@dataclass(frozen=True, slots=True)
class ActionDefinition:
    """Versioned metadata for an Action that may be referenced by Colang."""

    name: str
    version: str
    input_schema: tuple[tuple[str, str], ...]
    output_schema: tuple[tuple[str, str], ...]
    supported_rails: tuple[RailType, ...]
    timeout_ms: int
    failure_mode: Literal["fail_open", "fail_closed"]
    side_effects: bool
    concurrent: bool
    network_access: bool = False
    secret_names: tuple[str, ...] = ()
    provider_ready: bool = True


class ActionCatalog:
    def __init__(self, definitions: tuple[ActionDefinition, ...]) -> None:
        keys = tuple((item.name, item.version) for item in definitions)
        if len(set(keys)) != len(keys):
            raise ValueError("Action names and versions must be unique.")
        self._definitions = {key: item for key, item in zip(keys, definitions, strict=True)}

    def definitions(self) -> tuple[ActionDefinition, ...]:
        return tuple(self._definitions.values())

    def get(self, name: str, version: str) -> ActionDefinition:
        try:
            return self._definitions[(name, version)]
        except KeyError as error:
            raise KeyError(f"Action {name}@{version} is not registered.") from error

    def contains(self, name: str, version: str) -> bool:
        return (name, version) in self._definitions


BUILTIN_ACTION_CATALOG = ActionCatalog(
    (
        ActionDefinition(
            name="TaskLatticeCustomerIdentifierAction",
            version="1.0.0",
            input_schema=(("text", "string"),),
            output_schema=(("detected", "boolean"), ("redacted", "string")),
            supported_rails=("input", "output"),
            timeout_ms=100,
            failure_mode="fail_closed",
            side_effects=False,
            concurrent=True,
        ),
        ActionDefinition(
            name="TaskLatticeRecordControlAction",
            version="1.0.0",
            input_schema=(
                ("binding_id", "string"),
                ("safe", "boolean"),
                ("text", "string"),
                ("replacement", "string|null"),
            ),
            output_schema=(("verdict", "string"),),
            supported_rails=("input", "output"),
            timeout_ms=100,
            failure_mode="fail_closed",
            side_effects=False,
            concurrent=True,
        ),
    )
)
