"""Immutable assets shipped with TaskLattice built-in Policies."""

from __future__ import annotations

import yaml

from .content_safety import prompts_yaml as content_safety_prompts_yaml
from .topic_safety import prompts_yaml as topic_safety_prompts_yaml


def prompt_catalog_yaml() -> str:
    """Combine version-pinned built-in Prompt assets for NeMo compilation."""
    prompts = []
    for catalog in (
        content_safety_prompts_yaml(),
        topic_safety_prompts_yaml(),
    ):
        prompts.extend((yaml.safe_load(catalog) or {}).get("prompts", ()))
    return yaml.safe_dump(
        {"prompts": prompts},
        allow_unicode=True,
        sort_keys=False,
    )
