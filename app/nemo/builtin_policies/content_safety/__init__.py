from __future__ import annotations

from importlib.resources import files


CONTENT_SAFETY_POLICY_VERSION = 1


def prompts_yaml(*, version: int = CONTENT_SAFETY_POLICY_VERSION) -> str:
    """Load the prompt catalog pinned to a built-in Content Safety version."""
    if version != CONTENT_SAFETY_POLICY_VERSION:
        raise ValueError(f"Unsupported Content Safety Policy version: {version}.")
    return (
        files(f"{__package__}.v{version}")
        .joinpath("prompts.yml")
        .read_text(encoding="utf-8")
    )
