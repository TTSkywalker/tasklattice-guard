from __future__ import annotations

from app.control_plane.nemo_compiler import NeMoConfigCompiler
from app.nemo.runtime import NeMoRuntime
from app.nemo.registry import NeMoRuntimeRegistry
from app.nemo.action_registry import action_providers
from app.nemo.actions.contracts import ActionRequest
from app.runtime.content_views import request_view
from app.runtime.contracts import (
    EngineRequest,
    GuardrailPlanSnapshot,
    GuardrailPlanStep,
    NeMoActionBinding,
    NeMoConfigSnapshot,
)


class StaticNeMoStore:
    def __init__(
        self,
        plans: tuple[GuardrailPlanSnapshot, ...],
        configs: tuple[NeMoConfigSnapshot, ...],
    ) -> None:
        self._plans = {
            (item.guardrail_id, item.guardrail_version): item for item in plans
        }
        self._configs = {
            (item.guardrail_id, item.guardrail_version): item for item in configs
        }

    def plan(self, guardrail_id: str, version: int) -> GuardrailPlanSnapshot:
        return self._plans[(guardrail_id, version)]

    def nemo_config(self, guardrail_id: str, version: int) -> NeMoConfigSnapshot:
        return self._configs[(guardrail_id, version)]

    def active_plan_keys(self) -> tuple[tuple[str, int], ...]:
        return tuple(self._plans)


def nemo_engine(
    plan: GuardrailPlanSnapshot,
    *actions: object,
    max_concurrency_per_guardrail: int = 64,
) -> NeMoRuntime:
    config = NeMoConfigCompiler().compile(plan)
    return NeMoRuntime(
        NeMoRuntimeRegistry(
            StaticNeMoStore((plan,), (config,)),
            action_providers(*actions),
            max_concurrency_per_guardrail=max_concurrency_per_guardrail,
        )
    )


def provider_request(
    request: EngineRequest,
    step: GuardrailPlanStep,
) -> ActionRequest:
    """Build the same immutable request that the native NeMo Action bridge uses."""
    view = request_view(request)
    binding = NeMoActionBinding(
        id=step.id,
        risk=step.risk,
        stage=step.stage,
        phases=step.phases,
        on_unsafe=step.on_unsafe,
        escalation=step.escalation,
        parameters=step.parameters,
    )
    return ActionRequest(
        content=request.text,
        rail_type=request.phase,
        guardrail_id=request.plan.guardrail_id,
        guardrail_version=request.plan.guardrail_version,
        policy_id=None,
        policy_version=None,
        trusted_context=(("trusted_instruction", request.trusted_instruction),),
        content_blocks=view.blocks,
        deadline=0,
        parameters=step.parameters,
        risk=step.risk,
        proposed_action=step.on_unsafe,
        plan=request.plan,
        binding=binding,
        context_messages=request.context_messages,
        target_source=request.target_source,
        mode=request.mode,
        evidence_scope=request.evidence_scope,
        content_view=view,
        active_block_id=view.active_block_id,
    )
