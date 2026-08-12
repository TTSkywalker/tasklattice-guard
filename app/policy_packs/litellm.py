from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from .domain import (
    OWASP_2025_COLLECTION,
    RUNTIME_BASELINE_COLLECTION,
    CatalogMetadata,
    PolicyTemplate,
    TemplateControl,
    TemplateParameter,
)
from ..runtime.contracts import GuardrailPhase


LITELLM_POLICY_PACK_VERSION = "1.95.0"
LITELLM_POLICY_PACK_COMMIT = "ead62528e607b9d8e61273def638799c9c3a69ba"


_FASTPASS_LIMITATIONS = (
    "Keyword and pattern rules may not detect every semantic paraphrase.",
    "Adjacent integration and application security controls remain independently required.",
)


_CATALOG_METADATA: dict[str, CatalogMetadata] = {
    "advanced-au-pii-protection": CatalogMetadata(
        catalog_id="TALI-DP-102",
        collections=("TALI Australia Data Protection", OWASP_2025_COLLECTION),
        domain="Data Protection",
        owasp_risks=("LLM02:2025",),
        stages=("Input", "Output"),
        engine_tiers=("Fastpass",),
        coverage="Runtime enforcement",
        limitations=_FASTPASS_LIMITATIONS,
        tags=("PII Protection", "Australia"),
    ),
    "baseline-pii-protection": CatalogMetadata(
        catalog_id="TALI-DP-001",
        collections=(RUNTIME_BASELINE_COLLECTION, OWASP_2025_COLLECTION),
        domain="Data Protection",
        owasp_risks=("LLM02:2025",),
        stages=("Input", "Output"),
        engine_tiers=("Fastpass",),
        coverage="Runtime enforcement",
        limitations=_FASTPASS_LIMITATIONS,
        tags=("PII Protection",),
    ),
    "nsfw-content-filter-australia": CatalogMetadata(
        catalog_id="TALI-CS-102",
        collections=("TALI Global Content Safety", OWASP_2025_COLLECTION),
        domain="Content Safety",
        owasp_risks=("LLM05:2025",),
        stages=("Input", "Output"),
        engine_tiers=("Fastpass",),
        coverage="Runtime enforcement",
        limitations=_FASTPASS_LIMITATIONS,
        tags=("Content Safety", "Australia"),
    ),
    "nsfw-content-filter-basic": CatalogMetadata(
        catalog_id="TALI-CS-001",
        collections=(RUNTIME_BASELINE_COLLECTION, OWASP_2025_COLLECTION),
        domain="Content Safety",
        owasp_risks=("LLM05:2025",),
        stages=("Input", "Output"),
        engine_tiers=("Fastpass",),
        coverage="Runtime enforcement",
        limitations=_FASTPASS_LIMITATIONS,
        tags=("Content Safety",),
    ),
    "nsfw-content-filter-all-regions": CatalogMetadata(
        catalog_id="TALI-CS-002",
        collections=("TALI Global Content Safety", OWASP_2025_COLLECTION),
        domain="Content Safety",
        owasp_risks=("LLM05:2025",),
        stages=("Input", "Output"),
        engine_tiers=("Fastpass",),
        coverage="Runtime enforcement",
        limitations=_FASTPASS_LIMITATIONS,
        tags=("Content Safety", "Global"),
    ),
    "gdpr-eu-pii-protection": CatalogMetadata(
        catalog_id="TALI-DP-201",
        collections=("TALI EU AI & Data Protection", OWASP_2025_COLLECTION),
        domain="Data Protection",
        owasp_risks=("LLM02:2025",),
        stages=("Input", "Output"),
        engine_tiers=("Fastpass",),
        coverage="Runtime enforcement",
        limitations=(
            "This template covers selected identifiers and is not a complete GDPR compliance program.",
            *_FASTPASS_LIMITATIONS,
        ),
        tags=("PII Protection", "Regulatory", "EU"),
    ),
    "eu-ai-act-article5": CatalogMetadata(
        catalog_id="TALI-GV-201",
        collections=("TALI EU AI & Data Protection",),
        domain="Content Safety",
        owasp_risks=("LLM05:2025", "LLM09:2025"),
        stages=("Input", "Output"),
        engine_tiers=("Fastpass",),
        coverage="Shared responsibility",
        limitations=(
            "Runtime keyword controls cover selected prohibited-practice indicators only.",
            "Legal assessment and system-level governance remain outside this template.",
        ),
        tags=("Regulatory", "EU"),
    ),
    "mcp-security-unregistered-server-block": CatalogMetadata(
        catalog_id="TALI-AS-001",
        collections=("TALI Agent & Tool Security", OWASP_2025_COLLECTION),
        domain="Agent & Tool Security",
        owasp_risks=("LLM06:2025",),
        stages=("Execution",),
        engine_tiers=("Integration Adapter",),
        coverage="Integration-assisted",
        limitations=(
            "Requires trusted MCP registration metadata from the AI Integration.",
            "Tool authorization must still be enforced by the target service.",
        ),
        tags=("MCP", "Tool Calling"),
    ),
    "airline-passenger-data-protection-uae": CatalogMetadata(
        catalog_id="TALI-DP-301",
        collections=("TALI Aviation Safety", "TALI UAE Data & Culture", OWASP_2025_COLLECTION),
        domain="Data Protection",
        owasp_risks=("LLM02:2025",),
        stages=("Input", "Output"),
        engine_tiers=("Fastpass",),
        coverage="Runtime enforcement",
        limitations=_FASTPASS_LIMITATIONS,
        tags=("PII Protection", "Aviation", "UAE"),
    ),
    "aviation-operations-security": CatalogMetadata(
        catalog_id="TALI-PS-301",
        collections=("TALI Aviation Safety", OWASP_2025_COLLECTION),
        domain="Prompt & Interaction Security",
        owasp_risks=("LLM02:2025", "LLM05:2025", "LLM07:2025"),
        stages=("Input", "Output"),
        engine_tiers=("Fastpass",),
        coverage="Runtime enforcement",
        limitations=_FASTPASS_LIMITATIONS,
        tags=("Aviation", "Security", "Brand Protection"),
    ),
    "airline-off-topic-restriction": CatalogMetadata(
        catalog_id="TALI-PS-302",
        collections=("TALI Aviation Safety",),
        domain="Prompt & Interaction Security",
        owasp_risks=(),
        stages=("Input",),
        engine_tiers=("Fastpass",),
        coverage="Runtime enforcement",
        limitations=_FASTPASS_LIMITATIONS,
        tags=("Aviation", "Topic Control"),
    ),
    "uae-regulatory-compliance": CatalogMetadata(
        catalog_id="TALI-DP-302",
        collections=("TALI UAE Data & Culture", OWASP_2025_COLLECTION),
        domain="Data Protection",
        owasp_risks=("LLM02:2025", "LLM05:2025"),
        stages=("Input", "Output"),
        engine_tiers=("Fastpass",),
        coverage="Shared responsibility",
        limitations=(
            "This template is a runtime control, not a legal compliance determination.",
            *_FASTPASS_LIMITATIONS,
        ),
        tags=("Regulatory", "UAE"),
    ),
    "competitor-mention-detection": CatalogMetadata(
        catalog_id="TALI-PS-401",
        collections=("TALI Brand Protection",),
        domain="Prompt & Interaction Security",
        owasp_risks=(),
        stages=("Input", "Output"),
        engine_tiers=("Fastpass",),
        coverage="Runtime enforcement",
        limitations=(
            "The reviewed competitor list must be supplied when the Policy is created.",
            *_FASTPASS_LIMITATIONS,
        ),
        tags=("Brand Protection",),
    ),
    "topic-filtering": CatalogMetadata(
        catalog_id="TALI-PS-001",
        collections=(RUNTIME_BASELINE_COLLECTION,),
        domain="Prompt & Interaction Security",
        owasp_risks=(),
        stages=("Input",),
        engine_tiers=("Fastpass",),
        coverage="Runtime enforcement",
        limitations=_FASTPASS_LIMITATIONS,
        tags=("Topic Control",),
    ),
    "prompt-injection-protection": CatalogMetadata(
        catalog_id="TALI-PI-001",
        collections=(RUNTIME_BASELINE_COLLECTION, OWASP_2025_COLLECTION),
        domain="Prompt & Interaction Security",
        owasp_risks=("LLM01:2025", "LLM07:2025"),
        stages=("Input",),
        engine_tiers=("Fastpass",),
        coverage="Runtime enforcement",
        limitations=(
            "Pattern detection is a first-pass defense and should be paired with semantic jailbreak detection.",
            "Indirect injection requires retrieved content to be supplied for inspection.",
        ),
        tags=("Security", "Injection Protection"),
    ),
    "pdpa-singapore": CatalogMetadata(
        catalog_id="TALI-DP-202",
        collections=("TALI Singapore Data & AI Compliance", OWASP_2025_COLLECTION),
        domain="Data Protection",
        owasp_risks=("LLM02:2025",),
        stages=("Input", "Output"),
        engine_tiers=("Fastpass",),
        coverage="Shared responsibility",
        limitations=(
            "This template covers selected PDPA indicators and is not a complete compliance program.",
            *_FASTPASS_LIMITATIONS,
        ),
        tags=("PII Protection", "Regulatory", "Singapore"),
    ),
    "mas-ai-risk-management": CatalogMetadata(
        catalog_id="TALI-GV-202",
        collections=("TALI Singapore Data & AI Compliance", OWASP_2025_COLLECTION),
        domain="Platform & Consumption Security",
        owasp_risks=("LLM04:2025", "LLM06:2025", "LLM09:2025"),
        stages=("Input", "Output"),
        engine_tiers=("Fastpass",),
        coverage="Shared responsibility",
        limitations=(
            "Runtime checks do not validate training data, model provenance, or human governance processes.",
            *_FASTPASS_LIMITATIONS,
        ),
        tags=("Financial Services", "Regulatory", "Singapore"),
    ),
    "claims-agent-safety": CatalogMetadata(
        catalog_id="TALI-CS-301",
        collections=("TALI Healthcare Claims Safety", OWASP_2025_COLLECTION),
        domain="Content Safety",
        owasp_risks=("LLM01:2025", "LLM02:2025", "LLM05:2025", "LLM07:2025"),
        stages=("Input", "Output"),
        engine_tiers=("Fastpass",),
        coverage="Runtime enforcement",
        limitations=(
            "This template is scoped to claims conversations and is not clinical decision support.",
            *_FASTPASS_LIMITATIONS,
        ),
        tags=("Healthcare", "Claims", "Content Safety"),
    ),
}


