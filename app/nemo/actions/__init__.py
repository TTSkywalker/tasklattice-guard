"""TaskLattice policy providers exposed exclusively as NeMo Actions."""
from .content_filter import ContentFilterActionProvider
from .indirect_prompt_injection import IndirectPromptInjectionActionProvider
from .pii import PiiActionProvider
from .prompt_leakage import PromptLeakageActionProvider
from .prompt_security import PromptSecurityActionProvider
from .secrets import SecretsActionProvider
from .topic_rules import TopicRulesActionProvider


def local_action_providers() -> tuple[
    ContentFilterActionProvider,
    SecretsActionProvider,
    PiiActionProvider,
    TopicRulesActionProvider,
    PromptSecurityActionProvider,
    IndirectPromptInjectionActionProvider,
    PromptLeakageActionProvider,
]:
    """Return local providers registered directly as versioned NeMo Actions."""
    return (
        ContentFilterActionProvider(),
        SecretsActionProvider(),
        PiiActionProvider(),
        TopicRulesActionProvider(),
        PromptSecurityActionProvider(),
        IndirectPromptInjectionActionProvider(),
        PromptLeakageActionProvider(),
    )


__all__ = [
    "ContentFilterActionProvider",
    "IndirectPromptInjectionActionProvider",
    "PiiActionProvider",
    "PromptSecurityActionProvider",
    "PromptLeakageActionProvider",
    "SecretsActionProvider",
    "TopicRulesActionProvider",
    "local_action_providers",
]
