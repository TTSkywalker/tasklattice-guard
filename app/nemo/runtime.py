from __future__ import annotations

import asyncio
import difflib
import re
import time
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from nemoguardrails import Guardrails
from nemoguardrails.rails.llm.options import GenerationResponse

from ..runtime.content_views import request_view, with_active_text
from ..runtime.contracts import (
    AppliedIntervention,
    ContentPatch,
    DecisionFragment,
    EngineRequest,
    EvaluationDecision,
    EvaluationTraceStep,
    EvaluationUsage,
    GuardrailPlanModule,
    GuardrailPlanSnapshot,
    ModuleAssessment,
    NeMoActionBinding,
    NeMoConfigSnapshot,
    RiskFinding,
    RuntimeCoverage,
    StageResult,
)
from .action_registry import RuntimeActionRegistry
from .actions.contracts import ActionRequest, ActionResult
from .registry import NeMoRailsRegistry


_CURRENT_REQUEST: ContextVar[EngineRequest | None] = ContextVar(
    "tasklattice_nemo_request",
    default=None,
)
_CURRENT_RESULTS: ContextVar[list["_RuntimeResult"] | None] = ContextVar(
    "tasklattice_nemo_results",
    default=None,
)
_CURRENT_DECISION: ContextVar[dict[str, Any] | None] = ContextVar(
    "tasklattice_nemo_decision",
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


@dataclass(slots=True)
class _RuntimeResult:
    binding: NeMoActionBinding
    result: StageResult
    latency_ms: int
    provider_latency_ms: int = 0


class _PatchConflict(ValueError):
    pass


class NeMoActionExecutor:
    """Expose version-pinned TaskLattice evaluators exclusively as NeMo actions."""

    def __init__(
        self,
        plan: GuardrailPlanSnapshot,
        config: NeMoConfigSnapshot,
        registry: RuntimeActionRegistry,
    ) -> None:
        self._plan = plan
        self._config = config
        self._bindings = {item.id: item for item in config.action_bindings}
        self._registry = registry

    def register(self, rails: Guardrails) -> None:
        if _is_colang_v2(self._config):
            if "TaskLatticeEvaluateStepAction" in self._config.colang_content:
                # Compatibility for already-released compiler-v3 snapshots.
                # New artifacts call the fixed, versioned Action name directly.
                rails.register_action(
                    self.evaluate_step,
                    name="TaskLatticeEvaluateStepAction",
                )
            rails.register_action(
                self.record_native,
                name="TaskLatticeRecordNativeAction",
            )
            rails.register_action(
                self.resolve,
                name="TaskLatticeResolveAction",
            )
            rails.register_action(
                self.customer_identifier,
                name="TaskLatticeCustomerIdentifierAction",
            )
            rails.register_action(
                self.record_control,
                name="TaskLatticeRecordControlAction",
            )
            for provider in self._registry.providers():
                rails.register_action(
                    self._action_handler(provider.name, provider.version),
                    name=provider.name,
                )
        else:
            # Released v1 snapshots remain executable while versions are
            # deliberately recompiled and activated through the control plane.
            rails.register_action(
                self.evaluate_phase,
                name="tasklattice_evaluate_phase",
            )
            rails.register_action(self.evaluate_step, name="tasklattice_evaluate_step")
            rails.register_action(
                self.resolve,
                name="tasklattice_resolve",
            )
        if "sensitive_data_detection" in self._config.required_features:
            # Keep NeMo's native sensitive-data flows while providing a small,
            # dependency-free detector with the product's existing semantics.
            rails.register_action(
                self.detect_sensitive_data,
                name=(
                    "DetectSensitiveDataAction"
                    if _is_colang_v2(self._config)
                    else "detect_sensitive_data"
                ),
            )
            rails.register_action(
                self.mask_sensitive_data,
                name=(
                    "MaskSensitiveDataAction"
                    if _is_colang_v2(self._config)
                    else "mask_sensitive_data"
                ),
            )

    def _action_handler(self, action_name: str, action_version: str):
        async def execute_provider(
            text: str,
            binding_id: str,
            context: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            return await self.execute_action(
                action_name,
                action_version,
                text,
                binding_id,
                context,
            )

        return execute_provider

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
            if (
                binding.action_name
                and binding.action_version
                and not self._registry.contains(
                    binding.action_name, binding.action_version
                )
                and binding.escalation == "on_uncertain"
            ):
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
        if not binding.action_name or not binding.action_version:
            return self._record(
                context,
                binding,
                StageResult(
                    "error",
                    text,
                    reason=f"NeMo Action binding {binding.id!r} is not version pinned.",
                ),
                0,
            )
        return await self.execute_action(
            binding.action_name,
            binding.action_version,
            text,
            step_id,
            context,
        )

    async def execute_action(
        self,
        action_name: str,
        action_version: str,
        text: str,
        binding_id: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        binding = self._bindings.get(binding_id)
        if binding is None:
            return await self.evaluate_step(text, binding_id, context)
        started = time.perf_counter()
        provider_latency_ms = 0
        try:
            provider = self._registry.get(action_name, action_version)
            supported_risks = getattr(provider, "risks", frozenset())
            supported_rails = getattr(provider, "rails", frozenset())
            if supported_risks and binding.risk not in supported_risks:
                raise LookupError("provider does not support the pinned Control")
            if supported_rails and self._request().phase not in supported_rails:
                raise LookupError("provider does not support the active Rail")
            action_request = self._action_request(text, binding)
            async with asyncio.timeout(binding.timeout_ms / 1_000):
                action_result = await provider.execute(action_request)
            result = _stage_result(action_result)
            provider_latency_ms = action_result.usage.provider_latency_ms
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            result = StageResult(
                "error",
                text,
                reason=(
                    f"NeMo Action {action_name}@{action_version} hit its "
                    f"{binding.timeout_ms} ms timeout deadline."
                ),
            )
        except Exception as error:
            # Do not include provider messages, responses, credentials, or model
            # content in production errors.
            result = StageResult(
                "error",
                text,
                reason=(
                    f"NeMo Action {action_name}@{action_version} failed with "
                    f"{type(error).__name__}."
                ),
            )
        latency = max(0, round((time.perf_counter() - started) * 1_000))
        return self._record(
            context,
            binding,
            result,
            latency,
            provider_latency_ms=provider_latency_ms or latency,
        )

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
        resolve_started = time.perf_counter()
        runtime_results = self._ordered_results()
        terminal_by_risk: dict[str, _RuntimeResult] = {}
        for item in runtime_results:
            terminal_by_risk[item.binding.risk] = item
        decision_results = tuple(terminal_by_risk.values())
        unsafe = tuple(item for item in decision_results if item.result.verdict == "unsafe")
        errors = tuple(item for item in decision_results if item.result.verdict == "error")
        closed_errors = tuple(
            item for item in errors if self._fails_closed(item.binding)
        )
        uncertain = tuple(
            item for item in decision_results if item.result.verdict == "uncertain"
        )
        actions = [_runtime_action(item) for item in unsafe]
        if closed_errors:
            action = "reject"
            reason = (
                closed_errors[0].result.reason
                or "A required NeMo Action failed closed."
            )
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
        try:
            resolved = _resolved_content(request.text, action, unsafe)
        except _PatchConflict as error:
            action = "reject"
            reason = str(error)
            resolved = request.text
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
            "_resolve_latency_ms": max(
                0, round((time.perf_counter() - resolve_started) * 1_000)
            ),
        }
        if context is not None:
            context["tasklattice_decision"] = payload
        decision = _CURRENT_DECISION.get()
        if decision is not None:
            decision.clear()
            decision.update(payload)
        return payload

    async def record_native(
        self,
        risk: str,
        safe: bool,
        text: str,
        details: Any = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Normalize a NeMo-native Action result into product telemetry."""
        request = self._request()
        step = next(
            (
                item
                for item in self._plan.steps
                if item.risk == risk and request.phase in item.phases
            ),
            None,
        )
        binding = NeMoActionBinding(
            id=step.id if step is not None else f"{risk}:nemo-native",
            risk=risk,
            stage=step.stage if step is not None else "fast_semantic",
            phases=(request.phase,),
            on_unsafe=step.on_unsafe if step is not None else "reject",
            parameters=step.parameters if step is not None else (),
        )
        reason = (
            f"NeMo native {risk.replace('_', ' ')} Action passed."
            if safe
            else _native_reason(risk, details)
        )
        findings = () if safe else (
            RiskFinding(
                risk=risk,
                verdict="unsafe",
                confidence=0.9,
                evidence=reason,
                recommended_action=binding.on_unsafe,
            ),
        )
        result = StageResult(
            "safe" if safe else "unsafe",
            text,
            findings=findings,
            reason=reason,
        )
        return self._record(context, binding, result, 0)

    async def customer_identifier(
        self,
        text: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Reference catalog Action used by the Gate A custom-Control slice."""
        patterns = (
            re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"),
            re.compile(r"(?i)\b(?:customer|cust)[-_ ]?id[:# ]*[A-Z0-9-]{4,}\b"),
        )
        redacted = text
        detected = False
        for pattern in patterns:
            redacted, count = pattern.subn("[CUSTOMER_IDENTIFIER]", redacted)
            detected = detected or count > 0
        return {"detected": detected, "redacted": redacted}

    async def record_control(
        self,
        flow_name: str,
        safe: bool,
        text: str,
        replacement: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        request = self._request()
        binding = next(
            (
                item
                for item in self._config.action_bindings
                if item.control_id is not None
                and (
                    item.flow_name == flow_name
                    or _compiled_control_flow_name(item) == flow_name
                )
                and request.phase in item.phases
            ),
            None,
        )
        if binding is None:
            binding = NeMoActionBinding(
                id=f"unknown-control-flow:{flow_name}",
                risk="unknown_control",
                stage="deterministic",
                phases=(request.phase,),
                on_unsafe="reject",
            )
            result = StageResult(
                "error",
                text,
                reason=f"Control flow {flow_name!r} has no immutable Rail binding.",
            )
            return self._record(context, binding, result, 0)
        reason = (
            f"Control {binding.control_id}@{binding.control_version} "
            f"flow {binding.flow_name} passed."
            if safe
            else f"Control {binding.control_id}@{binding.control_version} detected customer data."
        )
        findings = () if safe else (
            RiskFinding(
                risk=binding.risk,
                verdict="unsafe",
                confidence=1.0,
                evidence=reason,
                recommended_action=binding.on_unsafe,
                replacement=replacement,
            ),
        )
        result = StageResult(
            "safe" if safe else "unsafe",
            replacement if not safe and replacement is not None else text,
            findings=findings,
            reason=reason,
        )
        return self._record(context, binding, result, 0)

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
            id=(
                plan_step.id
                if plan_step is not None
                else "pii:native-sensitive-data"
            ),
            risk="pii",
            stage="deterministic",
            phases=(phase,),
            on_unsafe=plan_step.on_unsafe if plan_step is not None else "redact",
            timeout_ms=750,
            parameters=plan_step.parameters if plan_step is not None else (),
            action_name="TaskLatticePiiAction",
            action_version="1.0.0",
        )
        started = time.perf_counter()
        if plan_step is None or not self._registry.contains(
            "TaskLatticePiiAction", "1.0.0"
        ):
            result = StageResult("error", text, reason="PII action is unavailable.")
        else:
            try:
                async with asyncio.timeout(binding.timeout_ms / 1_000):
                    result = _stage_result(
                        await self._registry.get(
                            "TaskLatticePiiAction", "1.0.0"
                        ).execute(self._action_request(text, binding))
                    )
            except asyncio.CancelledError:
                raise
            except Exception as error:
                result = StageResult(
                    "error",
                    text,
                    reason=f"PII action failed with {type(error).__name__}.",
                )
        return result, binding, max(0, round((time.perf_counter() - started) * 1_000))

    def _ordered_results(self) -> tuple[_RuntimeResult, ...]:
        return _ordered_runtime_results(self._plan, _runtime_results())

    def _engine_request(
        self,
        text: str,
        binding: NeMoActionBinding | None = None,
    ) -> EngineRequest:
        request = self._request()
        content = text
        view = request_view(request)
        module = self._module(binding) if binding is not None else None
        if module is not None and module.input_view == "masked":
            redactions = tuple(
                item
                for item in self._ordered_results()
                if item.result.verdict == "unsafe"
                and _runtime_action(item) == "redact"
            )
            content = _resolved_content(request.text, "redact", redactions)
            view = with_active_text(
                request_view(request),
                content,
                kind="masked",
            )
        return EngineRequest(
            phase=request.phase,
            text=content,
            plan=self._plan,
            context_messages=request.context_messages,
            trusted_instruction=request.trusted_instruction,
            target_source=request.target_source,
            mode=request.mode,
            evidence_scope=request.evidence_scope,
            content_view=view,
            active_block_id=request.active_block_id,
        )

    def _action_request(
        self,
        text: str,
        binding: NeMoActionBinding,
    ) -> ActionRequest:
        prepared = self._engine_request(text, binding)
        view = request_view(prepared)
        return ActionRequest(
            content=prepared.text,
            rail_type=prepared.phase,
            guardrail_id=self._plan.guardrail_id,
            guardrail_version=self._plan.guardrail_version,
            control_id=binding.control_id,
            control_version=binding.control_version,
            trusted_context=(
                ("trusted_instruction", prepared.trusted_instruction),
            ),
            content_blocks=view.blocks,
            deadline=time.monotonic() + binding.timeout_ms / 1_000,
            parameters=binding.parameters,
            risk=binding.risk,
            proposed_action=binding.on_unsafe,
            plan=self._plan,
            binding=binding,
            context_messages=prepared.context_messages,
            target_source=prepared.target_source,
            mode=prepared.mode,
            evidence_scope=prepared.evidence_scope,
            content_view=view,
            active_block_id=prepared.active_block_id,
        )

    def _module(
        self,
        binding: NeMoActionBinding | None,
    ) -> GuardrailPlanModule | None:
        if binding is None:
            return None
        return next(
            (
                module
                for module in self._plan.modules_for(self._request().phase)
                if binding.id in module.step_ids
            ),
            None,
        )

    def _fails_closed(self, binding: NeMoActionBinding) -> bool:
        if binding.control_id is not None:
            return binding.failure_mode == "fail_closed"
        module = self._module(binding)
        return (
            module is None
            or module.required_for_release and module.failure_mode == "fail_closed"
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
        provider_latency_ms: int | None = None,
    ) -> dict[str, Any]:
        runtime_result = _RuntimeResult(
            binding,
            result,
            latency_ms,
            latency_ms if provider_latency_ms is None else provider_latency_ms,
        )
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
                    "provider_latency_ms": runtime_result.provider_latency_ms,
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
            "provider_latency_ms": runtime_result.provider_latency_ms,
        }


class NeMoGuardrailsEngine:
    """Run every production Guardrail decision through a version-pinned NeMo runtime."""

    name = "nemo-guardrails"
    supported_phases = frozenset({"input", "output"})

    def __init__(self, registry: NeMoRailsRegistry) -> None:
        self._registry = registry

    async def evaluate(self, request: EngineRequest) -> EvaluationDecision:
        instance, cache_hit, registry_queue_latency_ms = self._registry.acquire(
            request.plan
        )
        programmable = _is_colang_v2(instance.config)
        messages = (
            _programmable_messages(request)
            if programmable
            else _messages(request)
        )
        token = _CURRENT_REQUEST.set(request)
        results: list[_RuntimeResult] = []
        result_token = _CURRENT_RESULTS.set(results)
        decision_state: dict[str, Any] = {}
        decision_token = _CURRENT_DECISION.set(decision_state)
        started = time.perf_counter()
        queue_started = started
        queue_latency_ms = registry_queue_latency_ms
        admitted = False
        active_concurrency = 0
        try:
            async with asyncio.timeout(_request_timeout_ms(request) / 1_000):
                await instance.admission.acquire()
                admitted = True
                instance.active_requests += 1
                active_concurrency = instance.active_requests
                queue_latency_ms += max(
                    0, round((time.perf_counter() - queue_started) * 1_000)
                )
                if programmable:
                    response = await instance.rails.generate_async(
                        messages=messages,
                        options={
                            "rails": {
                                "input": False,
                                "dialog": False,
                                "output": False,
                            },
                        },
                    )
                else:
                    response = await instance.rails.generate_async(
                        messages=messages,
                        options={
                            "rails": [request.phase],
                            "output_vars": ["tasklattice_decision"],
                            # Aggregate call counts remain available in log.stats;
                            # do not request raw LLM prompts/completions.
                            "log": {"activated_rails": True, "llm_calls": False},
                        },
                    )
        except Exception as error:
            duration = max(0, round((time.perf_counter() - started) * 1_000))
            if not admitted:
                queue_latency_ms += duration
            return _failed_decision(
                request,
                error,
                duration,
                instance.config,
                cache_hit=cache_hit,
                queue_latency_ms=queue_latency_ms,
                active_concurrency=active_concurrency,
            )
        finally:
            if admitted:
                instance.active_requests = max(0, instance.active_requests - 1)
                instance.admission.release()
            _CURRENT_RESULTS.reset(result_token)
            _CURRENT_REQUEST.reset(token)
            _CURRENT_DECISION.reset(decision_token)
        if not isinstance(response, GenerationResponse):
            return _failed_decision(
                request,
                RuntimeError(f"Unexpected NeMo response {type(response).__name__}."),
                max(0, round((time.perf_counter() - started) * 1_000)),
                instance.config,
                cache_hit=cache_hit,
                queue_latency_ms=queue_latency_ms,
                active_concurrency=active_concurrency,
            )
        if programmable and not decision_state:
            return _failed_decision(
                request,
                RuntimeError("The Colang policy completed without a decision."),
                max(0, round((time.perf_counter() - started) * 1_000)),
                instance.config,
                cache_hit=cache_hit,
                queue_latency_ms=queue_latency_ms,
                active_concurrency=active_concurrency,
            )
        return _decision(
            request,
            response,
            instance.config,
            _ordered_runtime_results(request.plan, tuple(results)),
            custom_decision=decision_state or None,
            cache_hit=cache_hit,
            queue_latency_ms=queue_latency_ms,
            active_concurrency=active_concurrency,
        )

    async def shutdown(self) -> None:
        await self._registry.shutdown()

    def ready(self) -> bool:
        return self._registry.ready()


def _runtime_results() -> tuple[_RuntimeResult, ...]:
    return tuple(_CURRENT_RESULTS.get() or ())


def _ordered_runtime_results(
    plan: GuardrailPlanSnapshot,
    results: tuple[_RuntimeResult, ...],
) -> tuple[_RuntimeResult, ...]:
    order = {step.id: index for index, step in enumerate(plan.steps)}
    return tuple(sorted(
        results,
        key=lambda item: (
            order.get(item.binding.id, len(order)),
            item.binding.id,
        ),
    ))


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


def _programmable_messages(request: EngineRequest) -> list[dict[str, Any]]:
    """Drive the Colang 2.x main flow without replaying prior user events."""
    return [
        {
            "role": "context",
            "content": {
                "tasklattice_guardrail_id": request.plan.guardrail_id,
                "tasklattice_guardrail_version": request.plan.guardrail_version,
                "tasklattice_phase": request.phase,
            },
        },
        {"role": "user", "content": request.text},
    ]


def _decision(
    request: EngineRequest,
    response: GenerationResponse,
    config: NeMoConfigSnapshot,
    runtime_results: tuple[_RuntimeResult, ...],
    *,
    custom_decision: dict[str, Any] | None = None,
    cache_hit: bool,
    queue_latency_ms: int,
    active_concurrency: int,
) -> EvaluationDecision:
    output_data = response.output_data or {}
    custom = custom_decision or output_data.get("tasklattice_decision")
    activated = tuple(response.log.activated_rails or ()) if response.log else ()
    stopping = next((rail for rail in activated if rail.stop), None)
    native_risk = _native_risk(stopping.name if stopping else None)
    native_action = _action_for_risk(request.plan, native_risk, request.phase)
    result_content = _response_content(response, request.text)

    if isinstance(custom, dict):
        decision = str(custom.get("decision", "allow"))
        action = str(custom.get("action", "pass"))
        reason = str(custom.get("reason", "NeMo Guardrails completed."))
        result_content = str(custom.get("content", result_content))
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
    trace = _trace(
        request,
        config,
        activated,
        runtime_results,
        request.active_block_id,
        queue_latency_ms=queue_latency_ms,
        resolve_latency_ms=int((custom_decision or {}).get("_resolve_latency_ms", 0)),
    )
    assessments = _assessments(request, runtime_results, trace, findings)
    interventions = _interventions(
        request,
        decision,
        action,
        reason,
        runtime_results,
    )
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
            evaluator_invocations=len(runtime_results),
            text_characters=len(request.text),
            rail_invocations=max(
                len(activated),
                len({item.binding.risk for item in runtime_results}),
            ),
            action_invocations=max(
                len(runtime_results),
                sum(len(rail.executed_actions) for rail in activated),
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
            fail_closed=any(
                item.result.verdict == "error"
                and _binding_fails_closed(request, item.binding)
                for item in _terminal_runtime_results(runtime_results)
            ),
            active_concurrency=active_concurrency,
            provider_latency_ms=sum(
                item.provider_latency_ms for item in runtime_results
            ),
        ),
        mode=request.mode,
    )


def _trace(
    request,
    config,
    activated,
    results,
    content_block_id,
    *,
    queue_latency_ms=0,
    resolve_latency_ms=0,
):
    checksum = _config_checksum(config)
    root_id = f"nemo:config:{config.guardrail_id}:{config.guardrail_version}"

    def common(**values):
        return {
            "guardrail_id": config.guardrail_id,
            "guardrail_version": config.guardrail_version,
            "engine": config.runtime_engine,
            "config_checksum": checksum,
            "content_block_id": content_block_id,
            **values,
        }

    trace = [
        EvaluationTraceStep(
            id=root_id,
            kind="runtime",
            name="NeMo Guardrails",
            status="active",
            outcome="active",
            detail=f"Executed immutable {config.compiler_version} configuration.",
            **common(),
        ),
        EvaluationTraceStep(
            id=f"{root_id}:queue",
            kind="queue",
            name="Runtime admission",
            status="passed",
            outcome="admitted",
            detail="Waited for the version-isolated Guardrail admission slot.",
            duration_ms=max(0, queue_latency_ms),
            parent_id=root_id,
            rail_type=request.phase,
            **common(),
        ),
    ]
    for index, rail in enumerate(activated):
        rail_type = str(rail.type or request.phase)
        trace.append(
            EvaluationTraceStep(
                id=f"nemo:rail:native:{index}",
                kind="rail",
                name=rail.name,
                status="blocked" if rail.stop else "passed",
                outcome="blocked" if rail.stop else "passed",
                detail=f"NeMo {rail_type} Rail {'stopped' if rail.stop else 'continued'} processing.",
                duration_ms=max(0, round((rail.duration or 0) * 1_000)),
                parent_id=root_id,
                verdict="unsafe" if rail.stop else "safe",
                route="enforce" if rail.stop else "complete",
                risk=_native_risk(rail.name),
                rail_type=rail_type,
                **common(),
            )
        )
    rail_ids: dict[str, str] = {}
    control_ids: dict[str, str] = {}
    if _is_colang_v2(config):
        risks = tuple(dict.fromkeys(item.binding.risk for item in results))
        for risk in risks:
            selected = tuple(item for item in results if item.binding.risk == risk)
            terminal = selected[-1]
            binding = terminal.binding
            error = terminal.result.verdict == "error"
            unsafe = terminal.result.verdict == "unsafe"
            uncertain = terminal.result.verdict == "uncertain"
            status = (
                "error" if error else "blocked" if unsafe else
                "needs_context" if uncertain else "passed"
            )
            rail_id = f"nemo:rail:{request.phase}:{risk}"
            rail_ids[risk] = rail_id
            trace.append(
                EvaluationTraceStep(
                    id=rail_id,
                    kind="rail",
                    name=f"{request.phase.title()} Rail",
                    status=status,
                    outcome=status,
                    detail="NeMo Colang 2.x Rail Flow completed.",
                    duration_ms=sum(item.latency_ms for item in selected),
                    parent_id=root_id,
                    verdict=(
                        "error" if error else "unsafe" if unsafe else
                        "uncertain" if uncertain else "safe"
                    ),
                    route=(
                        "fail_closed" if error else "enforce" if unsafe else
                        "escalate" if uncertain else "complete"
                    ),
                    risk=risk,
                    rail_type=request.phase,
                    flow_name=binding.flow_name,
                    parallel_group=binding.parallel_group,
                    timeout_ms=binding.timeout_ms,
                    timed_out=error and "timeout" in (terminal.result.reason or "").casefold(),
                    **common(),
                )
            )
            if binding.control_id is not None:
                control_id = (
                    f"nemo:control:{binding.control_id}:"
                    f"{binding.control_version}:{binding.flow_name or risk}"
                )
                control_ids[risk] = control_id
                trace.append(
                    EvaluationTraceStep(
                        id=control_id,
                        kind="control",
                        name=f"{binding.control_id}@{binding.control_version}",
                        status=status,
                        outcome=status,
                        detail="Executed the immutable Control Flow binding.",
                        duration_ms=sum(item.latency_ms for item in selected),
                        parent_id=rail_id,
                        risk=risk,
                        control_id=binding.control_id,
                        control_version=binding.control_version,
                        rail_type=request.phase,
                        flow_name=binding.flow_name,
                        parallel_group=binding.parallel_group,
                        timeout_ms=binding.timeout_ms,
                        timed_out=error and "timeout" in (terminal.result.reason or "").casefold(),
                        **common(),
                    )
                )
    for item in results:
        trace.extend(item.result.trace)
        binding = item.binding
        timed_out = (
            item.result.verdict == "error"
            and "timeout" in (item.result.reason or "").casefold()
        )
        trace.append(
            EvaluationTraceStep(
                id=f"nemo:action:{binding.id}",
                kind="action",
                name=binding.action_name or binding.id,
                status=item.result.verdict,
                outcome=item.result.verdict,
                detail=item.result.reason or "NeMo Action completed.",
                duration_ms=item.latency_ms,
                parent_id=(
                    control_ids.get(binding.risk)
                    or rail_ids.get(binding.risk)
                    or root_id
                ),
                stage=binding.stage,
                verdict=item.result.verdict,
                route=(
                    "enforce" if item.result.verdict == "unsafe" else
                    "fail_closed" if item.result.verdict == "error" else
                    "escalate" if item.result.verdict == "uncertain" else
                    "complete"
                ),
                risk=binding.risk,
                control_id=binding.control_id,
                control_version=binding.control_version,
                rail_type=request.phase,
                flow_name=binding.flow_name,
                action_name=binding.action_name,
                action_version=binding.action_version,
                timeout_ms=binding.timeout_ms,
                timed_out=timed_out,
                parallel_group=binding.parallel_group,
                provider_latency_ms=item.provider_latency_ms,
                **common(),
            )
        )
    trace.append(
        EvaluationTraceStep(
            id=f"{root_id}:resolve",
            kind="action",
            name="TaskLatticeResolveAction",
            status="passed",
            outcome="resolved",
            detail="Resolved Action results into the final policy decision.",
            duration_ms=max(0, resolve_latency_ms),
            parent_id=root_id,
            rail_type=request.phase,
            action_name="TaskLatticeResolveAction",
            action_version="1.0.0",
            provider_latency_ms=max(0, resolve_latency_ms),
            **common(),
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
        terminal = _terminal_runtime_results(selected)
        native_unsafe = any(
            item.kind == "rail" and item.risk in risks and item.verdict == "unsafe"
            for item in trace
        )
        status = (
            "error"
            if force_error or any(item.result.verdict == "error" for item in terminal)
            else "intervene"
            if native_unsafe or any(item.result.verdict == "unsafe" for item in terminal)
            else "needs_context"
            if any(item.result.verdict == "uncertain" for item in terminal)
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
                latency_ms=max(
                    (
                        sum(
                            item.latency_ms
                            for item in selected
                            if item.binding.risk == risk
                        )
                        for risk in risks
                    ),
                    default=0,
                ),
                trace=module_trace,
                content_block_id=request.active_block_id,
            )
        )
    return tuple(assessments)


def _interventions(request, decision, action, reason, runtime_results):
    terminal = _terminal_runtime_results(runtime_results)
    interventions = []
    for item in terminal:
        if item.result.verdict not in {"unsafe", "uncertain"}:
            continue
        proposed = (
            "clarify"
            if item.result.verdict == "uncertain"
            else _runtime_action(item)
        )
        if proposed == "pass":
            continue
        module = next(
            (
                value
                for value in request.plan.modules_for(request.phase)
                if item.binding.id in value.step_ids
            ),
            None,
        )
        interventions.append(
            AppliedIntervention(
                kind=proposed,
                module_id=module.id if module is not None else "nemo-guardrails",
                fragment_id=f"nemo:{item.binding.id}:{proposed}",
                reason=item.result.reason,
                patches=(
                    _redaction_patches(request.text, (item,))
                    if proposed == "redact"
                    else ()
                ),
                replacement=next(
                    (
                        finding.replacement
                        for finding in item.result.findings
                        if finding.recommended_action == proposed
                        and finding.replacement is not None
                    ),
                    None,
                ),
                content_block_id=request.active_block_id,
            )
        )
    if decision == "block" and action == "reject" and not any(
        item.kind == "reject" for item in interventions
    ):
        interventions.append(
            AppliedIntervention(
                kind="reject",
                module_id="nemo-guardrails",
                fragment_id="nemo:reject",
                reason=reason,
                content_block_id=request.active_block_id,
            )
        )
    return tuple(interventions)


def _failed_decision(
    request,
    error,
    duration,
    config,
    *,
    cache_hit=False,
    queue_latency_ms=0,
    active_concurrency=0,
):
    reason = f"NeMo Guardrails failed closed with {type(error).__name__}."
    checksum = _config_checksum(config)
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
            guardrail_id=request.plan.guardrail_id,
            guardrail_version=request.plan.guardrail_version,
            rail_type=request.phase,
            outcome="error",
            timed_out=isinstance(error, TimeoutError),
            engine=config.runtime_engine,
            config_checksum=checksum,
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
            config_checksum=checksum,
            fail_closed=True,
            active_concurrency=active_concurrency,
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


def _native_reason(risk: str, details: Any) -> str:
    reason = f"NeMo native {risk.replace('_', ' ')} Action reported unsafe content."
    if isinstance(details, (list, tuple)):
        labels = tuple(str(item) for item in details if str(item).strip())
        if labels:
            return f"{reason} Policy categories: {', '.join(labels[:8])}."
    return reason


def _is_colang_v2(config: NeMoConfigSnapshot) -> bool:
    return any(
        line.strip().removeprefix("colang_version:").strip().strip("'\"")
        in {"2.x", "2.0"}
        for line in config.config_yaml.splitlines()
        if line.strip().startswith("colang_version:")
    )


def _stage_result(result: ActionResult) -> StageResult:
    return StageResult(
        verdict=result.verdict,
        content=result.content,
        findings=result.findings,
        reason=result.reason or result.evidence or None,
    )


def _compiled_control_flow_name(binding: NeMoActionBinding) -> str:
    if binding.control_id is None or binding.control_version is None or not binding.flow_name:
        return ""

    def clean(value: str) -> str:
        return "_".join(re.sub(r"[^a-zA-Z0-9]+", " ", value).split()).lower()

    return "_".join(
        ("tl", clean(binding.control_id), f"v{binding.control_version}", clean(binding.flow_name))
    )


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
        patches = _redaction_patches(text, unsafe)
        content = text
        previous_end = -1
        for patch in sorted(set(patches), key=lambda value: (value.start, value.end)):
            if patch.start < previous_end:
                raise _PatchConflict(
                    "The interaction was blocked because redaction patches conflicted."
                )
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


def _redaction_patches(text, results):
    patches = []
    for item in results:
        matcher = difflib.SequenceMatcher(
            a=text,
            b=item.result.content,
            autojunk=False,
        )
        patches.extend(
            ContentPatch(start, end, item.result.content[new_start:new_end])
            for operation, start, end, new_start, new_end in matcher.get_opcodes()
            if operation != "equal"
        )
    return tuple(patches)


def _terminal_runtime_results(results):
    terminal = {}
    for item in results:
        terminal[item.binding.risk] = item
    return tuple(terminal.values())


def _runtime_action(item):
    reasoning = tuple(
        evidence
        for finding in item.result.findings
        for evidence in finding.reasoning
    )
    if not reasoning:
        recommended = tuple(
            finding.recommended_action
            for finding in item.result.findings
            if finding.recommended_action != "pass"
        )
        return recommended[0] if recommended else item.binding.on_unsafe
    severity = {
        "too_complex": 0,
        "translation_ambiguous": 1,
        "impossible": 2,
        "invalid": 3,
        "satisfiable": 4,
        "no_translations": 5,
        "valid": 6,
    }
    result = min(
        reasoning,
        key=lambda value: (severity[value.result], value.id),
    ).result
    return {
        "valid": "pass",
        "invalid": item.binding.on_unsafe,
        "satisfiable": "clarify",
        "impossible": "reject",
        "translation_ambiguous": "clarify",
        "too_complex": "reject",
        "no_translations": "clarify",
    }[result]


def _binding_fails_closed(request, binding):
    if binding.control_id is not None:
        return binding.failure_mode == "fail_closed"
    module = next(
        (
            item
            for item in request.plan.modules_for(request.phase)
            if binding.id in item.step_ids
        ),
        None,
    )
    return (
        module is None
        or module.required_for_release and module.failure_mode == "fail_closed"
    )


def _config_checksum(config: NeMoConfigSnapshot) -> str:
    import hashlib
    import json
    from dataclasses import asdict

    return hashlib.sha256(
        json.dumps(asdict(config), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _request_timeout_ms(request: EngineRequest) -> int:
    modules = request.plan.modules_for(request.phase)
    by_id = {module.id: module for module in modules}
    totals: dict[str, int] = {}
    pending = list(modules)
    while pending:
        ready = tuple(
            module
            for module in pending
            if all(dependency in totals for dependency in module.depends_on)
        )
        if not ready:
            # Compiled plans are validated earlier; this remains fail-closed for
            # a corrupt persisted snapshot.
            return sum(module.timeout_ms for module in modules) + 500
        for module in ready:
            dependency_budget = max(
                (totals[item] for item in module.depends_on if item in by_id),
                default=0,
            )
            totals[module.id] = dependency_budget + module.timeout_ms
            pending.remove(module)
    # Independent modules share a Colang wave, so the critical dependency path
    # is the request deadline. The fixed allowance covers flow and resolution.
    return max(totals.values(), default=2_000) + 500
