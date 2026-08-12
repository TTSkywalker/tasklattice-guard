from __future__ import annotations

from dataclasses import dataclass


LITELLM_GENERIC_GUARDRAIL_ADAPTER_ID = "litellm-generic-guardrail"
GENERIC_HTTP_GUARD_ADAPTER_ID = "generic-http-guard"
A2A_GUARD_ADAPTER_ID = "a2a-guard"

INTEGRATION_API_KEY_ENV_VAR = "TASKLATTICE_GUARD_API_KEY"
INTEGRATION_API_BASE_ENV_VAR = "TASKLATTICE_GUARD_API_BASE"


@dataclass(frozen=True, slots=True)
class IntegrationAdapterDefinition:
    id: str
    protocol: str
    name: str
    modes: tuple[str, ...]
    callback_suffix: str
    default_on: bool = True
    fail_on_error: bool = True
    unreachable_fallback: str = "fail_closed"

    def callback_path(self, integration_id: str) -> str:
        return (
            f"/runtime/v1/integrations/{integration_id}"
            f"/{self.callback_suffix.lstrip('/')}"
        )

    def setup(self, public_runtime_base_url: str, integration_id: str) -> dict[str, object]:
        public_root = public_runtime_base_url.rstrip("/")
        api_base_url = f"{public_root}/runtime/v1/integrations/{integration_id}"
        callback_url = f"{api_base_url}/{self.callback_suffix.lstrip('/')}"
        return {
            "api_base_url": api_base_url,
            "callback_url": callback_url,
            "auth_header": "x-api-key",
            "credential_env_var": INTEGRATION_API_KEY_ENV_VAR,
            "api_base_env_var": INTEGRATION_API_BASE_ENV_VAR,
            "recommended_modes": list(self.modes),
            "default_on": self.default_on,
            "fail_on_error": self.fail_on_error,
            "unreachable_fallback": self.unreachable_fallback,
            "yaml_template": self.yaml_template(api_base_url, callback_url),
        }

    def yaml_template(self, api_base_url: str, callback_url: str) -> str:
        if self.id == LITELLM_GENERIC_GUARDRAIL_ADAPTER_ID:
            return (
                "litellm_settings:\n"
                "  guardrails:\n"
                "    - guardrail_name: tasklattice-guard\n"
                "      litellm_params:\n"
                "        guardrail: generic_guardrail_api\n"
                "        mode: [pre_call, post_call]\n"
                f"        api_base: os.environ/{INTEGRATION_API_BASE_ENV_VAR}\n"
                f"        api_key: os.environ/{INTEGRATION_API_KEY_ENV_VAR}\n"
                "        default_on: true\n"
                "        fail_on_error: true\n"
                "        unreachable_fallback: fail_closed\n"
            )
        modes = ", ".join(self.modes)
        return (
            "tasklattice_guard:\n"
            f"  callback_url: \"{callback_url}\"\n"
            f"  api_key: os.environ/{INTEGRATION_API_KEY_ENV_VAR}\n"
            f"  modes: [{modes}]\n"
            "  default_on: true\n"
            "  fail_on_error: true\n"
        )


_ADAPTERS = (
    IntegrationAdapterDefinition(
        id=LITELLM_GENERIC_GUARDRAIL_ADAPTER_ID,
        protocol="litellm",
        name="LiteLLM Generic Guardrail API",
        modes=("pre_call", "post_call"),
        callback_suffix="beta/litellm_basic_guardrail_api",
    ),
    IntegrationAdapterDefinition(
        id=GENERIC_HTTP_GUARD_ADAPTER_ID,
        protocol="http",
        name="Generic HTTP Guard API",
        modes=("input", "output"),
        callback_suffix="guardrails/evaluate",
    ),
    IntegrationAdapterDefinition(
        id=A2A_GUARD_ADAPTER_ID,
        protocol="a2a",
        name="A2A Guard API",
        modes=("input", "output"),
        callback_suffix="guardrails/evaluate",
    ),
)

_ADAPTER_BY_ID = {item.id: item for item in _ADAPTERS}
_ADAPTER_BY_PROTOCOL = {item.protocol: item for item in _ADAPTERS}


def integration_adapters() -> tuple[IntegrationAdapterDefinition, ...]:
    return _ADAPTERS


def adapter_definition(adapter_id: str) -> IntegrationAdapterDefinition | None:
    return _ADAPTER_BY_ID.get(adapter_id)


def adapter_for_protocol(protocol: str) -> IntegrationAdapterDefinition | None:
    return _ADAPTER_BY_PROTOCOL.get(protocol)
