from __future__ import annotations

import yaml
import pytest

from app.nemo.builtin_policies import prompt_catalog_yaml
from app.nemo.builtin_policies.content_safety import (
    CONTENT_SAFETY_POLICY_VERSION,
    prompts_yaml,
)
from app.nemo.builtin_policies.topic_safety import (
    TOPIC_SAFETY_POLICY_VERSION,
    prompts_yaml as topic_safety_prompts_yaml,
)


def test_content_safety_prompt_catalog_is_pinned_to_policy_version_one():
    payload = yaml.safe_load(prompts_yaml())
    tasks = {item["task"] for item in payload["prompts"]}

    assert CONTENT_SAFETY_POLICY_VERSION == 1
    assert tasks == {
        "content_safety_check_input $model=content_safety",
        "content_safety_check_output $model=content_safety",
    }


def test_content_safety_prompt_catalog_rejects_unknown_versions():
    with pytest.raises(ValueError, match="Unsupported Content Safety Policy version"):
        prompts_yaml(version=2)


def test_topic_safety_prompt_catalog_is_pinned_and_combined_for_compilation():
    topic_payload = yaml.safe_load(topic_safety_prompts_yaml())
    combined = yaml.safe_load(prompt_catalog_yaml())

    assert TOPIC_SAFETY_POLICY_VERSION == 1
    assert {item["task"] for item in topic_payload["prompts"]} == {
        "topic_safety_check_input $model=topic_control"
    }
    assert len(combined["prompts"]) == 3
