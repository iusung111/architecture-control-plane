from __future__ import annotations

import re
import secrets
import threading
from contextvars import ContextVar

try:
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
    from opentelemetry.trace import SpanKind, Status, StatusCode
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
except ImportError:  # pragma: no cover - optional runtime dependency in tests
    trace = None
    OTLPSpanExporter = None
    Resource = None
    TracerProvider = None
    BatchSpanProcessor = None
    ParentBased = None
    TraceIdRatioBased = None
    SpanKind = None
    Status = None
    StatusCode = None
    TraceContextTextMapPropagator = None

TRACEPARENT_RE = re.compile(r"^[\da-f]{2}-([\da-f]{32})-([\da-f]{16})-([\da-f]{2})$", re.IGNORECASE)

_trace_id_ctx: ContextVar[str | None] = ContextVar("trace_id", default=None)
_span_id_ctx: ContextVar[str | None] = ContextVar("span_id", default=None)
_trace_flags_ctx: ContextVar[str] = ContextVar("trace_flags", default="01")

_tracing_lock = threading.Lock()
_metrics_server_lock = threading.Lock()
_metrics_servers_started: set[int] = set()
_tracing_initialized = False
_tracing_enabled = False
_trace_propagator = TraceContextTextMapPropagator() if TraceContextTextMapPropagator is not None else None


def new_trace_id() -> str:
    return secrets.token_hex(16)


def new_span_id() -> str:
    return secrets.token_hex(8)
