from __future__ import annotations

from runner.toolkit.nemo.actions import local_action_providers
from runner.toolkit.nemo.actions.contracts import ActionProvider
from runner.toolkit.nemo.actions.prompt_security import PromptSecurityActionProvider
from runner.toolkit.nemo.actions.topic import TopicJudgeActionProvider
from runner.toolkit.nemo.actions.grounding import GroundingActionProvider
from runner.toolkit.nemo.actions.automated_reasoning import HTTPAutomatedReasoningProvider, ReasoningActionProvider

from .config import RunnerSettings


def runtime_action_providers(settings: RunnerSettings) -> tuple[ActionProvider, ...]:
    providers: list[ActionProvider] = list(local_action_providers(
        PromptSecurityActionProvider(
            jailbreak_base_url=settings.nvidia_base_url,
            jailbreak_model=settings.jailbreak_model,
            api_key_env_var=settings.nvidia_api_key_env_var,
        )
    ))
    if settings.nvidia_base_url and settings.topic_control_model:
        providers.append(TopicJudgeActionProvider(
            base_url=settings.nvidia_base_url,
            model=settings.topic_control_model,
            api_key_env_var=settings.nvidia_api_key_env_var,
        ))
    if settings.nvidia_base_url and settings.grounding_model:
        providers.append(GroundingActionProvider(
            base_url=settings.nvidia_base_url,
            model=settings.grounding_model,
            api_key_env_var=settings.nvidia_api_key_env_var,
        ))
    if settings.automated_reasoning_endpoint_url:
        providers.append(ReasoningActionProvider(HTTPAutomatedReasoningProvider(
            endpoint_url=settings.automated_reasoning_endpoint_url,
            api_key_env_var=settings.automated_reasoning_api_key_env_var,
        )))
    return tuple(providers)