@dataclass(frozen=True, slots=True)
class PatternRule:
    name: str
    expression: str
    action: str
    redaction: str
    keyword_expression: str | None = None
    display_name: str = ""
    description: str = ""


@dataclass(frozen=True, slots=True)
class BlockedWordRule:
    keyword: str
    action: str
    description: str


@dataclass(frozen=True, slots=True)
class CategoryRule:
    name: str
    action: str
    severity_threshold: str
    keywords: tuple[tuple[str, str], ...]
    exceptions: tuple[str, ...]
    identifiers: tuple[str, ...]
    conditional_words: tuple[str, ...]
    always_block: tuple[tuple[str, str], ...]
    phrase_patterns: tuple[str, ...]
    description: str = ""


@dataclass(frozen=True, slots=True)
class ContentControlDefinition:
    name: str
    description: str
    phase: GuardrailPhase
    patterns: tuple[PatternRule, ...]
    blocked_words: tuple[BlockedWordRule, ...] | str
    categories: tuple[CategoryRule, ...]


@dataclass(frozen=True, slots=True)
class PolicyPack:
    templates: tuple[PolicyTemplate, ...]
    controls: dict[str, ContentControlDefinition]


def policy_templates() -> tuple[PolicyTemplate, ...]:
    return policy_pack().templates


