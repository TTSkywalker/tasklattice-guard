from __future__ import annotations

import asyncio
import difflib
import time
import threading
from collections import OrderedDict
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Protocol

from nemoguardrails import Guardrails, RailsConfig
from nemoguardrails.rails.llm.options import GenerationResponse

from .contracts import (
    AppliedIntervention,
    ContentPatch,
    DecisionFragment,
    EngineRequest,
    EvaluationDecision,
    EvaluationTraceStep,
    EvaluationUsage,
    GuardrailPlanModule,
    GuardrailPlanSnapshot,
    GuardrailPlanStep,
    GuardrailStage,
    ModuleAssessment,
    NeMoActionBinding,
    NeMoConfigSnapshot,
    RiskFinding,
    RuntimeCoverage,
    StageResult,
)


_CURRENT_REQUEST: ContextVar[EngineRequest | None] = ContextVar(
    "tasklattice_nemo_request",
    default=None,
)
_CURRENT_RESULTS: ContextVar[list["_RuntimeResult"] | None] = ContextVar(
    "tasklattice_nemo_results",
    default=None,
)
_ACTION_PRIORITY = (
    "reject",
    "clarify",
    "fallback",
    "regenerate",
    "rewrite",
    "redirect",
    "redact",
    "pass",
)


class NeMoConfigStore(Protocol):
    def plan(self, guardrail_id: str, version: int) -> GuardrailPlanSnapshot: ...

    def nemo_config(self, guardrail_id: str, version: int) -> NeMoConfigSnapshot: ...

    def active_plan_keys(self) -> tuple[tuple[str, int], ...]: ...


@dataclass(slots=True)
class _RuntimeResult:
    binding: NeMoActionBinding
    result: StageResult
    latency_ms: int


@dataclass(slots=True)
class NeMoRailsInstance:
    config: NeMoConfigSnapshot
    plan: GuardrailPlanSnapshot
    rails: Guardrails
    actions: "NeMoActionExecutor"


@dataclass(frozen=True, slots=True)
class _ActionStageGroup:
    """Read-only diagnostics for configured Action providers."""

    _children: tuple[GuardrailStage, ...]


class _ActionStageCatalog:
    """Compatibility-only introspection; this object never executes a policy DAG."""

    def __init__(self, stages: tuple[GuardrailStage, ...]) -> None:
        self._stages = {
            stage_name: _ActionStageGroup(
                tuple(item for item in stages if item.stage == stage_name)
            )
            for stage_name in ("deterministic", "fast_semantic", "deep_judge")
        }


