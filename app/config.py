from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    database_path: Path
    ui_dist_path: Path
    nvidia_base_url: str | None = None
    content_safety_model: str | None = None
    topic_control_model: str | None = None
    grounding_model: str | None = None
    nvidia_api_key_env_var: str = "MODEL_GUARDRAILS_NVIDIA_API_KEY"
    deep_judge_base_url: str | None = None
    deep_judge_model: str | None = None
    deep_judge_api_key_env_var: str = "MODEL_GUARDRAILS_DEEP_JUDGE_API_KEY"
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
    jailbreak_detection_api_key_env_var: str = (
        "MODEL_GUARDRAILS_JAILBREAK_API_KEY"
    )
    otel_enabled: bool = False
    otel_exporter_endpoint: str | None = None

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
        grounding_model = os.environ.get(
            "MODEL_GUARDRAILS_GROUNDING_MODEL",
            "",
        ).strip()
        nvidia_api_key_env_var = os.environ.get(
            "MODEL_GUARDRAILS_NVIDIA_API_KEY_ENV_VAR",
            "MODEL_GUARDRAILS_NVIDIA_API_KEY",
        ).strip() or "MODEL_GUARDRAILS_NVIDIA_API_KEY"
        deep_judge_base_url = os.environ.get(
            "MODEL_GUARDRAILS_DEEP_JUDGE_BASE_URL",
            "",
        ).strip()
        deep_judge_model = os.environ.get(
            "MODEL_GUARDRAILS_DEEP_JUDGE_MODEL",
            "",
        ).strip()
        deep_judge_api_key_env_var = os.environ.get(
            "MODEL_GUARDRAILS_DEEP_JUDGE_API_KEY_ENV_VAR",
            "MODEL_GUARDRAILS_DEEP_JUDGE_API_KEY",
        ).strip() or "MODEL_GUARDRAILS_DEEP_JUDGE_API_KEY"
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
        jailbreak_detection_api_key_env_var = os.environ.get(
            "MODEL_GUARDRAILS_JAILBREAK_API_KEY_ENV_VAR",
            "MODEL_GUARDRAILS_JAILBREAK_API_KEY",
        ).strip() or "MODEL_GUARDRAILS_JAILBREAK_API_KEY"
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
        if (content_safety_model or topic_control_model or grounding_model) and not nvidia_base_url:
            raise ValueError(
                "MODEL_GUARDRAILS_NVIDIA_BASE_URL is required when an NVIDIA "
                "guardrail model is configured."
            )
        if control_plane_ai_model and not control_plane_ai_base_url:
            raise ValueError(
                "MODEL_GUARDRAILS_CONTROL_PLANE_AI_BASE_URL is required when "
                "a control-plane AI model is configured."
            )
        if bool(deep_judge_base_url) != bool(deep_judge_model):
            raise ValueError(
                "MODEL_GUARDRAILS_DEEP_JUDGE_BASE_URL and "
                "MODEL_GUARDRAILS_DEEP_JUDGE_MODEL must be configured together."
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
                    str(root / "data" / "tasklattice-guard-schema-v2.db"),
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
            grounding_model=grounding_model or None,
            nvidia_api_key_env_var=nvidia_api_key_env_var,
            deep_judge_base_url=deep_judge_base_url.rstrip("/") or None,
            deep_judge_model=deep_judge_model or None,
            deep_judge_api_key_env_var=deep_judge_api_key_env_var,
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
