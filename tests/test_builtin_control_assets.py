from __future__ import annotations

import yaml
import pytest

from app.nemo.builtin_controls import prompt_catalog_yaml
from app.nemo.builtin_controls.content_safety import (
    CONTENT_SAFETY_CONTROL_VERSION,
    prompts_yaml,
)
from app.nemo.builtin_controls.topic_control import (
    TOPIC_CONTROL_VERSION,
    prompts_yaml as topic_control_prompts_yaml,
)


def test_content_safety_prompt_catalog_is_pinned_to_control_version_one():
    payload = yaml.safe_load(prompts_yaml())
    tasks = {item["task"] for item in payload["prompts"]}

    assert CONTENT_SAFETY_CONTROL_VERSION == 1
    assert tasks == {
        "content_safety_check_input $model=content_safety",
        "content_safety_check_output $model=content_safety",
    }


def test_content_safety_prompt_catalog_rejects_unknown_versions():
    with pytest.raises(ValueError, match="Unsupported Content Safety Control version"):
        prompts_yaml(version=2)


def test_topic_control_prompt_catalog_is_pinned_and_combined_for_compilation():
    topic_payload = yaml.safe_load(topic_control_prompts_yaml())
    combined = yaml.safe_load(prompt_catalog_yaml())

    assert TOPIC_CONTROL_VERSION == 1
    assert {item["task"] for item in topic_payload["prompts"]} == {
        "topic_safety_check_input $model=topic_control"
    }
    assert len(combined["prompts"]) == 3
