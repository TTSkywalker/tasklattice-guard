from __future__ import annotations

from functools import lru_cache

from .domain import ControlLibraryBundle, ControlPackSpec, ControlSpec, RuleSpec
from .importers.litellm_content_filter import import_bundle


BUILTIN_LIBRARY_ID = "litellm-content-filter"
_PHASES = frozenset({"input", "output"})
_DETECTORS = frozenset({"regex", "keyword", "category"})


class ControlLibraryRegistry:
    """Validated, indexed access to all installed Control Library bundles."""

    def __init__(self, bundles: tuple[ControlLibraryBundle, ...]) -> None:
        if not bundles:
            raise ValueError("The Control Library requires at least one bundle.")

        bundle_index: dict[str, ControlLibraryBundle] = {}
        control_index: dict[str, ControlSpec] = {}
        pack_index: dict[str, ControlPackSpec] = {}
        memberships: dict[str, list[ControlPackSpec]] = {}

        for bundle in bundles:
            self._validate_bundle(bundle)
            if bundle.id in bundle_index:
                raise ValueError(
                    f"Duplicate Control Library bundle ID {bundle.id!r}."
                )
            bundle_index[bundle.id] = bundle

            for control in bundle.controls:
                if control.id in control_index:
                    raise ValueError(f"Duplicate Control ID {control.id!r}.")
                control_index[control.id] = control
                memberships[control.id] = []

            for pack in bundle.packs:
                if pack.id in pack_index:
                    raise ValueError(f"Duplicate Control Pack ID {pack.id!r}.")
                pack_index[pack.id] = pack
                for control_id in pack.control_ids:
                    memberships[control_id].append(pack)

        unassigned = tuple(
            control_id
            for control_id, assigned_packs in memberships.items()
            if not assigned_packs
        )
        if unassigned:
            raise ValueError(
                "Every built-in Control must belong to a Control Pack: "
                + ", ".join(sorted(unassigned))
                + "."
            )

        self._bundles = bundles
        self._bundle_index = bundle_index
        self._controls = tuple(
            sorted(control_index.values(), key=lambda item: (item.name.casefold(), item.id))
        )
        self._control_index = control_index
        self._packs = tuple(pack for bundle in bundles for pack in bundle.packs)
        self._pack_index = pack_index
        self._memberships = {
            control_id: tuple(assigned_packs)
            for control_id, assigned_packs in memberships.items()
        }

    @property
    def bundles(self) -> tuple[ControlLibraryBundle, ...]:
        return self._bundles

    @property
    def controls(self) -> tuple[ControlSpec, ...]:
        return self._controls

    @property
    def packs(self) -> tuple[ControlPackSpec, ...]:
        return self._packs

    def bundle(self, bundle_id: str) -> ControlLibraryBundle | None:
        return self._bundle_index.get(bundle_id)

    def control(self, control_id: str) -> ControlSpec | None:
        return self._control_index.get(control_id)

    def control_pack(self, pack_id: str) -> ControlPackSpec | None:
        return self._pack_index.get(pack_id)

    def packs_for_control(self, control_id: str) -> tuple[ControlPackSpec, ...]:
        return self._memberships.get(control_id, ())

    @staticmethod
    def _validate_bundle(bundle: ControlLibraryBundle) -> None:
        _required(bundle.id, "Control Library bundle ID")
        _required(bundle.source.name, f"Control Library {bundle.id!r} source name")
        _required(bundle.source.version, f"Control Library {bundle.id!r} version")
        _required(bundle.source.commit, f"Control Library {bundle.id!r} commit")
        _required(bundle.source.license, f"Control Library {bundle.id!r} license")
        _required(bundle.source.url, f"Control Library {bundle.id!r} source URL")
        if not bundle.controls:
            raise ValueError(f"Control Library {bundle.id!r} contains no Controls.")
        if not bundle.packs:
            raise ValueError(f"Control Library {bundle.id!r} contains no Control Packs.")

        controls: dict[str, ControlSpec] = {}
        for control in bundle.controls:
            _validate_control(control, bundle)
            if control.id in controls:
                raise ValueError(
                    f"Control Library {bundle.id!r} contains duplicate Control "
                    f"{control.id!r}."
                )
            controls[control.id] = control

        pack_ids: set[str] = set()
        for pack in bundle.packs:
            _validate_pack(pack, bundle, controls)
            if pack.id in pack_ids:
                raise ValueError(
                    f"Control Library {bundle.id!r} contains duplicate Control Pack "
                    f"{pack.id!r}."
                )
            pack_ids.add(pack.id)


