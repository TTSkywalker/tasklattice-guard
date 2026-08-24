from __future__ import annotations

import os
import socket
import base64
from dataclasses import dataclass
from pathlib import Path


def _boolean(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "true" if default else "false").strip().casefold()
    if raw not in {"1", "0", "true", "false", "yes", "no", "on", "off"}:
        raise ValueError(f"{name} must be a boolean.")
    return raw in {"1", "true", "yes", "on"}


def _positive_int(name: str, default: int) -> int:
    value = int(os.environ.get(name, str(default)))
    if value <= 0:
        raise ValueError(f"{name} must be positive.")
    return value


def _ratio(name: str, default: float) -> float:
    value = float(os.environ.get(name, str(default)))
    if not 0 <= value <= 1:
        raise ValueError(f"{name} must be between 0 and 1.")
    return value


@dataclass(frozen=True, slots=True)
class RunnerSettings:
    runner_id: str
    pool_id: str
    controller_target: str
    controller_token: str
    metrics_token: str | None
    artifact_public_key_path: Path
    artifact_state_path: Path
    compiler_capable: bool
    max_concurrency: int
    controller_ca_path: Path | None
    client_certificate_path: Path | None
    client_key_path: Path | None
    telemetry_endpoint: str
    telemetry_batch_size: int
    call_context_redis_url: str | None
    nvidia_base_url: str | None
    content_safety_model: str | None
    topic_control_model: str | None
    jailbreak_model: str | None
    grounding_model: str | None
    nvidia_api_key_env_var: str
    automated_reasoning_endpoint_url: str | None
    automated_reasoning_api_key_env_var: str
    runtime_log_encryption_key: bytes | None
    otel_exporter_otlp_endpoint: str | None = None
    otel_trace_sample_ratio: float = 0.1
    pyroscope_server_address: str | None = None
    pyroscope_sample_rate: int = 100

    @classmethod
    def from_env(cls) -> "RunnerSettings":
        pool_id = os.environ.get("GUARD_RUNNER_POOL_ID", "default").strip()
        runner_id = os.environ.get("GUARD_RUNNER_ID", socket.gethostname()).strip()
        token = os.environ.get("GUARD_CONTROLLER_TOKEN", "")
        metrics_token = os.environ.get("GUARD_METRICS_TOKEN", "").strip()
        public_key = os.environ.get("GUARD_ARTIFACT_PUBLIC_KEY_PATH", "").strip()
        if not runner_id or not pool_id:
            raise ValueError("GUARD_RUNNER_ID and GUARD_RUNNER_POOL_ID cannot be empty.")
        if len(token) < 32:
            raise ValueError("GUARD_CONTROLLER_TOKEN must contain at least 32 characters.")
        if metrics_token and len(metrics_token) < 32:
            raise ValueError("GUARD_METRICS_TOKEN must contain at least 32 characters when configured.")
        if not public_key:
            raise ValueError("GUARD_ARTIFACT_PUBLIC_KEY_PATH is required.")
        target = os.environ.get("GUARD_CONTROLLER_TARGET", "tali-guard-controller:9090").strip()
        if not target:
            raise ValueError("GUARD_CONTROLLER_TARGET cannot be empty.")
        controller_ca = os.environ.get("GUARD_CONTROLLER_CA_PATH", "").strip()
        client_certificate = os.environ.get("GUARD_RUNNER_CLIENT_CERT_PATH", "").strip()
        client_key = os.environ.get("GUARD_RUNNER_CLIENT_KEY_PATH", "").strip()
        tls_values = (controller_ca, client_certificate, client_key)
        if any(tls_values) and not all(tls_values):
            raise ValueError(
                "GUARD_CONTROLLER_CA_PATH, GUARD_RUNNER_CLIENT_CERT_PATH, and "
                "GUARD_RUNNER_CLIENT_KEY_PATH must be configured together."
            )
        if all(tls_values) and not metrics_token:
            raise ValueError("GUARD_METRICS_TOKEN is required with production control-channel mTLS.")
        nvidia_base_url = os.environ.get("MODEL_GUARDRAILS_NVIDIA_BASE_URL", "").strip()
        content_safety_model = os.environ.get(
            "MODEL_GUARDRAILS_CONTENT_SAFETY_MODEL", ""
        ).strip()
        topic_control_model = os.environ.get(
            "MODEL_GUARDRAILS_TOPIC_CONTROL_MODEL", ""
        ).strip()
        jailbreak_model = os.environ.get(
            "MODEL_GUARDRAILS_JAILBREAK_MODEL", ""
        ).strip()
        grounding_model = os.environ.get(
            "MODEL_GUARDRAILS_GROUNDING_MODEL", ""
        ).strip()
        nvidia_api_key_env_var = os.environ.get(
            "MODEL_GUARDRAILS_NVIDIA_API_KEY_ENV_VAR",
            "MODEL_GUARDRAILS_NVIDIA_API_KEY",
        ).strip() or "MODEL_GUARDRAILS_NVIDIA_API_KEY"
        configured_models = tuple(
            item
            for item in (
                content_safety_model,
                topic_control_model,
                jailbreak_model,
                grounding_model,
            )
            if item
        )
        if configured_models and not nvidia_base_url:
            raise ValueError(
                "MODEL_GUARDRAILS_NVIDIA_BASE_URL is required when an NVIDIA "
                "guardrail model is configured."
            )
        if configured_models and not os.environ.get(nvidia_api_key_env_var, "").strip():
            raise ValueError(
                f"{nvidia_api_key_env_var} is required when an NVIDIA guardrail model is configured."
            )
        runtime_log_key_value = os.environ.get(
            "MODEL_GUARDRAILS_RUNTIME_LOG_ENCRYPTION_KEY", ""
        ).strip()
        runtime_log_encryption_key = None
        if runtime_log_key_value:
            try:
                runtime_log_encryption_key = base64.b64decode(
                    runtime_log_key_value, validate=True
                )
            except ValueError as error:
                raise ValueError(
                    "MODEL_GUARDRAILS_RUNTIME_LOG_ENCRYPTION_KEY must be valid base64."
                ) from error
            if len(runtime_log_encryption_key) != 32:
                raise ValueError(
                    "MODEL_GUARDRAILS_RUNTIME_LOG_ENCRYPTION_KEY must decode to 32 bytes."
                )
        automated_reasoning_endpoint_url = os.environ.get(
            "MODEL_GUARDRAILS_AUTOMATED_REASONING_ENDPOINT_URL", ""
        ).strip()
        automated_reasoning_api_key_env_var = os.environ.get(
            "MODEL_GUARDRAILS_AUTOMATED_REASONING_API_KEY_ENV_VAR",
            "MODEL_GUARDRAILS_AUTOMATED_REASONING_API_KEY",
        ).strip() or "MODEL_GUARDRAILS_AUTOMATED_REASONING_API_KEY"
        if automated_reasoning_endpoint_url:
            if not automated_reasoning_endpoint_url.startswith(("http://", "https://")):
                raise ValueError(
                    "MODEL_GUARDRAILS_AUTOMATED_REASONING_ENDPOINT_URL must be an HTTP(S) URL."
                )
            if not os.environ.get(automated_reasoning_api_key_env_var, "").strip():
                raise ValueError(
                    f"{automated_reasoning_api_key_env_var} is required when Automated Reasoning is configured."
                )
        return cls(
            runner_id=runner_id,
            pool_id=pool_id,
            controller_target=target,
            controller_token=token,
            metrics_token=metrics_token or None,
            artifact_public_key_path=Path(public_key),
            artifact_state_path=Path(
                os.environ.get("GUARD_RUNNER_STATE_PATH", "/var/lib/tasklattice/guard-runner")
            ),
            compiler_capable=_boolean("GUARD_RUNNER_COMPILER_CAPABLE", pool_id == "default"),
            max_concurrency=_positive_int("GUARD_RUNNER_MAX_CONCURRENCY", 64),
            controller_ca_path=Path(controller_ca) if controller_ca else None,
            client_certificate_path=(Path(client_certificate) if client_certificate else None),
            client_key_path=Path(client_key) if client_key else None,
            telemetry_endpoint=os.environ.get(
                "GUARD_CONTROLLER_TELEMETRY_ENDPOINT",
                "http://tali-guard-controller:8080/api/internal/v1/runtime-events",
            ).strip(),
            telemetry_batch_size=_positive_int("GUARD_RUNNER_TELEMETRY_BATCH_SIZE", 100),
            call_context_redis_url=(
                os.environ.get("GUARD_RUNNER_CALL_CONTEXT_REDIS_URL", "").strip() or None
            ),
            nvidia_base_url=nvidia_base_url.rstrip("/") or None,
            content_safety_model=content_safety_model or None,
            topic_control_model=topic_control_model or None,
            jailbreak_model=jailbreak_model or None,
            grounding_model=grounding_model or None,
            nvidia_api_key_env_var=nvidia_api_key_env_var,
            automated_reasoning_endpoint_url=automated_reasoning_endpoint_url or None,
            automated_reasoning_api_key_env_var=automated_reasoning_api_key_env_var,
            runtime_log_encryption_key=runtime_log_encryption_key,
            otel_exporter_otlp_endpoint=(
                os.environ.get("GUARD_OTEL_EXPORTER_OTLP_ENDPOINT", "").strip().rstrip("/")
                or None
            ),
            otel_trace_sample_ratio=_ratio("GUARD_OTEL_TRACE_SAMPLE_RATIO", 0.1),
            pyroscope_server_address=(
                os.environ.get("GUARD_PYROSCOPE_SERVER_ADDRESS", "").strip().rstrip("/")
                or None
            ),
            pyroscope_sample_rate=_positive_int("GUARD_PYROSCOPE_SAMPLE_RATE", 100),
        )
