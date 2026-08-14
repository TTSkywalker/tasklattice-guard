"""TaskLattice policy providers exposed exclusively as NeMo Actions."""
from .content_filter import ContentFilterActionProvider
from .pii import PiiActionProvider
from .prompt_security import PromptSecurityActionProvider
from .secrets import SecretsActionProvider
from .topic_rules import TopicRulesActionProvider


def local_action_providers() -> tuple[
    ContentFilterActionProvider,
    SecretsActionProvider,
    PiiActionProvider,
    TopicRulesActionProvider,
    PromptSecurityActionProvider,
]:
    """Return local providers registered directly as versioned NeMo Actions."""
    return (
        ContentFilterActionProvider(),
        SecretsActionProvider(),
        PiiActionProvider(),
        TopicRulesActionProvider(),
        PromptSecurityActionProvider(),
    )


__all__ = [
    "ContentFilterActionProvider",
    "PiiActionProvider",
    "PromptSecurityActionProvider",
    "SecretsActionProvider",
    "TopicRulesActionProvider",
    "local_action_providers",
]
