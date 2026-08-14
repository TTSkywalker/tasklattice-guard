from __future__ import annotations

import pytest

from app.config import Settings
from app.main import create_engine


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
        "MODEL_GUARDRAILS_DEEP_JUDGE_BASE_URL",
        "https://api.deepseek.com/",
    )
    monkeypatch.setenv("MODEL_GUARDRAILS_DEEP_JUDGE_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv(
        "MODEL_GUARDRAILS_DEEP_JUDGE_API_KEY_ENV_VAR",
        "DEEPSEEK_API_KEY",
    )
    monkeypatch.setenv(
        "MODEL_GUARDRAILS_CONTROL_PLANE_AI_API_KEY_ENV_VAR",
        "DEEPSEEK_API_KEY",
    )

    settings = Settings.from_env()

    assert settings.nvidia_api_key_env_var == "NVAPI_API_KEY"
    assert settings.deep_judge_base_url == "https://api.deepseek.com"
    assert settings.deep_judge_model == "deepseek-v4-flash"
    assert settings.deep_judge_api_key_env_var == "DEEPSEEK_API_KEY"
    assert settings.control_plane_ai_api_key_env_var == "DEEPSEEK_API_KEY"


def test_deepseek_fallback_registers_all_deep_judges(tmp_path):
    settings = Settings(
        database_path=tmp_path / "control-plane.db",
        ui_dist_path=tmp_path / "missing-ui",
        deep_judge_base_url="https://api.deepseek.com",
        deep_judge_model="deepseek-v4-flash",
        deep_judge_api_key_env_var="DEEPSEEK_API_KEY",
    )

    engine = create_engine(settings)
    children = tuple(
        item.evaluator
        for item in engine._registry._actions.providers()
        if item.name in {
            "TaskLatticePromptSecurityJudgeAction",
            "TaskLatticeTopicJudgeAction",
            "TaskLatticeGroundingAction",
        }
    )

    assert {child.name for child in children} == {
        "Prompt Security Judge",
        "Purpose-Aware Topic Judge",
        "Contextual Grounding Judge",
    }
    assert all(child._model == "deepseek-v4-flash" for child in children)
    assert all(child._api_key_env_var == "DEEPSEEK_API_KEY" for child in children)
    assert all(
        child._request_options["thinking"] == {"type": "disabled"}
        for child in children
    )
