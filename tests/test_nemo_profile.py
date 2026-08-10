from __future__ import annotations

import pytest

from app.engine.contracts import EngineRequest, GuardrailPlanSnapshot, GuardrailPlanStep
from app.engine.fast_pass import FastPassEngine


PLAN = GuardrailPlanSnapshot(
    profile_id="profile-test",
    profile_revision=1,
    compiler_version="test",
    safety_level="balanced",
    output_delivery="window_buffered",
    steps=(
        GuardrailPlanStep("secret", "secrets", "deterministic", ("input", "output"), "reject"),
        GuardrailPlanStep("pii", "pii", "deterministic", ("input", "output"), "redact"),
    ),
)


@pytest.mark.asyncio
async def test_deterministic_stage_detects_secret_and_pii():
    engine = FastPassEngine()
    steps = PLAN.steps_for("input", "deterministic")

    secret = await engine.evaluate(
        EngineRequest("input", "api_key=abcdefghijklmnop", PLAN), steps
    )
    pii = await engine.evaluate(
        EngineRequest("input", "Email alice@example.com", PLAN), steps
    )
    safe = await engine.evaluate(
        EngineRequest("input", "Summarize the approved guide.", PLAN), steps
    )

    assert secret.verdict == "unsafe"
    assert secret.findings[0].recommended_action == "reject"
    assert pii.verdict == "unsafe"
    assert "[PII_REDACTED]" in pii.content
    assert safe.verdict == "safe"
