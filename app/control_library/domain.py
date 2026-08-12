from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..runtime.contracts import GuardrailPhase, OutputDeliveryMode, SafetyLevel


DetectorType = Literal["regex", "keyword", "category"]


@dataclass(frozen=True, slots=True)
class KeywordSpec:
    value: str
    severity: str = "medium"


@dataclass(frozen=True, slots=True)
class RuleSpec:
    id: str
    name: str
    detector: DetectorType
    action: str
    phases: tuple[GuardrailPhase, ...]
    description: str = ""
    expression: str | None = None
    context_expression: str | None = None
    redaction: str | None = None
    severity_threshold: str | None = None
    identifiers: tuple[str, ...] = ()
    conditions: tuple[str, ...] = ()
    keywords: tuple[KeywordSpec, ...] = ()
    always_block: tuple[KeywordSpec, ...] = ()
    exceptions: tuple[str, ...] = ()
    phrase_patterns: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ParameterSpec:
    name: str
    label: str
    kind: str
    required: bool
    placeholder: str
    description: str = ""


@dataclass(frozen=True, slots=True)
class ControlSpec:
    id: str
    name: str
    description: str
    source: Literal["built_in"]
    version: str
    rules: tuple[RuleSpec, ...]

    @property
    def phases(self) -> tuple[GuardrailPhase, ...]:
        configured = {phase for rule in self.rules for phase in rule.phases}
        return tuple(
            phase for phase in ("input", "output") if phase in configured
        )

    @property
    def detector_types(self) -> tuple[DetectorType, ...]:
        configured = {rule.detector for rule in self.rules}
        return tuple(
            detector
            for detector in ("regex", "keyword", "category")
            if detector in configured
        )

    @property
    def allowed_actions(self) -> tuple[str, ...]:
        configured = {rule.action for rule in self.rules}
        preferred = ("MASK", "BLOCK")
        return tuple(action for action in preferred if action in configured) + tuple(
            sorted(configured.difference(preferred))
        )

    @property
    def default_action(self) -> str:
        return self.allowed_actions[0] if len(self.allowed_actions) == 1 else "POLICY"


@dataclass(frozen=True, slots=True)
class ControlPackSpec:
    id: str
    name: str
    description: str
    source: str
    version: str
    control_ids: tuple[str, ...]
    parameters: tuple[ParameterSpec, ...] = ()
    examples: tuple[str, ...] = ()
    safety_level: SafetyLevel = "balanced"
    output_delivery: OutputDeliveryMode = "window_buffered"


@dataclass(frozen=True, slots=True)
class ControlLibrarySource:
    name: str
    version: str
    commit: str
    license: str
    url: str


@dataclass(frozen=True, slots=True)
class ControlLibraryBundle:
    id: str
    source: ControlLibrarySource
    controls: tuple[ControlSpec, ...]
    packs: tuple[ControlPackSpec, ...]
