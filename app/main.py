from __future__ import annotations

import os
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException

from .adapters.http import HTTPAdapter
from .adapters.litellm import LiteLLMAdapter
from .config import Settings
from .control_plane.api import ControlPlaneAPI
from .control_plane.chat_model import (
    OpenAICompatibleChatModel,
    PlaygroundChatModel,
)
from .control_plane.intent_analyzer import DeepSeekIntentAnalyzer, IntentAnalyzer
from .control_plane.nemo_compiler import NeMoConfigCompiler
from .control_plane.service import ControlPlaneService
from .identity import IdentityAPI, IdentityService
from .nemo.action_registry import ActionProviders, action_providers
from .nemo.actions import local_action_providers
from .nemo.actions.automated_reasoning import (
    HTTPAutomatedReasoningProvider,
    ReasoningActionProvider,
)
from .nemo.actions.contracts import ActionProvider
from .nemo.actions.grounding import GroundingActionProvider
from .nemo.actions.topic import TopicJudgeActionProvider
from .nemo.builtin_policies import prompt_catalog_yaml
from .nemo.registry import NeMoRuntimeRegistry
from .nemo.runtime import NeMoRuntime
from .persistence import Database
from .runtime.contracts import NeMoPolicyRuntime
from .runtime.service import GuardrailRuntimeService
from .ui import ControlPlaneStaticFiles


def create_runtime(
    settings: Settings,
    control_plane: ControlPlaneService | None = None,
) -> NeMoRuntime:
    store = control_plane or _create_policy_plane(settings)
    registry = NeMoRuntimeRegistry(
        store,
        create_action_providers(settings),
        max_concurrency_per_guardrail=(
            settings.runtime_max_concurrency_per_guardrail
        ),
    )
    store.bind_nemo_runtime(validator=registry.validate, reloader=registry.reload)
    return NeMoRuntime(registry)


def create_action_providers(settings: Settings) -> ActionProviders:
    """Build direct, versioned providers registered as NeMo Actions."""
    components: list[ActionProvider] = list(local_action_providers())
    if settings.topic_control_model and settings.nvidia_base_url:
        components.append(
            TopicJudgeActionProvider(
                base_url=settings.nvidia_base_url,
                model=settings.topic_control_model,
                api_key_env_var=settings.nvidia_api_key_env_var,
            )
        )
    if settings.grounding_model and settings.nvidia_base_url:
        components.append(
            GroundingActionProvider(
                base_url=settings.nvidia_base_url,
                model=settings.grounding_model,
                api_key_env_var=settings.nvidia_api_key_env_var,
            )
        )
    if settings.automated_reasoning_endpoint_url:
        components.append(
            ReasoningActionProvider(
                HTTPAutomatedReasoningProvider(
                    endpoint_url=settings.automated_reasoning_endpoint_url,
                    api_key_env_var=settings.automated_reasoning_api_key_env_var,
                )
            )
        )
    return action_providers(*components)


