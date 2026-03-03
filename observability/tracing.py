"""
OpenTelemetry distributed tracing setup for Emily.

Use the `trace_span` context manager or `get_tracer` in any module that
needs to emit trace spans. Traces are exported to the configured OTLP endpoint
(Jaeger or any OTLP-compatible collector).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from observability.logger import get_logger

log = get_logger(__name__)

_tracer_provider: TracerProvider | None = None
_in_memory_exporter: InMemorySpanExporter | None = None


def configure_tracing(
    service_name: str = "emily",
    service_version: str = "1.0.0",
    otlp_endpoint: str = "http://localhost:4317",
    enabled: bool = True,
) -> None:
    """
    Initialize the OpenTelemetry tracer provider.

    When enabled=False (e.g., in tests), traces are collected in-memory only.

    Args:
        service_name: Logical service name shown in traces.
        service_version: Service version tag.
        otlp_endpoint: gRPC endpoint for the OTLP collector.
        enabled: Whether to export to OTLP. False → in-memory only.
    """
    global _tracer_provider, _in_memory_exporter

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": service_version,
        }
    )

    provider = TracerProvider(resource=resource)

    if enabled:
        try:
            exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            log.info("tracing_configured", endpoint=otlp_endpoint)
        except Exception as exc:
            log.warning("tracing_otlp_failed", error=str(exc))
            _in_memory_exporter = InMemorySpanExporter()
            provider.add_span_processor(SimpleSpanProcessor(_in_memory_exporter))
    else:
        _in_memory_exporter = InMemorySpanExporter()
        provider.add_span_processor(SimpleSpanProcessor(_in_memory_exporter))
        log.debug("tracing_in_memory_only")

    trace.set_tracer_provider(provider)
    _tracer_provider = provider


def get_tracer(name: str) -> trace.Tracer:
    """
    Return an OpenTelemetry Tracer for the given module.

    Args:
        name: Typically __name__ of the calling module.

    Returns:
        An OpenTelemetry Tracer instance.
    """
    return trace.get_tracer(name)


@contextmanager
def trace_span(
    name: str,
    tracer_name: str = "emily",
    attributes: dict[str, Any] | None = None,
) -> Iterator[trace.Span]:
    """
    Synchronous context manager that wraps a block in a trace span.

    Args:
        name: Span name (e.g., "stt.transcribe").
        tracer_name: Tracer identifier.
        attributes: Optional key/value attributes added to the span.

    Yields:
        The active Span.
    """
    tracer = get_tracer(tracer_name)
    with tracer.start_as_current_span(name) as span:
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, str(value))
        yield span


@asynccontextmanager
async def async_trace_span(
    name: str,
    tracer_name: str = "emily",
    attributes: dict[str, Any] | None = None,
) -> AsyncIterator[trace.Span]:
    """
    Async context manager that wraps an async block in a trace span.

    Args:
        name: Span name.
        tracer_name: Tracer identifier.
        attributes: Optional span attributes.

    Yields:
        The active Span.
    """
    tracer = get_tracer(tracer_name)
    with tracer.start_as_current_span(name) as span:
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, str(value))
        yield span


def get_in_memory_spans() -> list[Any]:
    """
    Return all collected in-memory spans (used in tests).

    Returns:
        List of finished spans, or empty list if OTLP exporter is active.
    """
    if _in_memory_exporter is None:
        return []
    return list(_in_memory_exporter.get_finished_spans())
