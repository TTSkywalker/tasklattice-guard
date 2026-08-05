from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class GenericGuardrailRequest(BaseModel):
    """LiteLLM 1.86 Generic Guardrail API request contract."""

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


class GenericGuardrailResponse(BaseModel):
    action: Literal["NONE", "BLOCKED", "GUARDRAIL_INTERVENED"]
    blocked_reason: str | None = None
    texts: list[str] | None = None
    images: list[str] | None = None
    tools: list[dict[str, Any]] | None = None


class RailResult(BaseModel):
    status: Literal["PASSED", "MODIFIED", "BLOCKED"]
    content: str
    rail: str | None = None
