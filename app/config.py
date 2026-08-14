from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    database_path: Path
    ui_dist_path: Path
    database_url: str | None = None
    public_runtime_base_url: str = "http://localhost:8091"
    nvidia_base_url: str | None = None
    content_safety_model: str | None = None
    topic_control_model: str | None = None
    grounding_model: str | None = None
    nvidia_api_key_env_var: str = "MODEL_GUARDRAILS_NVIDIA_API_KEY"
    playground_chat_base_url: str | None = None
    playground_chat_model: str | None = None
    playground_chat_api_key_env_var: str = (
        "MODEL_GUARDRAILS_PLAYGROUND_CHAT_API_KEY"
    )
    automated_reasoning_endpoint_url: str | None = None
    automated_reasoning_api_key_env_var: str = (
        "MODEL_GUARDRAILS_AUTOMATED_REASONING_API_KEY"
    )
    control_plane_ai_base_url: str | None = None
    control_plane_ai_model: str | None = None
    control_plane_ai_api_key_env_var: str = (
        "MODEL_GUARDRAILS_CONTROL_PLANE_AI_API_KEY"
    )
    runtime_p95_budget_ms: int = 2_500
    runtime_p99_budget_ms: int = 5_000
    runtime_max_concurrency_per_guardrail: int = 64
    jailbreak_detection_nim_base_url: str | None = None
    jailbreak_detection_nim_server_endpoint: str = "classify"
    jailbreak_detection_api_key_env_var: str = (
        "MODEL_GUARDRAILS_NVIDIA_API_KEY"
    )
    otel_enabled: bool = False
    otel_exporter_endpoint: str | None = None

    @property
    def database_locator(self) -> str | Path:
        """Return the deployment-selected SQLAlchemy URL or local fallback path."""
        return self.database_url or self.database_path

    @classmethod
    def from_env(cls) -> Settings:
        root = Path(__file__).resolve().parent.parent
        public_runtime_base_url = os.environ.get(
            "MODEL_GUARDRAILS_PUBLIC_RUNTIME_BASE_URL",
            "http://localhost:8091",
        ).strip().rstrip("/")
        if not public_runtime_base_url.startswith(("http://", "https://")):
            raise ValueError(
                "MODEL_GUARDRAILS_PUBLIC_RUNTIME_BASE_URL must be an HTTP(S) URL."
            )
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
        grounding_model = os.environ.get(
            "MODEL_GUARDRAILS_GROUNDING_MODEL",
            "",
        ).strip()
        nvidia_api_key_env_var = os.environ.get(
            "MODEL_GUARDRAILS_NVIDIA_API_KEY_ENV_VAR",
            "MODEL_GUARDRAILS_NVIDIA_API_KEY",
        ).strip() or "MODEL_GUARDRAILS_NVIDIA_API_KEY"
        playground_chat_base_url = os.environ.get(
            "MODEL_GUARDRAILS_PLAYGROUND_CHAT_BASE_URL",
            "",
        ).strip()
        playground_chat_model = os.environ.get(
            "MODEL_GUARDRAILS_PLAYGROUND_CHAT_MODEL",
            "",
        ).strip()
        playground_chat_api_key_env_var = os.environ.get(
            "MODEL_GUARDRAILS_PLAYGROUND_CHAT_API_KEY_ENV_VAR",
            "MODEL_GUARDRAILS_PLAYGROUND_CHAT_API_KEY",
        ).strip() or "MODEL_GUARDRAILS_PLAYGROUND_CHAT_API_KEY"
        automated_reasoning_endpoint_url = os.environ.get(
            "MODEL_GUARDRAILS_AUTOMATED_REASONING_ENDPOINT_URL",
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
        control_plane_ai_api_key_env_var = os.environ.get(
            "MODEL_GUARDRAILS_CONTROL_PLANE_AI_API_KEY_ENV_VAR",
            "MODEL_GUARDRAILS_CONTROL_PLANE_AI_API_KEY",
        ).strip() or "MODEL_GUARDRAILS_CONTROL_PLANE_AI_API_KEY"
        jailbreak_detection_nim_base_url = os.environ.get(
            "MODEL_GUARDRAILS_JAILBREAK_NIM_BASE_URL", ""
        ).strip()
        jailbreak_detection_nim_server_endpoint = os.environ.get(
            "MODEL_GUARDRAILS_JAILBREAK_NIM_SERVER_ENDPOINT",
            "classify",
        ).strip() or "classify"
        jailbreak_detection_api_key_env_var = os.environ.get(
            "MODEL_GUARDRAILS_JAILBREAK_API_KEY_ENV_VAR",
            nvidia_api_key_env_var,
        ).strip() or nvidia_api_key_env_var
        otel_enabled = os.environ.get(
            "MODEL_GUARDRAILS_OTEL_ENABLED", "false"
        ).strip().casefold() in {"1", "true", "yes", "on"}
        otel_exporter_endpoint = os.environ.get(
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
            os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", ""),
        ).strip()
        if otel_enabled and not otel_exporter_endpoint.startswith(("http://", "https://")):
            raise ValueError(
                "OTEL_EXPORTER_OTLP_ENDPOINT or OTEL_EXPORTER_OTLP_TRACES_ENDPOINT "
                "must be an HTTP(S) URL when OpenTelemetry is enabled."
            )
        if jailbreak_detection_nim_base_url and not jailbreak_detection_nim_base_url.startswith(
            ("https://", "http://")
        ):
            raise ValueError(
                "MODEL_GUARDRAILS_JAILBREAK_NIM_BASE_URL must be an HTTP(S) URL."
            )
        if jailbreak_detection_nim_base_url and not jailbreak_detection_nim_server_endpoint:
            raise ValueError(
                "MODEL_GUARDRAILS_JAILBREAK_NIM_SERVER_ENDPOINT is required when "
                "MODEL_GUARDRAILS_JAILBREAK_NIM_BASE_URL is configured."
            )
        if (content_safety_model or topic_control_model or grounding_model) and not nvidia_base_url:
            raise ValueError(
                "MODEL_GUARDRAILS_NVIDIA_BASE_URL is required when an NVIDIA "
                "guardrail model is configured."
            )
        if bool(playground_chat_base_url) != bool(playground_chat_model):
            raise ValueError(
                "MODEL_GUARDRAILS_PLAYGROUND_CHAT_BASE_URL and "
                "MODEL_GUARDRAILS_PLAYGROUND_CHAT_MODEL must be configured together."
            )
        if bool(control_plane_ai_base_url) != bool(control_plane_ai_model):
            raise ValueError(
                "MODEL_GUARDRAILS_CONTROL_PLANE_AI_BASE_URL and "
                "MODEL_GUARDRAILS_CONTROL_PLANE_AI_MODEL must be configured together."
            )
        if automated_reasoning_endpoint_url:
            if not automated_reasoning_endpoint_url.startswith(("https://", "http://")):
                raise ValueError(
                    "MODEL_GUARDRAILS_AUTOMATED_REASONING_ENDPOINT_URL must be an HTTP(S) URL."
                )
            if not os.environ.get(
                "MODEL_GUARDRAILS_AUTOMATED_REASONING_API_KEY", ""
            ).strip():
                raise ValueError(
                    "MODEL_GUARDRAILS_AUTOMATED_REASONING_API_KEY is required when "
                    "an Automated Reasoning endpoint is configured."
                )
        runtime_p95_budget_ms = _positive_int(
            "MODEL_GUARDRAILS_RUNTIME_P95_BUDGET_MS", 2_500
        )
        runtime_p99_budget_ms = _positive_int(
            "MODEL_GUARDRAILS_RUNTIME_P99_BUDGET_MS", 5_000
        )
        runtime_max_concurrency_per_guardrail = _positive_int(
            "MODEL_GUARDRAILS_RUNTIME_MAX_CONCURRENCY_PER_GUARDRAIL", 64
        )
        if runtime_p99_budget_ms < runtime_p95_budget_ms:
            raise ValueError(
                "MODEL_GUARDRAILS_RUNTIME_P99_BUDGET_MS must be at least the P95 budget."
            )
        return cls(
            database_path=Path(
                os.environ.get(
                    "MODEL_GUARDRAILS_DATABASE_PATH",
                    str(root / "data" / "tasklattice-guard-policy-schema-v3.db"),
                )
            ),
            database_url=(
                os.environ.get("MODEL_GUARDRAILS_DATABASE_URL", "").strip() or None
            ),
            ui_dist_path=Path(
                os.environ.get(
                    "MODEL_GUARDRAILS_UI_DIST_PATH",
                    str(root / "web" / "dist"),
                )
            ),
            public_runtime_base_url=public_runtime_base_url,
            nvidia_base_url=nvidia_base_url.rstrip("/") or None,
            content_safety_model=content_safety_model or None,
            topic_control_model=topic_control_model or None,
            grounding_model=grounding_model or None,
            nvidia_api_key_env_var=nvidia_api_key_env_var,
            playground_chat_base_url=playground_chat_base_url.rstrip("/") or None,
            playground_chat_model=playground_chat_model or None,
            playground_chat_api_key_env_var=playground_chat_api_key_env_var,
            automated_reasoning_endpoint_url=(
                automated_reasoning_endpoint_url or None
            ),
            control_plane_ai_base_url=control_plane_ai_base_url.rstrip("/") or None,
            control_plane_ai_model=control_plane_ai_model or None,
            control_plane_ai_api_key_env_var=control_plane_ai_api_key_env_var,
            runtime_p95_budget_ms=runtime_p95_budget_ms,
            runtime_p99_budget_ms=runtime_p99_budget_ms,
            runtime_max_concurrency_per_guardrail=(
                runtime_max_concurrency_per_guardrail
            ),
            jailbreak_detection_nim_base_url=(
                jailbreak_detection_nim_base_url.rstrip("/") or None
            ),
            jailbreak_detection_nim_server_endpoint=(
                jailbreak_detection_nim_server_endpoint
            ),
            jailbreak_detection_api_key_env_var=(
                jailbreak_detection_api_key_env_var
            ),
            otel_enabled=otel_enabled,
            otel_exporter_endpoint=otel_exporter_endpoint.rstrip("/") or None,
        )


def _positive_int(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer.") from error
    if value <= 0:
        raise ValueError(f"{name} must be positive.")
    return value
