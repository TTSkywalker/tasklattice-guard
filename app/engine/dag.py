from __future__ import annotations

import asyncio
import difflib
import time
from collections.abc import Iterable
from dataclasses import replace

from .contracts import (
    ContentPatch,
    ContentViewSnapshot,
    DecisionFragment,
    EnforcementAction,
    EngineRequest,
    EvaluationDecision,
    EvaluationStage,
    EvaluationTraceStep,
    GuardrailPlanModule,
    GuardrailPlanStep,
    GuardrailStage,
    ModuleAssessment,
    RiskFinding,
    RuntimeCoverage,
    StageResult,
)
from .content_views import request_view, with_active_text
from .resolver import DeterministicResolver, PatchConflict


STAGE_ORDER: tuple[EvaluationStage, ...] = (
    "deterministic",
    "fast_semantic",
    "deep_judge",
)


class ProgressiveModuleRunner:
    """Run escalation inside one module and emit an immutable assessment."""

    def __init__(self, stages: tuple[GuardrailStage, ...]) -> None:
        self._stages = {stage.stage: stage for stage in stages}

    async def evaluate(
        self,
        request: EngineRequest,
        module: GuardrailPlanModule,
    ) -> ModuleAssessment:
        started = time.perf_counter()
        content = request.text
        view = request_view(request)
        content_block_id = view.active_block_id
        trace: list[EvaluationTraceStep] = []
        findings: list[RiskFinding] = []
        uncertain_risks: set[str] = set()
        step_by_id = {step.id: step for step in request.plan.steps}
        module_steps = tuple(
            step_by_id[step_id]
            for step_id in module.step_ids
            if step_id in step_by_id and module.phase in step_by_id[step_id].phases
        )
        missing = tuple(step_id for step_id in module.step_ids if step_id not in step_by_id)
        if missing:
            return self._error(
                module,
                f"Module references unavailable plan steps: {', '.join(missing)}.",
                started,
                content_block_id=content_block_id,
            )

        for stage_name in STAGE_ORDER:
            planned = tuple(step for step in module_steps if step.stage == stage_name)
            if not planned:
                continue
            if stage_name == "deep_judge":
                planned = self._required_deep_steps(planned, uncertain_risks)
                if not planned:
                    trace.append(self._skip(module, stage_name, content_block_id))
                    continue

            stage = self._stages.get(stage_name)
            if stage is None or request.phase not in stage.supported_phases:
                return self._error(
                    module,
                    f"Configured {stage_name.replace('_', ' ')} evaluator is unavailable.",
                    started,
                    tuple(trace),
                    content_block_id=content_block_id,
                )

            stage_started = time.perf_counter()
            result = await stage.evaluate(
                EngineRequest(
                    phase=request.phase,
                    text=content,
                    plan=request.plan,
                    context_messages=request.context_messages,
                    trusted_instruction=request.trusted_instruction,
                    target_source=request.target_source,
                    mode=request.mode,
                    evidence_scope=request.evidence_scope,
                    content_view=with_active_text(view, content),
                    active_block_id=content_block_id,
                ),
                planned,
            )
            findings.extend(result.findings)
            route = self._route(stage_name, result, planned)
            trace.append(
                EvaluationTraceStep(
                    id=f"module:{module.id}:stage:{stage_name}",
                    kind="stage",
                    name=self._label(stage_name),
                    status=result.verdict,
                    detail=result.reason or f"Module stage returned {result.verdict}.",
                    duration_ms=max(0, round((time.perf_counter() - stage_started) * 1000)),
                    parent_id=f"module:{module.id}",
                    evidence="; ".join(item.evidence for item in result.findings) or None,
                    stage=stage_name,
                    verdict=result.verdict,
                    route=route,
                    risk=result.findings[0].risk if result.findings else None,
                    confidence=(
                        min(item.confidence for item in result.findings)
                        if result.findings
                        else None
                    ),
                    content_block_id=content_block_id,
                )
            )
            trace.extend(
                replace(step, content_block_id=content_block_id)
                if step.content_block_id is None
                else step
                for step in result.trace
            )

            if result.verdict == "error":
                return self._error(
                    module,
                    result.reason or "Control evaluation failed.",
                    started,
                    tuple(trace),
                    tuple(findings),
                    content_block_id,
                )
            if result.verdict == "uncertain":
                uncertain_risks.update(item.risk for item in result.findings)
                if stage_name == "deep_judge":
                    fragment = DecisionFragment(
                        id=f"{module.id}:needs-context",
                        module_id=module.id,
                        module=module.module,
                        status="needs_context",
                        action="clarify",
                        findings=tuple(findings),
                        reason=result.reason or "The control module needs more context.",
                        content_block_id=content_block_id,
                    )
                    return self._assessment(
                        module,
                        "needs_context",
                        (fragment,),
                        started,
                        tuple(trace),
                        content_block_id,
                    )
                continue
            if result.verdict == "unsafe":
                if not result.findings:
                    return self._error(
                        module,
                        "An evaluator returned unsafe without a finding.",
                        started,
                        tuple(trace),
                        content_block_id=content_block_id,
                    )
                detection_only = all(
                    item.risk == "automated_reasoning" for item in result.findings
                )
                action = (
                    "pass"
                    if detection_only
                    else self._strongest_action(
                        item.recommended_action for item in result.findings
                    )
                )
                if action == "redact" and module.input_view != "original":
                    return self._error(
                        module,
                        "A module using a derived content view cannot emit source-coordinate redactions.",
                        started,
                        tuple(trace),
                        tuple(findings),
                        content_block_id,
                    )
                fragment = DecisionFragment(
                    id=f"{module.id}:{stage_name}:intervention",
                    module_id=module.id,
                    module=module.module,
                    status="intervene",
                    action=action,
                    findings=tuple(findings),
                    patches=(
                        self._diff_patches(request.text, result.content)
                        if action == "redact"
                        else ()
                    ),
                    reason=result.reason or next(
                        (item.evidence for item in result.findings),
                        "A configured Control was triggered.",
                    ),
                    content_block_id=content_block_id,
                )
                return self._assessment(
                    module,
                    "intervene",
                    (fragment,),
                    started,
                    tuple(trace),
                    content_block_id,
                )
            content = result.content

        fragment = DecisionFragment(
            id=f"{module.id}:pass",
            module_id=module.id,
            module=module.module,
            status="pass",
            findings=tuple(findings),
            reason="All planned checks in the module completed without an intervention.",
            content_block_id=content_block_id,
        )
        return self._assessment(
            module,
            "pass",
            (fragment,),
            started,
            tuple(trace),
            content_block_id,
        )

    @staticmethod
    def _required_deep_steps(
        planned: tuple[GuardrailPlanStep, ...],
        uncertain_risks: set[str],
    ) -> tuple[GuardrailPlanStep, ...]:
        return tuple(
            step
            for step in planned
            if step.escalation == "always"
            or (step.escalation == "on_uncertain" and step.risk in uncertain_risks)
        )

    @staticmethod
    def _route(
        stage: EvaluationStage,
        result: StageResult,
        steps: tuple[GuardrailPlanStep, ...],
    ) -> str:
        if result.verdict == "unsafe":
            return "enforce"
        if result.verdict == "error":
            return "fail_closed"
        if result.verdict == "uncertain":
            return "escalate"
        if stage != "deep_judge" and any(step.escalation == "always" for step in steps):
            return "escalate"
        return "complete"

    @staticmethod
    def _strongest_action(actions: Iterable[EnforcementAction]) -> EnforcementAction:
        priority: tuple[EnforcementAction, ...] = (
            "reject",
            "clarify",
            "fallback",
            "regenerate",
            "rewrite",
            "redirect",
            "redact",
            "pass",
        )
        values = set(actions)
        return next((item for item in priority if item in values), "pass")

    @staticmethod
    def _diff_patches(original: str, transformed: str) -> tuple[ContentPatch, ...]:
        if original == transformed:
            return ()
        matcher = difflib.SequenceMatcher(a=original, b=transformed, autojunk=False)
        return tuple(
            ContentPatch(start, end, transformed[replacement_start:replacement_end])
            for operation, start, end, replacement_start, replacement_end in matcher.get_opcodes()
            if operation != "equal"
        )

    @staticmethod
    def _label(stage: EvaluationStage) -> str:
        return {
            "deterministic": "Deterministic",
            "fast_semantic": "Fast Semantic",
            "deep_judge": "Deep Judge",
        }[stage]

    def _skip(
        self,
        module: GuardrailPlanModule,
        stage: EvaluationStage,
        content_block_id: str | None,
    ) -> EvaluationTraceStep:
        return EvaluationTraceStep(
            id=f"module:{module.id}:stage:{stage}",
            kind="stage",
            name=self._label(stage),
            status="skipped",
            detail="Deeper judgment was not required because earlier evaluation was decisive.",
            parent_id=f"module:{module.id}",
            stage=stage,
            route="complete",
            content_block_id=content_block_id,
        )

    def _error(
        self,
        module: GuardrailPlanModule,
        reason: str,
        started: float,
        trace: tuple[EvaluationTraceStep, ...] = (),
        findings: tuple[RiskFinding, ...] = (),
        content_block_id: str | None = None,
    ) -> ModuleAssessment:
        error_trace = EvaluationTraceStep(
            id=f"module:{module.id}:error",
            kind="module",
            name=module.module.replace("_", " ").title(),
            status="error",
            detail=reason,
            duration_ms=max(0, round((time.perf_counter() - started) * 1000)),
            parent_id=f"module:{module.id}",
            verdict="error",
            route=module.failure_mode,
            content_block_id=content_block_id,
        )
        fragment = DecisionFragment(
            id=f"{module.id}:error",
            module_id=module.id,
            module=module.module,
            status="error",
            findings=findings,
            coverage="none",
            reason=reason,
            content_block_id=content_block_id,
        )
        return ModuleAssessment(
            module_id=module.id,
            module=module.module,
            status="error",
            fragments=(fragment,),
            coverage=RuntimeCoverage(status="none"),
            latency_ms=max(0, round((time.perf_counter() - started) * 1000)),
            trace=(*trace, error_trace),
            content_block_id=content_block_id,
        )

    @staticmethod
    def _assessment(
        module: GuardrailPlanModule,
        status: str,
        fragments: tuple[DecisionFragment, ...],
        started: float,
        trace: tuple[EvaluationTraceStep, ...],
        content_block_id: str | None,
    ) -> ModuleAssessment:
        duration = max(0, round((time.perf_counter() - started) * 1000))
        module_trace = EvaluationTraceStep(
            id=f"module:{module.id}",
            kind="module",
            name=module.module.replace("_", " ").title(),
            status=status,
            detail=f"Control module completed with status {status}.",
            duration_ms=duration,
            content_block_id=content_block_id,
        )
        return ModuleAssessment(
            module_id=module.id,
            module=module.module,
            status=status,
            fragments=fragments,
            coverage=RuntimeCoverage(status="complete"),
            latency_ms=duration,
            trace=(module_trace, *trace),
            content_block_id=content_block_id,
        )


