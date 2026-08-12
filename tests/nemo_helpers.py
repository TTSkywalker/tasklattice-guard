from __future__ import annotations

from app.control_plane.nemo_compiler import NeMoConfigCompiler
from app.nemo.runtime import NeMoGuardrailsEngine, NeMoRailsRegistry
from app.nemo.action_registry import runtime_action_registry
from app.runtime.contracts import (
    GuardrailPlanSnapshot,
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
) -> NeMoGuardrailsEngine:
    config = NeMoConfigCompiler().compile(plan)
    for action in actions:
        if not getattr(action, "supported_risks", frozenset()):
            setattr(
                action,
                "supported_risks",
                frozenset(
                    step.risk
                    for step in plan.steps
                    if step.stage == getattr(action, "stage", "")
                ),
            )
    return NeMoGuardrailsEngine(
        NeMoRailsRegistry(
            StaticNeMoStore((plan,), (config,)),
            runtime_action_registry(*actions),
            max_concurrency_per_guardrail=max_concurrency_per_guardrail,
        )
    )
