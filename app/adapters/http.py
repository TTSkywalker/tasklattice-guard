from __future__ import annotations

import time
import uuid
from dataclasses import asdict
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..control_plane.domain import Integration, IntegrationAuthenticationError, ControlPlaneError
from ..control_plane.service import ControlPlaneService
from ..engine.contracts import EvaluationRequest, GuardContentBlock, RequestContext
from ..engine.service import ModelGuardrailsEngineService
from .observability import record_runtime_decision, record_runtime_failure


SENSITIVE_HEADERS = frozenset({"authorization", "cookie", "proxy-authorization", "x-api-key"})


class HTTPContentBlock(BaseModel):
    """Caller-described content; trust is assigned by the adapter, never by the caller."""

    model_config = ConfigDict(extra="forbid")

    id: str | None = Field(default=None, min_length=1, max_length=160)
    text: str = Field(min_length=1, max_length=100_000)
    role: Literal[
        "user_input",
        "query",
        "retrieved_content",
        "grounding_source",
        "tool_output",
        "model_output",
    ]
    source: Literal[
        "user_input",
        "query",
        "retrieved_content",
        "grounding_source",
        "tool_output",
        "model_output",
    ] | None = None
    qualifiers: list[Literal["guard_content", "query", "grounding_source"]] = Field(
        default_factory=list,
        max_length=3,
    )


class HTTPGuardrailRequest(BaseModel):
    """SDK-independent guard request for HTTP and A2A traffic."""

    model_config = ConfigDict(extra="forbid")

    protocol: Literal["http", "a2a"] = "http"
    input_type: Literal["request", "response"] = "request"
    texts: list[str] = Field(default_factory=list, max_length=64)
    content: list[HTTPContentBlock] = Field(default_factory=list, max_length=64)
    model: str | None = None
    method: str | None = None
    path: str | None = None
    host: str | None = None
    attributes: dict[str, str] = Field(default_factory=dict)
    jwt_claims: dict[str, str] = Field(default_factory=dict)
    a2a_operation: str | None = None
    a2a_context_id: str | None = None
    a2a_task_id: str | None = None
    call_id: str | None = Field(default=None, min_length=1, max_length=256)
    messages: list[dict[str, Any]] = Field(default_factory=list)
    output_scope: Literal["interventions", "full"] = "interventions"

    @model_validator(mode="after")
    def exactly_one_content_shape(self):
        if bool(self.texts) == bool(self.content):
            raise ValueError("Provide exactly one of texts or content.")
        block_ids = tuple(
            block.id or f"{self.input_type}:{index}"
            for index, block in enumerate(self.content)
        )
        if len(set(block_ids)) != len(block_ids):
            raise ValueError("Content block identifiers must be unique.")
        for block in self.content:
            if "query" in block.qualifiers and block.role != "query":
                raise ValueError("The query qualifier requires the query role.")
            if (
                "grounding_source" in block.qualifiers
                and block.role not in {"retrieved_content", "grounding_source"}
            ):
                raise ValueError(
                    "The grounding_source qualifier requires a grounding-source role."
                )
        if (
            self.input_type == "response"
            and self.content
            and not any(
                block.role in {"model_output", "tool_output"}
                for block in self.content
            )
        ):
            raise ValueError("Structured response evaluation requires an output block.")
        return self


