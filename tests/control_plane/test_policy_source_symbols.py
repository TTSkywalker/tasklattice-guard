from copy import deepcopy

import pytest

from runner.compiler import DefaultRunnerCompiler
from runner.draft_preview import DraftPreviewRuntime
from runner.toolkit.nemo.action_registry import action_providers
from runner.toolkit.runtime.contracts import ProtectionRequest, RequestContext
from tests.control_plane.test_custom_policy_dependencies import custom_plan, compile_plan


SOURCE = '''import core
flow check $text
  # check is a business value, not a Flow reference here.
  $check = $text
  $target = "check"
  if $check == "check"
    $r = await GuardRecordPolicyAction(flow_name=$target, safe=False, text=$check, replacement="check reviewed")
  else
    $r = await GuardRecordPolicyAction(flow_name=$target, safe=True, text=$check)
'''


@pytest.mark.parametrize("phase", ["input", "output"])
@pytest.mark.parametrize("quote", ['"', "'", '"""'])
@pytest.mark.parametrize("value", [
    'ordinary"\n  $text = "safe"\n  $other = "ordinary',
    '{$text}',
    "passport $text \\path 'quoted' \"quoted\" 银行\nnext line",
    "${other}",
])
async def test_policy_parameters_remain_literal_data_in_real_nemo(phase, quote, value):
    source = (f'flow check $text\n  $label = {quote}${{label}}{quote}\n'
        '  $safe = $label != $text\n'
        '  $r = await GuardRecordPolicyAction(flow_name="check", safe=$safe, text=$text)\n')
    plan = custom_plan(source, ["GuardRecordPolicyAction"])
    plan["policy_versions"][0]["rail_bindings"][0]["rail_type"] = phase
    plan["policy_bindings"][0].update(enabled_rails=[phase], parameter_values=[
        ["label", value], ["other", "must not recursively substitute"]])
    runtime = DraftPreviewRuntime(DefaultRunnerCompiler(), action_providers())
    try:
        result = await runtime.evaluate(
            ProtectionRequest(phase=phase, texts=(value,), context=RequestContext(protocol="test")),
            preview_id="parameter-data", guardrail_id=plan["guardrail_id"], draft_revision=1,
            candidate_version=plan["guardrail_version"], plan=plan, runtime_profile="auto")
        assert not result.usage.fail_closed, result.reason
        assert result.decision == "block"
    finally:
        await runtime.shutdown()


def test_namespace_changes_only_symbols_not_business_literals_variables_or_comments():
    artifact = compile_plan(custom_plan(SOURCE, ["GuardRecordPolicyAction"]))
    assert '$check = $text' in artifact.colang_content
    assert '$target = "check"' in artifact.colang_content
    assert '$check == "check"' in artifact.colang_content
    assert 'replacement="check reviewed"' in artifact.colang_content
    assert '# check is a business value' in artifact.colang_content


@pytest.mark.parametrize("phase", ["input", "output"])
@pytest.mark.parametrize("text,expected", [("check", "block"), ("ordinary", "allow")])
async def test_real_nemo_keeps_the_authored_literal_match(phase, text, expected):
    plan = custom_plan(SOURCE, ["GuardRecordPolicyAction"])
    plan["policy_versions"][0]["rail_bindings"][0]["rail_type"] = phase
    plan["policy_bindings"][0]["enabled_rails"] = [phase]
    runtime = DraftPreviewRuntime(DefaultRunnerCompiler(), action_providers())
    try:
        result = await runtime.evaluate(
            ProtectionRequest(phase=phase, texts=(text,), context=RequestContext(protocol="test")),
            preview_id="symbols", guardrail_id=plan["guardrail_id"], draft_revision=1,
            candidate_version=plan["guardrail_version"], plan=plan, runtime_profile="auto")
        assert not result.usage.fail_closed, result.reason
        assert result.decision == expected
        if expected == "block":
            assert any(item.policy_id == "custom" for item in result.findings)
    finally:
        await runtime.shutdown()


def test_multiword_helpers_are_namespaced_without_changing_data():
    source = 'flow check $text\n  await inspect text $text\n\nflow inspect text $text\n  $s = "inspect text"\n  pass\n'
    artifact = compile_plan(custom_plan(source))
    assert '$s = "inspect text"' in artifact.colang_content


