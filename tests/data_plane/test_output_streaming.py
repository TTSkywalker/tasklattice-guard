from __future__ import annotations

import pytest

from runner.output_streaming import OutputStreamSessionStore, RedisOutputStreamSessionStore
from runner.toolkit.runtime.contracts import ProtectionDecision, ProtectionRequest, RequestContext


def request() -> ProtectionRequest:
    return ProtectionRequest(
        phase="output",
        texts=("placeholder",),
        context=RequestContext(protocol="http", integration_id="integration-1"),
        call_id="integration-1:call-1",
    )


@pytest.mark.asyncio
async def test_full_buffered_never_releases_before_complete_response_passes():
    seen: list[str] = []

    async def evaluate(candidate: ProtectionRequest) -> ProtectionDecision:
        seen.append(candidate.texts[0])
        return ProtectionDecision(decision="allow", action="pass")

    store = OutputStreamSessionStore(window_characters=8)
    first = await store.process(
        stream_key="stream-1", sequence=0, text="hello ", final=False,
        mode="full_buffered", request=request(), evaluate=evaluate,
    )
    final = await store.process(
        stream_key="stream-1", sequence=1, text="world", final=True,
        mode="full_buffered", request=request(), evaluate=evaluate,
    )

    assert first.status == "buffering"
    assert first.released_text == ""
    assert seen == ["hello world"]
    assert final.status == "completed"
    assert final.released_text == "hello world"


@pytest.mark.asyncio
async def test_window_buffered_releases_only_windows_that_pass():
    seen: list[str] = []

    async def evaluate(candidate: ProtectionRequest) -> ProtectionDecision:
        seen.append(candidate.texts[0])
        if "unsafe" in candidate.texts[0]:
            return ProtectionDecision(decision="block", action="reject", reason="unsafe output")
        return ProtectionDecision(decision="allow", action="pass")

    store = OutputStreamSessionStore(window_characters=6)
    first = await store.process(
        stream_key="stream-2", sequence=0, text="safe", final=False,
        mode="window_buffered", request=request(), evaluate=evaluate,
    )
    second = await store.process(
        stream_key="stream-2", sequence=1, text=" text", final=False,
        mode="window_buffered", request=request(), evaluate=evaluate,
    )
    blocked = await store.process(
        stream_key="stream-2", sequence=2, text="unsafe", final=True,
        mode="window_buffered", request=request(), evaluate=evaluate,
    )

    assert first.released_text == ""
    assert second.released_text == "saf"  # Keep one window pending across chunks.
    assert blocked.status == "blocked"
    assert blocked.terminate is True
    assert blocked.released_text == ""
    assert seen == ["safe text", "safe textunsafe"]


@pytest.mark.asyncio
async def test_interruptible_does_not_forward_a_blocked_chunk():
    async def evaluate(_candidate: ProtectionRequest) -> ProtectionDecision:
        return ProtectionDecision(decision="block", action="reject", reason="unsafe output")

    result = await OutputStreamSessionStore().process(
        stream_key="stream-3", sequence=0, text="already emitted", final=False,
        mode="interruptible", request=request(), evaluate=evaluate,
    )

    assert result.released_text == ""
    assert result.status == "blocked"
    assert result.terminate is True


@pytest.mark.asyncio
async def test_stream_rejects_out_of_order_or_post_completion_chunks():
    async def evaluate(_candidate: ProtectionRequest) -> ProtectionDecision:
        return ProtectionDecision(decision="allow", action="pass")

    store = OutputStreamSessionStore()
    with pytest.raises(ValueError, match="Expected output stream sequence 0"):
        await store.process(
            stream_key="stream-4", sequence=1, text="late", final=False,
            mode="full_buffered", request=request(), evaluate=evaluate,
        )
    await store.process(
        stream_key="stream-4", sequence=0, text="done", final=True,
        mode="full_buffered", request=request(), evaluate=evaluate,
    )
    with pytest.raises(ValueError, match="already complete"):
        await store.process(
            stream_key="stream-4", sequence=1, text="again", final=True,
            mode="full_buffered", request=request(), evaluate=evaluate,
        )


