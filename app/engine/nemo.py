from __future__ import annotations

from pathlib import Path
from typing import Any

from .contracts import EngineRequest, GuardrailPlanStep, RiskFinding, StageResult


class _NemoStage:
    def __init__(self, rails: Any) -> None:
        self._rails = rails

    async def evaluate(
        self,
        request: EngineRequest,
        steps: tuple[GuardrailPlanStep, ...],
    ) -> StageResult:
        from nemoguardrails.rails.llm.options import RailStatus, RailType

        if request.phase == "input":
            messages = [{"role": "user", "content": request.text}]
            rail_types = [RailType.INPUT]
        else:
            messages = [
                message
                for message in request.context_messages
                if message.get("role") in {"system", "user", "assistant"}
                and isinstance(message.get("content"), str)
            ]
            messages.append({"role": "assistant", "content": request.text})
            rail_types = [RailType.OUTPUT]
        try:
            result = await self._rails.check_async(messages, rail_types=rail_types)
        except Exception as error:
            return StageResult(
                verdict="error",
                content=request.text,
                reason=f"{self.name} evaluator failed: {type(error).__name__}.",
            )

        if result.status == RailStatus.BLOCKED:
            step = self._matching_step(result.rail, steps)
            return StageResult(
                verdict="unsafe",
                content=result.content or request.text,
                findings=(
                    RiskFinding(
                        risk=step.risk,
                        verdict="unsafe",
                        confidence=0.9,
                        evidence=result.rail or f"{self.name} classified the interaction as unsafe.",
                        recommended_action=step.on_unsafe,
                    ),
                ),
                reason=f"{self.name} found a configured safety risk.",
            )
        if result.status == RailStatus.MODIFIED:
            step = steps[0]
            return StageResult(
                verdict="unsafe",
                content=result.content,
                findings=(
                    RiskFinding(
                        risk=step.risk,
                        verdict="unsafe",
                        confidence=0.9,
                        evidence=result.rail or f"{self.name} modified unsafe content.",
                        recommended_action=step.on_unsafe,
                    ),
                ),
            )
        return StageResult(
            verdict="safe",
            content=request.text,
            reason=f"{self.name} returned a decisive safe classification.",
        )

    @staticmethod
    def _matching_step(
        rail: str | None,
        steps: tuple[GuardrailPlanStep, ...],
    ) -> GuardrailPlanStep:
        if rail:
            normalized = rail.replace("-", "_").lower()
            match = next((step for step in steps if step.risk in normalized), None)
            if match:
                return match
        return steps[0]


class NemoFastSemanticEngine(_NemoStage):
    name = "Fast Semantic"
    stage = "fast_semantic"
    supported_phases = frozenset({"input", "output"})
    supported_risks = frozenset({"pii", "content_safety"})

    def __init__(
        self,
        nemo_config_path: Path,
        *,
        base_url: str,
        model: str,
        api_key_env_var: str,
    ) -> None:
        from nemoguardrails import LLMRails, RailsConfig
        from nemoguardrails.rails.llm.config import Model

        config = RailsConfig.from_path(str(nemo_config_path))
        config.models = [
            Model(
                type="content_safety",
                engine="nim",
                model=model,
                api_key_env_var=api_key_env_var,
                parameters={"base_url": base_url},
            )
        ]
        config.rails.input.flows = ["content safety check input $model=content_safety"]
        config.rails.output.flows = ["content safety check output $model=content_safety"]
        super().__init__(LLMRails(config))