def policy_template(template_id: str) -> PolicyTemplate:
    return next(item for item in policy_pack().templates if item.id == template_id)


def control_definition(name: str) -> ContentControlDefinition | None:
    return policy_pack().controls.get(name)


@lru_cache(maxsize=1)
def policy_pack() -> PolicyPack:
    root = _builtin_root()
    templates_data = _read_json(root / "policy_templates.json")
    patterns_data = _read_json(root / "patterns.json")
    prebuilt_patterns = {
        item["name"]: item for item in patterns_data["patterns"]
    }
    category_root = root

    controls: dict[str, ContentControlDefinition] = {}
    templates: list[PolicyTemplate] = []
    for raw_template in templates_data:
        raw_controls = raw_template.get("guardrailDefinitions", [])
        if not raw_controls or any(
            item.get("litellm_params", {}).get("guardrail")
            != "litellm_content_filter"
            for item in raw_controls
        ):
            continue
        catalog = _CATALOG_METADATA.get(raw_template["id"])
        if catalog is None:
            raise RuntimeError(
                f"LiteLLM template {raw_template['id']!r} has no TALI catalog metadata."
            )
        translated_controls: list[TemplateControl] = []
        provider_supported = True
        for raw_control in raw_controls:
            params = raw_control.get("litellm_params", {})
            provider = params.get("guardrail")
            if provider != "litellm_content_filter":
                provider_supported = False
                translated_controls.append(
                    TemplateControl(
                        name=raw_control["guardrail_name"],
                        display_name=_display_name(raw_control["guardrail_name"]),
                        description=raw_control.get("guardrail_info", {}).get(
                            "description", "Integration metadata policy."
                        ),
                        default_enabled=True,
                        default_action="BLOCK",
                        allowed_actions=("BLOCK",),
                        phases=(_phase(params.get("mode")),),
                    )
                )
                continue

            definition = _translate_control(
                raw_control,
                prebuilt_patterns=prebuilt_patterns,
                category_root=category_root,
            )
            previous = controls.get(definition.name)
            if previous is not None and previous != definition:
                raise RuntimeError(
                    f"LiteLLM control {definition.name!r} has conflicting definitions."
                )
            controls[definition.name] = definition
            actions = _control_actions(definition)
            default_action = next(iter(actions)) if len(actions) == 1 else "POLICY"
            translated_controls.append(
                TemplateControl(
                    name=definition.name,
                    display_name=_display_name(definition.name),
                    description=definition.description,
                    default_enabled=True,
                    default_action=default_action,
                    allowed_actions=("POLICY", "MASK", "BLOCK"),
                    phases=(definition.phase,),
                )
            )

        parameters = [
            TemplateParameter(
                name=item["name"],
                label=item.get("label", _display_name(item["name"])),
                kind=item.get("type", "text"),
                required=bool(item.get("required", False)),
                placeholder=item.get("placeholder", ""),
            )
            for item in raw_template.get("parameters", [])
        ]
        if raw_template.get("llm_enrichment"):
            parameters.append(
                TemplateParameter(
                    name="competitors",
                    label="Competitors",
                    kind="textarea",
                    required=True,
                    placeholder="One competitor per line",
                    description=(
                        "The standalone service does not call a control-plane LLM. "
                        "Paste the reviewed competitor set used by this policy."
                    ),
                )
            )

        latency = int(raw_template.get("estimated_latency_ms", 1))
        templates.append(
            PolicyTemplate(
                id=raw_template["id"],
                display_name=raw_template["title"],
                description=raw_template["description"],
                source="LiteLLM OSS · locally built in",
                version=LITELLM_POLICY_PACK_VERSION,
                complexity=raw_template.get("complexity", "Low"),
                catalog=catalog,
                estimated_latency=f"~ {latency} ms",
                controls=tuple(translated_controls),
                examples=tuple(raw_template.get("example_sentences", [])),
                parameters=tuple(parameters),
                available=provider_supported,
                unavailable_reason=(
                    None
                    if provider_supported
                    else "Requires an MCP integration-metadata Adapter; model text is insufficient."
                ),
            )
        )

    return PolicyPack(templates=tuple(templates), controls=controls)


