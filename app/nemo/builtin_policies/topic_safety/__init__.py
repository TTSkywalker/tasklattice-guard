from __future__ import annotations

from importlib.resources import files


TOPIC_SAFETY_POLICY_VERSION = 1


def prompts_yaml(*, version: int = TOPIC_SAFETY_POLICY_VERSION) -> str:
    """Load the prompt catalog pinned to a built-in Topic Safety Policy version."""
    if version != TOPIC_SAFETY_POLICY_VERSION:
        raise ValueError(f"Unsupported Topic Safety Policy version: {version}.")
    return (
        files(f"{__package__}.v{version}")
        .joinpath("prompts.yml")
        .read_text(encoding="utf-8")
    )