def test_normalized_policy_names_cannot_collide():
    plan = custom_plan('flow check $text\n  pass\n')
    plan["policy_versions"][0]["policy_id"] = "policy-a"
    plan["policy_bindings"][0]["policy_id"] = "policy-a"
    other = deepcopy(plan["policy_versions"][0])
    other["policy_id"] = "policy_a"
    plan["policy_versions"].append(other)
    plan["policy_bindings"].append({"policy_id": "policy_a", "policy_version": "1", "enabled_rails": ["input"]})
    from nemoguardrails.colang.v2_x.lang.parser import parse_colang_file
    names = [flow.name for flow in parse_colang_file("compiled.co", compile_plan(plan).colang_content)["flows"]]
    assert len(names) == len(set(names))


@pytest.mark.parametrize("call", [
    'GuardRecordPolicyAction(flow_name="check", safe=True, text=$text)',
    'GuardRecordPolicyAction $flow_name="check" $safe=True $text=$text',
])
async def test_recording_call_styles_preserve_data_and_scope(call):
    plan = custom_plan(f"flow check $text\n  $r = await {call}\n", ["GuardRecordPolicyAction"])
    runtime = DraftPreviewRuntime(DefaultRunnerCompiler(), action_providers())
    try:
        result = await runtime.evaluate(
            ProtectionRequest(phase="input", texts=("check",), context=RequestContext(protocol="test")),
            preview_id="styles", guardrail_id=plan["guardrail_id"], draft_revision=1,
            candidate_version=plan["guardrail_version"], plan=plan, runtime_profile="auto")
        assert not result.usage.fail_closed, result.reason
        assert result.decision == "allow"
        assert any(item.kind == "action" and item.policy_id == "custom" and item.status != "error" for item in result.trace)
    finally:
        await runtime.shutdown()


@pytest.mark.parametrize("argument", ['policy_id="other"', 'policy_version="2"'])
def test_author_cannot_override_compiler_owned_recording_scope(argument):
    from runner.toolkit.compiler.domain import PlanCompilationError
    with pytest.raises(PlanCompilationError, match="compiler-owned RecordPolicy argument"):
        compile_plan(custom_plan(f'flow check $text\n  await GuardRecordPolicyAction(flow_name="check", safe=True, text=$text, {argument})\n', ["GuardRecordPolicyAction"]))


def test_nested_import_is_not_silently_dropped_by_source_linking():
    from runner.toolkit.compiler.domain import PlanCompilationError
    with pytest.raises(PlanCompilationError, match="forbidden import"):
        compile_plan(custom_plan("flow check $text\n  import llm\n  pass\n"))


def test_recording_action_requires_named_arguments_before_runtime_dispatch():
    from runner.toolkit.compiler.domain import PlanCompilationError
    with pytest.raises(PlanCompilationError, match="RecordPolicy requires named arguments"):
        compile_plan(custom_plan('flow check $text\n  await GuardRecordPolicyAction("check", True, $text)\n', ["GuardRecordPolicyAction"]))


@pytest.mark.parametrize("phase", ["input", "output"])
async def test_same_named_flows_keep_their_own_policy_result_and_order(phase):
    plan = custom_plan(SOURCE, ["GuardRecordPolicyAction"])
    first = plan["policy_versions"][0]
    first["rail_bindings"][0].update(rail_type=phase, on_unsafe="redact", execution_mode="mutate")
    plan["policy_bindings"][0]["enabled_rails"] = [phase]
    second = deepcopy(first)
    second["policy_id"] = "other"
    second["rail_bindings"][0].update(on_unsafe="reject", execution_mode="detect")
    second["sources"][0]["content"] = SOURCE.replace('$check == "check"', '$check == "check reviewed"')
    plan["policy_versions"].append(second)
    plan["policy_bindings"].append({"policy_id": "other", "policy_version": "1", "enabled_rails": [phase]})
    runtime = DraftPreviewRuntime(DefaultRunnerCompiler(), action_providers())
    try:
        result = await runtime.evaluate(
            ProtectionRequest(phase=phase, texts=("check",), context=RequestContext(protocol="test")),
            preview_id="ownership", guardrail_id=plan["guardrail_id"], draft_revision=1,
            candidate_version=plan["guardrail_version"], plan=plan, runtime_profile="auto")
        assert not result.usage.fail_closed, result.reason
        assert result.decision == "block"
        assert [finding.policy_id for finding in result.findings if finding.verdict == "unsafe"] == ["custom", "other"]
    finally:
        await runtime.shutdown()
