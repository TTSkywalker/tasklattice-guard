from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal

from ..runtime.contracts import RailType
from .actions.contracts import (
    ActionProvider,
    ActionRequest,
    ActionResult,
    binding_step,
    engine_request,
)


ACTION_SECRETS = "GuardSecretsAction"
ACTION_PII = "GuardPiiAction"
ACTION_CONTENT_FILTER = "GuardContentFilterAction"
ACTION_TOPIC_RULES = "GuardTopicRulesAction"
ACTION_PROMPT_SECURITY = "GuardPromptSecurityAction"
ACTION_TOPIC_JUDGE = "GuardTopicJudgeAction"
ACTION_GROUNDING = "GuardGroundingAction"
ACTION_AUTOMATED_REASONING = "GuardReasoningAction"
ACTION_CUSTOMER_IDENTIFIER = "GuardCustomerIdentifierAction"
ACTION_RECORD_POLICY = "GuardRecordPolicyAction"
ACTION_RECORD_NATIVE = "GuardRecordNativeAction"
ACTION_RESOLVE = "GuardResolveAction"


@dataclass(frozen=True, slots=True)
class ActionDefinition:
    """Versioned metadata for an Action that may be referenced by Colang."""

    name: str
    version: str
    input_schema: tuple[tuple[str, str], ...]
    output_schema: tuple[tuple[str, str], ...]
    supported_rails: tuple[RailType, ...]
    timeout_ms: int
    failure_mode: Literal["fail_open", "fail_closed"]
    side_effects: bool
    concurrent: bool
    network_access: bool = False
    secret_names: tuple[str, ...] = ()
    provider_ready: bool = True


class ActionCatalog:
    def __init__(self, definitions: tuple[ActionDefinition, ...]) -> None:
        keys = tuple((item.name, item.version) for item in definitions)
        if len(set(keys)) != len(keys):
            raise ValueError("Action names and versions must be unique.")
        self._definitions = {key: item for key, item in zip(keys, definitions, strict=True)}

    def definitions(self) -> tuple[ActionDefinition, ...]:
        return tuple(self._definitions.values())

    def get(self, name: str, version: str) -> ActionDefinition:
        try:
            return self._definitions[(name, version)]
        except KeyError as error:
            raise KeyError(f"Action {name}@{version} is not registered.") from error

    def contains(self, name: str, version: str) -> bool:
        return (name, version) in self._definitions


@dataclass(frozen=True, slots=True)
class EvaluatorActionProvider:
    """Temporary algorithm adapter with a direct, versioned NeMo Action contract."""

    name: str
    version: str
    evaluator: object
    risks: frozenset[str]
    rails: frozenset[str]

    async def execute(self, request: ActionRequest) -> ActionResult:
        result = await self.evaluator.evaluate(
            engine_request(request),
            (binding_step(request.binding),),
        )
        confidence = next(
            (item.confidence for item in result.findings), None
        )
        return ActionResult(
            verdict=result.verdict,
            content=result.content,
            findings=result.findings,
            confidence=confidence,
            proposed_action=request.proposed_action,
            evidence=result.reason or "",
            reason=result.reason,
        )


class RuntimeActionRegistry:
    def __init__(self, providers: tuple[ActionProvider, ...]) -> None:
        keys = tuple((item.name, item.version) for item in providers)
        if len(set(keys)) != len(keys):
            raise ValueError("Runtime Action provider names and versions must be unique.")
        self._providers = {
            key: provider for key, provider in zip(keys, providers, strict=True)
        }

    def providers(self) -> tuple[ActionProvider, ...]:
        return tuple(self._providers.values())

    def get(self, name: str, version: str) -> ActionProvider:
        try:
            return self._providers[(name, version)]
        except KeyError as error:
            raise KeyError(f"Action provider {name}@{version} is unavailable.") from error

    def contains(self, name: str, version: str) -> bool:
        return (name, version) in self._providers


_BUILTIN_RUNTIME_ACTIONS = (
    (ACTION_SECRETS, ("secrets",), ("input", "output")),
    (ACTION_PII, ("pii",), ("input", "output")),
    (ACTION_CONTENT_FILTER, ("builtin_content_filter",), ("input", "output")),
    (ACTION_TOPIC_RULES, ("topic_control",), ("input", "output")),
    (ACTION_PROMPT_SECURITY, ("prompt_injection", "jailbreak"), ("input",)),
    (ACTION_TOPIC_JUDGE, ("topic_control", "company_policy"), ("input", "output")),
    (ACTION_GROUNDING, ("contextual_grounding",), ("output",)),
    (ACTION_AUTOMATED_REASONING, ("automated_reasoning",), ("output",)),
)


