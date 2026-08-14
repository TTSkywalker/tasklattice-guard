from __future__ import annotations

import pytest

from app.config import Settings
from app.main import (
    _nemo_compiler,
    _specialized_evaluator_risks,
    create_action_registry,
    create_engine,
)


def test_default_database_path_uses_current_policy_schema(monkeypatch):
    monkeypatch.delenv("MODEL_GUARDRAILS_DATABASE_PATH", raising=False)
    monkeypatch.delenv("MODEL_GUARDRAILS_DATABASE_URL", raising=False)

    settings = Settings.from_env()

    assert settings.database_path.name == "tasklattice-guard-policy-schema-v3.db"


def test_database_url_takes_precedence_over_local_path(monkeypatch):
    database_url = "postgresql+psycopg://guard:secret@postgres/guard"
    monkeypatch.setenv("MODEL_GUARDRAILS_DATABASE_URL", database_url)

    settings = Settings.from_env()

    assert settings.database_locator == database_url


def test_database_url_is_not_restricted_by_core_configuration(monkeypatch):
    monkeypatch.setenv("MODEL_GUARDRAILS_DATABASE_URL", "mysql://guard/db")

    settings = Settings.from_env()

    assert settings.database_locator == "mysql://guard/db"


def test_public_runtime_base_url_is_canonical(monkeypatch):
    monkeypatch.setenv(
        "MODEL_GUARDRAILS_PUBLIC_RUNTIME_BASE_URL",
        "https://guard.example.com/",
    )

    settings = Settings.from_env()

    assert settings.public_runtime_base_url == "https://guard.example.com"


def test_public_runtime_base_url_rejects_non_http_url(monkeypatch):
    monkeypatch.setenv(
        "MODEL_GUARDRAILS_PUBLIC_RUNTIME_BASE_URL",
        "guard.internal.local",
    )

    with pytest.raises(ValueError, match="PUBLIC_RUNTIME_BASE_URL"):
        Settings.from_env()


def test_settings_reuses_existing_provider_key_variables(monkeypatch):
    monkeypatch.setenv(
        "MODEL_GUARDRAILS_NVIDIA_BASE_URL",
        "https://integrate.api.nvidia.com/v1/",
    )
    monkeypatch.setenv("MODEL_GUARDRAILS_CONTENT_SAFETY_MODEL", "nvidia/safety")
    monkeypatch.setenv("MODEL_GUARDRAILS_NVIDIA_API_KEY_ENV_VAR", "NVAPI_API_KEY")
    monkeypatch.setenv(
        "MODEL_GUARDRAILS_PLAYGROUND_CHAT_BASE_URL",
        "https://api.deepseek.com/",
    )
    monkeypatch.setenv("MODEL_GUARDRAILS_PLAYGROUND_CHAT_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv(
        "MODEL_GUARDRAILS_PLAYGROUND_CHAT_API_KEY_ENV_VAR",
        "DEEPSEEK_API_KEY",
    )
    monkeypatch.setenv(
        "MODEL_GUARDRAILS_CONTROL_PLANE_AI_API_KEY_ENV_VAR",
        "DEEPSEEK_API_KEY",
    )

    settings = Settings.from_env()

    assert settings.nvidia_api_key_env_var == "NVAPI_API_KEY"
    assert settings.playground_chat_base_url == "https://api.deepseek.com"
    assert settings.playground_chat_model == "deepseek-v4-flash"
    assert settings.playground_chat_api_key_env_var == "DEEPSEEK_API_KEY"
    assert settings.control_plane_ai_api_key_env_var == "DEEPSEEK_API_KEY"


def test_nvidia_guard_models_cover_runtime_without_a_generic_llm(tmp_path):
    settings = Settings(
        database_path=tmp_path / "control-plane.db",
        ui_dist_path=tmp_path / "missing-ui",
        nvidia_base_url="https://integrate.api.nvidia.com/v1",
        content_safety_model="nvidia/content-safety",
        topic_control_model="nvidia/topic-control",
        grounding_model="nvidia/grounding-evaluator",
        jailbreak_detection_nim_base_url="https://ai.api.nvidia.com",
        jailbreak_detection_nim_server_endpoint=(
            "/v1/security/nvidia/nemoguard-jailbreak-detect"
        ),
    )

    assert _specialized_evaluator_risks(settings) == frozenset(
        {
            "prompt_injection",
            "jailbreak",
            "topic_control",
            "company_policy",
            "contextual_grounding",
        }
    )
    compiler = _nemo_compiler(settings)
    assert {item["type"] for item in compiler._models} == {
        "content_safety",
        "topic_control",
    }
    assert compiler._jailbreak_detection == {
        "nim_base_url": "https://ai.api.nvidia.com",
        "nim_server_endpoint": "/v1/security/nvidia/nemoguard-jailbreak-detect",
        "api_key_env_var": "MODEL_GUARDRAILS_NVIDIA_API_KEY",
    }
    providers = create_action_registry(settings).providers()
    topic_provider = next(
        item for item in providers if item.name == "GuardTopicJudgeAction"
    )
    assert topic_provider.risks == frozenset({"topic_control", "company_policy"})


def test_jailbreak_detection_reuses_the_nvidia_credential_by_default(monkeypatch):
    monkeypatch.setenv(
        "MODEL_GUARDRAILS_NVIDIA_API_KEY_ENV_VAR", "NVAPI_API_KEY"
    )
    monkeypatch.setenv(
        "MODEL_GUARDRAILS_JAILBREAK_NIM_BASE_URL",
        "https://ai.api.nvidia.com",
    )
    monkeypatch.setenv(
        "MODEL_GUARDRAILS_JAILBREAK_NIM_SERVER_ENDPOINT",
        "/v1/security/nvidia/nemoguard-jailbreak-detect",
    )

    settings = Settings.from_env()

    assert settings.jailbreak_detection_api_key_env_var == "NVAPI_API_KEY"
    assert settings.jailbreak_detection_nim_server_endpoint.endswith(
        "nemoguard-jailbreak-detect"
    )


def test_playground_model_is_not_registered_as_a_runtime_evaluator(tmp_path):
    settings = Settings(
        database_path=tmp_path / "control-plane.db",
        ui_dist_path=tmp_path / "missing-ui",
        playground_chat_base_url="https://api.deepseek.com",
        playground_chat_model="deepseek-v4-flash",
        playground_chat_api_key_env_var="DEEPSEEK_API_KEY",
    )

    engine = create_engine(settings)
    runtime_actions = {
        item.name for item in engine._registry._actions.providers()
    }

    assert "GuardPromptSecurityJudgeAction" not in runtime_actions
    assert "GuardTopicJudgeAction" not in runtime_actions
    assert "GuardGroundingAction" not in runtime_actions
