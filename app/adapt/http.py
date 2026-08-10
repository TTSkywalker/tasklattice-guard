from __future__ import annotations

from dataclasses import asdict
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from ..control_plane.domain import Gateway, GatewayAuthenticationError, ControlPlaneError
from ..control_plane.service import ControlPlaneService
from ..engine.contracts import EvaluationRequest, RequestContext
from ..engine.service import ModelGuardrailsEngineService


SENSITIVE_HEADERS = frozenset({"authorization", "cookie", "proxy-authorization", "x-api-key"})


class HTTPGuardrailRequest(BaseModel):
    """SDK-independent guard request for HTTP and A2A traffic."""

    model_config = ConfigDict(extra="forbid")

    protocol: Literal["http", "a2a"] = "http"
    input_type: Literal["request", "response"] = "request"
    texts: list[str] = Field(min_length=1)
    model: str | None = None
    method: str | None = None
    path: str | None = None
    host: str | None = None
    attributes: dict[str, str] = Field(default_factory=dict)
    jwt_claims: dict[str, str] = Field(default_factory=dict)
    a2a_operation: str | None = None
    a2a_context_id: str | None = None
    a2a_task_id: str | None = None
    messages: list[dict[str, Any]] = Field(default_factory=list)


class HTTPGuardrailResponse(BaseModel):
    decision: Literal["allow", "transform", "block"]
    action: str
    reason: str | None = None
    texts: list[str] = Field(default_factory=list)
    safe_id: str | None = None
    safe_revision: int | None = None
    workload_id: str | None = None
    findings: list[dict[str, Any]] = Field(default_factory=list)
    trace: list[dict[str, Any]] = Field(default_factory=list)


class HTTPAdapter:
    """Normalize plain HTTP and A2A request facts into the engine contract."""

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
            "/v1/guardrails/evaluate",
            response_model=HTTPGuardrailResponse,
        )
        async def evaluate(
            payload: HTTPGuardrailRequest,
            request: Request,
            x_api_key: str | None = Header(default=None),
        ) -> HTTPGuardrailResponse:
            gateway = self._authorize(x_api_key, payload.protocol)
            try:
                decision = await self._service.evaluate(
                    self._to_engine_request(payload, request, gateway)
                )
            except ControlPlaneError as error:
                self._control_plane.record_gateway_activity(gateway.id, success=True)
                return HTTPGuardrailResponse(
                    decision="block",
                    action="reject",
                    reason=str(error),
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
                detail=decision.reason or "HTTP interaction evaluated.",
            )
            return HTTPGuardrailResponse(
                decision=decision.decision,
                action=decision.action,
                reason=decision.reason,
                texts=list(decision.texts),
                safe_id=decision.profile_id,
                safe_revision=decision.profile_revision,
                workload_id=decision.workload_id,
                findings=[asdict(item) for item in decision.findings],
                trace=[asdict(item) for item in decision.trace],
            )

    def _authorize(self, api_key: str | None, protocol: str) -> Gateway:
        try:
            return self._control_plane.authenticate_gateway(api_key, protocol)
        except GatewayAuthenticationError as error:
            raise HTTPException(status_code=401, detail="Unauthorized.") from error

    @staticmethod
    def _to_engine_request(
        payload: HTTPGuardrailRequest,
        request: Request,
        gateway: Gateway,
    ) -> EvaluationRequest:
        headers = {
            key.lower(): value
            for key, value in request.headers.items()
            if key.lower() not in SENSITIVE_HEADERS
        }
        method = (payload.method or headers.get("x-original-method") or request.method).upper()
        path = payload.path or headers.get("x-original-uri") or request.url.path
        host = payload.host or headers.get("x-forwarded-host") or request.url.hostname or ""
        fields = {
            **{str(key): str(value) for key, value in payload.attributes.items()},
            "protocol": payload.protocol,
            "integration.id": gateway.id,
            "auth.principal": gateway.id,
            "http.method": method,
            "http.path": path,
            "http.host": host,
            "model": payload.model or "",
        }
        if payload.protocol == "a2a":
            fields.update(
                {
                    "a2a.version": headers.get("a2a-version", ""),
                    "a2a.extensions": headers.get("a2a-extensions", ""),
                    "a2a.operation": payload.a2a_operation or "",
                    "a2a.context_id": payload.a2a_context_id or "",
                    "a2a.task_id": payload.a2a_task_id or "",
                }
            )
        return EvaluationRequest(
            phase="input" if payload.input_type == "request" else "output",
            texts=tuple(payload.texts),
            context=RequestContext(
                gateway=payload.protocol,
                gateway_id=gateway.id,
                headers=tuple(sorted(headers.items())),
                jwt_claims=tuple(sorted(payload.jwt_claims.items())),
                fields=tuple(sorted(fields.items())),
            ),
            messages=tuple(payload.messages),
        )
