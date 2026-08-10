from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ..control_plane.domain import (
    Gateway,
    GatewayAuthenticationError,
    ControlPlaneError,
)
from ..control_plane.service import ControlPlaneService
from ..engine.contracts import EvaluationDecision, EvaluationRequest, RequestContext
from ..engine.service import ModelGuardrailsEngineService
from .http import SENSITIVE_HEADERS


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


class LiteLLMAdapter:
    """Translate LiteLLM's API contract into the Engine contract."""

    def __init__(
        self,
        service: ModelGuardrailsEngineService,
        control_plane: ControlPlaneService,
    ) -> None:
        self._service = service
        self._control_plane = control_plane
        self.router = APIRouter()
        self._register_routes()

    def _register_routes(self) -> None:
        @self.router.post(
            "/beta/litellm_basic_guardrail_api",
            response_model=LiteLLMGuardrailResponse,
            response_model_exclude_none=True,
        )
        async def apply_guardrail(
            request: LiteLLMGuardrailRequest,
            x_api_key: str | None = Header(default=None),
        ) -> LiteLLMGuardrailResponse:
            gateway = self._authorize(x_api_key)
            try:
                decision = await self._service.evaluate(
                    self._to_engine_request(request, gateway)
                )
            except ControlPlaneError:
                self._control_plane.record_gateway_activity(gateway.id, success=True)
                return LiteLLMGuardrailResponse(
                    action="BLOCKED",
                    blocked_reason="No Protected Workload matches this request.",
                )
            except Exception:
                self._control_plane.record_gateway_activity(gateway.id, success=False)
                raise
            self._control_plane.record_gateway_activity(gateway.id, success=True)
            self._control_plane.record_decision(
                outcome=decision.decision,
                profile_id=decision.profile_id,
                workload_id=decision.workload_id,
                risk=decision.findings[0].risk if decision.findings else None,
                detail=decision.reason or "Model interaction evaluated.",
            )
            return self._to_litellm_response(decision)

    def _authorize(self, api_key: str | None) -> Gateway:
        try:
            return self._control_plane.authenticate_gateway(api_key, "litellm")
        except GatewayAuthenticationError as error:
            raise HTTPException(status_code=401, detail="Unauthorized.") from error

    @staticmethod
    def _to_engine_request(
        request: LiteLLMGuardrailRequest,
        gateway: Gateway,
    ) -> EvaluationRequest:
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
            gateway.id,
        )
        fields.update(
            {
                "protocol": "litellm",
                "integration.id": gateway.id,
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

        return EvaluationRequest(
            phase="input" if request.input_type == "request" else "output",
            texts=tuple(request.texts or ()),
            context=RequestContext(
                gateway="litellm",
                gateway_id=gateway.id,
                headers=tuple(sorted(headers.items())),
                fields=tuple(sorted(fields.items())),
            ),
            call_id=(
                f"{gateway.id}:{request.litellm_call_id}"
                if request.litellm_call_id
                else None
            ),
            messages=tuple(request.structured_messages or ()),
        )

    @staticmethod
    def _to_litellm_response(
        decision: EvaluationDecision,
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
