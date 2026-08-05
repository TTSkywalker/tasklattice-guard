from __future__ import annotations

import hmac

from fastapi import FastAPI, Header, HTTPException

from .config import Settings
from .contracts import GenericGuardrailRequest, GenericGuardrailResponse
from .runtime import GuardrailsRuntime, NemoGuardrailsRuntime
from .service import ModelGuardrailsService


def create_app(
    *,
    settings: Settings | None = None,
    runtime: GuardrailsRuntime | None = None,
) -> FastAPI:
    configured = settings or Settings.from_env()
    guardrails_runtime = runtime or NemoGuardrailsRuntime(
        configured.profile_path,
        nvidia_base_url=configured.nvidia_base_url,
        content_safety_model=configured.content_safety_model,
        topic_control_model=configured.topic_control_model,
        nvidia_api_key_env_var=configured.nvidia_api_key_env_var,
    )
    service = ModelGuardrailsService(guardrails_runtime)

    app = FastAPI(
        title="TaskLattice Model Guardrails",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
    )

    def authorize(x_api_key: str | None) -> None:
        if not x_api_key or not hmac.compare_digest(x_api_key, configured.api_key):
            raise HTTPException(status_code=401, detail="Unauthorized.")

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    async def ready() -> dict[str, str]:
        return {"status": "ready"}

    @app.post(
        "/beta/litellm_basic_guardrail_api",
        response_model=GenericGuardrailResponse,
        response_model_exclude_none=True,
    )
    async def apply_guardrail(
        request: GenericGuardrailRequest,
        x_api_key: str | None = Header(default=None),
    ) -> GenericGuardrailResponse:
        authorize(x_api_key)
        return await service.apply(request)

    return app


app = create_app()
