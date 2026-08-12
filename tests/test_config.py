from __future__ import annotations

from app.config import Settings
from app.main import create_engine


def test_default_database_path_uses_current_v4_schema(monkeypatch):
    monkeypatch.delenv("MODEL_GUARDRAILS_DATABASE_PATH", raising=False)

    settings = Settings.from_env()

    assert settings.database_path.name == "tasklattice-guard-schema-v4.db"


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
