from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from runner.toolkit.nemo.action_registry import action_providers
from runner.toolkit.nemo.registry import NeMoRuntimeRegistry
from runner.toolkit.nemo.runtime import NeMoRuntime
from runner.toolkit.runtime.context import CallContextStore
from runner.toolkit.runtime.service import GuardrailRuntimeService

from .api import RunnerAPI
from .artifact_store import ArtifactStore
from .compiler import DefaultRunnerCompiler
from .call_context import RedisCallContextStore
from .config import RunnerSettings
from .control_client import RunnerControlClient
from .draft_preview import DraftPreviewRuntime
from .metrics import RunnerMetrics
from .providers import runtime_action_providers
from .telemetry import RuntimeTelemetryExporter


def create_app(settings: RunnerSettings | None = None) -> FastAPI:
    configured = settings or RunnerSettings.from_env()
    store = ArtifactStore(configured.artifact_public_key_path, configured.artifact_state_path)
    providers = action_providers(*runtime_action_providers(configured))
    registry = NeMoRuntimeRegistry(
        store,
        providers,
        max_concurrency_per_guardrail=configured.max_concurrency,
    )
    store.attach_registry(registry)
    engine = NeMoRuntime(registry)
    contexts = (
        RedisCallContextStore(configured.call_context_redis_url)
        if configured.call_context_redis_url
        else CallContextStore()
    )
    runtime = GuardrailRuntimeService(engine, store, contexts=contexts)
    metrics = RunnerMetrics(configured.max_concurrency)
    telemetry = RuntimeTelemetryExporter(
        configured.telemetry_endpoint,
        configured.controller_token,
        configured.artifact_state_path,
        configured.telemetry_batch_size,
        configured.runner_id,
    )
    control = RunnerControlClient(configured, store, metrics)
    draft_previews = DraftPreviewRuntime(
        DefaultRunnerCompiler(configured),
        providers,
        max_concurrency_per_guardrail=min(configured.max_concurrency, 8),
    ) if configured.compiler_capable else None
    runtime_api = RunnerAPI(
        runtime,
        store,
        metrics,
        telemetry,
        configured.runner_id,
        configured.controller_token,
        configured.runtime_log_encryption_key,
        draft_previews,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        control_task = asyncio.create_task(control.run(), name="runner-control")
        telemetry_task = asyncio.create_task(telemetry.run(), name="runtime-telemetry")
        try:
            yield
        finally:
            await control.stop()
            await telemetry.stop()
            control_task.cancel()
            telemetry_task.cancel()
            await asyncio.gather(control_task, telemetry_task, return_exceptions=True)
            if draft_previews is not None:
                await draft_previews.shutdown()
            await engine.shutdown()

    app = FastAPI(
        title="TaskLattice Guard Runner",
        version="0.2.0",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.include_router(runtime_api.router)

    @app.get("/health/live")
    async def live():
        return {"status": "ok", "component": "guard-runner"}

    @app.get("/health/ready")
    async def ready():
        detail = registry.readiness()
        # A temporary Controller outage must not remove a Runner that already
        # holds a verified last-known-good generation from the runtime Service.
        # Fresh Pods still stay unready until their first successful sync.
        ready_now = control.synchronized and bool(detail["ready"])
        response = {
            **detail,
            "ready": ready_now,
            "component": "guard-runner",
            "controller_connected": control.connected,
            "desired_state_synchronized": control.synchronized,
            "applied_generation": store.generation,
            "compiler_capable": configured.compiler_capable,
        }
        if not ready_now:
            raise HTTPException(status_code=503, detail=response)
        return response

    @app.get("/metrics")
    async def prometheus_metrics():
        return Response(generate_latest(metrics.registry), media_type=CONTENT_TYPE_LATEST)

    app.state.artifact_store = store
    app.state.runner_control = control
    return app
app = create_app()
