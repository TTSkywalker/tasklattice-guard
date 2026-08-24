from __future__ import annotations

import logging
import threading

import pyroscope
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from pyroscope.otel import PyroscopeSpanProcessor

from .config import RunnerSettings


_LOGGER = logging.getLogger(__name__)
_LOCK = threading.Lock()
_CONFIGURED = False


def configure_observability(settings: RunnerSettings) -> None:
    """Configure tracing and profiling once for the Runner process.

    Metrics remain available independently. Tracing and profiling are opt-in so
    production operators can point them at an approved collector/backend.
    """
    global _CONFIGURED
    if _CONFIGURED or not (
        settings.otel_exporter_otlp_endpoint or settings.pyroscope_server_address
    ):
        return
    with _LOCK:
        if _CONFIGURED:
            return

        if settings.pyroscope_server_address:
            pyroscope.configure(
                application_name="tasklattice.guard-runner",
                server_address=settings.pyroscope_server_address,
                sample_rate=settings.pyroscope_sample_rate,
                cpu_enabled=True,
                mem_enabled=False,
                enable_logging=False,
                tags={
                    "service_name": "tasklattice.guard-runner",
                    "runner_id": settings.runner_id,
                    "pool": settings.pool_id,
                },
            )

        if settings.otel_exporter_otlp_endpoint:
            provider = TracerProvider(
                resource=Resource.create({
                    "service.name": "tasklattice.guard-runner",
                    "service.namespace": "tasklattice",
                    "service.version": "0.2.0",
                    "runner.id": settings.runner_id,
                    "runner.pool": settings.pool_id,
                }),
                sampler=ParentBased(TraceIdRatioBased(settings.otel_trace_sample_ratio)),
            )
            if settings.pyroscope_server_address:
                provider.add_span_processor(PyroscopeSpanProcessor())
            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(
                endpoint=f"{settings.otel_exporter_otlp_endpoint}/v1/traces",
            )))
            trace.set_tracer_provider(provider)
        elif settings.pyroscope_server_address:
            _LOGGER.warning(
                "Pyroscope profiling is enabled without tracing; span profiles are unavailable."
            )

        _CONFIGURED = True


def current_trace_id() -> str | None:
    context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        return None
    return f"{context.trace_id:032x}"


def current_exemplar() -> dict[str, str] | None:
    trace_id = current_trace_id()
    return {"trace_id": trace_id} if trace_id is not None else None
