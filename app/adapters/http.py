from __future__ import annotations

import time
import uuid
from dataclasses import asdict
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..control_plane.domain import Integration, IntegrationAuthenticationError, ControlPlaneError
from ..control_plane.service import ControlPlaneService
from ..runtime.contracts import ProtectionRequest, GuardContentBlock, RequestContext
from ..runtime.service import GuardrailRuntimeService
from ..integrations import (
    A2A_GUARD_ADAPTER_ID,
    GENERIC_HTTP_GUARD_ADAPTER_ID,
)
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
    source_id: str | None = Field(default=None, min_length=1, max_length=256)
    source_type: str | None = Field(default=None, min_length=1, max_length=64)
    tool_name: str | None = Field(default=None, min_length=1, max_length=256)
    retrieval_index: int | None = Field(default=None, ge=0, le=1_000_000)
    provenance_id: str | None = Field(default=None, min_length=1, max_length=256)
    mime_type: str | None = Field(default=None, min_length=1, max_length=128)
    origin_hash: str | None = Field(
        default=None,
        min_length=16,
        max_length=128,
        pattern=r"^[A-Za-z0-9:_-]+$",
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
    # These claims are assertions made by the API-key-authenticated Integration.
    # Public callers must not be allowed to call this endpoint with the
    # Integration credential directly.
    jwt_claims: dict[str, str] = Field(default_factory=dict)
    output_sink: Literal[
        "display",
        "markdown",
        "html",
        "sql",
        "shell",
        "url",
        "json",
        "tool_argument",
    ] | None = None
    content_type: str | None = Field(default=None, min_length=1, max_length=128)
    schema_id: str | None = Field(default=None, min_length=1, max_length=256)
    tool_name: str | None = Field(default=None, min_length=1, max_length=256)
    target_environment: str | None = Field(default=None, min_length=1, max_length=128)
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
            raise ValueError("A structured response check requires an output block.")
        return self


class HTTPGuardrailResponse(BaseModel):
    decision: Literal["allow", "transform", "block"]
    action: str
    reason: str | None = None
    texts: list[str] = Field(default_factory=list)
    guardrail_id: str | None = None
    guardrail_version: int | None = None
    deployment_id: str | None = None
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
        service: GuardrailRuntimeService,
        control_plane: ControlPlaneService,
    ) -> None:
        self._service = service
        self._control_plane = control_plane
        self.router = APIRouter()
        self._register_routes()

    def _register_routes(self) -> None:
        @self.router.post(
            "/runtime/v1/integrations/{integration_id}/guardrails/evaluate",
            response_model=HTTPGuardrailResponse,
        )
        async def evaluate(
            integration_id: str,
            payload: HTTPGuardrailRequest,
            request: Request,
            x_api_key: str | None = Header(default=None),
        ) -> HTTPGuardrailResponse:
            started = time.perf_counter()
            integration = self._authorize(
                integration_id, x_api_key, payload.protocol
            )
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
                self._control_plane.record_integration_activity(
                    integration.id, phase=phase, success=True
                )
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
                self._control_plane.record_integration_activity(
                    integration.id, phase=phase, success=False
                )
                record_runtime_failure(
                    self._control_plane,
                    integration_id=integration.id,
                    protocol=payload.protocol,
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
                deployment_id=decision.deployment_id,
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

    def _authorize(
        self, integration_id: str, api_key: str | None, protocol: str
    ) -> Integration:
        try:
            adapter_id = (
                A2A_GUARD_ADAPTER_ID
                if protocol == "a2a"
                else GENERIC_HTTP_GUARD_ADAPTER_ID
            )
            return self._control_plane.authenticate_integration(
                integration_id, api_key, adapter_id
            )
        except IntegrationAuthenticationError as error:
            raise HTTPException(status_code=401, detail="Unauthorized.") from error

    @staticmethod
    def _to_engine_request(
        payload: HTTPGuardrailRequest,
        request: Request,
        integration: Integration,
        external_call_id: str | None = None,
    ) -> ProtectionRequest:
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
        trusted_output_facts = {
            "output.sink": payload.output_sink,
            "output.content_type": payload.content_type,
            "output.schema_id": payload.schema_id,
            "tool.name": payload.tool_name,
            "target.environment": payload.target_environment,
        }
        fields.update(
            {
                key: value
                for key, value in trusted_output_facts.items()
                if value is not None
            }
        )
        if payload.jwt_claims:
            fields["auth.claim_source"] = "integration_asserted"
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
        return ProtectionRequest(
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
                metadata=tuple(
                    (key, str(value))
                    for key, value in (
                        ("source_id", item.source_id),
                        ("source_type", item.source_type),
                        ("tool_name", item.tool_name),
                        ("retrieval_index", item.retrieval_index),
                        ("provenance_id", item.provenance_id),
                        ("mime_type", item.mime_type),
                        ("origin_hash", item.origin_hash),
                    )
                    if value is not None
                ),
            )
        )
    return tuple(blocks)