class ModularGuardrailsEngine:
    """Execute module DAG layers concurrently and resolve their fragments once."""

    name = "modular-dag"
    supported_phases = frozenset({"input", "output"})

    def __init__(
        self,
        stages: tuple[GuardrailStage, ...],
        resolver: DeterministicResolver | None = None,
    ) -> None:
        self._runner = ProgressiveModuleRunner(stages)
        self._resolver = resolver or DeterministicResolver()

    async def evaluate(self, request: EngineRequest) -> EvaluationDecision:
        active_block_id = request_view(request).active_block_id
        modules = request.plan.modules_for(request.phase)
        if not modules:
            if request.plan.steps_for(request.phase):
                invalid = GuardrailPlanModule(
                    id=f"plan-validation:{request.phase}",
                    module="interaction_safety",
                    phase=request.phase,
                    step_ids=(),
                )
                return self._resolver.resolve(
                    request,
                    (
                        self._invalid_module(
                            invalid,
                            "Compiled plan has evaluation steps but no control modules.",
                            active_block_id,
                        ),
                    ),
                )
            return self._resolver.resolve(request, ())
        module_by_id = {module.id: module for module in modules}
        if len(module_by_id) != len(modules):
            return self._resolver.resolve(
                request,
                tuple(
                    self._invalid_module(
                        module,
                        "Module identifiers must be unique.",
                        active_block_id,
                    )
                    for module in modules
                ),
            )

        completed: dict[str, ModuleAssessment] = {}
        pending = dict(module_by_id)
        while pending:
            ready = tuple(
                module
                for module in modules
                if module.id in pending
                and all(dependency in completed for dependency in module.depends_on)
            )
            if not ready:
                completed.update(
                    {
                        module.id: self._invalid_module(
                            module,
                            "Control module dependencies contain a cycle or unknown node.",
                            active_block_id,
                        )
                        for module in pending.values()
                    }
                )
                break

            tasks: dict[str, asyncio.Task[ModuleAssessment]] = {}
            async with asyncio.TaskGroup() as group:
                for module in ready:
                    tasks[module.id] = group.create_task(
                        self._execute_module(request, module, completed)
                    )
            for module in ready:
                completed[module.id] = tasks[module.id].result()
                pending.pop(module.id)

        return self._resolver.resolve(request, completed.values())

    async def _execute_module(
        self,
        request: EngineRequest,
        module: GuardrailPlanModule,
        completed: dict[str, ModuleAssessment],
    ) -> ModuleAssessment:
        active_block_id = request_view(request).active_block_id
        try:
            view = self._input_view(request, module, completed)
            async with asyncio.timeout(module.timeout_ms / 1_000):
                return await self._runner.evaluate(
                    EngineRequest(
                        phase=request.phase,
                        text=view.active_block.text,
                        plan=request.plan,
                        context_messages=request.context_messages,
                        trusted_instruction=request.trusted_instruction,
                        target_source=view.active_block.source,
                        mode=request.mode,
                        evidence_scope=request.evidence_scope,
                        content_view=view,
                        active_block_id=view.active_block_id,
                    ),
                    module,
                )
        except TimeoutError:
            return self._invalid_module(
                module,
                f"Control module exceeded its {module.timeout_ms} ms timeout.",
                active_block_id,
            )
        except PatchConflict as error:
            return self._invalid_module(module, str(error), active_block_id)
        except Exception as error:  # evaluators are an isolation boundary
            return self._invalid_module(
                module,
                f"Control module failed with {type(error).__name__}.",
                active_block_id,
            )

    def _input_view(
        self,
        request: EngineRequest,
        module: GuardrailPlanModule,
        completed: dict[str, ModuleAssessment],
    ) -> ContentViewSnapshot:
        original = request_view(request)
        if module.input_view in {"original", "complete_output"}:
            return with_active_text(original, request.text, kind=module.input_view)
        dependencies = tuple(
            completed[dependency]
            for dependency in module.depends_on
            if dependency in completed
        )
        masked = self._resolver.masked_view(original.active_block.text, dependencies)
        return with_active_text(original, masked, kind=module.input_view)

    @staticmethod
    def _invalid_module(
        module: GuardrailPlanModule,
        reason: str,
        content_block_id: str | None = None,
    ) -> ModuleAssessment:
        trace = EvaluationTraceStep(
            id=f"module:{module.id}:error",
            kind="module",
            name=module.module.replace("_", " ").title(),
            status="error",
            detail=reason,
            verdict="error",
            route=module.failure_mode,
            content_block_id=content_block_id,
        )
        fragment = DecisionFragment(
            id=f"{module.id}:error",
            module_id=module.id,
            module=module.module,
            status="error",
            coverage="none",
            reason=reason,
            content_block_id=content_block_id,
        )
        return ModuleAssessment(
            module_id=module.id,
            module=module.module,
            status="error",
            fragments=(fragment,),
            coverage=RuntimeCoverage(status="none"),
            trace=(trace,),
            content_block_id=content_block_id,
        )
