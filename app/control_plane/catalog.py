from __future__ import annotations

import re

from ..policy_packs.litellm import policy_pack, policy_templates
from .domain import (
    ControlDefinition,
    ControlTemplate,
    ControlTemplatePackReference,
    ControlTemplateRule,
    GuardrailTemplate,
    TemplateParameterDefinition,
    TemplateControl,
)


CONTROL_DEFINITIONS: tuple[ControlDefinition, ...] = (
    ControlDefinition(
        id="secrets",
        display_name="Secrets & credentials",
        description="Detect API keys, bearer tokens, private keys, and credential-like values.",
        domain="Data protection",
        default_phases=("input", "output"),
        default_action="reject",
        allowed_actions=("reject", "redact"),
        available_stages=("deterministic",),
        limitations=("Only high-confidence structured credentials are detected locally.",),
        module="data_protection",
    ),
    ControlDefinition(
        id="pii",
        display_name="Personal information",
        description="Prevent personal identifiers and customer data from entering or leaving the model boundary.",
        domain="Data protection",
        default_phases=("input", "output"),
        default_action="redact",
        allowed_actions=("redact", "reject", "rewrite"),
        available_stages=("deterministic", "fast_semantic"),
        limitations=("Semantic PII detection requires a configured Fast Semantic evaluator.",),
        module="data_protection",
    ),
    ControlDefinition(
        id="prompt_injection",
        display_name="Prompt injection",
        description="Detect attempts to override instructions, extract prompts, or redirect model behavior.",
        domain="Prompt security",
        default_phases=("input",),
        default_action="reject",
        allowed_actions=("reject", "redirect"),
        available_stages=("fast_semantic", "deep_judge"),
        limitations=("Detection quality depends on evaluator configuration and language coverage.",),
        module="interaction_safety",
    ),
    ControlDefinition(
        id="jailbreak",
        display_name="Jailbreak",
        description="Detect adversarial attempts to bypass safety and policy constraints.",
        domain="Prompt security",
        default_phases=("input",),
        default_action="reject",
        allowed_actions=("reject", "redirect"),
        available_stages=("fast_semantic", "deep_judge"),
        limitations=("Novel attacks may require contextual Deep Judge review.",),
        module="interaction_safety",
    ),
    ControlDefinition(
        id="content_safety",
        display_name="Unsafe content",
        description="Classify harmful, violent, sexual, self-harm, and hateful model interactions.",
        domain="Content safety",
        default_phases=("input", "output"),
        default_action="reject",
        allowed_actions=("reject", "rewrite", "regenerate"),
        available_stages=("fast_semantic",),
        limitations=("Classification is evaluator- and locale-dependent.",),
        module="interaction_safety",
    ),
    ControlDefinition(
        id="topic_control",
        display_name="Topic boundary",
        description="Keep interactions within the declared purpose, allowed topics, and restrictions.",
        domain="Policy compliance",
        default_phases=("input", "output"),
        default_action="redirect",
        allowed_actions=("redirect", "reject", "rewrite"),
        available_stages=("deterministic", "deep_judge"),
        limitations=(
            "Explicit allowed and restricted topics are enforced locally; ambiguous intent requires an optional Deep Judge.",
        ),
        module="business_assurance",
    ),
    ControlDefinition(
        id="company_policy",
        display_name="Organization policy",
        description="Judge interaction compliance against organization-specific safety intent.",
        domain="Policy compliance",
        default_phases=("input", "output"),
        default_action="reject",
        allowed_actions=("reject", "redact", "rewrite", "regenerate"),
        available_stages=("deep_judge",),
        limitations=("Requires a configured Deep Judge and reviewed policy language.",),
        module="business_assurance",
    ),
    ControlDefinition(
        id="contextual_grounding",
        display_name="Contextual grounding",
        description="Check that model output is supported by supplied sources and relevant to the user query.",
        domain="Response assurance",
        default_phases=("output",),
        default_action="regenerate",
        allowed_actions=("regenerate", "rewrite", "reject"),
        available_stages=("deep_judge",),
        limitations=(
            "Requires query, grounding_source, and model_output Content Blocks plus a configured grounding evaluator.",
            "Designed for source-grounded summarization and question answering, not open-domain truth verification.",
        ),
        module="business_assurance",
    ),
    ControlDefinition(
        id="automated_reasoning",
        display_name="Automated reasoning",
        description="Validate complete model responses against a deployed formal policy and return proof-oriented findings.",
        domain="Response assurance",
        default_phases=("output",),
        default_action="rewrite",
        allowed_actions=("rewrite", "reject"),
        available_stages=("deep_judge",),
        limitations=(
            "Requires a deployed immutable policy version and a configured Automated Reasoning provider.",
            "Validation is detection-only, policy-scoped, and requires complete non-streaming output.",
        ),
        module="business_assurance",
    ),
    ControlDefinition(
        id="builtin_content_filter",
        display_name="Built-in content filter policy",
        description="Run a locally bundled LiteLLM content-filter policy without Integration-side templates.",
        domain="Built-in policy",
        default_phases=("input", "output"),
        default_action="reject",
        allowed_actions=("reject",),
        available_stages=("deterministic",),
        limitations=("Coverage is limited to the patterns, keywords, and categories bundled with the selected template version.",),
        module="interaction_safety",
    ),
)


