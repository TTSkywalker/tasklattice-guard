from __future__ import annotations

from .domain import RuntimeCapability


RUNTIME_CAPABILITIES: tuple[RuntimeCapability, ...] = (
    RuntimeCapability(
        id="secrets",
        policy_id="builtin-secrets",
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
    RuntimeCapability(
        id="pii",
        policy_id="builtin-pii",
        display_name="Personal information",
        description="Prevent personal identifiers and customer data from entering or leaving the model boundary.",
        domain="Data protection",
        default_phases=("input", "output"),
        default_action="redact",
        allowed_actions=("redact", "reject", "rewrite"),
        available_stages=("deterministic", "fast_semantic"),
        limitations=("Semantic PII detection requires a configured Guard Model.",),
        module="data_protection",
    ),
    RuntimeCapability(
        id="prompt_injection",
        policy_id="builtin-prompt-injection",
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
    RuntimeCapability(
        id="jailbreak",
        policy_id="builtin-jailbreak",
        display_name="Jailbreak",
        description="Detect adversarial attempts to bypass safety and policy constraints.",
        domain="Prompt security",
        default_phases=("input",),
        default_action="reject",
        allowed_actions=("reject", "redirect"),
        available_stages=("fast_semantic", "deep_judge"),
        limitations=("Novel attacks may require contextual Policy Judge review.",),
        module="interaction_safety",
    ),
    RuntimeCapability(
        id="content_safety",
        policy_id="builtin-content-safety",
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
    RuntimeCapability(
        id="topic_control",
        policy_id="builtin-topic-safety",
        display_name="Topic boundary",
        description="Keep interactions within the declared purpose, allowed topics, and restrictions.",
        domain="Policy compliance",
        default_phases=("input", "output"),
        default_action="redirect",
        allowed_actions=("redirect", "reject", "rewrite"),
        available_stages=("deterministic", "deep_judge"),
        limitations=(
            "Explicit allowed and restricted topics are enforced locally; ambiguous intent requires an optional Policy Judge.",
        ),
        module="business_assurance",
    ),
    RuntimeCapability(
        id="company_policy",
        policy_id="builtin-company-policy",
        display_name="Organization policy",
        description="Judge interaction compliance against organization-specific safety intent.",
        domain="Policy compliance",
        default_phases=("input", "output"),
        default_action="reject",
        allowed_actions=("reject", "redact", "rewrite", "regenerate"),
        available_stages=("deep_judge",),
        limitations=("Requires a configured Policy Judge and reviewed policy language.",),
        module="business_assurance",
    ),
    RuntimeCapability(
        id="contextual_grounding",
        policy_id="builtin-contextual-grounding",
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
    RuntimeCapability(
        id="automated_reasoning",
        policy_id="builtin-automated-reasoning",
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
    RuntimeCapability(
        id="builtin_content_filter",
        policy_id=None,
        display_name="Built-in content filter policy",
        description="Run locally bundled, versioned content-filter Policies without an external policy service.",
        domain="Built-in policy",
        default_phases=("input", "output"),
        default_action="reject",
        allowed_actions=("reject",),
        available_stages=("deterministic",),
        limitations=("Coverage is limited to the Rules bundled with the selected Policy version.",),
        module="interaction_safety",
    ),
)

# ``builtin_content_filter`` is the execution adapter used by declarative
# Policy Rules. It is not an independently configurable product Policy.
BUILTIN_POLICY_CAPABILITIES = tuple(
    item for item in RUNTIME_CAPABILITIES if item.policy_id is not None
)

_CAPABILITY_BY_ID = {item.id: item for item in RUNTIME_CAPABILITIES}
_CAPABILITY_BY_POLICY_ID = {
    item.policy_id: item for item in BUILTIN_POLICY_CAPABILITIES
}


def runtime_capability(risk: str) -> RuntimeCapability:
    return _CAPABILITY_BY_ID[risk]


def builtin_policy_id(capability_id: str) -> str:
    policy_id = runtime_capability(capability_id).policy_id
    if policy_id is None:
        raise KeyError(f"Runtime capability {capability_id!r} is not a product Policy.")
    return policy_id


def capability_id_for_policy(policy_id: str) -> str:
    return _CAPABILITY_BY_POLICY_ID[policy_id].id
