from __future__ import annotations

import pytest

from app.runtime.contracts import (
    EngineRequest,
    GuardrailPlanModule,
    GuardrailPlanSnapshot,
    GuardrailPlanStep,
)
from app.nemo.actions import local_action_providers
from tests.nemo_helpers import nemo_engine


PLAN = GuardrailPlanSnapshot(
    guardrail_id="guardrail-test",
    guardrail_version=1,
    compiler_version="test",
    safety_level="balanced",
    output_delivery="window_buffered",
    steps=(
        GuardrailPlanStep("secret", "secrets", "deterministic", ("input", "output"), "reject"),
        GuardrailPlanStep("pii", "pii", "deterministic", ("input", "output"), "redact"),
    ),
    modules=tuple(
        GuardrailPlanModule(
            f"data-protection-{phase}",
            "data_protection",
            phase,
            ("secret", "pii"),
        )
        for phase in ("input", "output")
    ),
)


@pytest.mark.asyncio
async def test_deterministic_stage_detects_secret_and_pii():
    engine = nemo_engine(PLAN, *local_action_providers())

    secret = await engine.evaluate(
        EngineRequest("input", "api_key=abcdefghijklmnop", PLAN)
    )
    pii = await engine.evaluate(
        EngineRequest("input", "Email alice@example.com", PLAN)
    )
    safe = await engine.evaluate(
        EngineRequest("input", "Summarize the approved guide.", PLAN)
    )

    assert secret.decision == "block"
    assert secret.findings[0].recommended_action == "reject"
    assert pii.decision == "transform"
    assert "[PII_REDACTED]" in pii.texts[0]
    assert safe.decision == "allow"
    await engine.shutdown()
