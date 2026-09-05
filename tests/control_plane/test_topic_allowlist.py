from __future__ import annotations

import asyncio
import time

from runner.toolkit.nemo.actions.contracts import ActionRequest
from runner.toolkit.nemo.actions.topic_rules import TopicRulesActionProvider
from runner.toolkit.runtime.contracts import (
    GuardrailPlanSnapshot,
    GuardrailPlanStep,
    NeMoActionBinding,
)


def _request(content: str) -> ActionRequest:
    step = GuardrailPlanStep(
        id="topic:rules",
        capability="topic_control",
        contract_ref="tali.guard.topic-control.rules.v1",
        phases=("input",),
        on_unsafe="redirect",
        parameters=(
            ("topic_mode", "allowlist"),
            ("allowed_topics", "Order status\nReturns"),
            # A legacy field must not restore deny-list behavior.
            ("restricted_topics", "Order status"),
        ),
    )
    plan = GuardrailPlanSnapshot(
        guardrail_id="topic-allowlist",
        guardrail_version="20260905-010000.001Z",
        compiler_version="test",
        safety_level="balanced",
        output_delivery="full_buffered",
        steps=(step,),
    )
    binding = NeMoActionBinding(
        id=step.id,
        capability=step.capability,
        contract_ref=step.contract_ref,
        phases=step.phases,
        on_unsafe=step.on_unsafe,
        parameters=step.parameters,
    )
    return ActionRequest(
        content=content,
        rail_type="input",
        guardrail_id=plan.guardrail_id,
        guardrail_version=plan.guardrail_version,
        policy_id="builtin-topic-safety",
        policy_version=1,
        trusted_context=(),
        content_blocks=(),
        deadline=time.monotonic() + 5,
        parameters=step.parameters,
        capability=step.capability,
        proposed_action="redirect",
        plan=plan,
        binding=binding,
    )


def test_explicit_allowlist_match_is_safe_even_when_legacy_restricted_value_matches() -> None:
    result = asyncio.run(TopicRulesActionProvider().execute(_request("Please check my order status")))
    assert result.verdict == "safe"
    assert "allowed" in result.reason


def test_unlisted_topic_escalates_to_semantic_allowlist_judgment() -> None:
    result = asyncio.run(TopicRulesActionProvider().execute(_request("Give me medical advice")))
    assert result.verdict == "uncertain"
    assert "allowlist" in result.reason
