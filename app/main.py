from __future__ import annotations

import os
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException

from .adapters.http import HTTPAdapter
from .adapters.litellm import LiteLLMAdapter
from .config import Settings
from .control_plane.api import ControlPlaneAPI
from .control_plane.intent_analyzer import DeepSeekIntentAnalyzer, IntentAnalyzer
from .control_plane.nemo_compiler import NeMoConfigCompiler
from .control_plane.service import ControlPlaneService
from .engine.contracts import GuardrailEngine, GuardrailStage
from .engine.automated_reasoning import (
    AutomatedReasoningPolicyEngine,
    HTTPAutomatedReasoningProvider,
)
from .engine.contextual_grounding import ContextualGroundingJudgeEngine
from .engine.fast_pass import FastPassEngine
from .engine.migration import RuntimeRolloutCoordinator
from .engine.nemo_runtime import (
    NeMoGuardrailsEngine,
    NeMoRailsRegistry,
)
from .engine.prompt_security import PromptSecurityFastEngine, PromptSecurityJudgeEngine
from .engine.service import ModelGuardrailsEngineService
from .engine.topic_judge import PurposeAwareTopicJudgeEngine
from .identity import IdentityAPI, IdentityService
from .ui import ControlPlaneStaticFiles


def create_engine(
    settings: Settings,
    control_plane: ControlPlaneService | None = None,
) -> NeMoGuardrailsEngine:
    store = control_plane or _create_control_plane(settings)
    registry = NeMoRailsRegistry(
        store,
        create_action_stages(settings),
        max_concurrency_per_guardrail=(
            settings.runtime_max_concurrency_per_guardrail
        ),
    )
    store.bind_nemo_runtime(validator=registry.validate, reloader=registry.reload)
    return NeMoGuardrailsEngine(registry)


