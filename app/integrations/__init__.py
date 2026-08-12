"""Runtime Integration adapter definitions and setup material."""

from .registry import (
    A2A_GUARD_ADAPTER_ID,
    GENERIC_HTTP_GUARD_ADAPTER_ID,
    LITELLM_GENERIC_GUARDRAIL_ADAPTER_ID,
    IntegrationAdapterDefinition,
    adapter_definition,
    adapter_for_protocol,
    integration_adapters,
)

__all__ = [
    "A2A_GUARD_ADAPTER_ID",
    "GENERIC_HTTP_GUARD_ADAPTER_ID",
    "LITELLM_GENERIC_GUARDRAIL_ADAPTER_ID",
    "IntegrationAdapterDefinition",
    "adapter_definition",
    "adapter_for_protocol",
    "integration_adapters",
]
