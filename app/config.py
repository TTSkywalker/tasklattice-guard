from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    profile_path: Path
    database_path: Path
    ui_dist_path: Path
    nvidia_base_url: str | None = None
    content_safety_model: str | None = None
    topic_control_model: str | None = None
    nvidia_api_key_env_var: str = "MODEL_GUARDRAILS_NVIDIA_API_KEY"
    control_plane_ai_base_url: str | None = None
    control_plane_ai_model: str | None = None
    control_plane_ai_api_key_env_var: str = (
        "MODEL_GUARDRAILS_CONTROL_PLANE_AI_API_KEY"
    )

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
        control_plane_ai_base_url = os.environ.get(
            "MODEL_GUARDRAILS_CONTROL_PLANE_AI_BASE_URL",
            "",
        ).strip()
        control_plane_ai_model = os.environ.get(
            "MODEL_GUARDRAILS_CONTROL_PLANE_AI_MODEL",
            "",
        ).strip()
        if (content_safety_model or topic_control_model) and not nvidia_base_url:
            raise ValueError(
                "MODEL_GUARDRAILS_NVIDIA_BASE_URL is required when an NVIDIA "
                "guardrail model is configured."
            )
        if control_plane_ai_model and not control_plane_ai_base_url:
            raise ValueError(
                "MODEL_GUARDRAILS_CONTROL_PLANE_AI_BASE_URL is required when "
                "a control-plane AI model is configured."
            )
        return cls(
            profile_path=Path(
                os.environ.get(
                    "MODEL_GUARDRAILS_PROFILE_PATH",
                    str(root / "profiles" / "model-io-default-v1"),
                )
            ),
            database_path=Path(
                os.environ.get(
                    "MODEL_GUARDRAILS_DATABASE_PATH",
                    str(root / "data" / "tasklattice-guard-v8.db"),
                )
            ),
            ui_dist_path=Path(
                os.environ.get(
                    "MODEL_GUARDRAILS_UI_DIST_PATH",
                    str(root / "web" / "dist"),
                )
            ),
            nvidia_base_url=nvidia_base_url.rstrip("/") or None,
            content_safety_model=content_safety_model or None,
            topic_control_model=topic_control_model or None,
            control_plane_ai_base_url=control_plane_ai_base_url.rstrip("/") or None,
            control_plane_ai_model=control_plane_ai_model or None,
        )
