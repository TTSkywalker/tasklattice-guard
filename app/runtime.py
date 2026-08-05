from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from .contracts import RailResult


class GuardrailsRuntime(Protocol):
    async def check(
        self,
        input_type: str,
        text: str,
        context_messages: list[dict[str, Any]],
    ) -> RailResult: ...


class NemoGuardrailsRuntime:
    """Run the configured Colang profile and NVIDIA model rails in order."""

    def __init__(
        self,
        profile_path: Path,
        *,
        nvidia_base_url: str | None = None,
        content_safety_model: str | None = None,
        topic_control_model: str | None = None,
        nvidia_api_key_env_var: str = "MODEL_GUARDRAILS_NVIDIA_API_KEY",
    ):
        from nemoguardrails import LLMRails, RailsConfig
        from nemoguardrails.rails.llm.config import Model

        if (content_safety_model or topic_control_model) and not nvidia_base_url:
            raise ValueError(
                "NVIDIA base URL is required when a guardrail model is configured."
            )

        config = RailsConfig.from_path(str(profile_path))
        if content_safety_model and nvidia_base_url:
            config.models.append(
                Model(
                    type="content_safety",
                    engine="nim",
                    model=content_safety_model,
                    api_key_env_var=nvidia_api_key_env_var,
                    parameters={"base_url": nvidia_base_url},
                )
            )
            config.rails.input.flows.append(
                "content safety check input $model=content_safety"
            )
            config.rails.output.flows.append(
                "content safety check output $model=content_safety"
            )

        if topic_control_model and nvidia_base_url:
            config.models.append(
                Model(
                    type="topic_control",
                    engine="nim",
                    model=topic_control_model,
                    api_key_env_var=nvidia_api_key_env_var,
                    parameters={"base_url": nvidia_base_url},
                )
            )
            config.rails.input.flows.append(
                "topic safety check input $model=topic_control"
            )

        self._rails = LLMRails(config)

    async def check(
        self,
        input_type: str,
        text: str,
        context_messages: list[dict[str, Any]],
    ) -> RailResult:
        from nemoguardrails.rails.llm.options import RailStatus, RailType

        if input_type == "request":
            messages = [{"role": "user", "content": text}]
            rail_types = [RailType.INPUT]
        else:
            messages = [
                message
                for message in context_messages
                if message.get("role") in {"system", "user", "assistant"}
                and isinstance(message.get("content"), str)
            ]
            messages.append({"role": "assistant", "content": text})
            rail_types = [RailType.OUTPUT]

        result = await self._rails.check_async(messages, rail_types=rail_types)
        if result.status == RailStatus.BLOCKED:
            status = "BLOCKED"
        elif result.status == RailStatus.MODIFIED:
            status = "MODIFIED"
        else:
            status = "PASSED"
        return RailResult(
            status=status,
            content=result.content,
            rail=result.rail,
        )
