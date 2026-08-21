from __future__ import annotations

import math
import threading
import time
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass

import psutil
from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    GCCollector,
    Histogram,
    PlatformCollector,
    ProcessCollector,
)

from .generated import runner_control_pb2 as protocol


@dataclass(slots=True)
class _Window:
    requests: int = 0
    errors: int = 0
    timeouts: int = 0


class RunnerMetrics:
    def __init__(self, max_concurrency: int) -> None:
        self._max_concurrency = max_concurrency
        self._lock = threading.Lock()
        self._window = _Window()
        self._latencies: deque[float] = deque(maxlen=2_000)
        self._inflight = 0
        self._queue_depth = 0
        self._active_guardrails = 0
        self._compile_queue_depth = 0
        self.registry = CollectorRegistry()
        ProcessCollector(registry=self.registry)
        PlatformCollector(registry=self.registry)
        GCCollector(registry=self.registry)
        self.requests = Counter(
            "guard_runner_requests_total", "Runtime requests handled by this Runner.", ["outcome"],
            registry=self.registry,
        )
        self.duration = Histogram(
            "guard_runner_request_duration_seconds", "Runtime request latency.",
            buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
            registry=self.registry,
        )
        self.inflight = Gauge("guard_runner_inflight", "Currently executing Runtime requests.", registry=self.registry)
        self.queue = Gauge("guard_runner_queue_depth", "Requests waiting for Runtime admission.", registry=self.registry)
        self.generation = Gauge("guard_runner_applied_generation", "Applied Controller desired-state generation.", registry=self.registry)
        self.active_guardrails = Gauge("guard_runner_active_guardrails", "Active Guardrail versions in this Runner.", registry=self.registry)
        self.compile_queue = Gauge("guard_runner_compile_queue_depth", "Default Runner compile work currently in progress.", registry=self.registry)
        self.cpu = Gauge("guard_runner_cpu_utilization_ratio", "Host CPU utilization observed by this Runner.", registry=self.registry)
        self.memory = Gauge("guard_runner_memory_utilization_ratio", "Host memory utilization observed by this Runner.", registry=self.registry)

    @contextmanager
    def request(self):
        started = time.perf_counter()
        with self._lock:
            self._inflight += 1
            self.inflight.set(self._inflight)
        outcome = "success"
        try:
            yield
        except TimeoutError:
            outcome = "timeout"
            raise
        except Exception:
            outcome = "error"
            raise
        finally:
            latency = (time.perf_counter() - started) * 1_000
            with self._lock:
                self._inflight -= 1
                self._window.requests += 1
                self._window.errors += int(outcome == "error")
                self._window.timeouts += int(outcome == "timeout")
                self._latencies.append(latency)
                self.inflight.set(self._inflight)
            self.requests.labels(outcome=outcome).inc()
            self.duration.observe(latency / 1_000)

    def set_active_guardrails(self, count: int, generation: int) -> None:
        with self._lock:
            self._active_guardrails = max(0, count)
            self.generation.set(generation)
            self.active_guardrails.set(self._active_guardrails)

    def heartbeat(self) -> protocol.RunnerLoad:
        with self._lock:
            window, self._window = self._window, _Window()
            latencies = sorted(self._latencies)
            p95 = _percentile(latencies, 0.95)
            cpu = psutil.cpu_percent(interval=None) / 100
            memory = psutil.virtual_memory().percent / 100
            self.cpu.set(cpu)
            self.memory.set(memory)
            return protocol.RunnerLoad(
                inflight=self._inflight,
                max_concurrency=self._max_concurrency,
                queue_depth=self._queue_depth,
                requests_delta=window.requests,
                errors_delta=window.errors,
                timeouts_delta=window.timeouts,
                latency_p95_ms=p95,
                cpu_utilization=cpu,
                memory_utilization=memory,
                active_guardrails=self._active_guardrails,
                compile_queue_depth=self._compile_queue_depth,
            )

    def compiling(self, active: bool) -> None:
        with self._lock:
            self._compile_queue_depth = int(active)
            self.compile_queue.set(self._compile_queue_depth)


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0
    index = min(len(values) - 1, max(0, math.ceil(len(values) * percentile) - 1))
    return round(values[index], 3)
