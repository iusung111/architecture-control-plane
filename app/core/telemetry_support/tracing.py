from __future__ import annotations

from collections.abc import Generator, Mapping
from contextlib import contextmanager, nullcontext
from time import perf_counter
from typing import Any

from app.core.config import get_settings

from . import common


def _parse_traceparent(value: str | None) -> tuple[str, str, str] | None:
    if not value:
        return None
    match = common.TRACEPARENT_RE.match(value.strip())
    if not match:
        return None
    trace_id, parent_span_id, trace_flags = match.groups()
    if trace_id == "0" * 32 or parent_span_id == "0" * 16:
        return None
    return trace_id.lower(), parent_span_id.lower(), trace_flags.lower()


def _set_trace_context(trace_id: str, span_id: str, trace_flags: str) -> tuple[object, object, object]:
    return (
        common._trace_id_ctx.set(trace_id),
        common._span_id_ctx.set(span_id),
        common._trace_flags_ctx.set(trace_flags),
    )


def _parse_otel_headers(raw_headers: str | None) -> dict[str, str] | None:
    if not raw_headers:
        return None
    parsed: dict[str, str] = {}
    for item in raw_headers.split(","):
        if not item.strip() or "=" not in item:
            continue
        key, value = item.split("=", 1)
        parsed[key.strip()] = value.strip()
    return parsed or None


def initialize_tracing() -> bool:
    settings = get_settings()
    if not settings.otel_enabled or not settings.otel_exporter_otlp_endpoint:
        common._tracing_initialized = True
        common._tracing_enabled = False
        return False
    if (
        common.trace is None
        or common.TracerProvider is None
        or common.OTLPSpanExporter is None
        or common.BatchSpanProcessor is None
        or common.ParentBased is None
    ):
        common._tracing_initialized = True
        common._tracing_enabled = False
        return False
    with common._tracing_lock:
        if common._tracing_initialized and (
            common._tracing_enabled or not settings.otel_enabled or not settings.otel_exporter_otlp_endpoint
        ):
            return common._tracing_enabled
        existing_provider = common.trace.get_tracer_provider()
        if isinstance(existing_provider, common.TracerProvider):
            common._tracing_initialized = True
            common._tracing_enabled = True
            return True
        resource = common.Resource.create(
            {
                "service.name": settings.otel_service_name or settings.app_name,
                "service.namespace": settings.otel_service_namespace,
                "service.version": settings.otel_service_version,
                "deployment.environment": settings.environment,
            }
        )
        sampler = common.ParentBased(root=common.TraceIdRatioBased(settings.otel_traces_sampler_ratio))
        provider = common.TracerProvider(resource=resource, sampler=sampler)
        exporter = common.OTLPSpanExporter(
            endpoint=settings.otel_exporter_otlp_endpoint,
            headers=_parse_otel_headers(settings.otel_exporter_otlp_headers),
        )
        provider.add_span_processor(common.BatchSpanProcessor(exporter))
        common.trace.set_tracer_provider(provider)
        common._tracing_initialized = True
        common._tracing_enabled = True
        return True


def shutdown_tracing() -> None:
    if common.trace is None:
        return
    provider = common.trace.get_tracer_provider()
    force_flush = getattr(provider, "force_flush", None)
    if callable(force_flush):
        force_flush()


def tracing_enabled() -> bool:
    return common._tracing_enabled and common.trace is not None and common._trace_propagator is not None


def reset_trace_context(tokens: tuple[object, object, object]) -> None:
    trace_token, span_token, flags_token = tokens
    common._trace_id_ctx.reset(trace_token)
    common._span_id_ctx.reset(span_token)
    common._trace_flags_ctx.reset(flags_token)


def set_trace_context_from_traceparent(traceparent: str | None) -> tuple[object, object, object] | None:
    parsed = _parse_traceparent(traceparent)
    if not parsed:
        return None
    return _set_trace_context(*parsed)


def start_request_trace(traceparent_header: str | None) -> tuple[str, tuple[object, object, object]]:
    parsed = _parse_traceparent(traceparent_header)
    trace_flags = parsed[2] if parsed else "01"
    trace_id = parsed[0] if parsed else common.new_trace_id()
    span_id = common.new_span_id()
    tokens = _set_trace_context(trace_id, span_id, trace_flags)
    return format_traceparent(trace_id, span_id, trace_flags), tokens