def _translate_control(
    raw_control: dict[str, Any],
    *,
    prebuilt_patterns: dict[str, dict[str, Any]],
    category_root: Path,
) -> ContentControlDefinition:
    params = raw_control["litellm_params"]
    redaction_format = params.get(
        "pattern_redaction_format", "[{pattern_name}_REDACTED]"
    )
    patterns: list[PatternRule] = []
    for item in params.get("patterns", []):
        if item.get("pattern_type") == "prebuilt":
            prebuilt = prebuilt_patterns[item["pattern_name"]]
            expression = prebuilt["pattern"]
            name = item["pattern_name"]
            keyword_expression = prebuilt.get("keyword_pattern")
        else:
            expression = item["pattern"]
            name = item.get("name", "custom_regex")
            keyword_expression = None
        patterns.append(
            PatternRule(
                name=name,
                expression=expression,
                action=item.get("action", "BLOCK"),
                redaction=redaction_format.replace("{pattern_name}", name),
                keyword_expression=keyword_expression,
                display_name=prebuilt.get("display_name", _display_name(name))
                if item.get("pattern_type") == "prebuilt"
                else _display_name(name),
                description=prebuilt.get("description", "")
                if item.get("pattern_type") == "prebuilt"
                else "Custom regular-expression rule.",
            )
        )

    raw_words = params.get("blocked_words", [])
    if isinstance(raw_words, str):
        blocked_words: tuple[BlockedWordRule, ...] | str = raw_words
    else:
        blocked_words = tuple(
            BlockedWordRule(
                keyword=item["keyword"],
                action=item.get("action", "BLOCK"),
                description=item.get("description", "Blocked phrase detected"),
            )
            for item in raw_words
        )

    categories = tuple(
        _load_category(category_root, item)
        for item in params.get("categories", [])
        if item.get("enabled", True)
    )
    return ContentControlDefinition(
        name=raw_control["guardrail_name"],
        description=raw_control.get("guardrail_info", {}).get(
            "description", "LiteLLM content-filter control."
        ),
        phase=_phase(params.get("mode")),
        patterns=tuple(patterns),
        blocked_words=blocked_words,
        categories=categories,
    )


