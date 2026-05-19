from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Iterator
from uuid import uuid4

logger = logging.getLogger(__name__)

_tracer: Any | None = None
_enabled = False


def init_tracing(*, service_name: str = "newsroom") -> bool:
    """Initialize OpenTelemetry when optional deps are installed."""
    global _tracer, _enabled
    import os

    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        if otlp_endpoint:
            try:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                    OTLPSpanExporter,
                )

                provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
                logger.info("event=tracing_otlp endpoint=%s", otlp_endpoint)
            except ImportError:
                logger.warning("event=tracing_otlp_unavailable fallback=console")
                provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        else:
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer(service_name)
        _enabled = True
        logger.info("event=tracing_initialized service=%s", service_name)
        return True
    except ImportError:
        logger.info("event=tracing_disabled reason=opentelemetry_not_installed")
        _tracer = None
        _enabled = False
        return False


def is_enabled() -> bool:
    return _enabled


def new_trace_ids() -> tuple[str, str]:
    return uuid4().hex, uuid4().hex[:16]


@contextmanager
def trace_span(
    name: str,
    *,
    trace_id: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> Iterator[dict[str, str]]:
    """Yield trace context for envelope propagation (works without OTEL)."""
    tid, sid = trace_id or uuid4().hex, uuid4().hex[:16]
    ctx = {"trace_id": tid, "span_id": sid}
    try:
        from bot.observability.metrics import record_trace_span

        record_trace_span(name)
    except Exception:
        pass
    if _tracer is None:
        yield ctx
        return
    with _tracer.start_as_current_span(name) as span:
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, value)
        yield ctx


def inject_trace(envelope_factory, **kwargs: Any) -> Any:
    """Helper to pass trace_id/span_id into EventEnvelope constructors."""
    tid, sid = new_trace_ids()
    return envelope_factory(trace_id=tid, span_id=sid, **kwargs)
