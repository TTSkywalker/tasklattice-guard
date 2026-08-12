from __future__ import annotations

from importlib.resources import files


TOPIC_CONTROL_VERSION = 1


def prompts_yaml(*, version: int = TOPIC_CONTROL_VERSION) -> str:
    """Load the prompt catalog pinned to a built-in Topic Control version."""
    if version != TOPIC_CONTROL_VERSION:
        raise ValueError(f"Unsupported Topic Control version: {version}.")
    return (
        files(f"{__package__}.v{version}")
        .joinpath("prompts.yml")
        .read_text(encoding="utf-8")
    )
