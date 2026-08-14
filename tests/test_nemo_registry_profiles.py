from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any

import pytest
import yaml

from app.control_plane.domain import ControlPlaneError, PlanCompilationError
from app.control_plane.service import _nemo_config_from_payload
from app.nemo.action_registry import ActionProviders, action_providers
from app.nemo.registry import NeMoRuntimeRegistry
from app.runtime.contracts import (
    GuardrailPlanSnapshot,
    NeMoActionBinding,
    NeMoConfigSnapshot,
)


class _EmptyStore:
    def active_plan_keys(self) -> tuple[tuple[str, int], ...]:
        return ()

    def plan(self, guardrail_id: str, version: int) -> GuardrailPlanSnapshot:
        raise KeyError((guardrail_id, version))

    def nemo_config(self, guardrail_id: str, version: int) -> NeMoConfigSnapshot:
        raise KeyError((guardrail_id, version))


@dataclass(frozen=True)
class _Provider:
    name: str
    version: str

    async def execute(self, request: Any) -> Any:
        raise AssertionError(f"Unexpected provider execution: {request!r}")


def _plan() -> GuardrailPlanSnapshot:
    return GuardrailPlanSnapshot(
        guardrail_id="profile-test",
        guardrail_version=1,
        compiler_version="test",
        safety_level="balanced",
        output_delivery="window_buffered",
        steps=(),
    )


def _binding(
    *, name: str = "ExampleAction", version: str = "1.0.0",
    result_var: str | None = "example_result",
) -> NeMoActionBinding:
    return NeMoActionBinding(
        id=f"binding-{version}",
        risk="example",
        stage="deterministic",
        phases=("input",),
        on_unsafe="reject",
        action_name=name,
        action_version=version,
        result_var=result_var,
    )


def _config(
    *,
    profile: str = "llmrails_colang1_standard",
    engine: str = "llmrails",
    colang_version: str = "1.0",
    tracing: bool = True,
    bindings: tuple[NeMoActionBinding, ...] = (),
    dependencies: tuple[tuple[str, str, str], ...] | None = None,
) -> NeMoConfigSnapshot:
    return NeMoConfigSnapshot(
        guardrail_id="profile-test",
        guardrail_version=1,
        compiler_version="test",
        output_delivery="window_buffered",
        config_yaml=yaml.safe_dump(
            {
                "colang_version": colang_version,
                "rails": {},
                "tracing": {"enabled": tracing},
                "metrics": {"enabled": False},
            },
            sort_keys=False,
        ),
        colang_content="",
        action_bindings=bindings,
        runtime_engine=engine,
        runtime_profile=profile,
        colang_version=colang_version,
        dependency_manifest=(
            dependencies
            if dependencies is not None
            else tuple(
                ("action", item.action_name or "", item.action_version or "")
                for item in bindings
                if item.action_name
            )
        ),
    )


def test_artifact_requires_explicit_runtime_profile() -> None:
    payload = asdict(
        replace(
            _config(),
            compiler_version="tasklattice-nemo-config-v6",
        )
    )
    payload.pop("runtime_profile")

    with pytest.raises(ControlPlaneError, match="missing its explicit runtime_profile"):
        _nemo_config_from_payload(payload)


@pytest.mark.parametrize(
    ("profile", "engine", "colang_version"),
    (
        ("iorails_native", "llmrails", "1.0"),
        ("llmrails_colang1_standard", "iorails", "1.0"),
        ("llmrails_colang2_programmable", "llmrails", "1.0"),
    ),
)
def test_registry_rejects_illegal_profile_engine_colang_combinations(
    profile: str,
    engine: str,
    colang_version: str,
) -> None:
    registry = NeMoRuntimeRegistry(_EmptyStore(), action_providers())

    with pytest.raises(PlanCompilationError, match="requires runtime_engine"):
        registry.validate(
            _plan(),
            _config(
                profile=profile,
                engine=engine,
                colang_version=colang_version,
                tracing=False,
            ),
        )