def _load_category(root: Path, config: dict[str, Any]) -> CategoryRule:
    name = config["category"]
    explicit = config.get("category_file")
    candidates: list[Path] = []
    if explicit:
        candidates.append(root / "policy_templates" / Path(explicit).name)
    candidates.extend(
        (
            root / "categories" / f"{name}.yaml",
            root / "categories" / f"{name}.json",
            root / "policy_templates" / f"{name}.yaml",
        )
    )
    path = next((candidate for candidate in candidates if candidate.is_file()), None)
    if path is None:
        return _inline_category(name, config)

    if path.suffix == ".json":
        entries = _read_json(path)
        severity_map = {4: "high", 3: "high", 2: "medium", 1: "low"}
        keywords: list[tuple[str, str]] = []
        seen: set[str] = set()
        for item in entries:
            severity = severity_map.get(item.get("severity", 2), "medium")
            for phrase in item.get("match", "").split("|"):
                normalized = phrase.strip().lower()
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    keywords.append((normalized, severity))
        data: dict[str, Any] = {}
    else:
        data = yaml.safe_load(path.read_text()) or {}
        keywords = tuple(
            (item["keyword"].lower(), item.get("severity", "medium"))
            for item in data.get("keywords", [])
        )

    conditional_words = list(data.get("additional_block_words", []))
    inherited = data.get("inherit_from")
    if inherited:
        inherited_path = root / "categories" / inherited
        if inherited_path.suffix == ".json":
            for item in _read_json(inherited_path):
                if _severity_applies(
                    {4: "high", 3: "high", 2: "medium", 1: "low"}.get(
                        item.get("severity", 2), "medium"
                    ),
                    config.get("severity_threshold", "medium"),
                ):
                    conditional_words.extend(item.get("match", "").split("|"))

    return CategoryRule(
        name=name,
        action=config.get("action") or data.get("default_action", "BLOCK"),
        severity_threshold=config.get("severity_threshold", "medium"),
        keywords=tuple(keywords),
        exceptions=tuple(item.lower() for item in data.get("exceptions", [])),
        identifiers=tuple(item.lower() for item in data.get("identifier_words", [])),
        conditional_words=tuple(item.lower() for item in conditional_words if item),
        always_block=tuple(
            (item["keyword"].lower(), item.get("severity", "high"))
            for item in data.get("always_block_keywords", [])
        ),
        phrase_patterns=tuple(data.get("phrase_patterns", [])),
        description=data.get("description", ""),
    )


