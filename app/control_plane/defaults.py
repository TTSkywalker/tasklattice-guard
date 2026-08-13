from __future__ import annotations


DEFAULT_GUARDRAIL_ID = "guardrail-default"
DEFAULT_GUARDRAIL_VERSION = 1
DEFAULT_GUARDRAIL_NAME = "Default Guardrail"
DEFAULT_GUARDRAIL_PURPOSE = (
    "Protect unmatched model traffic with local credential, personal-data, "
    "prompt-injection, SQL-injection, and code-injection checks without calling "
    "an external model."
)
DEFAULT_GUARDRAIL_POLICY_ID = "prompt-injection-protection"

DEFAULT_DEPLOYMENT_ID = "deployment-default"
DEFAULT_DEPLOYMENT_NAME = "Default Deployment"


def is_default_guardrail(guardrail_id: str) -> bool:
    return guardrail_id == DEFAULT_GUARDRAIL_ID


def is_default_deployment(deployment_id: str) -> bool:
    return deployment_id == DEFAULT_DEPLOYMENT_ID
