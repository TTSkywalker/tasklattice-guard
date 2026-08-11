from __future__ import annotations

import os
from urllib.parse import urlsplit

from fastapi import FastAPI

from .adapters.http import HTTPAdapter
from .adapters.litellm import LiteLLMAdapter
from .config import Settings
from .control_plane.api import ControlPlaneAPI
from .control_plane.intent_analyzer import DeepSeekIntentAnalyzer, IntentAnalyzer
from .control_plane.service import ControlPlaneService
from .engine.contracts import GuardrailEngine
from .engine.automated_reasoning import (
    AutomatedReasoningPolicyEngine,
    HTTPAutomatedReasoningProvider,
)
from .engine.contextual_grounding import ContextualGroundingJudgeEngine
from .engine.dag import ModularGuardrailsEngine
from .engine.fast_pass import FastPassEngine
from .engine.nemo import NemoFastSemanticEngine
from .engine.prompt_security import PromptSecurityFastEngine, PromptSecurityJudgeEngine
from .engine.risk_router import RiskAwareStageRouter
from .engine.service import ModelGuardrailsEngineService
from .engine.topic_judge import PurposeAwareTopicJudgeEngine
from .identity import IdentityAPI, IdentityService
from .ui import ControlPlaneStaticFiles


def create_engine(
    settings: Settings,
) -> ModularGuardrailsEngine:
    stages = [FastPassEngine()]
    fast_semantic = [PromptSecurityFastEngine()]
    if settings.content_safety_model and settings.nvidia_base_url:
        fast_semantic.append(
            NemoFastSemanticEngine(
                settings.nemo_config_path,
                base_url=settings.nvidia_base_url,
                model=settings.content_safety_model,
                api_key_env_var=settings.nvidia_api_key_env_var,
            )
        )
    stages.append(RiskAwareStageRouter("fast_semantic", tuple(fast_semantic)))

    deep_judges = []
    generic_deep_judge = _deep_judge_configured(settings)
    if generic_deep_judge:
        deep_judges.append(
            PromptSecurityJudgeEngine(
                base_url=settings.deep_judge_base_url or "",
                model=settings.deep_judge_model or "",
                api_key_env_var=settings.deep_judge_api_key_env_var,
                request_options=_deepseek_options(
                    settings.deep_judge_base_url or "",
                    json_output=True,
                ),
            )
        )
    elif settings.content_safety_model and settings.nvidia_base_url:
        deep_judges.append(
            PromptSecurityJudgeEngine(
                base_url=settings.nvidia_base_url,
                model=settings.content_safety_model,
                api_key_env_var=settings.nvidia_api_key_env_var,
            )
        )
    if settings.topic_control_model and settings.nvidia_base_url:
        deep_judges.append(
            PurposeAwareTopicJudgeEngine(
                base_url=settings.nvidia_base_url,
                model=settings.topic_control_model,
                api_key_env_var=settings.nvidia_api_key_env_var,
            )
        )
    elif generic_deep_judge:
        deep_judges.append(
            PurposeAwareTopicJudgeEngine(
                base_url=settings.deep_judge_base_url or "",
                model=settings.deep_judge_model or "",
                api_key_env_var=settings.deep_judge_api_key_env_var,
                request_options=_deepseek_options(
                    settings.deep_judge_base_url or ""
                ),
            )
        )
    if settings.grounding_model and settings.nvidia_base_url:
        deep_judges.append(
            ContextualGroundingJudgeEngine(
                base_url=settings.nvidia_base_url,
                model=settings.grounding_model,
                api_key_env_var=settings.nvidia_api_key_env_var,
            )
        )
    elif generic_deep_judge:
        deep_judges.append(
            ContextualGroundingJudgeEngine(
                base_url=settings.deep_judge_base_url or "",
                model=settings.deep_judge_model or "",
                api_key_env_var=settings.deep_judge_api_key_env_var,
                request_options=_deepseek_options(
                    settings.deep_judge_base_url or ""
                ),
            )
        )
    if settings.automated_reasoning_endpoint_url:
        deep_judges.append(
            AutomatedReasoningPolicyEngine(
                HTTPAutomatedReasoningProvider(
                    endpoint_url=settings.automated_reasoning_endpoint_url,
                    api_key_env_var=settings.automated_reasoning_api_key_env_var,
                )
            )
        )
    if deep_judges:
        stages.append(RiskAwareStageRouter("deep_judge", tuple(deep_judges)))
    return ModularGuardrailsEngine(tuple(stages))


def create_app(
    *,
    settings: Settings | None = None,
    engine: GuardrailEngine | None = None,
    intent_analyzer: IntentAnalyzer | None = None,
) -> FastAPI:
    configured = settings or Settings.from_env()
    control_plane = ControlPlaneService(
        configured.database_path,
        fast_semantic_configured=bool(
            configured.content_safety_model and configured.nvidia_base_url
        ),
        deep_judge_configured=bool(
            _deep_judge_configured(configured)
            or (
                (
                    configured.topic_control_model
                    or configured.grounding_model
                )
                and configured.nvidia_base_url
            )
            or configured.automated_reasoning_endpoint_url
        ),
        automated_reasoning_configured=bool(
            configured.automated_reasoning_endpoint_url
        ),
    )
    runtime_engine = engine or create_engine(configured)
    service = ModelGuardrailsEngineService(
        runtime_engine,
        control_plane,
    )
    identity = IdentityService(configured.database_path)
    identity_api = IdentityAPI(identity)
    litellm = LiteLLMAdapter(service, control_plane)
    http_adapter = HTTPAdapter(service, control_plane)
    configured_intent_analyzer = intent_analyzer or _intent_analyzer(configured)
    control_plane_api = ControlPlaneAPI(
        control_plane,
        runtime_engine,
        require_user=identity_api.require_user,
        intent_analyzer=configured_intent_analyzer,
    )

    app = FastAPI(
        title="TaskLattice Model Guardrails",
        version="0.0.1",
        docs_url=None,
        redoc_url=None,
    )
    app.include_router(litellm.router)
    app.include_router(http_adapter.router)
    app.include_router(identity_api.router)
    app.include_router(control_plane_api.router)
    app.state.control_plane = control_plane

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    async def ready() -> dict[str, str]:
        return {"status": "ready"}

    if configured.ui_dist_path.is_dir():
        app.mount(
            "/",
            ControlPlaneStaticFiles(directory=configured.ui_dist_path, html=True),
            name="control-plane-ui",
        )

    return app


def _intent_analyzer(settings: Settings) -> IntentAnalyzer | None:
    if not settings.control_plane_ai_base_url or not settings.control_plane_ai_model:
        return None
    if not os.environ.get(settings.control_plane_ai_api_key_env_var, "").strip():
        return None
    return DeepSeekIntentAnalyzer(
        base_url=settings.control_plane_ai_base_url,
        model=settings.control_plane_ai_model,
        api_key_env_var=settings.control_plane_ai_api_key_env_var,
    )


def _deepseek_options(
    base_url: str,
    *,
    json_output: bool = False,
) -> dict[str, object]:
    if urlsplit(base_url).hostname != "api.deepseek.com":
        return {}
    options: dict[str, object] = {"thinking": {"type": "disabled"}}
    if json_output:
        options["response_format"] = {"type": "json_object"}
    return options


def _deep_judge_configured(settings: Settings) -> bool:
    return bool(settings.deep_judge_model and settings.deep_judge_base_url)


app = create_app()