class NeMoActionExecutor:
    """Expose version-pinned TaskLattice evaluators exclusively as NeMo actions."""

    def __init__(
        self,
        plan: GuardrailPlanSnapshot,
        config: NeMoConfigSnapshot,
        stages: tuple[GuardrailStage, ...],
    ) -> None:
        self._plan = plan
        self._config = config
        self._bindings = {item.id: item for item in config.action_bindings}
        self._stages = stages

    def register(self, rails: Guardrails) -> None:
        rails.register_action(
            self.evaluate_phase,
            name="tasklattice_evaluate_phase",
        )
        rails.register_action(
            self.evaluate_step,
            name="tasklattice_evaluate_step",
        )
        rails.register_action(
            self.resolve,
            name="tasklattice_resolve",
        )
        if "sensitive_data_detection" in self._config.required_features:
            # Keep NeMo's native sensitive-data flows while providing a small,
            # dependency-free detector with the product's existing semantics.
            rails.register_action(
                self.detect_sensitive_data,
                name="detect_sensitive_data",
            )
            rails.register_action(
                self.mask_sensitive_data,
                name="mask_sensitive_data",
            )

    async def evaluate_phase(
        self,
        text: str,
        phase: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        request = self._request()
        if phase != request.phase:
            raise RuntimeError(
                f"NeMo requested {phase!r} Actions during a {request.phase!r} evaluation."
            )
        groups: dict[str, list[NeMoActionBinding]] = {}
        for binding in self._config.bindings_for(request.phase):
            groups.setdefault(binding.risk, []).append(binding)
        # Risk families are detection-only here and evaluate independently. Any
        # content mutation is deferred to the deterministic resolver/NeMo rail.
        await asyncio.gather(
            *(
                self._evaluate_risk(text, tuple(bindings), context)
                for bindings in groups.values()
            )
        )
        results = _runtime_results()
        return {
            "phase": phase,
            "action_count": len(results),
            "unsafe": any(item.result.verdict == "unsafe" for item in results),
            "error": any(item.result.verdict == "error" for item in results),
        }

    async def _evaluate_risk(
        self,
        text: str,
        bindings: tuple[NeMoActionBinding, ...],
        context: dict[str, Any] | None,
    ) -> None:
        previous: str | None = None
        for index, binding in enumerate(bindings):
            should_run = (
                index == 0
                or binding.escalation == "always" and previous in {"safe", "uncertain"}
                or binding.escalation == "on_uncertain" and previous == "uncertain"
                or binding.escalation == "never" and previous is None
            )
            if not should_run:
                continue
            if self._stage(binding) is None and binding.escalation == "on_uncertain":
                # A contextual judge is optional when a decisive local detector
                # is already the first Action for this risk family.
                continue
            result = await self.evaluate_step(text, binding.id, context)
            previous = str(result["verdict"])

    async def evaluate_step(
        self,
        text: str,
        step_id: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        binding = self._bindings.get(step_id)
        if binding is None:
            return self._record(
                context,
                NeMoActionBinding(
                    id=step_id,
                    risk="unknown",
                    stage="deterministic",
                    phases=(self._request().phase,),
                    on_unsafe="reject",
                ),
                StageResult(
                    "error",
                    text,
                    reason=f"NeMo action binding {step_id!r} is unavailable.",
                ),
                0,
            )
        started = time.perf_counter()
        stage = self._stage(binding)
        if stage is None:
            result = StageResult(
                "error",
                text,
                reason=(
                    f"No configured NeMo Action supports {binding.risk} "
                    f"at the {binding.stage.replace('_', ' ')} stage."
                ),
            )
        else:
            request = self._engine_request(text)
            step = _step(binding)
            try:
                async with asyncio.timeout(binding.timeout_ms / 1_000):
                    result = await stage.evaluate(request, (step,))
            except TimeoutError:
                result = StageResult(
                    "error",
                    text,
                    reason=(
                        f"NeMo action {binding.id} exceeded its "
                        f"{binding.timeout_ms} ms timeout."
                    ),
                )
            except Exception as error:
                result = StageResult(
                    "error",
                    text,
                    reason=f"NeMo action {binding.id} failed with {type(error).__name__}.",
                )
        latency = max(0, round((time.perf_counter() - started) * 1_000))
        return self._record(context, binding, result, latency)

    async def detect_sensitive_data(
        self,
        source: str,
        text: str,
        context: dict[str, Any] | None = None,
        **_: Any,
    ) -> bool:
        result, binding, latency = await self._pii(text)
        self._record(context, binding, result, latency)
        return result.verdict == "unsafe"

    async def mask_sensitive_data(
        self,
        source: str,
        text: str,
        context: dict[str, Any] | None = None,
        **_: Any,
    ) -> str:
        result, binding, latency = await self._pii(text)
        self._record(context, binding, result, latency)
        return result.content if result.verdict == "unsafe" else text

    async def resolve(
        self,
        text: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        runtime_results = _runtime_results()
        unsafe = tuple(item for item in runtime_results if item.result.verdict == "unsafe")
        errors = tuple(item for item in runtime_results if item.result.verdict == "error")
        uncertain = tuple(item for item in runtime_results if item.result.verdict == "uncertain")
        actions = [
            finding.recommended_action
            for item in unsafe
            for finding in item.result.findings
        ] or [item.binding.on_unsafe for item in unsafe]
        if errors:
            action = "reject"
            reason = errors[0].result.reason or "A required NeMo action failed closed."
        elif actions:
            action = next(value for value in _ACTION_PRIORITY if value in set(actions))
            reason = next(
                (
                    item.result.reason
                    for item in unsafe
                    if item.binding.on_unsafe == action and item.result.reason
                ),
                unsafe[0].result.reason,
            )
        elif uncertain:
            action = "clarify"
            reason = uncertain[0].result.reason or "More context is required."
        else:
            action = "pass"
            reason = "All NeMo Actions passed."

        request = self._request()
        resolved = _resolved_content(request.text, action, unsafe)
        enforce = request.mode == "enforce"
        blocked = enforce and action == "reject"
        modified = enforce and action not in {"pass", "reject"}
        payload = {
            "decision": "block" if blocked else "transform" if modified else "allow",
            "action": action if enforce else "pass",
            "proposed_action": action,
            "blocked": blocked,
            "modified": modified,
            "content": resolved if modified else text,
            "reason": reason,
        }
        if context is not None:
            context["tasklattice_decision"] = payload
        return payload

    async def _pii(
        self,
        text: str,
    ) -> tuple[StageResult, NeMoActionBinding, int]:
        request = self._request()
        phase = request.phase
        plan_step = next(
            (
                step
                for step in self._plan.steps
                if step.risk == "pii"
                and step.stage == "deterministic"
                and phase in step.phases
            ),
            None,
        )
        binding = NeMoActionBinding(
            id="pii:native-sensitive-data",
            risk="pii",
            stage="deterministic",
            phases=(phase,),
            on_unsafe=plan_step.on_unsafe if plan_step is not None else "redact",
            timeout_ms=750,
            parameters=plan_step.parameters if plan_step is not None else (),
        )
        stage = next((item for item in self._stages if item.stage == "deterministic"), None)
        started = time.perf_counter()
        if stage is None or plan_step is None:
            result = StageResult("error", text, reason="PII action is unavailable.")
        else:
            try:
                async with asyncio.timeout(binding.timeout_ms / 1_000):
                    result = await stage.evaluate(self._engine_request(text), (plan_step,))
            except Exception as error:
                result = StageResult(
                    "error",
                    text,
                    reason=f"PII action failed with {type(error).__name__}.",
                )
        return result, binding, max(0, round((time.perf_counter() - started) * 1_000))

    def _stage(self, binding: NeMoActionBinding) -> GuardrailStage | None:
        return next(
            (
                stage
                for stage in self._stages
                if stage.stage == binding.stage
                and self._request().phase in stage.supported_phases
                and (
                    not stage.supported_risks
                    or binding.risk in stage.supported_risks
                )
            ),
            None,
        )

    def _engine_request(self, text: str) -> EngineRequest:
        request = self._request()
        return EngineRequest(
            phase=request.phase,
            text=text,
            plan=self._plan,
            context_messages=request.context_messages,
            trusted_instruction=request.trusted_instruction,
            target_source=request.target_source,
            mode=request.mode,
            evidence_scope=request.evidence_scope,
            content_view=request.content_view,
            active_block_id=request.active_block_id,
        )

    @staticmethod
    def _request() -> EngineRequest:
        request = _CURRENT_REQUEST.get()
        if request is None:
            raise RuntimeError("A NeMo Action ran outside a Guardrail request context.")
        return request

    @staticmethod
    def _record(
        context: dict[str, Any] | None,
        binding: NeMoActionBinding,
        result: StageResult,
        latency_ms: int,
    ) -> dict[str, Any]:
        runtime_result = _RuntimeResult(binding, result, latency_ms)
        results = _CURRENT_RESULTS.get()
        if results is not None:
            results.append(runtime_result)
        if context is not None:
            context.setdefault("tasklattice_action_results", []).append(
                {
                    "step_id": binding.id,
                    "risk": binding.risk,
                    "stage": binding.stage,
                    "verdict": result.verdict,
                    "action": binding.on_unsafe,
                    "latency_ms": latency_ms,
                }
            )
        return {
            "step_id": binding.id,
            "risk": binding.risk,
            "stage": binding.stage,
            "verdict": result.verdict,
            "content": result.content,
            "reason": result.reason,
            "action": binding.on_unsafe,
            "latency_ms": latency_ms,
        }


class NeMoRailsRegistry:
    """Construct and cache one immutable NeMo runtime per Guardrail version."""

    def __init__(
        self,
        store: NeMoConfigStore,
        stages: tuple[GuardrailStage, ...],
        *,
        max_entries: int = 128,
    ) -> None:
        self._store = store
        self._stages = stages
        self._max_entries = max(1, max_entries)
        self._items: OrderedDict[tuple[str, int, str], NeMoRailsInstance] = OrderedDict()
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0
        self.reload()

    @property
    def action_stages(self) -> tuple[GuardrailStage, ...]:
        return self._stages

    def get(self, plan: GuardrailPlanSnapshot) -> NeMoRailsInstance:
        return self.acquire(plan)[0]

    def acquire(
        self,
        plan: GuardrailPlanSnapshot,
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
        self,
        plan: GuardrailPlanSnapshot,
        config: NeMoConfigSnapshot,
    ) -> None:
        key = (plan.guardrail_id, plan.guardrail_version, _config_checksum(config))
        with self._lock:
            if key not in self._items:
                self._build(plan, config, key)

    def reload(self) -> None:
        active = set(self._store.active_plan_keys())
        with self._lock:
            for guardrail_id, version in active:
                plan = self._store.plan(guardrail_id, version)
                self.get(plan)

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "entries": len(self._items),
                "hits": self._hits,
                "misses": self._misses,
            }

    def ready(self) -> bool:
        with self._lock:
            available = {key[:2] for key in self._items}
            return set(self._store.active_plan_keys()) <= available

    async def shutdown(self) -> None:
        with self._lock:
            rails = tuple(item.rails for item in self._items.values())
            self._items.clear()
        await asyncio.gather(
            *(item.shutdown() for item in rails),
            return_exceptions=True,
        )

    def _build(
        self,
        plan: GuardrailPlanSnapshot,
        config: NeMoConfigSnapshot,
        key: tuple[str, int, str],
    ) -> NeMoRailsInstance:
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
        actions = NeMoActionExecutor(plan, config, self._stages)
        actions.register(rails)
        item = NeMoRailsInstance(config, plan, rails, actions)
        self._items[key] = item
        self._items.move_to_end(key)
        while len(self._items) > self._max_entries:
            candidate = next(iter(self._items))
            if candidate[:2] in set(self._store.active_plan_keys()):
                self._items.move_to_end(candidate)
                if all(key[:2] in set(self._store.active_plan_keys()) for key in self._items):
                    break
                continue
            self._items.pop(candidate)
        return item

    def _validate_bindings(self, config: NeMoConfigSnapshot) -> None:
        first_binding_ids = {
            selected[0].id
            for phase in ("input", "output")
            for risk in {item.risk for item in config.bindings_for(phase)}
            if (selected := config.bindings_for(phase, risk))
        }
        missing = tuple(
            binding
            for binding in config.action_bindings
            if not any(
                stage.stage == binding.stage
                and all(phase in stage.supported_phases for phase in binding.phases)
                and (
                    not stage.supported_risks
                    or binding.risk in stage.supported_risks
                )
                for stage in self._stages
            )
            and (
                binding.id in first_binding_ids
                or binding.escalation != "on_uncertain"
            )
        )
        if "sensitive_data_detection" in config.required_features and not any(
            stage.stage == "deterministic" and (
                not stage.supported_risks or "pii" in stage.supported_risks
            )
            for stage in self._stages
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


class NeMoGuardrailsEngine:
    """Run every production Guardrail decision through a version-pinned NeMo runtime."""

    name = "nemo-guardrails"
    supported_phases = frozenset({"input", "output"})

    def __init__(self, registry: NeMoRailsRegistry) -> None:
        self._registry = registry
        # Existing deployment diagnostics inspect configured provider groups.
        # Policy orchestration itself remains exclusively inside NeMo.
        self._runner = _ActionStageCatalog(registry.action_stages)

    async def evaluate(self, request: EngineRequest) -> EvaluationDecision:
        instance, cache_hit, queue_latency_ms = self._registry.acquire(request.plan)
        messages = _messages(request)
        token = _CURRENT_REQUEST.set(request)
        results: list[_RuntimeResult] = []
        result_token = _CURRENT_RESULTS.set(results)
        started = time.perf_counter()
        try:
            async with asyncio.timeout(_request_timeout_ms(request) / 1_000):
                response = await instance.rails.generate_async(
                    messages=messages,
                    options={
                        "rails": [request.phase],
                        "output_vars": True,
                        "log": {"activated_rails": True, "llm_calls": True},
                    },
                )
        except Exception as error:
            duration = max(0, round((time.perf_counter() - started) * 1_000))
            return _failed_decision(
                request,
                error,
                duration,
                instance.config,
                cache_hit=cache_hit,
                queue_latency_ms=queue_latency_ms,
            )
        finally:
            _CURRENT_RESULTS.reset(result_token)
            _CURRENT_REQUEST.reset(token)
        if not isinstance(response, GenerationResponse):
            return _failed_decision(
                request,
                RuntimeError(f"Unexpected NeMo response {type(response).__name__}."),
                max(0, round((time.perf_counter() - started) * 1_000)),
                instance.config,
                cache_hit=cache_hit,
                queue_latency_ms=queue_latency_ms,
            )
        return _decision(
            request,
            response,
            instance.config,
            tuple(results),
            cache_hit=cache_hit,
            queue_latency_ms=queue_latency_ms,
        )

    async def shutdown(self) -> None:
        await self._registry.shutdown()

    def ready(self) -> bool:
        return self._registry.ready()


def _step(binding: NeMoActionBinding) -> GuardrailPlanStep:
    return GuardrailPlanStep(
        id=binding.id,
        risk=binding.risk,
        stage=binding.stage,
        phases=binding.phases,
        on_unsafe=binding.on_unsafe,
        escalation=binding.escalation,
        parameters=binding.parameters,
    )


def _runtime_results() -> tuple[_RuntimeResult, ...]:
    return tuple(_CURRENT_RESULTS.get() or ())


def _messages(request: EngineRequest) -> list[dict[str, Any]]:
    context = {
        "tasklattice_action_results": [],
        "tasklattice_guardrail_id": request.plan.guardrail_id,
        "tasklattice_guardrail_version": request.plan.guardrail_version,
        "tasklattice_phase": request.phase,
    }
    messages: list[dict[str, Any]] = [{"role": "context", "content": context}]
    messages.extend(
        {
            "role": str(item.get("role")),
            "content": str(item.get("content", "")),
        }
        for item in request.context_messages
        if item.get("role") in {"system", "user", "assistant"}
        and isinstance(item.get("content"), str)
    )
    role = "user" if request.phase == "input" else "assistant"
    if messages and messages[-1].get("role") == role:
        messages[-1] = {"role": role, "content": request.text}
    else:
        messages.append({"role": role, "content": request.text})
    return messages


def _decision(
    request: EngineRequest,
    response: GenerationResponse,
    config: NeMoConfigSnapshot,
    runtime_results: tuple[_RuntimeResult, ...],
    *,
    cache_hit: bool,
    queue_latency_ms: int,
) -> EvaluationDecision:
    output_data = response.output_data or {}
    custom = output_data.get("tasklattice_decision")
    activated = tuple(response.log.activated_rails or ()) if response.log else ()
    stopping = next((rail for rail in activated if rail.stop), None)
    native_risk = _native_risk(stopping.name if stopping else None)
    native_action = _action_for_risk(request.plan, native_risk, request.phase)
    result_content = _response_content(response, request.text)

    if isinstance(custom, dict):
        decision = str(custom.get("decision", "allow"))
        action = str(custom.get("action", "pass"))
        reason = str(custom.get("reason", "NeMo Guardrails completed."))
    elif stopping is not None:
        decision = (
            "allow"
            if request.mode == "detect"
            else "block"
            if native_action == "reject"
            else "transform"
        )
        action = "pass" if request.mode == "detect" else native_action
        reason = f"NeMo rail {stopping.name} blocked the interaction."
    elif result_content != request.text and request.mode == "enforce":
        decision = "transform"
        action = native_action if native_action != "reject" else "redact"
        reason = "NeMo Guardrails modified sensitive content."
    else:
        decision = "allow"
        action = "pass"
        reason = "All activated NeMo rails passed."

    findings = tuple(
        finding
        for item in runtime_results
        for finding in item.result.findings
    )
    if native_risk and not any(item.risk == native_risk for item in findings):
        findings = (
            *findings,
            RiskFinding(
                risk=native_risk,
                verdict="unsafe",
                confidence=0.9,
                evidence=reason,
                recommended_action=native_action,
            ),
        )
    trace = _trace(config, activated, runtime_results, request.active_block_id)
    assessments = _assessments(request, runtime_results, trace, findings)
    interventions = _interventions(request, decision, action, reason, findings)
    modules = request.plan.modules_for(request.phase)
    complete = not any(item.status == "error" for item in assessments)
    coverage = RuntimeCoverage(
        status="complete" if complete else "partial",
        guarded_items=1 if complete else 0,
        total_items=1,
        guarded_characters=len(request.text) if complete else 0,
        total_characters=len(request.text),
        required_modules_completed=sum(item.status != "error" for item in assessments),
        required_modules_total=len(modules),
    )
    return EvaluationDecision(
        decision=decision,  # type: ignore[arg-type]
        action=action,  # type: ignore[arg-type]
        reason=reason,
        texts=(result_content,) if decision == "transform" else (),
        guardrail_id=request.plan.guardrail_id,
        guardrail_version=request.plan.guardrail_version,
        output_delivery=request.plan.output_delivery,
        findings=findings,
        trace=trace,
        assessments=assessments,
        interventions=interventions,
        coverage=coverage,
        usage=EvaluationUsage(
            module_invocations=len(assessments),
            evaluator_invocations=len(assessments),
            text_characters=len(request.text),
            rail_invocations=len(activated),
            action_invocations=sum(
                len(rail.executed_actions) for rail in activated
            ),
            model_invocations=(
                int(response.log.stats.llm_calls_count or 0)
                if response.log is not None
                else 0
            ),
            cache_hits=int(cache_hit),
            cache_misses=int(not cache_hit),
            queue_latency_ms=queue_latency_ms,
            runtime_engine=config.runtime_engine,
            config_checksum=_config_checksum(config),
        ),
        mode=request.mode,
    )


def _trace(config, activated, results, content_block_id):
    trace = [
        EvaluationTraceStep(
            id=f"nemo:config:{config.guardrail_id}:{config.guardrail_version}",
            kind="runtime",
            name="NeMo Guardrails",
            status="active",
            detail=(
                f"Executed immutable {config.compiler_version} configuration "
                f"with {config.runtime_engine}; checksum={_config_checksum(config)}."
            ),
            content_block_id=content_block_id,
        )
    ]
    for index, rail in enumerate(activated):
        trace.append(
            EvaluationTraceStep(
                id=f"nemo:rail:{index}",
                kind="rail",
                name=rail.name,
                status="blocked" if rail.stop else "passed",
                detail=f"NeMo {rail.type} rail {'stopped' if rail.stop else 'continued'} processing.",
                duration_ms=max(0, round((rail.duration or 0) * 1_000)),
                verdict="unsafe" if rail.stop else "safe",
                route="enforce" if rail.stop else "complete",
                risk=_native_risk(rail.name),
                content_block_id=content_block_id,
            )
        )
    for item in results:
        trace.extend(item.result.trace)
        trace.append(
            EvaluationTraceStep(
                id=f"nemo:action:{item.binding.id}",
                kind="evaluator",
                name=item.binding.id,
                status=item.result.verdict,
                detail=item.result.reason or "NeMo Action completed.",
                duration_ms=item.latency_ms,
                stage=item.binding.stage,
                verdict=item.result.verdict,
                route=(
                    "enforce"
                    if item.result.verdict == "unsafe"
                    else "fail_closed"
                    if item.result.verdict == "error"
                    else "escalate"
                    if item.result.verdict == "uncertain"
                    else "complete"
                ),
                risk=item.binding.risk,
                content_block_id=content_block_id,
            )
        )
    return tuple(trace)


def _assessments(request, results, trace, all_findings=(), *, force_error=False):
    assessments = []
    for module in request.plan.modules_for(request.phase):
        risks = {
            step.risk
            for step in request.plan.steps
            if step.id in module.step_ids
        }
        selected = tuple(item for item in results if item.binding.risk in risks)
        native_unsafe = any(
            item.kind == "rail" and item.risk in risks and item.verdict == "unsafe"
            for item in trace
        )
        status = (
            "error"
            if force_error or any(item.result.verdict == "error" for item in selected)
            else "intervene"
            if native_unsafe or any(item.result.verdict == "unsafe" for item in selected)
            else "needs_context"
            if any(item.result.verdict == "uncertain" for item in selected)
            else "pass"
        )
        findings = tuple(
            dict.fromkeys(
                (
                    *(f for item in selected for f in item.result.findings),
                    *(f for f in all_findings if f.risk in risks),
                )
            )
        )
        reason = next(
            (item.result.reason for item in selected if item.result.reason),
            "NeMo rail completed.",
        )
        fragment = DecisionFragment(
            id=f"nemo:{module.id}:{status}",
            module_id=module.id,
            module=module.module,
            status=status,
            action=_strongest(tuple(f.recommended_action for f in findings)),
            findings=findings,
            reason=reason,
            content_block_id=request.active_block_id,
        )
        module_trace = tuple(
            item
            for item in trace
            if item.risk in risks or item.kind == "runtime"
        )
        assessments.append(
            ModuleAssessment(
                module_id=module.id,
                module=module.module,
                status=status,
                fragments=(fragment,),
                coverage=RuntimeCoverage(status="none" if status == "error" else "complete"),
                latency_ms=sum(item.latency_ms for item in selected),
                trace=module_trace,
                content_block_id=request.active_block_id,
            )
        )
    return tuple(assessments)


def _interventions(request, decision, action, reason, findings):
    if decision == "allow" or action == "pass":
        return ()
    return (
        AppliedIntervention(
            kind=action,
            module_id="nemo-guardrails",
            fragment_id=f"nemo:{action}",
            reason=reason,
            content_block_id=request.active_block_id,
        ),
    )


def _failed_decision(
    request,
    error,
    duration,
    config,
    *,
    cache_hit=False,
    queue_latency_ms=0,
):
    reason = f"NeMo Guardrails failed closed with {type(error).__name__}."
    trace = (
        EvaluationTraceStep(
            id="nemo:runtime:error",
            kind="runtime",
            name="NeMo Guardrails",
            status="error",
            detail=reason,
            duration_ms=duration,
            route="fail_closed",
            content_block_id=request.active_block_id,
        ),
    )
    return EvaluationDecision(
        decision="block" if request.mode == "enforce" else "allow",
        action="reject" if request.mode == "enforce" else "pass",
        reason=reason,
        guardrail_id=request.plan.guardrail_id,
        guardrail_version=request.plan.guardrail_version,
        output_delivery=request.plan.output_delivery,
        trace=trace,
        assessments=_assessments(request, (), trace, force_error=True),
        coverage=RuntimeCoverage(
            status="none",
            total_items=1,
            total_characters=len(request.text),
            required_modules_total=len(request.plan.modules_for(request.phase)),
        ),
        usage=EvaluationUsage(
            text_characters=len(request.text),
            cache_hits=int(cache_hit),
            cache_misses=int(not cache_hit),
            queue_latency_ms=queue_latency_ms,
            runtime_engine=config.runtime_engine,
            config_checksum=_config_checksum(config),
            fail_closed=True,
        ),
        mode=request.mode,
    )


def _response_content(response: GenerationResponse, fallback: str) -> str:
    if isinstance(response.response, list) and response.response:
        return str(response.response[-1].get("content", fallback))
    if isinstance(response.response, str):
        return response.response
    return fallback


def _native_risk(rail: str | None) -> str | None:
    if not rail:
        return None
    normalized = rail.casefold()
    if "sensitive data" in normalized or "pii" in normalized:
        return "pii"
    if "topic safety" in normalized:
        return "topic_control"
    if "content safety" in normalized:
        return "content_safety"
    if "jailbreak" in normalized:
        return "jailbreak"
    if "injection" in normalized:
        return "prompt_injection"
    return None


def _action_for_risk(plan, risk, phase):
    step = next(
        (item for item in plan.steps if item.risk == risk and phase in item.phases),
        None,
    )
    return step.on_unsafe if step is not None else "reject"


def _strongest(actions):
    values = set(actions)
    return next((item for item in _ACTION_PRIORITY if item in values), "pass")


def _resolved_content(text, action, unsafe):
    if action == "redact":
        patches = []
        for item in unsafe:
            matcher = difflib.SequenceMatcher(a=text, b=item.result.content, autojunk=False)
            patches.extend(
                ContentPatch(start, end, item.result.content[new_start:new_end])
                for operation, start, end, new_start, new_end in matcher.get_opcodes()
                if operation != "equal"
            )
        content = text
        previous_end = -1
        for patch in sorted(set(patches), key=lambda value: (value.start, value.end)):
            if patch.start < previous_end:
                return "The interaction was withheld because redaction patches conflicted."
            previous_end = patch.end
        for patch in reversed(sorted(set(patches), key=lambda value: (value.start, value.end))):
            content = content[:patch.start] + patch.replacement + content[patch.end:]
        return content
    replacement = next(
        (
            finding.replacement
            for item in unsafe
            for finding in item.result.findings
            if finding.recommended_action == action and finding.replacement is not None
        ),
        None,
    )
    if replacement is not None:
        return replacement
    return {
        "clarify": "More information is required before the request can be evaluated safely.",
        "redirect": "I can help with topics inside this assistant's approved purpose.",
        "regenerate": "The response was withheld and should be regenerated under the active Guardrail.",
        "rewrite": "The response was rewritten to comply with the active Guardrail.",
        "fallback": "A safe fallback response was selected by the active Guardrail.",
    }.get(action, text)


def _config_checksum(config: NeMoConfigSnapshot) -> str:
    import hashlib
    import json
    from dataclasses import asdict

    return hashlib.sha256(
        json.dumps(asdict(config), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _request_timeout_ms(request: EngineRequest) -> int:
    module_timeouts = tuple(
        module.timeout_ms for module in request.plan.modules_for(request.phase)
    )
    # Module detections run concurrently. The small fixed allowance covers NeMo
    # flow evaluation and deterministic resolution outside provider timeouts.
    return max(module_timeouts, default=2_000) + 500
