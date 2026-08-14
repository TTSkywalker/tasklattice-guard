from __future__ import annotations

import re

from ...runtime.contracts import EngineRequest, GuardrailPlanStep, RiskFinding, StageResult


_OVERRIDE = re.compile(
    r"(?:ignore|disregard|forget|override)\s+(?:all\s+)?(?:previous|prior|above|system|developer)\s+(?:instructions?|rules?|messages?)",
    re.IGNORECASE,
)
_EXFILTRATE = re.compile(
    r"(?:reveal|show|print|repeat|quote|expose|leak)\b.{0,80}\b(?:system\s+prompt|developer\s+message|hidden\s+instructions?)",
    re.IGNORECASE | re.DOTALL,
)
_JAILBREAK = re.compile(
    r"(?:developer\s+mode|jailbreak|bypass|disable|evade)\b.{0,80}\b(?:safety|guardrails?|restrictions?|policy|policies?)",
    re.IGNORECASE | re.DOTALL,
)
_CHINESE_ATTACK = re.compile(
    r"(?:忽略|无视|覆盖|绕过).{0,30}(?:之前|系统|开发者|安全|限制|指令|规则)|(?:泄露|显示|输出).{0,30}(?:系统提示词|隐藏指令)",
)
_SECURITY_MENTION = re.compile(
    r"prompt\s+injection|system\s+prompt|developer\s+message|jailbreak|提示注入|系统提示词|越狱",
    re.IGNORECASE,
)


class PromptSecurityFastEngine:
    name = "Prompt Security Fast"
    stage = "fast_semantic"
    supported_phases = frozenset({"input"})
    supported_risks = frozenset({"prompt_injection", "jailbreak"})

    async def evaluate(
        self,
        request: EngineRequest,
        steps: tuple[GuardrailPlanStep, ...],
    ) -> StageResult:
        text = request.text.strip()
        prompt_attack = bool(_OVERRIDE.search(text) or _EXFILTRATE.search(text) or _CHINESE_ATTACK.search(text))
        jailbreak = bool(_JAILBREAK.search(text))
        if prompt_attack or jailbreak:
            risk = "jailbreak" if jailbreak and not prompt_attack else "prompt_injection"
            step = next((item for item in steps if item.risk == risk), steps[0])
            reason = (
                f"The untrusted {request.target_source.replace('_', ' ')} attempts to "
                + (
                    "bypass trusted safety policies."
                    if risk == "jailbreak"
                    else "override or extract trusted instructions."
                )
            )
            return StageResult(
                verdict="unsafe",
                content=request.text,
                findings=(
                    RiskFinding(
                        risk=step.risk,
                        verdict="unsafe",
                        confidence=0.99,
                        evidence=reason,
                        recommended_action=step.on_unsafe,
                    ),
                ),
                reason=reason,
            )
        if _SECURITY_MENTION.search(text):
            step = steps[0]
            reason = "The target discusses protected instructions or prompt security; intent requires contextual review."
            return StageResult(
                verdict="uncertain",
                content=request.text,
                findings=(
                    RiskFinding(
                        risk=step.risk,
                        verdict="uncertain",
                        confidence=0.5,
                        evidence=reason,
                        recommended_action=step.on_unsafe,
                    ),
                ),
                reason=reason,
            )
        return StageResult(
            verdict="safe",
            content=request.text,
            reason="No instruction override, prompt extraction, or safety-bypass intent was detected.",
        )
