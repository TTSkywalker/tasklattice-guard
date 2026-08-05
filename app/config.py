from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    api_key: str
    profile_path: Path
    nvidia_base_url: str | None = None
    content_safety_model: str | None = None
    topic_control_model: str | None = None
    nvidia_api_key_env_var: str = "MODEL_GUARDRAILS_NVIDIA_API_KEY"

    @classmethod
    def from_env(cls) -> "Settings":
        root = Path(__file__).resolve().parent.parent
        nvidia_base_url = os.environ.get(
            "MODEL_GUARDRAILS_NVIDIA_BASE_URL",
            "",
        ).strip()
        content_safety_model = os.environ.get(
            "MODEL_GUARDRAILS_CONTENT_SAFETY_MODEL",
            "",
        ).strip()
        topic_control_model = os.environ.get(
            "MODEL_GUARDRAILS_TOPIC_CONTROL_MODEL",
            "",
        ).strip()
        if (content_safety_model or topic_control_model) and not nvidia_base_url:
            raise ValueError(
                "MODEL_GUARDRAILS_NVIDIA_BASE_URL is required when an NVIDIA "
                "guardrail model is configured."
            )
        return cls(
            api_key=os.environ.get("MODEL_GUARDRAILS_API_KEY", "local-model-guardrails-key"),
            profile_path=Path(
                os.environ.get(
                    "MODEL_GUARDRAILS_PROFILE_PATH",
                    str(root / "profiles" / "model-io-default-v1"),
                )
            ),
            nvidia_base_url=nvidia_base_url.rstrip("/") or None,
            content_safety_model=content_safety_model or None,
            topic_control_model=topic_control_model or None,
        )
