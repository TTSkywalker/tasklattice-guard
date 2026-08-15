from __future__ import annotations

import time
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ..control_plane.domain import (
    Integration,
    IntegrationAuthenticationError,
    ControlPlaneError,
)
from ..control_plane.service import ControlPlaneService
from ..runtime.contracts import ProtectionDecision, ProtectionRequest, RequestContext
from ..runtime.service import GuardrailRuntimeService
from ..integrations import LITELLM_GENERIC_GUARDRAIL_ADAPTER_ID
from .http import SENSITIVE_HEADERS
from .observability import record_runtime_decision, record_runtime_failure


class LiteLLMGuardrailRequest(BaseModel):
    """LiteLLM Generic Guardrail API request contract."""

    model_config = ConfigDict(extra="allow")

    input_type: Literal["request", "response"]
    litellm_call_id: str | None = None
    litellm_trace_id: str | None = None
    structured_messages: list[dict[str, Any]] | None = None
    images: list[str] | None = None
    tools: list[dict[str, Any]] | None = None
    texts: list[str] | None = None
    request_data: dict[str, Any] = Field(default_factory=dict)
    request_headers: dict[str, str] | None = None
    litellm_version: str | None = None
    additional_provider_specific_params: dict[str, Any] | None = None
    tool_calls: list[dict[str, Any]] | None = None
    model: str | None = None


class LiteLLMGuardrailResponse(BaseModel):
    action: Literal["NONE", "BLOCKED", "GUARDRAIL_INTERVENED"]
    blocked_reason: str | None = None
    texts: list[str] | None = None
    images: list[str] | None = None
    tools: list[dict[str, Any]] | None = None


class LiteLLMVerificationResponse(BaseModel):
    ready: Literal[True] = True
    adapter_id: Literal["litellm-generic-guardrail"] = (
        LITELLM_GENERIC_GUARDRAIL_ADAPTER_ID
    )
    protocol: Literal["litellm"] = "litellm"
    integration_id: str


