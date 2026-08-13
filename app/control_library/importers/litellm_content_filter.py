from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from ..acceptance import attach_test_suites
from ..domain import (
    ControlLibraryBundle,
    ControlLibrarySource,
    ControlPackSpec,
    ControlSpec,
    KeywordSpec,
    ParameterSpec,
    RuleSpec,
)
from ..matching import severity_applies
from ...runtime.contracts import GuardrailPhase


def import_bundle() -> ControlLibraryBundle:
    root = _vendor_root()
    manifest = _read_json(root / "SOURCE.json")
    version = str(manifest["version"])
    patterns_data = _read_json(root / "patterns.json")
    prebuilt_patterns = {
        item["name"]: item for item in patterns_data["patterns"]
    }

    controls: dict[str, ControlSpec] = {}
    packs: list[ControlPackSpec] = []
    for raw_pack in _read_json(root / "policy_templates.json"):
        raw_controls = raw_pack.get("guardrailDefinitions", [])
        if not raw_controls or any(
            item.get("litellm_params", {}).get("guardrail")
            != "litellm_content_filter"
            for item in raw_controls
        ):
            continue

        control_ids: list[str] = []
        for raw_control in raw_controls:
            control = _translate_control(
                raw_control,
                version=version,
                prebuilt_patterns=prebuilt_patterns,
                resource_root=root,
            )
            previous = controls.get(control.id)
            if previous is not None and previous != control:
                raise RuntimeError(
                    f"Imported Control {control.id!r} has conflicting definitions."
                )
            controls[control.id] = control
            control_ids.append(control.id)

        parameters = [
            ParameterSpec(
                name=item["name"],
                label=item.get("label", display_name(item["name"])),
                kind=item.get("type", "text"),
                required=bool(item.get("required", False)),
                placeholder=item.get("placeholder", ""),
            )
            for item in raw_pack.get("parameters", [])
        ]
        if raw_pack.get("llm_enrichment"):
            parameters.append(
                ParameterSpec(
                    name="competitors",
                    label="Competitors",
                    kind="textarea",
                    required=True,
                    placeholder="One competitor per line",
                    description=(
                        "Paste the reviewed competitor set used by this Control Pack."
                    ),
                )
            )

        packs.append(
            ControlPackSpec(
                id=raw_pack["id"],
                name=raw_pack["title"],
                description=raw_pack["description"],
                source="built_in",
                version=version,
                control_ids=tuple(control_ids),
                parameters=tuple(parameters),
                examples=tuple(raw_pack.get("example_sentences", [])),
            )
        )

    controls = attach_test_suites(
        controls,
        asset_path=Path(__file__).resolve().parents[1]
        / "assets"
        / "builtin_control_tests.json",
    )

    return ControlLibraryBundle(
        id="litellm-content-filter",
        source=ControlLibrarySource(
            name=str(manifest["name"]),
            version=version,
            commit=str(manifest["commit"]),
            license=str(manifest["license"]),
            url=str(manifest["source"]),
        ),
        controls=tuple(
            sorted(controls.values(), key=lambda item: (item.name.casefold(), item.id))
        ),
        packs=tuple(packs),
    )


def _translate_control(
    raw_control: dict[str, Any],
    *,
    version: str,
    prebuilt_patterns: dict[str, dict[str, Any]],
    resource_root: Path,
) -> ControlSpec:
    control_id = raw_control["guardrail_name"]
    params = raw_control["litellm_params"]
    phase = _phase(params.get("mode"))
    redaction_format = params.get(
        "pattern_redaction_format", "[{pattern_name}_REDACTED]"
    )
    rules: list[RuleSpec] = []

    for item in params.get("patterns", []):
        if item.get("pattern_type") == "prebuilt":
            prebuilt = prebuilt_patterns[item["pattern_name"]]
            rule_id = item["pattern_name"]
            expression = prebuilt["pattern"]
            context_expression = prebuilt.get("keyword_pattern")
            name = prebuilt.get("display_name", display_name(rule_id))
            description = prebuilt.get("description", "")
        else:
            rule_id = item.get("name", "custom_regex")
            expression = item["pattern"]
            context_expression = None
            name = display_name(rule_id)
            description = "Custom regular-expression rule."
        rules.append(
            RuleSpec(
                id=rule_id,
                name=name,
                detector="regex",
                action=item.get("action", "BLOCK"),
                phases=(phase,),
                description=description,
                expression=expression,
                context_expression=context_expression,
                redaction=redaction_format.replace("{pattern_name}", rule_id),
            )
        )

    raw_words = params.get("blocked_words", [])
    if isinstance(raw_words, str):
        parameter = raw_words.strip("{}")
        rules.append(
            RuleSpec(
                id=f"dynamic-{parameter.replace('_', '-')}",
                name=display_name(parameter),
                detector="keyword",
                action="BLOCK",
                phases=(phase,),
                description="Resolved from reviewed Control Pack parameters.",
                keywords=(KeywordSpec(raw_words),),
            )
        )
    else:
        for index, item in enumerate(raw_words, start=1):
            rules.append(
                RuleSpec(
                    id=f"blocked-word-{index}",
                    name=item["keyword"],
                    detector="keyword",
                    action=item.get("action", "BLOCK"),
                    phases=(phase,),
                    description=item.get(
                        "description", "Blocked phrase detected"
                    ),
                    keywords=(KeywordSpec(item["keyword"]),),
                )
            )

    rules.extend(
        _load_category(resource_root, item, phase=phase)
        for item in params.get("categories", [])
        if item.get("enabled", True)
    )
    rules.extend(_tasklattice_rules(control_id, phase=phase))
    return ControlSpec(
        id=control_id,
        name=display_name(control_id),
        description=raw_control.get("guardrail_info", {}).get(
            "description", "Built-in content-filter Control."
        ),
        source="built_in",
        version=version,
        rules=tuple(rules),
    )