@pytest.mark.asyncio
async def test_redis_store_continues_a_stream_on_another_runner_replica():
    backend = _FakeRedis()
    first_runner = RedisOutputStreamSessionStore("redis://unused")
    second_runner = RedisOutputStreamSessionStore("redis://unused")
    first_runner._redis = backend  # type: ignore[assignment]
    second_runner._redis = backend  # type: ignore[assignment]

    async def evaluate(candidate: ProtectionRequest) -> ProtectionDecision:
        return ProtectionDecision(
            decision="transform", action="redact", texts=(candidate.texts[0].replace("secret", "[REDACTED]"),),
        )

    first = await first_runner.process(
        stream_key="stream-shared", sequence=0, text="shared ", final=False,
        mode="full_buffered", request=request(), evaluate=evaluate,
    )
    final = await second_runner.process(
        stream_key="stream-shared", sequence=1, text="secret", final=True,
        mode="full_buffered", request=request(), evaluate=evaluate,
    )

    assert first.status == "buffering"
    assert final.status == "completed"
    assert final.released_text == "shared [REDACTED]"


class _FakeLock:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def lock(self, *_args, **_kwargs):
        return _FakeLock()

    async def get(self, key: str):
        return self.values.get(key)

    async def set(self, key: str, value: str, **_kwargs):
        self.values[key] = value


@pytest.fixture(params=["memory", "redis"])
def stream_store(request):
    if request.param == "memory":
        return OutputStreamSessionStore(window_characters=8)
    store = RedisOutputStreamSessionStore("redis://unused", window_characters=8)
    store._redis = _FakeRedis()
    return store


@pytest.mark.asyncio
async def test_cross_window_secret_is_checked_with_prior_context(stream_store):
    async def evaluate(candidate):
        if "api_key=abcdefghijklmnop" in candidate.texts[0]:
            return ProtectionDecision(decision="block", action="reject")
        return ProtectionDecision(decision="allow", action="pass")

    first = await stream_store.process(stream_key="split", sequence=0, text="api_key=", final=False,
                                       mode="window_buffered", request=request(), evaluate=evaluate)
    last = await stream_store.process(stream_key="split", sequence=1, text="abcdefghijklmnop", final=True,
                                      mode="window_buffered", request=request(), evaluate=evaluate)
    assert first.released_text + last.released_text == ""
    assert last.terminate


@pytest.mark.asyncio
async def test_failed_evaluation_does_not_consume_sequence_or_duplicate_text(stream_store):
    async def broken(_candidate):
        raise TimeoutError("test timeout")

    async def evaluate(candidate):
        assert candidate.texts == ("one",)
        return ProtectionDecision(decision="allow", action="pass")

    with pytest.raises(TimeoutError):
        await stream_store.process(stream_key="retry", sequence=0, text="one", final=True,
                                   mode="full_buffered", request=request(), evaluate=broken)
    result = await stream_store.process(stream_key="retry", sequence=0, text="one", final=True,
                                        mode="full_buffered", request=request(), evaluate=evaluate)
    assert result.released_text == "one"
    assert result.next_sequence == 1


@pytest.mark.asyncio
async def test_late_transform_cannot_rewrite_a_released_prefix(stream_store):
    async def evaluate(candidate):
        text = candidate.texts[0]
        return ProtectionDecision(decision="transform", action="redact", texts=(text.replace("hello", "[REDACTED]") if text.endswith("!") else text,))

    first = await stream_store.process(stream_key="prefix", sequence=0, text="hello world long", final=False,
                                       mode="window_buffered", request=request(), evaluate=evaluate)
    assert first.released_text
    last = await stream_store.process(stream_key="prefix", sequence=1, text="!", final=True,
                                      mode="window_buffered", request=request(), evaluate=evaluate)
    assert last.terminate
    assert last.released_text == ""
    assert "already released prefix" in last.decision.reason
