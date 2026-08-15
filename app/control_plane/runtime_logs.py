from __future__ import annotations

import json
from collections.abc import Iterable, Mapping

from cryptography.fernet import Fernet, InvalidToken


MAX_CAPTURE_CHARACTERS = 100_000


class RuntimeLogCipher:
    """Encrypt runtime content before it crosses the database boundary."""

    def __init__(self, key: str | None) -> None:
        clean_key = (key or "").strip()
        self._fernet = Fernet(clean_key.encode()) if clean_key else None

    @property
    def configured(self) -> bool:
        return self._fernet is not None

    def encrypt(self, blocks: Iterable[Mapping[str, object]]) -> str | None:
        if self._fernet is None:
            return None
        normalized = normalize_content_blocks(blocks)
        if not normalized:
            return None
        payload = json.dumps(
            normalized,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
        return self._fernet.encrypt(payload).decode()

    def decrypt(self, ciphertext: str | None) -> tuple[dict[str, object], ...] | None:
        if not ciphertext or self._fernet is None:
            return None
        try:
            payload = json.loads(self._fernet.decrypt(ciphertext.encode()))
        except (InvalidToken, UnicodeDecodeError, json.JSONDecodeError):
            return None
        if not isinstance(payload, list):
            return None
        return tuple(item for item in payload if isinstance(item, dict))


def normalize_content_blocks(
    blocks: Iterable[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    """Bound captured text while preserving block identity and provenance."""

    remaining = MAX_CAPTURE_CHARACTERS
    normalized: list[dict[str, object]] = []
    for index, block in enumerate(blocks):
        if remaining <= 0:
            break
        text = str(block.get("text", ""))
        captured = text[:remaining]
        truncated = len(captured) < len(text)
        normalized.append(
            {
                "id": str(block.get("id") or f"content-{index}"),
                "role": str(block.get("role") or "content"),
                "source": str(block.get("source") or "unknown"),
                "text": captured,
                "truncated": truncated,
            }
        )
        remaining -= len(captured)
    return tuple(normalized)