def test_registry_rejects_actions_in_iorails_profile() -> None:
    registry = NeMoRuntimeRegistry(
        _EmptyStore(),
        action_providers(),
        execution_surface="owned_generation",
    )
    config = _config(
        profile="iorails_native",
        engine="iorails",
        colang_version="1.0",
        tracing=True,
        bindings=(
            _binding(name="GuardResolveAction", version="1.0.0"),
        ),
    )

    with pytest.raises(PlanCompilationError, match="must be action-free"):
        registry.validate(_plan(), config)


def test_standalone_registry_rejects_iorails_before_reporting_ready() -> None:
    registry = NeMoRuntimeRegistry(_EmptyStore(), action_providers())
    config = _config(
        profile="iorails_native",
        engine="iorails",
        colang_version="1.0",
        tracing=True,
    )

    with pytest.raises(PlanCompilationError, match="owned-generation host"):
        registry.validate(_plan(), config)


def test_registry_rejects_tracing_for_pinned_colang2_runtime() -> None:
    registry = NeMoRuntimeRegistry(_EmptyStore(), action_providers())
    config = _config(
        profile="llmrails_colang2_programmable",
        engine="llmrails",
        colang_version="2.x",
        tracing=True,
    )

    with pytest.raises(PlanCompilationError, match="requires tracing to be disabled"):
        registry.validate(_plan(), config)


@pytest.mark.parametrize(
    "profile",
    ("llmrails_colang1_standard", "llmrails_colang2_programmable"),
)
def test_registry_rejects_metrics_for_llmrails_profiles(profile: str) -> None:
    config = _config(
        profile=profile,
        engine="llmrails",
        colang_version="1.0" if profile.endswith("standard") else "2.x",
        tracing=False,
    )
    payload = yaml.safe_load(config.config_yaml)
    payload["metrics"]["enabled"] = True
    config = replace(config, config_yaml=yaml.safe_dump(payload, sort_keys=False))

    with pytest.raises(PlanCompilationError, match="metrics to be disabled"):
        NeMoRuntimeRegistry(_EmptyStore(), action_providers()).validate(
            _plan(), config
        )


def test_registry_requires_unique_c1_result_variables() -> None:
    missing = _config(bindings=(_binding(result_var=None),))
    with pytest.raises(PlanCompilationError, match="explicit result variables"):
        NeMoRuntimeRegistry(_EmptyStore(), action_providers()).validate(
            _plan(), missing
        )

    duplicate = _config(
        bindings=(
            _binding(),
            replace(_binding(), id="binding-two"),
        )
    )
    with pytest.raises(PlanCompilationError, match="must be unique"):
        NeMoRuntimeRegistry(_EmptyStore(), action_providers()).validate(
            _plan(), duplicate
        )


def test_registry_rejects_programmable_executor_actions_in_c1() -> None:
    config = _config(
        bindings=(_binding(),),
        dependencies=(
            ("action", "ExampleAction", "1.0.0"),
            ("action", "GuardResolveAction", "1.0.0"),
        ),
    )

    with pytest.raises(PlanCompilationError, match="programmable executor Actions"):
        NeMoRuntimeRegistry(
            _EmptyStore(),
            action_providers(_Provider("ExampleAction", "1.0.0")),
        ).validate(_plan(), config)


def test_registry_requires_the_exact_provider_version() -> None:
    registry = NeMoRuntimeRegistry(
        _EmptyStore(),
        action_providers(_Provider("ExampleAction", "1.0.0")),
    )
    config = _config(bindings=(_binding(version="2.0.0"),))

    with pytest.raises(PlanCompilationError, match="providers are unavailable"):
        registry.validate(_plan(), config)


def test_registry_requires_the_pinned_executor_action_version() -> None:
    registry = NeMoRuntimeRegistry(_EmptyStore(), action_providers())
    config = _config(
        profile="llmrails_colang2_programmable",
        engine="llmrails",
        colang_version="2.x",
        tracing=False,
        bindings=(
            _binding(
                name="GuardResolveAction",
                version="2.0.0",
                result_var=None,
            ),
        ),
    )

    with pytest.raises(PlanCompilationError, match="providers are unavailable"):
        registry.validate(_plan(), config)


