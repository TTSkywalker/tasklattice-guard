"""Deterministic concurrency regression using an existing signed artifact."""
from __future__ import annotations

import asyncio
import base64
from pathlib import Path
import threading

import pytest

from runner import generated as protocol
from runner.artifact_store import ArtifactStore
from runner.toolkit.nemo.action_registry import action_providers
from runner.toolkit.nemo.actions import local_action_providers
from runner.toolkit.nemo.registry import NeMoRuntimeRegistry


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/artifacts/local-secrets-v1"


class DeadlineLock:
    """Turn a real lock inversion into a bounded failure, not a hung test job."""
    def __init__(self):
        self.lock = threading.RLock()

    def __enter__(self):
        assert self.lock.acquire(timeout=2), "ArtifactStore/Registry lock inversion"
        return self

    def __exit__(self, *_args):
        self.lock.release()


@pytest.mark.parametrize("read_method", ["readiness", "admission_load"])
def test_publication_does_not_deadlock_runtime_observers(tmp_path, monkeypatch, read_method):
    state = protocol.DesiredState()
    state.ParseFromString(base64.b64decode((FIXTURE / "desired-state.pb.b64").read_text()))
    store = ArtifactStore(FIXTURE / "public-key.pem", tmp_path)
    registry = NeMoRuntimeRegistry(store, action_providers(*local_action_providers()))
    store.attach_registry(registry)
    store.apply(state)
    store._lock = DeadlineLock()
    state.generation += 1
    publishing = threading.Event()
    reading = threading.Event()
    errors = []
    original_publish = registry.publish_release
    original_keys = store.active_plan_keys

    def publish(*args):
        publishing.set()
        assert reading.wait(3), "Observer never reached the store"
        return original_publish(*args)

    def active_keys():
        if threading.current_thread().name == "runtime-observer":
            reading.set()  # Registry lock is held before taking the store lock.
        return original_keys()

    def capture(fn):
        try:
            fn()
        except BaseException as error:
            errors.append(error)

    monkeypatch.setattr(registry, "publish_release", publish)
    monkeypatch.setattr(store, "active_plan_keys", active_keys)
    publisher = threading.Thread(target=lambda: capture(lambda: store.apply(state)), daemon=True)

    def observe():
        assert publishing.wait(3), "Publication never reached the release boundary"
        getattr(registry, read_method)()

    observer = threading.Thread(target=lambda: capture(observe), name="runtime-observer", daemon=True)
    try:
        publisher.start()
        observer.start()
        publisher.join(timeout=6)
        observer.join(timeout=6)
        assert not publisher.is_alive() and not observer.is_alive()
        assert not errors, errors
        assert store.generation == state.generation
        assert registry.readiness()["ready"]
    finally:
        asyncio.run(registry.shutdown())
