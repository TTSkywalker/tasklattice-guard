from __future__ import annotations

import asyncio
import hashlib
import json
import threading
import time
from collections import OrderedDict
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from nemoguardrails import Guardrails, RailsConfig

from ..runtime.contracts import GuardrailPlanSnapshot, NeMoConfigSnapshot
from .action_registry import RuntimeActionRegistry


class NeMoConfigStore(Protocol):
    def plan(self, guardrail_id: str, version: int) -> GuardrailPlanSnapshot: ...

    def nemo_config(self, guardrail_id: str, version: int) -> NeMoConfigSnapshot: ...

    def active_plan_keys(self) -> tuple[tuple[str, int], ...]: ...


@dataclass(slots=True)
class NeMoRailsInstance:
    config: NeMoConfigSnapshot
    plan: GuardrailPlanSnapshot
    rails: Guardrails
    actions: Any
    admission: asyncio.BoundedSemaphore
    active_requests: int = 0


class NeMoRailsRegistry:
    """Prewarmed, version-isolated NeMo Runtime registry."""

    def __init__(
        self,
        store: NeMoConfigStore,
        actions: RuntimeActionRegistry,
        *,
        max_entries: int = 128,
        max_concurrency_per_guardrail: int = 64,
    ) -> None:
        self._store = store
        self._actions = actions
        self._max_entries = max(1, max_entries)
        self._max_concurrency_per_guardrail = max(1, max_concurrency_per_guardrail)
        self._items: OrderedDict[tuple[str, int, str], NeMoRailsInstance] = OrderedDict()
        self._retired: list[Guardrails] = []
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0
        self.reload()

    def get(self, plan: GuardrailPlanSnapshot) -> NeMoRailsInstance:
        return self.acquire(plan)[0]

    def acquire(
        self, plan: GuardrailPlanSnapshot
    ) -> tuple[NeMoRailsInstance, bool, int]:
        config = self._store.nemo_config(plan.guardrail_id, plan.guardrail_version)
        key = (plan.guardrail_id, plan.guardrail_version, _config_checksum(config))
        waiting_started = time.perf_counter()
        with self._lock:
            queue_latency_ms = max(
                0, round((time.perf_counter() - waiting_started) * 1_000)
            )
            item = self._items.get(key)
            if item is not None:
                self._hits += 1
                self._items.move_to_end(key)
                return item, True, queue_latency_ms
            self._misses += 1
            return self._build(plan, config, key), False, queue_latency_ms

    def validate(
        self, plan: GuardrailPlanSnapshot, config: NeMoConfigSnapshot
    ) -> None:
        key = (plan.guardrail_id, plan.guardrail_version, _config_checksum(config))
        with self._lock:
            if key not in self._items:
                self._build(plan, config, key)

    def reload(self) -> None:
        active = set(self._store.active_plan_keys())
        with self._lock:
            for guardrail_id, version in active:
                self.get(self._store.plan(guardrail_id, version))

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "entries": len(self._items),
                "retired": len(self._retired),
                "hits": self._hits,
                "misses": self._misses,
            }

    def ready(self) -> bool:
        with self._lock:
            available = {key[:2] for key in self._items}
            return set(self._store.active_plan_keys()) <= available

    async def shutdown(self) -> None:
        with self._lock:
            rails = (
                *(item.rails for item in self._items.values()),
                *self._retired,
            )
            self._items.clear()
            self._retired.clear()
        await asyncio.gather(
            *(item.shutdown() for item in rails), return_exceptions=True
        )

    def _build(
        self,
        plan: GuardrailPlanSnapshot,
        config: NeMoConfigSnapshot,
        key: tuple[str, int, str],
    ) -> NeMoRailsInstance:
        from .runtime import NeMoActionExecutor

        self._validate_bindings(config)
        rails_config = RailsConfig.from_content(
            yaml_content=config.config_yaml,
            colang_content=config.colang_content or None,
        )
        rails = Guardrails(
            rails_config,
            use_iorails=config.runtime_engine == "iorails",
            require_iorails=config.runtime_engine == "iorails",
        )
        actions = NeMoActionExecutor(plan, config, self._actions)
        if config.runtime_engine == "llmrails":
            actions.register(rails)
        item = NeMoRailsInstance(
            config,
            plan,
            rails,
            actions,
            asyncio.BoundedSemaphore(self._max_concurrency_per_guardrail),
        )
        self._items[key] = item
        self._items.move_to_end(key)
        active = set(self._store.active_plan_keys())
        while len(self._items) > self._max_entries:
            candidate = next(iter(self._items))
            if candidate[:2] in active:
                self._items.move_to_end(candidate)
                if all(item_key[:2] in active for item_key in self._items):
                    break
                continue
            retired = self._items.pop(candidate)
            self._retired.append(retired.rails)
        return item

    def _validate_bindings(self, config: NeMoConfigSnapshot) -> None:
        executor_actions = {
            "TaskLatticeCustomerIdentifierAction",
            "TaskLatticeRecordControlAction",
            "TaskLatticeRecordNativeAction",
            "TaskLatticeResolveAction",
        }
        first_binding_ids = {
            selected[0].id
            for phase in ("input", "output")
            for risk in {item.risk for item in config.bindings_for(phase)}
            if (selected := config.bindings_for(phase, risk))
        }
        missing = tuple(
            binding
            for binding in config.action_bindings
            if (
                (
                    not binding.action_name
                    and not binding.flow_name
                )
                or (
                    binding.action_name
                    and not binding.action_version
                )
                or (
                    binding.action_name
                    and binding.action_name not in executor_actions
                    and not self._actions.contains(
                        binding.action_name,
                        binding.action_version,
                    )
                )
            )
            and (
                binding.id in first_binding_ids
                or binding.escalation != "on_uncertain"
            )
        )
        if "sensitive_data_detection" in config.required_features and not (
            self._actions.contains("TaskLatticePiiAction", "1.0.0")
        ):
            from ..control_plane.domain import PlanCompilationError

            raise PlanCompilationError(
                "NeMo sensitive-data rails require a configured PII Action provider."
            )
        if missing:
            from ..control_plane.domain import PlanCompilationError

            names = ", ".join(
                f"{item.id} ({item.stage})" for item in missing
            )
            raise PlanCompilationError(
                f"NeMo Action providers are unavailable for: {names}."
            )


def _config_checksum(config: NeMoConfigSnapshot) -> str:
    payload = json.dumps(asdict(config), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()
