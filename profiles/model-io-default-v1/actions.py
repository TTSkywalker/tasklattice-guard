from __future__ import annotations

import re

from nemoguardrails.actions import action


_BLOCKED_PATTERNS = (
    re.compile(r"\btasklattice-test-block\b", re.IGNORECASE),
    re.compile(r"\b(?:api[-_ ]?key|access[-_ ]?token)\s*[:=]\s*[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\b(?:authorization\s*:\s*bearer|bearer)\s+[A-Za-z0-9._~+\-/]+=*", re.IGNORECASE),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
)


@action(name="tasklattice_detect_model_io_violation", is_system_action=True)
async def tasklattice_detect_model_io_violation(text: str = "") -> bool:
    """Block high-confidence secrets and identifiers before model evaluation."""

    return any(pattern.search(text) for pattern in _BLOCKED_PATTERNS)