def create_app(
    *,
    settings: Settings | None = None,
    engine: NeMoPolicyRuntime | None = None,
    intent_analyzer: IntentAnalyzer | None = None,
    playground_chat_models: tuple[PlaygroundChatModel, ...] | None = None,
) -> FastAPI:
    configured = settings or Settings.from_env()
    tracer_provider = _configure_telemetry(configured)
    database = Database(configured.database_locator)
    control_plane = _create_policy_plane(configured, database=database)
    if engine is None:
        runtime_engine: NeMoPolicyRuntime = create_runtime(configured, control_plane)
    else:
        # Explicit injection is reserved for tests and embedding. Production
        # construction always installs the version-pinned NeMo runtime above.
        runtime_engine = engine
    service = GuardrailRuntimeService(
        runtime_engine,
        control_plane,
    )
    identity = IdentityService(database)
    identity_api = IdentityAPI(identity)
    litellm = LiteLLMAdapter(service, control_plane)
    http_adapter = HTTPAdapter(service, control_plane)
    configured_intent_analyzer = intent_analyzer or _intent_analyzer(configured)
    configured_playground_models = (
        playground_chat_models
        if playground_chat_models is not None
        else _playground_chat_models(configured)
    )
    control_plane_api = ControlPlaneAPI(
        control_plane,
        runtime_engine,
        require_user=identity_api.require_user,
        intent_analyzer=configured_intent_analyzer,
        playground_chat_models=configured_playground_models,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            shutdown = getattr(runtime_engine, "shutdown", None)
            if shutdown is not None:
                await shutdown()
            database.dispose()
            if tracer_provider is not None:
                tracer_provider.shutdown()

    app = FastAPI(
        title="TaskLattice Model Guardrails",
        version="0.1.0",
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
    async def ready() -> dict[str, object]:
        runtime_readiness = getattr(runtime_engine, "readiness", None)
        if runtime_readiness is not None:
            detail = runtime_readiness()
            if not bool(detail.get("ready")):
                raise HTTPException(status_code=503, detail=detail)
            return detail
        runtime_ready = getattr(runtime_engine, "ready", None)
        if runtime_ready is not None and not runtime_ready():
            raise HTTPException(
                status_code=503,
                detail={
                    "ready": False,
                    "status": "not_ready",
                    "reason": "runtime_not_prewarmed",
                },
            )
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


def _playground_chat_models(settings: Settings) -> tuple[PlaygroundChatModel, ...]:
    base_url = settings.playground_chat_base_url
    model = settings.playground_chat_model
    api_key_env_var = settings.playground_chat_api_key_env_var
    if (
        not base_url
        or not model
        or not os.environ.get(api_key_env_var, "").strip()
    ):
        return ()
    provider = (
        "DeepSeek"
        if urlsplit(base_url).hostname == "api.deepseek.com"
        else "OpenAI compatible"
    )
    return (
        OpenAICompatibleChatModel(
            model_id="playground-chat",
            provider=provider,
            base_url=base_url,
            model=model,
            api_key_env_var=api_key_env_var,
            request_options=_deepseek_options(base_url),
        ),
    )


def _create_policy_plane(
    settings: Settings, *, database: Database | None = None
) -> ControlPlaneService:
    return ControlPlaneService(
        database or settings.database_locator,
        public_runtime_base_url=settings.public_runtime_base_url,
        fast_semantic_configured=bool(
            settings.content_safety_model and settings.nvidia_base_url
        ),
        specialized_evaluator_risks=_specialized_evaluator_risks(settings),
        automated_reasoning_configured=bool(
            settings.automated_reasoning_endpoint_url
        ),
        nemo_compiler=_nemo_compiler(settings),
        runtime_p95_budget_ms=settings.runtime_p95_budget_ms,
        runtime_p99_budget_ms=settings.runtime_p99_budget_ms,
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
    jailbreak_detection = None
    if settings.jailbreak_detection_nim_base_url:
        jailbreak_detection = {
            "nim_base_url": settings.jailbreak_detection_nim_base_url,
            "nim_server_endpoint": settings.jailbreak_detection_nim_server_endpoint,
            "api_key_env_var": settings.jailbreak_detection_api_key_env_var,
        }
    return NeMoConfigCompiler(
        models=tuple(models),
        builtin_prompts_yaml=prompt_catalog_yaml(),
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


def _deepseek_options(base_url: str) -> dict[str, object]:
    if urlsplit(base_url).hostname != "api.deepseek.com":
        return {}
    return {"thinking": {"type": "disabled"}}


def _specialized_evaluator_risks(settings: Settings) -> frozenset[str]:
    risks: set[str] = set()
    if settings.topic_control_model and settings.nvidia_base_url:
        risks.update({"topic_control", "company_policy"})
    if settings.jailbreak_detection_nim_base_url:
        risks.update({"prompt_injection", "jailbreak"})
    if settings.grounding_model and settings.nvidia_base_url:
        risks.add("contextual_grounding")
    if settings.automated_reasoning_endpoint_url:
        risks.add("automated_reasoning")
    return frozenset(risks)


app = create_app()