class HTTPGuardrailResponse(BaseModel):
    decision: Literal["allow", "transform", "block"]
    action: str
    reason: str | None = None
    texts: list[str] = Field(default_factory=list)
    guardrail_id: str | None = None
    guardrail_version: int | None = None
    assignment_id: str | None = None
    findings: list[dict[str, Any]] = Field(default_factory=list)
    trace: list[dict[str, Any]] = Field(default_factory=list)
    mode: Literal["enforce", "detect"] = "enforce"
    assessments: list[dict[str, Any]] = Field(default_factory=list)
    interventions: list[dict[str, Any]] = Field(default_factory=list)
    coverage: dict[str, Any] | None = None
    usage: dict[str, Any] | None = None
    content_results: list[dict[str, Any]] = Field(default_factory=list)
    call_id: str | None = None


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
            started = time.perf_counter()
            integration = self._authorize(x_api_key, payload.protocol)
            phase = "input" if payload.input_type == "request" else "output"
            external_call_id = (
                payload.call_id
                or payload.a2a_task_id
                or payload.a2a_context_id
                or (
                    f"http-{uuid.uuid4().hex}"
                    if payload.input_type == "request"
                    else None
                )
            )
            try:
                decision = await self._service.evaluate(
                    self._to_engine_request(
                        payload,
                        request,
                        integration,
                        external_call_id,
                    )
                )
            except ControlPlaneError as error:
                self._control_plane.record_integration_activity(integration.id, success=True)
                record_runtime_failure(
                    self._control_plane,
                    integration_id=integration.id,
                    protocol=payload.protocol,
                    phase=phase,
                    started=started,
                    outcome="block",
                    detail=str(error),
                )
                return HTTPGuardrailResponse(
                    decision="block",
                    action="reject",
                    reason=str(error),
                    mode="enforce",
                    call_id=external_call_id,
                )
            except Exception as error:
                self._control_plane.record_integration_activity(integration.id, success=False)
                record_runtime_failure(
                    self._control_plane,
                    integration_id=integration.id,
                    protocol=payload.protocol,
                    phase=phase,
                    started=started,
                    outcome="error",
                    detail=f"Guardrail evaluation failed with {type(error).__name__}.",
                )
                raise
            self._control_plane.record_integration_activity(integration.id, success=True)
            record_runtime_decision(
                self._control_plane,
                decision=decision,
                integration_id=integration.id,
                protocol=payload.protocol,
                phase=phase,
                started=started,
                detail=decision.reason or "HTTP interaction evaluated.",
            )
            return HTTPGuardrailResponse(
                decision=decision.decision,
                action=decision.action,
                reason=decision.reason,
                texts=list(decision.texts),
                guardrail_id=decision.guardrail_id,
                guardrail_version=decision.guardrail_version,
                assignment_id=decision.assignment_id,
                findings=[asdict(item) for item in decision.findings],
                trace=[asdict(item) for item in decision.trace],
                mode=decision.mode,
                assessments=[
                    asdict(item)
                    for item in decision.assessments
                    if payload.output_scope == "full" or item.status != "pass"
                ],
                interventions=[asdict(item) for item in decision.interventions],
                coverage=asdict(decision.coverage) if decision.coverage is not None else None,
                usage=(
                    {
                        "module_invocations": decision.usage.module_invocations,
                        "evaluator_invocations": decision.usage.evaluator_invocations,
                        "text_characters": decision.usage.text_characters,
                    }
                    if decision.usage is not None
                    else None
                ),
                content_results=[asdict(item) for item in decision.content_results],
                call_id=external_call_id,
            )

    def _authorize(self, api_key: str | None, protocol: str) -> Integration:
        try:
            return self._control_plane.authenticate_integration(api_key, protocol)
        except IntegrationAuthenticationError as error:
            raise HTTPException(status_code=401, detail="Unauthorized.") from error

    @staticmethod
    def _to_engine_request(
        payload: HTTPGuardrailRequest,
        request: Request,
        integration: Integration,
        external_call_id: str | None = None,
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
            "integration.id": integration.id,
            "auth.principal": integration.id,
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
            content_blocks=_content_blocks(payload),
            context=RequestContext(
                protocol=payload.protocol,
                integration_id=integration.id,
                headers=tuple(sorted(headers.items())),
                jwt_claims=tuple(sorted(payload.jwt_claims.items())),
                fields=tuple(sorted(fields.items())),
            ),
            messages=tuple(payload.messages),
            evidence_scope=payload.output_scope,
            call_id=(
                f"{integration.id}:{external_call_id}"
                if external_call_id
                else None
            ),
        )


def _content_blocks(payload: HTTPGuardrailRequest) -> tuple[GuardContentBlock, ...]:
    blocks: list[GuardContentBlock] = []
    for index, item in enumerate(payload.content):
        qualifiers = set(item.qualifiers)
        if item.role == "query":
            qualifiers.add("query")
        if item.role in {"retrieved_content", "grounding_source"}:
            qualifiers.add("grounding_source")
        if payload.input_type == "request" or item.role in {
            "user_input",
            "tool_output",
            "model_output",
        }:
            qualifiers.add("guard_content")
        source = item.source or {
            "query": "query",
            "retrieved_content": "retrieved_content",
            "grounding_source": "grounding_source",
            "tool_output": "tool_output",
            "model_output": "model_output",
        }.get(item.role, "user_input")
        blocks.append(
            GuardContentBlock(
                id=item.id or f"{payload.input_type}:{index}",
                text=item.text,
                role=item.role,
                trust="untrusted",
                source=source,
                qualifiers=tuple(
                    qualifier
                    for qualifier in ("guard_content", "query", "grounding_source")
                    if qualifier in qualifiers
                ),
            )
        )
    return tuple(blocks)
