from __future__ import annotations

import json

import pytest
import yaml

from runner.compiler import DefaultRunnerCompiler
from runner.config import RunnerSettings
from runner.generated import runner_control_pb2 as protocol
from runner.providers import runtime_action_providers
from runner.toolkit.nemo.actions.names import ACTION_PROMPT_SECURITY, ACTION_TOPIC_JUDGE


def test_runner_restores_nvidia_models_for_compilation(monkeypatch: pytest.MonkeyPatch) -> None:
    _required_runner_env(monkeypatch)
    monkeypatch.setenv("MODEL_GUARDRAILS_NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1/")
    monkeypatch.setenv("MODEL_GUARDRAILS_CONTENT_SAFETY_MODEL", "nvidia/content-safety-test")
    monkeypatch.setenv("MODEL_GUARDRAILS_TOPIC_CONTROL_MODEL", "nvidia/topic-control-test")
    monkeypatch.setenv("MODEL_GUARDRAILS_JAILBREAK_MODEL", "nvidia/jailbreak-chat-test")
    monkeypatch.setenv("MODEL_GUARDRAILS_NVIDIA_API_KEY", "test-key")

    settings = RunnerSettings.from_env()
    compiler = DefaultRunnerCompiler(settings)

    assert settings.nvidia_base_url == "https://integrate.api.nvidia.com/v1"
    assert settings.content_safety_model == "nvidia/content-safety-test"
    assert settings.topic_control_model == "nvidia/topic-control-test"
    assert settings.jailbreak_model == "nvidia/jailbreak-chat-test"
    assert compiler._compiler.has_model_dependency("content_safety")
    assert compiler._compiler.has_model_dependency("topic_control")
    providers = runtime_action_providers(settings)
    assert any(provider.name == ACTION_TOPIC_JUDGE for provider in providers)
    prompt_security = next(provider for provider in providers if provider.name == ACTION_PROMPT_SECURITY)
    assert prompt_security._jailbreak_base_url == "https://integrate.api.nvidia.com/v1"
    assert prompt_security._jailbreak_model == "nvidia/jailbreak-chat-test"

    plan = {
        "safety_level": "balanced",
        "output_delivery": "full_buffered",
        "steps": [{
            "id": "topic_control:deep_semantic",
            "risk": "topic_control",
            "stage": "deep_semantic",
            "phases": ["input"],
            "on_unsafe": "reject",
            "escalation": "never",
            "parameters": [
                ["purpose", "Answer questions about employee benefits."],
                ["allowed_topics", "health insurance, paid leave"],
                ["restricted_topics", "investment advice, source code"],
            ],
        }],
        "modules": [{
            "id": "interaction_safety:input",
            "module": "interaction_safety",
            "phase": "input",
            "step_ids": ["topic_control:deep_semantic"],
            "depends_on": [],
            "input_view": "original",
            "required_for_release": True,
            "timeout_ms": 2_500,
            "failure_mode": "fail_closed",
        }],
        "reasoning_policies": [],
        "policy_versions": [],
        "policy_bindings": [],
    }
    artifact = compiler.compile(protocol.CompileRequest(
        compile_id="compile-nvidia-topic",
        guardrail_id="guardrail-nvidia-topic",
        guardrail_version=1,
        generation=1,
        plan_json=json.dumps(plan),
        runtime_profile="auto",
    ))
    config = yaml.safe_load(artifact.config_yaml)

    assert artifact.runtime_profile == "llmrails_colang1_standard"
    assert config["rails"]["input"]["flows"] == [
        "topic safety check input $model=topic_control"
    ]
    assert {item["type"]: item["model"] for item in config["models"]} == {
        "content_safety": "nvidia/content-safety-test",
        "topic_control": "nvidia/topic-control-test",
    }

    jailbreak_plan = {
        "safety_level": "balanced",
        "output_delivery": "full_buffered",
        "steps": [{
            "id": "jailbreak:fast-semantic",
            "risk": "jailbreak",
            "stage": "fast_semantic",
            "phases": ["input"],
            "on_unsafe": "reject",
            "escalation": "never",
            "parameters": [],
        }],
        "modules": [{
            "id": "interaction_safety:input",
            "module": "interaction_safety",
            "phase": "input",
            "step_ids": ["jailbreak:fast-semantic"],
            "depends_on": [],
            "input_view": "original",
            "required_for_release": True,
            "timeout_ms": 2_500,
            "failure_mode": "fail_closed",
        }],
        "reasoning_policies": [],
        "policy_versions": [],
        "policy_bindings": [],
    }
    jailbreak_artifact = compiler.compile(protocol.CompileRequest(
        compile_id="compile-nvidia-jailbreak",
        guardrail_id="guardrail-nvidia-jailbreak",
        guardrail_version=1,
        generation=1,
        plan_json=json.dumps(jailbreak_plan),
        runtime_profile="auto",
    ))
    jailbreak_config = yaml.safe_load(jailbreak_artifact.config_yaml)
    jailbreak_bindings = json.loads(jailbreak_artifact.action_bindings_json)

    assert jailbreak_bindings[0]["action_name"] == ACTION_PROMPT_SECURITY
    assert "jailbreak_detection" not in jailbreak_config.get("rails", {}).get("config", {})
    assert "/v1/security/" not in jailbreak_artifact.config_yaml