def control(risk: str) -> ControlDefinition:
    return next(item for item in CONTROL_DEFINITIONS if item.id == risk)


def guardrail_template(template_id: str) -> GuardrailTemplate:
    return next(item for item in guardrail_templates() if item.id == template_id)


def guardrail_templates() -> tuple[GuardrailTemplate, ...]:
    return tuple(
        GuardrailTemplate(
            id=item.id,
            name=item.display_name,
            description=item.description,
            purpose=item.description,
            allowed_topics=(),
            restricted_topics=(),
            default_controls=(TemplateControl("builtin_content_filter", "reject"),),
            safety_level="balanced",
            output_delivery="window_buffered",
            source=item.source,
            version=item.version,
            domain=item.catalog.domain,
            collections=item.catalog.collections,
            tags=item.catalog.tags,
            limitations=item.catalog.limitations,
            controls=tuple(control.name for control in item.controls),
            parameters=tuple(
                TemplateParameterDefinition(
                    name=parameter.name,
                    label=parameter.label,
                    kind=parameter.kind,
                    required=parameter.required,
                    placeholder=parameter.placeholder,
                    description=parameter.description,
                )
                for parameter in item.parameters
            ),
        )
        for item in policy_templates()
    )


def control_templates() -> tuple[ControlTemplate, ...]:
    """Expose each vendored executable control as an auditable library resource."""
    pack = policy_pack()
    memberships: dict[str, list[ControlTemplatePackReference]] = {
        name: [] for name in pack.controls
    }
    tags: dict[str, set[str]] = {name: set() for name in pack.controls}
    limitations: dict[str, set[str]] = {name: set() for name in pack.controls}
    presentation = {}

    for policy in pack.templates:
        reference = ControlTemplatePackReference(
            id=policy.id,
            name=policy.display_name,
            domain=policy.catalog.domain,
        )
        for template_control in policy.controls:
            memberships[template_control.name].append(reference)
            tags[template_control.name].update(policy.catalog.tags)
            limitations[template_control.name].update(policy.catalog.limitations)
            presentation.setdefault(template_control.name, template_control)

    resources: list[ControlTemplate] = []
    for name, definition in pack.controls.items():
        template_control = presentation[name]
        rules = _control_template_rules(definition)
        detector_types = tuple(
            detector
            for detector in ("regex", "keyword", "category")
            if any(rule.detector == detector for rule in rules)
        )
        resources.append(
            ControlTemplate(
                id=name,
                name=_control_display_name(name),
                description=definition.description,
                source="LiteLLM OSS · locally built in",
                version=pack.templates[0].version,
                status="built_in",
                phases=(definition.phase,),
                default_action=template_control.default_action,
                allowed_actions=template_control.allowed_actions,
                detector_types=detector_types,
                rules=rules,
                packs=tuple(sorted(memberships[name], key=lambda item: item.name)),
                tags=tuple(sorted(tags[name])),
                limitations=tuple(sorted(limitations[name])),
            )
        )
    return tuple(sorted(resources, key=lambda item: (item.name.lower(), item.id)))


def _control_template_rules(definition) -> tuple[ControlTemplateRule, ...]:
    rules: list[ControlTemplateRule] = []
    for item in definition.patterns:
        rules.append(
            ControlTemplateRule(
                id=item.name,
                name=item.display_name or _control_display_name(item.name),
                detector="regex",
                action=item.action,
                description=item.description,
                expression=item.expression,
                context_expression=item.keyword_expression,
                redaction=item.redaction,
            )
        )

    if isinstance(definition.blocked_words, tuple):
        for index, item in enumerate(definition.blocked_words, start=1):
            rules.append(
                ControlTemplateRule(
                    id=f"blocked-word-{index}",
                    name=item.keyword,
                    detector="keyword",
                    action=item.action,
                    description=item.description,
                    keywords=(item.keyword,),
                )
            )
    elif definition.blocked_words:
        parameter = definition.blocked_words.strip("{}")
        rules.append(
            ControlTemplateRule(
                id=f"dynamic-{parameter.replace('_', '-')}",
                name=_control_display_name(parameter),
                detector="keyword",
                action="BLOCK",
                description="Resolved from reviewed Guardrail template parameters.",
                keywords=(definition.blocked_words,),
            )
        )

    for item in definition.categories:
        rules.append(
            ControlTemplateRule(
                id=item.name,
                name=_control_display_name(item.name),
                detector="category",
                action=item.action,
                description=item.description,
                severity_threshold=item.severity_threshold,
                identifiers=item.identifiers,
                conditions=item.conditional_words,
                keywords=tuple(keyword for keyword, _severity in item.keywords),
                always_block=tuple(keyword for keyword, _severity in item.always_block),
                exceptions=item.exceptions,
                phrase_patterns=item.phrase_patterns,
            )
        )
    return tuple(rules)


_CONTROL_ACRONYMS = {
    "ai",
    "api",
    "au",
    "dnc",
    "eu",
    "fin",
    "gdpr",
    "ip",
    "llm",
    "mas",
    "nric",
    "nsfw",
    "owasp",
    "pdpa",
    "pii",
    "sg",
    "sql",
    "uae",
    "uen",
    "url",
}


def _control_display_name(value: str) -> str:
    return " ".join(
        token.upper() if token.lower() in _CONTROL_ACRONYMS else token.capitalize()
        for token in re.split(r"[-_]+", value)
        if token
    )
