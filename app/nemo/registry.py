from __future__ import annotations

import asyncio
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import yaml
from nemoguardrails import Guardrails, RailsConfig

from ..control_plane.domain import PlanCompilationError
from ..runtime.contracts import GuardrailPlanSnapshot, NeMoConfigSnapshot
from .action_registry import RuntimeActionRegistry
from .artifacts import config_checksum


_PROFILE_RUNTIME = {
    "iorails_native": ("iorails", "1.0"),
    "llmrails_colang1_standard": ("llmrails", "1.0"),
    "llmrails_colang2_programmable": ("llmrails", "2.x"),
}
_EXECUTOR_ACTION_VERSIONS = {
    "TaskLatticeCustomerIdentifierAction": "1.0.0",
    "TaskLatticeRecordControlAction": "1.0.0",
    "TaskLatticeRecordNativeAction": "1.0.0",
    "TaskLatticeResolveAction": "1.0.0",
}


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
        execution_surface: Literal[
            "standalone_check", "owned_generation"
        ] = "standalone_check",
    ) -> None:
        self._store = store
        self._actions = actions
        self._max_entries = max(1, max_entries)
        self._max_concurrency_per_guardrail = max(1, max_concurrency_per_guardrail)
        self._execution_surface = execution_surface
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
        key = (plan.guardrail_id, plan.guardrail_version, config_checksum(config))
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
        key = (plan.guardrail_id, plan.guardrail_version, config_checksum(config))
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

        self._validate_runtime_profile(config)
        self._validate_bindings(config)
        rails_config = RailsConfig.from_content(
            yaml_content=config.config_yaml,
            colang_content=config.colang_content or None,
        )
        use_iorails = config.runtime_profile == "iorails_native"
        rails = Guardrails(
            rails_config,
            use_iorails=use_iorails,
            require_iorails=use_iorails,
        )
        actions = NeMoActionExecutor(
            plan,
            config,
            self._actions_for(config),
        )
        if config.runtime_profile in {
            "llmrails_colang1_standard",
            "llmrails_colang2_programmable",
        }:
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

    def _validate_runtime_profile(self, config: NeMoConfigSnapshot) -> None:
        expected = _PROFILE_RUNTIME.get(config.runtime_profile)
        if expected is None:
            names = ", ".join(sorted(_PROFILE_RUNTIME))
            raise PlanCompilationError(
                f"Unknown NeMo runtime profile {config.runtime_profile!r}; "
                f"expected one of: {names}."
            )
        actual = (config.runtime_engine, config.colang_version)
        if actual != expected:
            raise PlanCompilationError(
                f"NeMo runtime profile {config.runtime_profile!r} requires "
                f"runtime_engine={expected[0]!r} and colang_version={expected[1]!r}; "
                f"received runtime_engine={actual[0]!r} and "
                f"colang_version={actual[1]!r}."
            )

        try:
            payload = yaml.safe_load(config.config_yaml) or {}
        except yaml.YAMLError as error:
            raise PlanCompilationError(
                "Compiled NeMo configuration YAML is invalid: "
                f"{error.__class__.__name__}."
            ) from error
        if not isinstance(payload, dict):
            raise PlanCompilationError(
                "Compiled NeMo configuration YAML must contain a mapping."
            )
        yaml_version = str(payload.get("colang_version", ""))
        if yaml_version != config.colang_version:
            raise PlanCompilationError(
                "NeMo artifact colang_version does not match config_yaml: "
                f"{config.colang_version!r} != {yaml_version!r}."
            )

        if config.runtime_profile == "iorails_native":
            if self._execution_surface != "owned_generation":
                raise PlanCompilationError(
                    "The iorails_native profile requires an owned-generation host; "
                    "publish a new llmrails_colang1_standard version before using "
                    "the standalone check service."
                )
            action_dependencies = tuple(
                item
                for item in config.dependency_manifest
                if item and item[0] == "action"
            )
            if config.action_bindings or action_dependencies:
                raise PlanCompilationError(
                    "The iorails_native profile must be action-free."
                )
            if "sensitive_data_detection" in config.required_features:
                raise PlanCompilationError(
                    "The iorails_native profile cannot require runtime Action-backed "
                    "sensitive-data detection."
                )

        tracing = payload.get("tracing", {})
        tracing_enabled = isinstance(tracing, dict) and _enabled(
            tracing.get("enabled")
        )
        metrics = payload.get("metrics", {})
        metrics_enabled = isinstance(metrics, dict) and _enabled(
            metrics.get("enabled")
        )
        if (
            config.runtime_profile == "llmrails_colang2_programmable"
            and tracing_enabled
        ):
            raise PlanCompilationError(
                "NeMo 0.23 requires tracing to be disabled for the "
                "llmrails_colang2_programmable profile."
            )
        if config.runtime_profile != "iorails_native" and metrics_enabled:
            raise PlanCompilationError(
                f"NeMo 0.23 requires metrics to be disabled for the "
                f"{config.runtime_profile} profile."
            )

    def _validate_bindings(self, config: NeMoConfigSnapshot) -> None:
        result_vars = tuple(
            binding.result_var
            for binding in config.action_bindings
            if binding.result_var
        )
        if config.runtime_profile == "llmrails_colang1_standard":
            missing = tuple(
                item.id for item in config.action_bindings if not item.result_var
            )
            if missing:
                raise PlanCompilationError(
                    "Colang 1 Action bindings require explicit result variables: "
                    + ", ".join(missing)
                    + "."
                )
            if len(result_vars) != len(set(result_vars)):
                raise PlanCompilationError(
                    "Colang 1 Action result variables must be unique."
                )
        elif result_vars:
            raise PlanCompilationError(
                f"The {config.runtime_profile} profile cannot carry Colang 1 "
                "Action result variables."
            )
        references = _action_references(config)
        if config.runtime_profile == "llmrails_colang1_standard":
            c2_only = sorted(
                name for name, _ in references if name in _EXECUTOR_ACTION_VERSIONS
            )
            if c2_only:
                raise PlanCompilationError(
                    "The Colang 1 standard profile cannot depend on programmable "
                    "executor Actions: " + ", ".join(c2_only) + "."
                )
        versions_by_name: dict[str, set[str]] = {}
        for name, version in references:
            versions_by_name.setdefault(name, set()).add(version)
        ambiguous = {
            name: versions
            for name, versions in versions_by_name.items()
            if len(versions) > 1
        }
        if ambiguous:
            names = ", ".join(
                f"{name} ({', '.join(sorted(versions))})"
                for name, versions in sorted(ambiguous.items())
            )
            raise PlanCompilationError(
                "A NeMo configuration cannot bind multiple versions under the same "
                f"Action name: {names}."
            )

        malformed = tuple(
            binding
            for binding in config.action_bindings
            if (
                (not binding.action_name and not binding.flow_name)
                or (binding.action_name and not binding.action_version)
            )
        )
        malformed_dependencies = tuple(
            item
            for item in config.dependency_manifest
            if item[0] == "action" and (not item[1] or not item[2])
        )
        unavailable = tuple(
            (name, version)
            for name, version in sorted(references)
            if (
                (
                    name in _EXECUTOR_ACTION_VERSIONS
                    and version != _EXECUTOR_ACTION_VERSIONS[name]
                )
                or (
                    name not in _EXECUTOR_ACTION_VERSIONS
                    and not self._actions.contains(name, version)
                )
            )
        )
        if "sensitive_data_detection" in config.required_features and not (
            self._actions.contains("TaskLatticePiiAction", "1.0.0")
        ):
            raise PlanCompilationError(
                "NeMo sensitive-data rails require a configured PII Action provider."
            )
        if malformed:
            names = ", ".join(
                f"{item.id} ({item.stage})" for item in malformed
            )
            raise PlanCompilationError(
                f"NeMo Action bindings are incomplete for: {names}."
            )
        if malformed_dependencies:
            raise PlanCompilationError(
                "NeMo Action dependencies must pin a non-empty name and version."
            )
        if unavailable:
            names = ", ".join(
                f"{name}@{version}" for name, version in unavailable
            )
            raise PlanCompilationError(
                f"NeMo Action providers are unavailable for: {names}."
            )

    def _actions_for(self, config: NeMoConfigSnapshot) -> RuntimeActionRegistry:
        """Scope name-based NeMo registration to artifact-pinned providers."""
        references = {
            (name, version)
            for name, version in _action_references(config)
            if name not in _EXECUTOR_ACTION_VERSIONS
        }
        if "sensitive_data_detection" in config.required_features:
            references.add(("TaskLatticePiiAction", "1.0.0"))
        return RuntimeActionRegistry(
            tuple(
                self._actions.get(name, version)
                for name, version in sorted(references)
            )
        )


def _action_references(
    config: NeMoConfigSnapshot,
) -> set[tuple[str, str]]:
    references = {
        (binding.action_name, binding.action_version)
        for binding in config.action_bindings
        if binding.action_name and binding.action_version
    }
    references.update(
        (name, version)
        for kind, name, version in config.dependency_manifest
        if kind == "action" and name and version
    )
    return references


def _enabled(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "on", "true", "yes"}
    return value is True or value == 1
