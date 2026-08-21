from __future__ import annotations

import json

import httpx
import pytest

from runner.telemetry import RuntimeTelemetryExporter


@pytest.mark.asyncio
async def test_runtime_events_remain_in_wal_until_controller_accepts_them(tmp_path):
    exporter = RuntimeTelemetryExporter("http://controller/events", "token", tmp_path, 100, "runner-0")
    event = {"id": "event-1", "requestId": "request-1", "decision": "allow"}
    await exporter.emit(event)
    assert "event-1" in (tmp_path / "runtime-events.wal").read_text()

    received = []
    transport = httpx.MockTransport(lambda request: (
        received.append(request) or httpx.Response(202, json={"accepted": 1})
    ))
    async with httpx.AsyncClient(transport=transport) as client:
        assert await exporter._flush_once(client) is False

    assert received[0].headers["authorization"] == "Bearer token"
    assert not (tmp_path / "runtime-events.wal").read_text()


@pytest.mark.asyncio
async def test_zero_traffic_watermark_proves_the_export_channel_is_fresh(tmp_path):
    exporter = RuntimeTelemetryExporter("http://controller/events", "token", tmp_path, 100, "runner-0")
    received = []
    transport = httpx.MockTransport(lambda request: (
        received.append(request) or httpx.Response(202, json={"accepted": 0})
    ))

    async with httpx.AsyncClient(transport=transport) as client:
        await exporter._report_watermark(client)

    payload = json.loads(received[0].content)
    assert payload["events"] == []
    assert payload["runnerId"] == "runner-0"
    assert payload["observedAt"]
