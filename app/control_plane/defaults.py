from __future__ import annotations


DEFAULT_GUARDRAIL_ID = "guardrail-default"
DEFAULT_GUARDRAIL_VERSION = 1
DEFAULT_GUARDRAIL_NAME = "Default Guardrail"
DEFAULT_GUARDRAIL_PURPOSE = (
    "Protect unmatched model traffic with local credential, personal-data, "
    "prompt-injection, SQL-injection, and code-injection checks without calling "
    "an external model."
)
DEFAULT_GUARDRAIL_TEMPLATE_ID = "prompt-injection-protection"

DEFAULT_ASSIGNMENT_ID = "assignment-default"
DEFAULT_ASSIGNMENT_NAME = "Default Assignment"


def is_default_guardrail(guardrail_id: str) -> bool:
    return guardrail_id == DEFAULT_GUARDRAIL_ID


def is_default_assignment(assignment_id: str) -> bool:
    return assignment_id == DEFAULT_ASSIGNMENT_ID
