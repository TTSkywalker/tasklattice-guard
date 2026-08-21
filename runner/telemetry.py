from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx


logger = logging.getLogger("tasklattice.guard.runner.telemetry")


class RuntimeTelemetryExporter:
    """Disk-backed, non-hot-path delivery of immutable Runtime events."""

    def __init__(
        self,
        endpoint: str,
        token: str,
        state_path: Path,
        batch_size: int,
        runner_id: str,
    ) -> None:
        self._endpoint = endpoint
        self._token = token
        self._batch_size = batch_size
        self._runner_id = runner_id
        self._wal_path = state_path / "runtime-events.wal"
        self._wake = asyncio.Event()
        self._stop = asyncio.Event()
        self._lock = asyncio.Lock()

    async def emit(self, event: dict[str, Any]) -> None:
        encoded = json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n"
        async with self._lock:
            await asyncio.to_thread(self._append, encoded)
        self._wake.set()

    async def run(self) -> None:
        timeout = httpx.Timeout(10)
        async with httpx.AsyncClient(timeout=timeout) as client:
            while not self._stop.is_set():
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=5)
                except TimeoutError:
                    pass
                self._wake.clear()
                try:
                    while await self._flush_once(client):
                        pass
                    await self._report_watermark(client)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Runtime telemetry delivery failed; events remain in the WAL.")

    async def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    async def _flush_once(self, client: httpx.AsyncClient) -> bool:
        async with self._lock:
            lines = await asyncio.to_thread(self._read_lines)
            batch = lines[: self._batch_size]
        if not batch:
            return False
        events = [json.loads(line) for line in batch]
        response = await client.post(
            self._endpoint,
            headers={"authorization": f"Bearer {self._token}"},
            json={"events": events},
        )
        response.raise_for_status()
        async with self._lock:
            latest = await asyncio.to_thread(self._read_lines)
            if latest[: len(batch)] != batch:
                raise RuntimeError("Runtime telemetry WAL changed unexpectedly during delivery.")
            await asyncio.to_thread(self._replace_lines, latest[len(batch) :])
            return len(latest) > len(batch)

    async def _report_watermark(self, client: httpx.AsyncClient) -> None:
        """Confirm that the telemetry channel is healthy even during zero traffic."""
        response = await client.post(
            self._endpoint,
            headers={"authorization": f"Bearer {self._token}"},
            json={
                "events": [],
                "runnerId": self._runner_id,
                "observedAt": datetime.now(UTC).isoformat(),
            },
        )
        response.raise_for_status()

    def _append(self, encoded: str) -> None:
        self._wal_path.parent.mkdir(parents=True, exist_ok=True)
        with self._wal_path.open("a", encoding="utf-8") as stream:
            stream.write(encoded)
            stream.flush()

    def _read_lines(self) -> list[str]:
        if not self._wal_path.exists():
            return []
        return [line for line in self._wal_path.read_text(encoding="utf-8").splitlines() if line]

    def _replace_lines(self, lines: list[str]) -> None:
        temporary = self._wal_path.with_suffix(".wal.tmp")
        temporary.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
        temporary.replace(self._wal_path)