def start_child_trace(traceparent_header: str | None = None) -> tuple[str, tuple[object, object, object]]:
    parsed = _parse_traceparent(traceparent_header)
    trace_id = parsed[0] if parsed else (common._trace_id_ctx.get() or common.new_trace_id())
    trace_flags = parsed[2] if parsed else common._trace_flags_ctx.get()
    span_id = common.new_span_id()
    tokens = _set_trace_context(trace_id, span_id, trace_flags)
    return format_traceparent(trace_id, span_id, trace_flags), tokens


def format_traceparent(trace_id: str | None = None, span_id: str | None = None, trace_flags: str | None = None) -> str:
    return f"00-{trace_id or common._trace_id_ctx.get() or common.new_trace_id()}-{span_id or common._span_id_ctx.get() or common.new_span_id()}-{trace_flags or common._trace_flags_ctx.get()}"


def get_trace_context() -> tuple[str | None, str | None, str]:
    return common._trace_id_ctx.get(), common._span_id_ctx.get(), common._trace_flags_ctx.get()


def get_current_traceparent() -> str | None:
    trace_id = common._trace_id_ctx.get()
    span_id = common._span_id_ctx.get()
    if not trace_id or not span_id:
        return None
    return format_traceparent(trace_id, span_id, common._trace_flags_ctx.get())


def _kind_from_name(kind: str | None):
    if common.SpanKind is None:
        return None
    mapping = {
        "server": common.SpanKind.SERVER,
        "consumer": common.SpanKind.CONSUMER,
        "producer": common.SpanKind.PRODUCER,
        "client": common.SpanKind.CLIENT,
    }
    return mapping.get((kind or "internal").lower(), common.SpanKind.INTERNAL)


def _start_otel_span(name: str, *, kind: str = "internal", traceparent_header: str | None = None, attributes: Mapping[str, Any] | None = None):
    if not tracing_enabled():
        return nullcontext(None)
    carrier = {"traceparent": traceparent_header} if traceparent_header else {}
    parent_context = common._trace_propagator.extract(carrier=carrier) if common._trace_propagator is not None else None
    settings = get_settings()
    tracer = common.trace.get_tracer(settings.otel_service_name or settings.app_name)
    return tracer.start_as_current_span(name, context=parent_context, kind=_kind_from_name(kind), attributes=dict(attributes or {}))


def get_current_otel_traceparent() -> str | None:
    if not tracing_enabled() or common._trace_propagator is None:
        return None
    carrier: dict[str, str] = {}
    common._trace_propagator.inject(carrier)
    return carrier.get("traceparent")


def set_span_attribute(span, key: str, value: Any) -> None:
    if span is not None and hasattr(span, "set_attribute"):
        span.set_attribute(key, value)


def set_span_error(span, exc: Exception) -> None:
    if span is None or common.Status is None or common.StatusCode is None:
        return
    if hasattr(span, "record_exception"):
        span.record_exception(exc)
    span.set_status(common.Status(common.StatusCode.ERROR, str(exc)))


def set_span_http_status(span, status_code: int) -> None:
    if span is None:
        return
    if hasattr(span, "set_attribute"):
        span.set_attribute("http.status_code", status_code)
    if common.Status is not None and common.StatusCode is not None:
        status = common.StatusCode.ERROR if status_code >= 500 else common.StatusCode.OK
        span.set_status(common.Status(status))


@contextmanager
def timed_span(
    traceparent_header: str | None = None,
    *,
    name: str = "acp.operation",
    kind: str = "internal",
    attributes: Mapping[str, Any] | None = None,
) -> Generator[tuple[str, float], None, None]:
    span_cm = _start_otel_span(name, kind=kind, traceparent_header=traceparent_header, attributes=attributes)
    span = span_cm.__enter__()
    traceparent = get_current_otel_traceparent()
    tokens = set_trace_context_from_traceparent(traceparent)
    if tokens is None:
        traceparent, tokens = start_child_trace(traceparent_header)
    started_at = perf_counter()
    try:
        yield traceparent, started_at
    except Exception as exc:
        set_span_error(span, exc)
        raise
    finally:
        span_cm.__exit__(None, None, None)
        reset_trace_context(tokens)
