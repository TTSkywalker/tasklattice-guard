from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from .contracts import GuardContentBlock, PlanResolution


@dataclass(slots=True)
class CallContext:
    messages: tuple[dict[str, Any], ...]
    content_blocks: tuple[GuardContentBlock, ...]
    resolution: PlanResolution
    expires_at: float


class CallContextStore:
    """Pin one immutable Policy Revision across an input/output call cycle."""

    def __init__(self, ttl_seconds: float = 300.0, max_entries: int = 10_000):
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._items: dict[str, CallContext] = {}

    def put(
        self,
        call_id: str | None,
        messages: tuple[dict[str, Any], ...],
        resolution: PlanResolution,
        content_blocks: tuple[GuardContentBlock, ...] = (),
    ) -> None:
        if not call_id:
            return
        self._prune()
        if len(self._items) >= self._max_entries:
            oldest = min(self._items, key=lambda key: self._items[key].expires_at)
            self._items.pop(oldest, None)
        self._items[call_id] = CallContext(
            messages=messages[-20:],
            content_blocks=content_blocks,
            resolution=resolution,
            expires_at=time.monotonic() + self._ttl_seconds,
        )

    def get(self, call_id: str | None) -> CallContext | None:
        if not call_id:
            return None
        item = self._items.get(call_id)
        if not item:
            return None
        if item.expires_at <= time.monotonic():
            self._items.pop(call_id, None)
            return None
        return item

    def _prune(self) -> None:
        now = time.monotonic()
        for call_id, item in list(self._items.items()):
            if item.expires_at <= now:
                self._items.pop(call_id, None)