def _control_actions(definition: ContentControlDefinition) -> set[str]:
    actions = {item.action for item in definition.patterns}
    if isinstance(definition.blocked_words, tuple):
        actions.update(item.action for item in definition.blocked_words)
    actions.update(item.action for item in definition.categories)
    return actions or {"BLOCK"}


def _inline_category(name: str, config: dict[str, Any]) -> CategoryRule:
    """Definitions referenced by LiteLLM 1.95.0 but absent from its wheel."""
    definitions = {
        "off_topic": (
            "latest news",
            "weather forecast",
            "stock price",
            "tell me a joke",
            "movie recommendation",
            "sports score",
            "political campaign",
            "celebrity gossip",
            "cryptocurrency advice",
        ),
        "airline_off_topic_restriction": (
            "write source code",
            "medical diagnosis",
            "legal advice",
            "investment advice",
            "political campaign",
            "cryptocurrency trading",
            "weapon instructions",
            "explicit adult content",
            "celebrity gossip",
        ),
    }
    keywords = definitions.get(name)
    if keywords is None:
        raise RuntimeError(f"LiteLLM category resource {name!r} was not packaged.")
    return CategoryRule(
        name=name,
        action=config.get("action", "BLOCK"),
        severity_threshold=config.get("severity_threshold", "medium"),
        keywords=tuple((keyword, "medium") for keyword in keywords),
        exceptions=(),
        identifiers=(),
        conditional_words=(),
        always_block=(),
        phrase_patterns=(),
        description="Inline keyword category bundled with the local policy pack.",
    )


def _phase(mode: str | None) -> GuardrailPhase:
    return "output" if mode == "post_call" else "input"


def _display_name(value: str) -> str:
    return value.replace("-", " ").replace("_", " ").title()


def _builtin_root() -> Path:
    return Path(__file__).resolve().parent / "builtin" / "litellm_content_filter"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def _severity_applies(severity: str, threshold: str) -> bool:
    order = {"low": 0, "medium": 1, "high": 2}
    return order.get(severity, 0) >= order.get(threshold, 1)


def keyword_expression(keyword: str) -> str:
    escaped = re.escape(keyword).replace(r"\*", ".?")
    return escaped if " " in keyword else rf"\b{escaped}\b"


def severity_applies(severity: str, threshold: str) -> bool:
    return _severity_applies(severity, threshold)
