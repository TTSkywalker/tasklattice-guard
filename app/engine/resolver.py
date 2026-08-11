from __future__ import annotations

from collections.abc import Iterable

from .automated_reasoning import aggregate_reasoning_result
from .contracts import (
    AppliedIntervention,
    ContentPatch,
    DecisionFragment,
    EnforcementAction,
    EngineRequest,
    EvaluationDecision,
    EvaluationUsage,
    ModuleAssessment,
    RuntimeCoverage,
)


_ACTION_PRIORITY: tuple[EnforcementAction, ...] = (
    "reject",
    "clarify",
    "fallback",
    "regenerate",
    "rewrite",
    "redirect",
    "redact",
    "pass",
)


class PatchConflict(ValueError):
    pass


class DeterministicResolver:
    """Combine unordered module assessments into one stable policy decision."""

    def resolve(
        self,
        request: EngineRequest,
        assessments: Iterable[ModuleAssessment],
    ) -> EvaluationDecision:
        ordered = self._ordered_assessments(request, tuple(assessments))
        fragments = tuple(
            sorted(
                (fragment for assessment in ordered for fragment in assessment.fragments),
                key=lambda item: (self._module_index(request, item.module_id), item.id),
            )
        )
        findings = tuple(finding for fragment in fragments for finding in fragment.findings)
        trace = tuple(step for assessment in ordered for step in assessment.trace)
        interventions = list(self._interventions(request, fragments))

        module_by_id = {module.id: module for module in request.plan.modules_for(request.phase)}
        for assessment in ordered:
            if assessment.status not in {"error", "uncovered"}:
                continue
            module = module_by_id.get(assessment.module_id)
            failure_mode = module.failure_mode if module is not None else "fail_closed"
            if failure_mode == "fail_closed" and (
                module is None or module.required_for_release
            ):
                interventions.append(
                    AppliedIntervention(
                        kind="reject",
                        module_id=assessment.module_id,
                        fragment_id=f"failure:{assessment.module_id}",
                        reason=next(
                            (
                                fragment.reason
                                for fragment in assessment.fragments
                                if fragment.reason
                            ),
                            (
                                "A required control module failed closed."
                                if assessment.status == "error"
                                else "A required control module did not fully cover the content."
                            ),
                        ),
                        content_block_id=assessment.content_block_id,
                    )
                )

        interventions_tuple = tuple(
            sorted(
                interventions,
                key=lambda item: (
                    self._module_index(request, item.module_id),
                    item.fragment_id,
                    item.kind,
                ),
            )
        )
        coverage = self._coverage(request, ordered)
        usage = self._usage(request, ordered)

        if request.mode == "detect":
            return EvaluationDecision(
                decision="allow",
                action="pass",
                reason=(
                    "Observe mode recorded proposed interventions without changing the content."
                    if interventions_tuple
                    else "All required control modules completed without an intervention."
                ),
                guardrail_id=request.plan.guardrail_id,
                guardrail_version=request.plan.guardrail_version,
                output_delivery=request.plan.output_delivery,
                findings=findings,
                trace=trace,
                assessments=ordered,
                interventions=interventions_tuple,
                coverage=coverage,
                usage=usage,
                mode=request.mode,
            )

        action = self._strongest_action(item.kind for item in interventions_tuple)
        reason = next(
            (item.reason for item in interventions_tuple if item.kind == action and item.reason),
            None,
        )
        if action == "reject":
            return EvaluationDecision(
                decision="block",
                action="reject",
                reason=reason or "A control module blocked the interaction.",
                guardrail_id=request.plan.guardrail_id,
                guardrail_version=request.plan.guardrail_version,
                output_delivery=request.plan.output_delivery,
                findings=findings,
                trace=trace,
                assessments=ordered,
                interventions=interventions_tuple,
                coverage=coverage,
                usage=usage,
                mode=request.mode,
            )

        if action == "pass":
            return EvaluationDecision(
                decision="allow",
                action="pass",
                reason="All required control modules completed without an intervention.",
                guardrail_id=request.plan.guardrail_id,
                guardrail_version=request.plan.guardrail_version,
                output_delivery=request.plan.output_delivery,
                findings=findings,
                trace=trace,
                assessments=ordered,
                interventions=interventions_tuple,
                coverage=coverage,
                usage=usage,
                mode=request.mode,
            )

        try:
            content = self._resolved_content(request.text, action, interventions_tuple)
        except PatchConflict as error:
            conflict = AppliedIntervention(
                kind="reject",
                module_id="resolver",
                fragment_id="resolver:patch-conflict",
                reason=str(error),
                content_block_id=request.active_block_id or (
                    request.content_view.active_block_id if request.content_view else None
                ),
            )
            return EvaluationDecision(
                decision="block",
                action="reject",
                reason=str(error),
                guardrail_id=request.plan.guardrail_id,
                guardrail_version=request.plan.guardrail_version,
                output_delivery=request.plan.output_delivery,
                findings=findings,
                trace=trace,
                assessments=ordered,
                interventions=(*interventions_tuple, conflict),
                coverage=coverage,
                usage=usage,
                mode=request.mode,
            )

        return EvaluationDecision(
            decision="transform",
            action=action,
            reason=reason or "Control modules proposed a deterministic intervention.",
            texts=(content,),
            guardrail_id=request.plan.guardrail_id,
            guardrail_version=request.plan.guardrail_version,
            output_delivery=request.plan.output_delivery,
            findings=findings,
            trace=trace,
            assessments=ordered,
            interventions=interventions_tuple,
            coverage=coverage,
            usage=usage,
            mode=request.mode,
        )

    def masked_view(
        self,
        original: str,
        assessments: Iterable[ModuleAssessment],
    ) -> str:
        patches = tuple(
            patch
            for assessment in assessments
            for fragment in assessment.fragments
            if fragment.action == "redact"
            for patch in fragment.patches
        )
        return self._apply_patches(original, patches)

    def _interventions(
        self,
        request: EngineRequest,
        fragments: tuple[DecisionFragment, ...],
    ) -> tuple[AppliedIntervention, ...]:
        interventions: list[AppliedIntervention] = []
        for fragment in fragments:
            if fragment.status not in {"intervene", "needs_context"}:
                continue
            action, reason = self._fragment_enforcement(request, fragment)
            if action == "pass":
                continue
            interventions.append(
                AppliedIntervention(
                    kind=action,
                    module_id=fragment.module_id,
                    fragment_id=fragment.id,
                    reason=reason or fragment.reason,
                    patches=fragment.patches,
                    replacement=fragment.replacement,
                    content_block_id=fragment.content_block_id,
                )
            )
        return tuple(interventions)

    @staticmethod
    def _fragment_enforcement(
        request: EngineRequest,
        fragment: DecisionFragment,
    ) -> tuple[EnforcementAction, str | None]:
        reasoning = tuple(
            item
            for finding in fragment.findings
            for item in finding.reasoning
        )
        if not reasoning:
            return fragment.action, fragment.reason

        result = aggregate_reasoning_result(reasoning)
        if result == "valid":
            return "pass", fragment.reason
        if result == "invalid":
            action = next(
                (
                    step.on_unsafe
                    for step in request.plan.steps_for(request.phase)
                    if step.risk == "automated_reasoning"
                ),
                "reject",
            )
        else:
            action = {
                "satisfiable": "clarify",
                "impossible": "reject",
                "translation_ambiguous": "clarify",
                "too_complex": "reject",
                "no_translations": "clarify",
            }[result]
        return action, (
            f"Automated Reasoning returned {result.upper()}; "
            f"the deterministic enforcement policy selected {action}."
        )

    def _ordered_assessments(
        self,
        request: EngineRequest,
        assessments: tuple[ModuleAssessment, ...],
    ) -> tuple[ModuleAssessment, ...]:
        return tuple(
            sorted(
                assessments,
                key=lambda item: (self._module_index(request, item.module_id), item.module_id),
            )
        )

    @staticmethod
    def _module_index(request: EngineRequest, module_id: str) -> int:
        return next(
            (
                index
                for index, module in enumerate(request.plan.modules_for(request.phase))
                if module.id == module_id
            ),
            10_000,
        )

    @staticmethod
    def _coverage(
        request: EngineRequest,
        assessments: tuple[ModuleAssessment, ...],
    ) -> RuntimeCoverage:
        configured = request.plan.modules_for(request.phase)
        required_ids = {
            module.id for module in configured if module.required_for_release
        } or {assessment.module_id for assessment in assessments}
        if not required_ids:
            return RuntimeCoverage(
                status="none",
                guarded_items=0,
                total_items=1,
                guarded_characters=0,
                total_characters=len(request.text),
            )
        completed_ids = {
            assessment.module_id
            for assessment in assessments
            if assessment.module_id in required_ids
            and assessment.status not in {"error", "uncovered"}
            and assessment.coverage.status == "complete"
        }
        complete = len(completed_ids) == len(required_ids)
        return RuntimeCoverage(
            status="complete" if complete else "partial",
            guarded_items=1 if complete else 0,
            total_items=1,
            guarded_characters=len(request.text) if complete else 0,
            total_characters=len(request.text),
            required_modules_completed=len(completed_ids),
            required_modules_total=len(required_ids),
        )

    @staticmethod
    def _usage(
        request: EngineRequest,
        assessments: tuple[ModuleAssessment, ...],
    ) -> EvaluationUsage:
        evaluator_invocations = 0
        for assessment in assessments:
            leaf_invocations = sum(
                1 for step in assessment.trace if step.kind == "evaluator"
            )
            evaluator_invocations += leaf_invocations or sum(
                1
                for step in assessment.trace
                if step.kind == "stage" and step.status != "skipped"
            )
        return EvaluationUsage(
            module_invocations=len(assessments),
            evaluator_invocations=evaluator_invocations,
            text_characters=len(request.text),
        )

    @staticmethod
    def _strongest_action(actions: Iterable[EnforcementAction]) -> EnforcementAction:
        values = set(actions)
        return next((item for item in _ACTION_PRIORITY if item in values), "pass")

    def _resolved_content(
        self,
        original: str,
        action: EnforcementAction,
        interventions: tuple[AppliedIntervention, ...],
    ) -> str:
        if action == "redact":
            return self._apply_patches(
                original,
                tuple(patch for item in interventions for patch in item.patches),
            )
        proposed = next(
            (
                item.replacement
                for item in interventions
                if item.kind == action and item.replacement is not None
            ),
            None,
        )
        if proposed is not None:
            return proposed
        return {
            "clarify": "More information is required before the request can be evaluated safely.",
            "redirect": "I can help with topics inside this assistant's approved purpose.",
            "regenerate": "The response was withheld and should be regenerated under the active Guardrail.",
            "rewrite": "The response was rewritten to comply with the active Guardrail.",
            "fallback": "A safe fallback response was selected by the active Guardrail.",
        }.get(action, original)

    @staticmethod
    def _apply_patches(original: str, patches: tuple[ContentPatch, ...]) -> str:
        unique = sorted(set(patches), key=lambda item: (item.start, item.end, item.replacement))
        previous: ContentPatch | None = None
        for patch in unique:
            if patch.start < 0 or patch.end < patch.start or patch.end > len(original):
                raise PatchConflict("A control module proposed an invalid content patch.")
            if previous is not None and patch.start < previous.end:
                raise PatchConflict("Control modules proposed conflicting content patches.")
            previous = patch
        content = original
        for patch in reversed(unique):
            content = content[: patch.start] + patch.replacement + content[patch.end :]
        return content
