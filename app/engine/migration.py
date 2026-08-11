from __future__ import annotations

import asyncio
import hashlib
import time
from collections.abc import Callable
from typing import Protocol

from .contracts import (
    EngineRequest,
    EvaluationDecision,
    GuardrailEngine,
    RuntimeCoverage,
)


class RuntimeModeStore(Protocol):
    def version_execution_mode(self, guardrail_id: str, version: int) -> str: ...

    def record_runtime_comparison(self, **values) -> None: ...


class RuntimeRolloutCoordinator:
    """Temporary release coordinator around a NeMo-primary production runtime.

    Every newly compiled version starts in ``nemo_only``. Other modes exist only
    to gather migration evidence before a version is promoted back to that final
    state; they never alter the immutable NeMo configuration.
    """

    name = "nemo-runtime-rollout"
    supported_phases = frozenset({"input", "output"})

    def __init__(
        self,
        nemo: GuardrailEngine,
        legacy_factory: Callable[[], GuardrailEngine],
        store: RuntimeModeStore,
        *,
        canary_percent: int = 10,
        transition_enabled: bool = False,
    ) -> None:
        self._nemo = nemo
        self._legacy_factory = legacy_factory
        self._legacy_instance: GuardrailEngine | None = None
        self._store = store
        self._canary_percent = max(0, min(canary_percent, 100))
        self._transition_enabled = transition_enabled
        self._background: set[asyncio.Task] = set()

    @property
    def _legacy(self) -> GuardrailEngine:
        if self._legacy_instance is None:
            self._legacy_instance = self._legacy_factory()
        return self._legacy_instance

    async def evaluate(self, request: EngineRequest) -> EvaluationDecision:
        if not self._transition_enabled:
            return await self._nemo.evaluate(request)
        mode = self._store.version_execution_mode(
            request.plan.guardrail_id,
            request.plan.guardrail_version,
        )
        if mode == "nemo_only":
            return await self._nemo.evaluate(request)
        if mode == "legacy_only":
            return await self._legacy.evaluate(request)
        if mode == "shadow_nemo":
            legacy, legacy_ms = await _timed(self._legacy, request)
            self._spawn_compare(
                request,
                mode,
                "legacy",
                primary=legacy,
                primary_ms=legacy_ms,
                shadow_engine=self._nemo,
            )
            return legacy
        if mode == "nemo_primary_legacy_shadow":
            nemo, nemo_ms = await _timed(self._nemo, request)
            self._spawn_compare(
                request,
                mode,
                "nemo",
                primary=nemo,
                primary_ms=nemo_ms,
                shadow_engine=self._legacy,
            )
            return nemo
        if mode == "nemo_canary":
            use_nemo = _canary_bucket(request) < self._canary_percent
            primary_engine = self._nemo if use_nemo else self._legacy
            shadow_engine = self._legacy if use_nemo else self._nemo
            primary_name = "nemo" if use_nemo else "legacy"
            primary, primary_ms = await _timed(primary_engine, request)
            self._spawn_compare(
                request,
                mode,
                primary_name,
                primary=primary,
                primary_ms=primary_ms,
                shadow_engine=shadow_engine,
            )
            return primary

        # Explicit compare is a release gate: wait for both results, record the
        # diff, and retain legacy behavior until the operator promotes it.
        (legacy, legacy_ms), (nemo, nemo_ms) = await asyncio.gather(
            _timed(self._legacy, request),
            _timed(self._nemo, request),
        )
        self._record(
            request,
            mode,
            "legacy",
            legacy=legacy,
            nemo=nemo,
            legacy_ms=legacy_ms,
            nemo_ms=nemo_ms,
        )
        return legacy

    async def drain(self) -> None:
        if self._background:
            await asyncio.gather(*tuple(self._background), return_exceptions=True)

    async def shutdown(self) -> None:
        await self.drain()
        shutdown = getattr(self._nemo, "shutdown", None)
        if shutdown is not None:
            await shutdown()

    def ready(self) -> bool:
        ready = getattr(self._nemo, "ready", None)
        return bool(ready()) if ready is not None else True

    def _spawn_compare(
        self,
        request: EngineRequest,
        mode: str,
        primary_name: str,
        *,
        primary: EvaluationDecision,
        primary_ms: int,
        shadow_engine: GuardrailEngine,
    ) -> None:
        async def run() -> None:
            shadow, shadow_ms = await _timed(shadow_engine, request)
            legacy = primary if primary_name == "legacy" else shadow
            nemo = primary if primary_name == "nemo" else shadow
            legacy_ms = primary_ms if primary_name == "legacy" else shadow_ms
            nemo_ms = primary_ms if primary_name == "nemo" else shadow_ms
            self._record(
                request,
                mode,
                primary_name,
                legacy=legacy,
                nemo=nemo,
                legacy_ms=legacy_ms,
                nemo_ms=nemo_ms,
            )

        task = asyncio.create_task(run())
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    def _record(
        self,
        request: EngineRequest,
        mode: str,
        primary_engine: str,
        *,
        legacy: EvaluationDecision,
        nemo: EvaluationDecision,
        legacy_ms: int,
        nemo_ms: int,
    ) -> None:
        legacy_findings = _finding_signature(legacy)
        nemo_findings = _finding_signature(nemo)
        self._store.record_runtime_comparison(
            guardrail_id=request.plan.guardrail_id,
            guardrail_version=request.plan.guardrail_version,
            execution_mode=mode,
            primary_engine=primary_engine,
            primary_decision=legacy.decision if primary_engine == "legacy" else nemo.decision,
            legacy_decision=legacy.decision,
            nemo_decision=nemo.decision,
            decision_match=legacy.decision == nemo.decision,
            action_match=legacy.action == nemo.action,
            finding_match=legacy_findings == nemo_findings,
            legacy_latency_ms=legacy_ms,
            nemo_latency_ms=nemo_ms,
        )


async def _timed(
    engine: GuardrailEngine,
    request: EngineRequest,
) -> tuple[EvaluationDecision, int]:
    started = time.perf_counter()
    try:
        decision = await engine.evaluate(request)
    except Exception as error:
        decision = EvaluationDecision(
            decision="block" if request.mode == "enforce" else "allow",
            action="reject" if request.mode == "enforce" else "pass",
            reason=f"Migration runtime failed closed with {type(error).__name__}.",
            guardrail_id=request.plan.guardrail_id,
            guardrail_version=request.plan.guardrail_version,
            output_delivery=request.plan.output_delivery,
            coverage=RuntimeCoverage(status="none"),
            mode=request.mode,
        )
    return decision, max(0, round((time.perf_counter() - started) * 1_000))


def _canary_bucket(request: EngineRequest) -> int:
    value = "\0".join(
        (
            request.plan.guardrail_id,
            str(request.plan.guardrail_version),
            request.phase,
            request.active_block_id or "",
            request.text,
        )
    )
    return int.from_bytes(hashlib.sha256(value.encode()).digest()[:4], "big") % 100


def _finding_signature(decision: EvaluationDecision) -> tuple[tuple[str, str, str], ...]:
    return tuple(
        sorted(
            (item.risk, item.verdict, item.recommended_action)
            for item in decision.findings
        )
    )