def _validate_control(
    control: ControlSpec,
    bundle: ControlLibraryBundle,
) -> None:
    _required(control.id, "Control ID")
    _required(control.name, f"Control {control.id!r} name")
    _required(control.description, f"Control {control.id!r} description")
    if control.version != bundle.source.version:
        raise ValueError(
            f"Control {control.id!r} version {control.version!r} does not match "
            f"bundle version {bundle.source.version!r}."
        )
    if not control.rules:
        raise ValueError(f"Control {control.id!r} contains no Rules.")
    if not control.allowed_actions:
        raise ValueError(f"Control {control.id!r} allows no actions.")

    rule_ids: set[str] = set()
    for rule in control.rules:
        _validate_rule(rule, control)
        if rule.id in rule_ids:
            raise ValueError(
                f"Control {control.id!r} contains duplicate Rule {rule.id!r}."
            )
        rule_ids.add(rule.id)


def _validate_rule(rule: RuleSpec, control: ControlSpec) -> None:
    _required(rule.id, f"Control {control.id!r} Rule ID")
    _required(rule.name, f"Control {control.id!r} Rule {rule.id!r} name")
    if rule.detector not in _DETECTORS:
        raise ValueError(
            f"Control {control.id!r} Rule {rule.id!r} has unsupported detector "
            f"{rule.detector!r}."
        )
    if not rule.phases or any(phase not in _PHASES for phase in rule.phases):
        raise ValueError(
            f"Control {control.id!r} Rule {rule.id!r} requires a supported phase."
        )
    if len(set(rule.phases)) != len(rule.phases):
        raise ValueError(
            f"Control {control.id!r} Rule {rule.id!r} repeats a phase."
        )
    if rule.action not in control.allowed_actions:
        raise ValueError(
            f"Control {control.id!r} Rule {rule.id!r} uses disallowed action "
            f"{rule.action!r}."
        )
    if rule.detector == "regex" and not (rule.expression or "").strip():
        raise ValueError(
            f"Regex Rule {control.id!r}/{rule.id!r} requires an expression."
        )
    if rule.detector == "keyword" and not rule.keywords:
        raise ValueError(
            f"Keyword Rule {control.id!r}/{rule.id!r} requires keywords."
        )
    if any(not keyword.value.strip() for keyword in (*rule.keywords, *rule.always_block)):
        raise ValueError(
            f"Control {control.id!r} Rule {rule.id!r} contains an empty keyword."
        )


def _validate_pack(
    pack: ControlPackSpec,
    bundle: ControlLibraryBundle,
    controls: dict[str, ControlSpec],
) -> None:
    _required(pack.id, "Control Pack ID")
    _required(pack.name, f"Control Pack {pack.id!r} name")
    _required(pack.description, f"Control Pack {pack.id!r} description")
    _required(pack.source, f"Control Pack {pack.id!r} source")
    if pack.version != bundle.source.version:
        raise ValueError(
            f"Control Pack {pack.id!r} version {pack.version!r} does not match "
            f"bundle version {bundle.source.version!r}."
        )
    if not pack.control_ids:
        raise ValueError(f"Control Pack {pack.id!r} contains no Controls.")
    if len(set(pack.control_ids)) != len(pack.control_ids):
        raise ValueError(f"Control Pack {pack.id!r} repeats a Control.")
    unknown = tuple(control_id for control_id in pack.control_ids if control_id not in controls)
    if unknown:
        raise ValueError(
            f"Control Pack {pack.id!r} references unknown Controls: "
            + ", ".join(unknown)
            + "."
        )
    parameter_names = tuple(parameter.name for parameter in pack.parameters)
    if any(not name.strip() for name in parameter_names):
        raise ValueError(f"Control Pack {pack.id!r} has an unnamed parameter.")
    if len(set(parameter_names)) != len(parameter_names):
        raise ValueError(f"Control Pack {pack.id!r} repeats a parameter.")


def _required(value: str, label: str) -> None:
    if not value.strip():
        raise ValueError(f"{label} is required.")


@lru_cache(maxsize=1)
def registry() -> ControlLibraryRegistry:
    return ControlLibraryRegistry((import_bundle(),))


def control_library() -> ControlLibraryBundle:
    bundle = registry().bundle(BUILTIN_LIBRARY_ID)
    if bundle is None:  # pragma: no cover - protected by registry construction
        raise RuntimeError(f"Built-in Control Library {BUILTIN_LIBRARY_ID!r} is missing.")
    return bundle


def controls() -> tuple[ControlSpec, ...]:
    return registry().controls


def control(control_id: str) -> ControlSpec | None:
    return registry().control(control_id)


def control_packs() -> tuple[ControlPackSpec, ...]:
    return registry().packs


def control_pack(pack_id: str) -> ControlPackSpec | None:
    return registry().control_pack(pack_id)


def packs_for_control(control_id: str) -> tuple[ControlPackSpec, ...]:
    return registry().packs_for_control(control_id)
