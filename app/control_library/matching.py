from __future__ import annotations

import re


def keyword_expression(keyword: str) -> str:
    """Build the case-insensitive expression used by local keyword rules."""
    escaped = re.escape(keyword).replace(r"\*", ".?")
    return escaped if " " in keyword else rf"\b{escaped}\b"


def severity_applies(severity: str, threshold: str) -> bool:
    """Return whether a source keyword meets a configured severity threshold."""
    order = {"low": 0, "medium": 1, "high": 2}
    return order.get(severity, 0) >= order.get(threshold, 1)