def _tasklattice_rules(
    control_id: str,
    *,
    phase: GuardrailPhase,
) -> tuple[RuleSpec, ...]:
    if control_id != "competitor-comparison-input-filter":
        return ()
    return (
        RuleSpec(
            id="competitor-comparison-intent",
            name="Competitor comparison intent",
            detector="category",
            action="BLOCK",
            phases=(phase,),
            description=(
                "Blocks airline ranking, comparison, recommendation, and switching "
                "requests while allowing destination and service-policy questions."
            ),
            identifiers=("airline", "airlines", "airways", "carrier", "carriers"),
            conditions=("better", "best", "ranked", "number one", "compare", "switch"),
            phrase_patterns=(
                r"\bcompare\b.{0,80}\b(?:airlines?|airways|carriers?|vs\.?)\b",
                r"\b(?:airlines?|airways|carriers?)\b.{0,80}\b(?:better|best|ranked|number\s+one|versus|vs\.?)\b",
                r"\b(?:better|best|ranked|number\s+one)\b.{0,80}\b(?:airlines?|airways|carriers?|business\s+class|lounges?|customer\s+satisfaction)\b",
                r"\bshould\s+i\s+(?:choose|switch)\b.{0,80}\b(?:airlines?|airways|carriers?|qatar|singapore|turkish|lufthansa)\b",
                r"\bdoha\s+airline\b.{0,40}\bbetter\s+than\b",
            ),
        ),
    )


def _load_category(
    root: Path,
    config: dict[str, Any],
    *,
    phase: GuardrailPhase,
) -> RuleSpec:
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
        return _inline_category(name, config, phase=phase)

    if path.suffix == ".json":
        entries = _read_json(path)
        severity_map = {4: "high", 3: "high", 2: "medium", 1: "low"}
        keywords: list[KeywordSpec] = []
        seen: set[str] = set()
        for item in entries:
            severity = severity_map.get(item.get("severity", 2), "medium")
            for phrase in item.get("match", "").split("|"):
                normalized = phrase.strip().lower()
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    keywords.append(KeywordSpec(normalized, severity))
        data: dict[str, Any] = {}
    else:
        data = yaml.safe_load(path.read_text()) or {}
        keywords = [
            KeywordSpec(
                item["keyword"].lower(), item.get("severity", "medium")
            )
            for item in data.get("keywords", [])
        ]

    conditions = list(data.get("additional_block_words", []))
    inherited = data.get("inherit_from")
    if inherited:
        inherited_path = root / "categories" / inherited
        if inherited_path.suffix == ".json":
            for item in _read_json(inherited_path):
                if severity_applies(
                    {4: "high", 3: "high", 2: "medium", 1: "low"}.get(
                        item.get("severity", 2), "medium"
                    ),
                    config.get("severity_threshold", "medium"),
                ):
                    conditions.extend(item.get("match", "").split("|"))

    return RuleSpec(
        id=name,
        name=display_name(name),
        detector="category",
        action=config.get("action") or data.get("default_action", "BLOCK"),
        phases=(phase,),
        description=data.get("description", ""),
        severity_threshold=config.get("severity_threshold", "medium"),
        identifiers=tuple(
            item.lower() for item in data.get("identifier_words", [])
        ),
        conditions=tuple(item.lower() for item in conditions if item),
        keywords=tuple(keywords),
        always_block=tuple(
            KeywordSpec(
                item["keyword"].lower(), item.get("severity", "high")
            )
            for item in data.get("always_block_keywords", [])
        ),
        exceptions=tuple(item.lower() for item in data.get("exceptions", [])),
        phrase_patterns=tuple(data.get("phrase_patterns", [])),
    )


def _inline_category(
    name: str,
    config: dict[str, Any],
    *,
    phase: GuardrailPhase,
) -> RuleSpec:
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
        raise RuntimeError(f"Category resource {name!r} was not packaged.")
    return RuleSpec(
        id=name,
        name=display_name(name),
        detector="category",
        action=config.get("action", "BLOCK"),
        phases=(phase,),
        description="Inline keyword category bundled with this Control Library.",
        severity_threshold=config.get("severity_threshold", "medium"),
        keywords=tuple(KeywordSpec(keyword) for keyword in keywords),
    )


def display_name(value: str) -> str:
    acronyms = {
        "ai", "api", "au", "dnc", "eu", "fin", "gdpr", "ip", "llm",
        "mas", "nric", "nsfw", "owasp", "pdpa", "pii", "sg", "sql",
        "uae", "uen", "url",
    }
    return " ".join(
        token.upper() if token.lower() in acronyms else token.capitalize()
        for token in re.split(r"[-_]+", value)
        if token
    )


def _phase(mode: str | None) -> GuardrailPhase:
    return "output" if mode == "post_call" else "input"


def _vendor_root() -> Path:
    return Path(__file__).resolve().parents[2] / "vendor" / "litellm_content_filter"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text())