def test_registry_rejects_two_versions_under_one_action_name() -> None:
    registry = NeMoRuntimeRegistry(
        _EmptyStore(),
        action_providers(
            _Provider("ExampleAction", "1.0.0"),
            _Provider("ExampleAction", "2.0.0"),
        ),
    )
    config = _config(
        bindings=(
            _binding(version="1.0.0"),
            replace(
                _binding(version="2.0.0", result_var="example_result_two"),
                id="binding-two",
            ),
        )
    )

    with pytest.raises(PlanCompilationError, match="multiple versions"):
        registry.validate(_plan(), config)


@pytest.mark.parametrize(
    ("profile", "engine", "colang_version", "registered"),
    (
        ("iorails_native", "iorails", "1.0", False),
        ("llmrails_colang1_standard", "llmrails", "1.0", True),
        ("llmrails_colang2_programmable", "llmrails", "2.x", True),
    ),
)
def test_registry_constructs_the_explicit_profile_engine(
    monkeypatch: pytest.MonkeyPatch,
    profile: str,
    engine: str,
    colang_version: str,
    registered: bool,
) -> None:
    import app.nemo.registry as registry_module
    import app.nemo.runtime as runtime_module

    built: list[dict[str, Any]] = []
    executors: list[Any] = []

    class _RailsConfig:
        @staticmethod
        def from_content(**content: Any) -> dict[str, Any]:
            return content

    class _Guardrails:
        def __init__(self, config: Any, **options: Any) -> None:
            built.append({"config": config, **options})

    class _Executor:
        def __init__(
            self,
            plan: GuardrailPlanSnapshot,
            config: NeMoConfigSnapshot,
            actions: ActionProviders,
        ) -> None:
            self.plan = plan
            self.config = config
            self.actions = actions
            self.registered = False
            executors.append(self)

        def register(self, rails: Any) -> None:
            assert rails is not None
            self.registered = True

    monkeypatch.setattr(registry_module, "RailsConfig", _RailsConfig)
    monkeypatch.setattr(registry_module, "Guardrails", _Guardrails)
    monkeypatch.setattr(runtime_module, "NeMoActionBridge", _Executor)
    registry = NeMoRuntimeRegistry(
        _EmptyStore(),
        action_providers(),
        execution_surface=(
            "owned_generation" if profile == "iorails_native" else "standalone_check"
        ),
    )
    config = _config(
        profile=profile,
        engine=engine,
        colang_version=colang_version,
        tracing=profile != "llmrails_colang2_programmable",
    )

    registry.validate(_plan(), config)

    assert built == [
        {
            "config": {
                "yaml_content": config.config_yaml,
                "colang_content": None,
            },
            "use_iorails": profile == "iorails_native",
            "require_iorails": profile == "iorails_native",
        }
    ]
    assert len(executors) == 1
    assert executors[0].registered is registered


def test_registry_scopes_registration_to_the_artifact_pinned_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.nemo.registry as registry_module
    import app.nemo.runtime as runtime_module

    selected: list[tuple[tuple[str, str], ...]] = []

    class _RailsConfig:
        @staticmethod
        def from_content(**content: Any) -> dict[str, Any]:
            return content

    class _Guardrails:
        def __init__(self, config: Any, **options: Any) -> None:
            del config, options

    class _Executor:
        def __init__(
            self,
            plan: GuardrailPlanSnapshot,
            config: NeMoConfigSnapshot,
            actions: ActionProviders,
        ) -> None:
            del plan, config
            selected.append(
                tuple((item.name, item.version) for item in actions.values())
            )

        def register(self, rails: Any) -> None:
            del rails

    monkeypatch.setattr(registry_module, "RailsConfig", _RailsConfig)
    monkeypatch.setattr(registry_module, "Guardrails", _Guardrails)
    monkeypatch.setattr(runtime_module, "NeMoActionBridge", _Executor)
    registry = NeMoRuntimeRegistry(
        _EmptyStore(),
        action_providers(
            _Provider("ExampleAction", "1.0.0"),
            _Provider("ExampleAction", "2.0.0"),
        ),
    )

    registry.validate(_plan(), _config(bindings=(_binding(version="2.0.0"),)))

    assert selected == [(('ExampleAction', '2.0.0'),)]