class LiteLLMAdapter:
    """Translate LiteLLM's API contract into the engine contract."""

    def __init__(
        self,
        service: GuardrailRuntimeService,
        control_plane: ControlPlaneService,
    ) -> None:
        self._service = service
        self._control_plane = control_plane
        self.router = APIRouter()
        self._register_routes()

    def _register_routes(self) -> None:
        @self.router.post(
            "/runtime/v1/integrations/{integration_id}/verify",
            response_model=LiteLLMVerificationResponse,
        )
        async def verify_connection(
            integration_id: str,
            x_api_key: str | None = Header(default=None),
        ) -> LiteLLMVerificationResponse:
            """Authenticate a LiteLLM Integration without recording runtime traffic."""

            self._authorize(integration_id, x_api_key)
            return LiteLLMVerificationResponse(integration_id=integration_id)

        @self.router.post(
            "/runtime/v1/integrations/{integration_id}/beta/litellm_basic_guardrail_api",
            response_model=LiteLLMGuardrailResponse,
            response_model_exclude_none=True,
        )
        async def apply_guardrail(
            integration_id: str,
            request: LiteLLMGuardrailRequest,
            x_api_key: str | None = Header(default=None),
        ) -> LiteLLMGuardrailResponse:
            started = time.perf_counter()
            integration = self._authorize(integration_id, x_api_key)
            phase = "input" if request.input_type == "request" else "output"
            protection_request = self._to_engine_request(request, integration)
            try:
                decision = await self._service.evaluate(protection_request)
            except ControlPlaneError as error:
                self._control_plane.record_integration_activity(
                    integration.id, phase=phase, success=True
                )
                record_runtime_failure(
                    self._control_plane,
                    integration_id=integration.id,
                    protocol="litellm",
                    phase=phase,
                    started=started,
                    outcome="block",
                    detail=str(error),
                )
                return LiteLLMGuardrailResponse(
                    action="BLOCKED",
                    blocked_reason="No Deployment matches this request.",
                )
            except Exception as error:
                self._control_plane.record_integration_activity(
                    integration.id, phase=phase, success=False
                )
                record_runtime_failure(
                    self._control_plane,
                    integration_id=integration.id,
                    protocol="litellm",
                    phase=phase,
                    started=started,
                    outcome="error",
                    detail=f"Guardrail runtime check failed with {type(error).__name__}.",
                )
                raise
            self._control_plane.record_integration_activity(
                integration.id, phase=phase, success=True
            )
            record_runtime_decision(
                self._control_plane,
                decision=decision,
                integration_id=integration.id,
                protocol="litellm",
                phase=phase,
                started=started,
                detail=decision.reason or "Model interaction evaluated.",
                request=protection_request,
            )
            return self._to_litellm_response(decision)

    def _authorize(
        self, integration_id: str, api_key: str | None
    ) -> Integration:
        try:
            return self._control_plane.authenticate_integration(
                integration_id,
                api_key,
                LITELLM_GENERIC_GUARDRAIL_ADAPTER_ID,
            )
        except IntegrationAuthenticationError as error:
            raise HTTPException(status_code=401, detail="Unauthorized.") from error

    @staticmethod
    def _to_engine_request(
        request: LiteLLMGuardrailRequest,
        integration: Integration,
    ) -> ProtectionRequest:
        headers = {
            str(key).lower(): str(value)
            for key, value in (request.request_headers or {}).items()
            if str(key).lower() not in SENSITIVE_HEADERS
        }
        native_fields = {
            "user_api_key_hash": "litellm.api_key_hash",
            "user_api_key_alias": "litellm.api_key_alias",
            "user_api_key_user_id": "litellm.user_id",
            "user_api_key_user_email": "litellm.user_email",
            "user_api_key_team_id": "litellm.team_id",
            "user_api_key_team_alias": "litellm.team_alias",
            "user_api_key_end_user_id": "litellm.end_user_id",
            "output_sink": "output.sink",
            "content_type": "output.content_type",
            "schema_id": "output.schema_id",
            "tool_name": "tool.name",
            "target_environment": "target.environment",
        }
        fields = {
            target: str(request.request_data[source])
            for source, target in native_fields.items()
            if request.request_data.get(source) is not None
        }
        principal = next(
            (
                fields[key]
                for key in (
                    "litellm.api_key_hash",
                    "litellm.api_key_alias",
                    "litellm.team_id",
                    "litellm.user_id",
                )
                if fields.get(key)
            ),
            integration.id,
        )
        fields.update(
            {
                "protocol": "litellm",
                "integration.id": integration.id,
                "auth.principal": principal,
                "model": str(request.model or request.request_data.get("model") or ""),
                "litellm.operation": request.input_type,
                "http.method": headers.get("x-original-method", "POST").upper(),
                "http.path": headers.get("x-original-uri", ""),
                "http.host": headers.get("x-forwarded-host", headers.get("host", "")),
                "a2a.version": headers.get("a2a-version", ""),
                "a2a.extensions": headers.get("a2a-extensions", ""),
            }
        )

        return ProtectionRequest(
            phase="input" if request.input_type == "request" else "output",
            texts=tuple(request.texts or ()),
            context=RequestContext(
                protocol="litellm",
                integration_id=integration.id,
                headers=tuple(sorted(headers.items())),
                fields=tuple(sorted(fields.items())),
            ),
            call_id=(
                f"{integration.id}:{request.litellm_call_id}"
                if request.litellm_call_id
                else None
            ),
            messages=tuple(request.structured_messages or ()),
        )

    @staticmethod
    def _to_litellm_response(
        decision: ProtectionDecision,
    ) -> LiteLLMGuardrailResponse:
        if decision.decision == "block":
            return LiteLLMGuardrailResponse(
                action="BLOCKED",
                blocked_reason=decision.reason,
            )
        if decision.decision == "transform":
            return LiteLLMGuardrailResponse(
                action="GUARDRAIL_INTERVENED",
                texts=list(decision.texts),
            )
        return LiteLLMGuardrailResponse(action="NONE")
