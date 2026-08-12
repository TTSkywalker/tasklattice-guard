from __future__ import annotations

from dataclasses import dataclass

from ..runtime.contracts import GuardrailPhase


OWASP_2025_COLLECTION = "OWASP Top 10 for LLM Applications 2025"
RUNTIME_BASELINE_COLLECTION = "TALI Runtime Baseline"


@dataclass(frozen=True, slots=True)
class CatalogMetadata:
    catalog_id: str
    collections: tuple[str, ...]
    domain: str
    owasp_risks: tuple[str, ...]
    stages: tuple[str, ...]
    engine_tiers: tuple[str, ...]
    coverage: str
    limitations: tuple[str, ...]
    tags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TemplateControl:
    name: str
    display_name: str
    description: str
    default_enabled: bool
    default_action: str
    allowed_actions: tuple[str, ...]
    phases: tuple[GuardrailPhase, ...]


@dataclass(frozen=True, slots=True)
class TemplateParameter:
    name: str
    label: str
    kind: str
    required: bool
    placeholder: str
    description: str = ""


@dataclass(frozen=True, slots=True)
class PolicyTemplate:
    id: str
    display_name: str
    description: str
    source: str
    version: str
    complexity: str
    catalog: CatalogMetadata
    estimated_latency: str
    controls: tuple[TemplateControl, ...]
    examples: tuple[str, ...]
    parameters: tuple[TemplateParameter, ...]
    available: bool
    unavailable_reason: str | None
