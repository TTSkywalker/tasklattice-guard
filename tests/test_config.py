from __future__ import annotations

from pathlib import Path

from app.config import Settings
from app.main import create_engine


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


def test_deepseek_fallback_registers_all_deep_judges():
    settings = Settings(
        nemo_config_path=Path("unused"),
        database_path=Path("unused.db"),
        ui_dist_path=Path("missing-ui"),
        deep_judge_base_url="https://api.deepseek.com",
        deep_judge_model="deepseek-v4-flash",
        deep_judge_api_key_env_var="DEEPSEEK_API_KEY",
    )

    engine = create_engine(settings)
    deep_stage = engine._runner._stages["deep_judge"]
    children = deep_stage._children

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