def test_runner_rejects_model_names_without_endpoint_or_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _required_runner_env(monkeypatch)
    monkeypatch.setenv("MODEL_GUARDRAILS_JAILBREAK_MODEL", "nvidia/jailbreak-chat-test")

    with pytest.raises(ValueError, match="NVIDIA_BASE_URL"):
        RunnerSettings.from_env()

    monkeypatch.setenv("MODEL_GUARDRAILS_NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
    with pytest.raises(ValueError, match="NVIDIA_API_KEY"):
        RunnerSettings.from_env()


def test_runner_validates_the_optional_metrics_token(monkeypatch: pytest.MonkeyPatch) -> None:
    _required_runner_env(monkeypatch)
    monkeypatch.setenv("GUARD_METRICS_TOKEN", "metrics-token-that-is-at-least-32-characters")
    assert RunnerSettings.from_env().metrics_token == "metrics-token-that-is-at-least-32-characters"

    monkeypatch.setenv("GUARD_METRICS_TOKEN", "short")
    with pytest.raises(ValueError, match="GUARD_METRICS_TOKEN"):
        RunnerSettings.from_env()


def test_runner_requires_metrics_authentication_with_production_mtls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _required_runner_env(monkeypatch)
    monkeypatch.setenv("GUARD_CONTROLLER_CA_PATH", "/tmp/ca.crt")
    monkeypatch.setenv("GUARD_RUNNER_CLIENT_CERT_PATH", "/tmp/runner.crt")
    monkeypatch.setenv("GUARD_RUNNER_CLIENT_KEY_PATH", "/tmp/runner.key")

    with pytest.raises(ValueError, match="GUARD_METRICS_TOKEN"):
        RunnerSettings.from_env()


def test_runner_uses_standard_opentelemetry_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _required_runner_env(monkeypatch)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://tempo.monitoring:4318/")
    monkeypatch.setenv("OTEL_TRACES_SAMPLER_ARG", "0.25")

    settings = RunnerSettings.from_env()

    assert settings.otel_exporter_otlp_endpoint == "http://tempo.monitoring:4318"
    assert settings.otel_trace_sample_ratio == 0.25


def _required_runner_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "MODEL_GUARDRAILS_NVIDIA_BASE_URL",
        "MODEL_GUARDRAILS_CONTENT_SAFETY_MODEL",
        "MODEL_GUARDRAILS_TOPIC_CONTROL_MODEL",
        "MODEL_GUARDRAILS_JAILBREAK_MODEL",
        "MODEL_GUARDRAILS_NVIDIA_API_KEY",
        "MODEL_GUARDRAILS_NVIDIA_API_KEY_ENV_VAR",
        "GUARD_METRICS_TOKEN",
        "GUARD_CONTROLLER_CA_PATH",
        "GUARD_RUNNER_CLIENT_CERT_PATH",
        "GUARD_RUNNER_CLIENT_KEY_PATH",
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        "OTEL_TRACES_SAMPLER_ARG",
        "GUARD_OTEL_EXPORTER_OTLP_ENDPOINT",
        "GUARD_OTEL_TRACE_SAMPLE_RATIO",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GUARD_RUNNER_ID", "runner-test")
    monkeypatch.setenv("GUARD_RUNNER_POOL_ID", "default")
    monkeypatch.setenv("GUARD_CONTROLLER_TOKEN", "runner-token-that-is-at-least-32-characters")
    monkeypatch.setenv("GUARD_ARTIFACT_PUBLIC_KEY_PATH", "/tmp/public-key.pem")
