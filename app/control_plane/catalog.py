from __future__ import annotations

from ..policy_packs.litellm import policy_templates
from .domain import (
    ProtectionDefinition,
    SafetyTemplate,
    TemplateParameterDefinition,
    TemplateRisk,
)


PROTECTIONS: tuple[ProtectionDefinition, ...] = (
    ProtectionDefinition(
        id="secrets",
        display_name="Secrets & credentials",
        description="Detect API keys, bearer tokens, private keys, and credential-like values.",
        domain="Data protection",
        default_phases=("input", "output"),
        default_action="reject",
        allowed_actions=("reject", "redact"),
        available_stages=("deterministic",),
        limitations=("Only high-confidence structured credentials are detected locally.",),
    ),
    ProtectionDefinition(
        id="pii",
        display_name="Personal information",
        description="Prevent personal identifiers and customer data from entering or leaving the model boundary.",
        domain="Data protection",
        default_phases=("input", "output"),
        default_action="redact",
        allowed_actions=("redact", "reject", "rewrite"),
        available_stages=("deterministic", "fast_semantic"),
        limitations=("Semantic PII detection requires a configured Fast Semantic evaluator.",),
    ),
    ProtectionDefinition(
        id="prompt_injection",
        display_name="Prompt injection",
        description="Detect attempts to override instructions, extract prompts, or redirect model behavior.",
        domain="Prompt security",
        default_phases=("input",),
        default_action="reject",
        allowed_actions=("reject", "redirect"),
        available_stages=("fast_semantic", "deep_judge"),
        limitations=("Detection quality depends on evaluator configuration and language coverage.",),
    ),
    ProtectionDefinition(
        id="jailbreak",
        display_name="Jailbreak",
        description="Detect adversarial attempts to bypass safety and policy constraints.",
        domain="Prompt security",
        default_phases=("input",),
        default_action="reject",
        allowed_actions=("reject", "redirect"),
        available_stages=("fast_semantic", "deep_judge"),
        limitations=("Novel attacks may require contextual Deep Judge review.",),
    ),
    ProtectionDefinition(
        id="content_safety",
        display_name="Unsafe content",
        description="Classify harmful, violent, sexual, self-harm, and hateful model interactions.",
        domain="Content safety",
        default_phases=("input", "output"),
        default_action="reject",
        allowed_actions=("reject", "rewrite", "regenerate"),
        available_stages=("fast_semantic",),
        limitations=("Classification is evaluator- and locale-dependent.",),
    ),
    ProtectionDefinition(
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
    ),
    ProtectionDefinition(
        id="company_policy",
        display_name="Organization policy",
        description="Judge interaction compliance against organization-specific safety intent.",
        domain="Policy compliance",
        default_phases=("input", "output"),
        default_action="reject",
        allowed_actions=("reject", "redact", "rewrite", "regenerate"),
        available_stages=("deep_judge",),
        limitations=("Requires a configured Deep Judge and reviewed policy language.",),
    ),
    ProtectionDefinition(
        id="builtin_content_filter",
        display_name="Built-in content filter policy",
        description="Run a locally bundled LiteLLM content-filter policy without Gateway-side templates.",
        domain="Built-in policy",
        default_phases=("input", "output"),
        default_action="reject",
        allowed_actions=("reject",),
        available_stages=("deterministic",),
        limitations=("Coverage is limited to the patterns, keywords, and categories bundled with the selected template version.",),
    ),
)


def protection(risk: str) -> ProtectionDefinition:
    return next(item for item in PROTECTIONS if item.id == risk)


def safety_template(template_id: str) -> SafetyTemplate:
    return next(item for item in safety_templates() if item.id == template_id)


def safety_templates() -> tuple[SafetyTemplate, ...]:
    return tuple(
        SafetyTemplate(
            id=item.id,
            name=item.display_name,
            description=item.description,
            purpose=item.description,
            allowed_topics=(),
            restricted_topics=(),
            risks=(TemplateRisk("builtin_content_filter", "reject"),),
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