def create_action_stages(settings: Settings) -> tuple[GuardrailStage, ...]:
    """Build detector/provider implementations registered only as NeMo Actions."""
    stages: list[GuardrailStage] = [FastPassEngine(), PromptSecurityFastEngine()]
    generic_deep_judge = _deep_judge_configured(settings)
    if generic_deep_judge:
        stages.append(
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
        stages.append(
            PromptSecurityJudgeEngine(
                base_url=settings.nvidia_base_url,
                model=settings.content_safety_model,
                api_key_env_var=settings.nvidia_api_key_env_var,
            )
        )
    if settings.topic_control_model and settings.nvidia_base_url:
        stages.append(
            PurposeAwareTopicJudgeEngine(
                base_url=settings.nvidia_base_url,
                model=settings.topic_control_model,
                api_key_env_var=settings.nvidia_api_key_env_var,
            )
        )
    elif generic_deep_judge:
        stages.append(
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
        stages.append(
            ContextualGroundingJudgeEngine(
                base_url=settings.nvidia_base_url,
                model=settings.grounding_model,
                api_key_env_var=settings.nvidia_api_key_env_var,
            )
        )
    elif generic_deep_judge:
        stages.append(
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
        stages.append(
            AutomatedReasoningPolicyEngine(
                HTTPAutomatedReasoningProvider(
                    endpoint_url=settings.automated_reasoning_endpoint_url,
                    api_key_env_var=settings.automated_reasoning_api_key_env_var,
                )
            )
        )
    return tuple(stages)


def create_legacy_engine(settings: Settings) -> GuardrailEngine:
    """Lazily construct the former runtime only for time-bounded migration modes."""
    from .engine.dag import ModularGuardrailsEngine
    from .engine.nemo import NemoFastSemanticEngine
    from .engine.risk_router import RiskAwareStageRouter

    action_stages = create_action_stages(settings)
    deterministic = next(item for item in action_stages if item.stage == "deterministic")
    fast = [item for item in action_stages if item.stage == "fast_semantic"]
    if settings.content_safety_model and settings.nvidia_base_url:
        fast.append(
            NemoFastSemanticEngine(
                settings.nemo_config_path,
                base_url=settings.nvidia_base_url,
                model=settings.content_safety_model,
                api_key_env_var=settings.nvidia_api_key_env_var,
            )
        )
    stages: list[GuardrailStage] = [
        deterministic,
        RiskAwareStageRouter("fast_semantic", tuple(fast)),
    ]
    deep = tuple(item for item in action_stages if item.stage == "deep_judge")
    if deep:
        stages.append(RiskAwareStageRouter("deep_judge", deep))
    return ModularGuardrailsEngine(tuple(stages))


def create_app(
    *,
    settings: Settings | None = None,
    engine: GuardrailEngine | None = None,
    intent_analyzer: IntentAnalyzer | None = None,
) -> FastAPI:
    configured = settings or Settings.from_env()
    tracer_provider = _configure_telemetry(configured)
    control_plane = _create_control_plane(configured)
    if engine is None:
        nemo_engine = create_engine(configured, control_plane)
        runtime_engine: GuardrailEngine = RuntimeRolloutCoordinator(
            nemo_engine,
            lambda: create_legacy_engine(configured),
            control_plane,
            transition_enabled=configured.legacy_migration_enabled,
        )
    else:
        # Explicit injection is reserved for tests/embedding; normal application
        # construction always installs the NeMo rollout coordinator above.
        runtime_engine = engine
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

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            shutdown = getattr(runtime_engine, "shutdown", None)
            if shutdown is not None:
                await shutdown()
            if tracer_provider is not None:
                tracer_provider.shutdown()

    app = FastAPI(
        title="TaskLattice Model Guardrails",
        version="0.0.1",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.include_router(litellm.router)
    app.include_router(http_adapter.router)
    app.include_router(identity_api.router)
    app.include_router(control_plane_api.router)
    app.state.control_plane = control_plane
    app.state.guardrail_engine = runtime_engine

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    async def ready() -> dict[str, str]:
        runtime_ready = getattr(runtime_engine, "ready", None)
        if runtime_ready is not None and not runtime_ready():
            raise HTTPException(status_code=503, detail="NeMo runtime is not prewarmed.")
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


def _create_control_plane(settings: Settings) -> ControlPlaneService:
    return ControlPlaneService(
        settings.database_path,
        fast_semantic_configured=bool(
            settings.content_safety_model and settings.nvidia_base_url
        ),
        deep_judge_configured=bool(
            _deep_judge_configured(settings)
            or (
                (settings.topic_control_model or settings.grounding_model)
                and settings.nvidia_base_url
            )
            or settings.automated_reasoning_endpoint_url
        ),
        automated_reasoning_configured=bool(
            settings.automated_reasoning_endpoint_url
        ),
        nemo_compiler=_nemo_compiler(settings),
        runtime_p95_budget_ms=settings.runtime_p95_budget_ms,
        runtime_p99_budget_ms=settings.runtime_p99_budget_ms,
        legacy_migration_enabled=settings.legacy_migration_enabled,
    )


def _nemo_compiler(settings: Settings) -> NeMoConfigCompiler:
    models: list[dict[str, object]] = []
    if settings.content_safety_model and settings.nvidia_base_url:
        models.append(
            {
                "type": "content_safety",
                "engine": "nim",
                "model": settings.content_safety_model,
                "api_key_env_var": settings.nvidia_api_key_env_var,
                "parameters": {"base_url": settings.nvidia_base_url},
            }
        )
    if settings.topic_control_model and settings.nvidia_base_url:
        models.append(
            {
                "type": "topic_control",
                "engine": "nim",
                "model": settings.topic_control_model,
                "api_key_env_var": settings.nvidia_api_key_env_var,
                "parameters": {"base_url": settings.nvidia_base_url},
            }
        )
    prompts_path = settings.nemo_config_path / "prompts.yml"
    prompts_yaml = prompts_path.read_text() if prompts_path.is_file() else ""
    jailbreak_detection = None
    if settings.jailbreak_detection_nim_base_url:
        jailbreak_detection = {
            "nim_base_url": settings.jailbreak_detection_nim_base_url,
            "nim_server_endpoint": "classify",
            "api_key_env_var": settings.jailbreak_detection_api_key_env_var,
        }
    return NeMoConfigCompiler(
        models=tuple(models),
        profile_prompts_yaml=prompts_yaml,
        jailbreak_detection=jailbreak_detection,
        otel_enabled=settings.otel_enabled,
    )


def _configure_telemetry(settings: Settings):
    if not settings.otel_enabled or not settings.otel_exporter_endpoint:
        return None
    # NeMo's content-capture environment switch has precedence over RailsConfig.
    # Force it off so prompts/responses cannot leave the process through tracing.
    os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = "false"
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    current = trace.get_tracer_provider()
    if isinstance(current, TracerProvider):
        # An existing SDK provider is owned by the embedding process. Reuse it
        # without registering another exporter or shutting it down ourselves.
        return None
    provider = TracerProvider(
        resource=Resource.create({"service.name": "tasklattice-guard"})
    )
    exporter = OTLPSpanExporter(
        endpoint=_otlp_trace_endpoint(settings.otel_exporter_endpoint)
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return provider


def _otlp_trace_endpoint(endpoint: str) -> str:
    normalized = endpoint.rstrip("/")
    return normalized if normalized.endswith("/v1/traces") else f"{normalized}/v1/traces"


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