def runtime_action_registry(*evaluators: object) -> RuntimeActionRegistry:
    providers: list[EvaluatorActionProvider] = []
    for evaluator in evaluators:
        stage = str(getattr(evaluator, "stage", ""))
        risks = frozenset(getattr(evaluator, "supported_risks", frozenset()))
        rails = frozenset(getattr(evaluator, "supported_phases", frozenset()))
        if not risks and stage == "deterministic":
            risks = frozenset(
                {"secrets", "pii", "builtin_content_filter", "topic_control"}
            )
        grouped: dict[str, set[str]] = {}
        for risk in risks:
            grouped.setdefault(action_name_for(risk, stage), set()).add(risk)
        if not risks:
            for name in {
                "fast_semantic": (ACTION_PROMPT_SECURITY,),
                "deep_judge": (
                    ACTION_TOPIC_JUDGE,
                    ACTION_GROUNDING,
                    ACTION_AUTOMATED_REASONING,
                ),
            }.get(stage, ()):
                grouped[name] = set()
        for name, selected_risks in grouped.items():
            if rails:
                providers.append(
                    EvaluatorActionProvider(
                        name=name,
                        version="1.0.0",
                        evaluator=evaluator,
                        risks=frozenset(selected_risks),
                        rails=rails,
                    )
                )
    return RuntimeActionRegistry(tuple(providers))


def _dynamic_action_name(risk: str) -> str:
    parts = tuple(item for item in re.split(r"[^A-Za-z0-9]+", risk) if item)
    capability = "".join(item.capitalize() for item in parts) or "Custom"
    return f"Guard{capability}Action"


def action_name_for(risk: str, stage: str) -> str:
    """Return the stable NeMo Action name for one native Policy stage."""
    if stage == "deterministic":
        return {
            "secrets": ACTION_SECRETS,
            "pii": ACTION_PII,
            "builtin_content_filter": ACTION_CONTENT_FILTER,
            "topic_control": ACTION_TOPIC_RULES,
        }.get(risk, _dynamic_action_name(risk))
    if stage == "fast_semantic":
        return (
            ACTION_PROMPT_SECURITY
            if risk in {"prompt_injection", "jailbreak"}
            else _dynamic_action_name(risk)
        )
    return {
        "topic_control": ACTION_TOPIC_JUDGE,
        "company_policy": ACTION_TOPIC_JUDGE,
        "contextual_grounding": ACTION_GROUNDING,
        "automated_reasoning": ACTION_AUTOMATED_REASONING,
    }.get(risk, _dynamic_action_name(risk))


BUILTIN_ACTION_CATALOG = ActionCatalog(
    (
        *tuple(
            ActionDefinition(
                name=name,
                version="1.0.0",
                input_schema=(("request", "ActionRequest"),),
                output_schema=(("result", "ActionResult"),),
                supported_rails=tuple(rails),
                timeout_ms=30_000 if name == ACTION_AUTOMATED_REASONING else 5_000,
                failure_mode="fail_closed",
                side_effects=False,
                concurrent=True,
                network_access=name in {
                    ACTION_TOPIC_JUDGE,
                    ACTION_GROUNDING,
                    ACTION_AUTOMATED_REASONING,
                },
            )
            for name, _, rails in _BUILTIN_RUNTIME_ACTIONS
        ),
        ActionDefinition(
            name=ACTION_CUSTOMER_IDENTIFIER,
            version="1.0.0",
            input_schema=(("text", "string"),),
            output_schema=(("detected", "boolean"), ("redacted", "string")),
            supported_rails=("input", "output"),
            timeout_ms=100,
            failure_mode="fail_closed",
            side_effects=False,
            concurrent=True,
        ),
        ActionDefinition(
            name=ACTION_RECORD_POLICY,
            version="1.0.0",
            input_schema=(
                ("binding_id", "string"),
                ("safe", "boolean"),
                ("text", "string"),
                ("replacement", "string|null"),
            ),
            output_schema=(("verdict", "string"),),
            supported_rails=("input", "output"),
            timeout_ms=100,
            failure_mode="fail_closed",
            side_effects=False,
            concurrent=True,
        ),
    )
)
