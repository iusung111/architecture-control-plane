from __future__ import annotations

import logging
from time import perf_counter
from uuid import uuid4

from fastapi import Request

from app.core.logging import get_logger, log_event, reset_request_id, set_request_id
from app.core.rate_limit import RateLimitBackendUnavailable, RateLimitExceeded, enforce_global_request_limit
from app.core.telemetry import (
    HTTP_REQUESTS_IN_PROGRESS,
    _start_otel_span,
    get_current_otel_traceparent,
    record_http_request,
    reset_trace_context,
    set_span_error,
    set_span_http_status,
    set_trace_context_from_traceparent,
    start_request_trace,
)

logger = get_logger(__name__)


async def request_context_middleware(request: Request, call_next, error_response_factory):
    request_id = request.headers.get("x-request-id") or str(uuid4())
    request.state.request_id = request_id
    ctx_token = set_request_id(request_id)

    request_method = request.method
    request_path = request.url.path
    span_cm = _start_otel_span(
        f"{request_method} {request_path}",
        kind="server",
        traceparent_header=request.headers.get("traceparent"),
        attributes={
            "http.method": request_method,
            "http.target": request.url.path,
            "http.scheme": request.url.scheme,
        },
    )
    span = span_cm.__enter__()
    traceparent_response = get_current_otel_traceparent()
    trace_tokens = set_trace_context_from_traceparent(traceparent_response)
    if trace_tokens is None:
        traceparent_response, trace_tokens = start_request_trace(request.headers.get("traceparent"))

    request.state.traceparent = traceparent_response
    started_at = perf_counter()
    in_progress_path = request.url.path
    HTTP_REQUESTS_IN_PROGRESS.labels(method=request_method, path=in_progress_path).inc()
    log_event(
        logger,
        logging.INFO,
        "request.started",
        method=request_method,
        path=request.url.path,
        client=(request.client.host if request.client else None),
    )
    try:
        enforce_global_request_limit(request)
        response = await call_next(request)
        request.state.response_status_code = response.status_code
        response.headers["x-request-id"] = request_id
        response.headers["traceparent"] = traceparent_response
        set_span_http_status(span, response.status_code)
        return response
    except RateLimitExceeded as exc:
        set_span_http_status(span, 429)
        return error_response_factory(
            request,
            429,
            "too_many_requests",
            str(exc.detail),
            retryable=True,
            extra_headers=dict(exc.headers or {}),
        )
    except RateLimitBackendUnavailable as exc:
        set_span_http_status(span, 503)
        return error_response_factory(
            request,
            503,
            "rate_limit_backend_unavailable",
            str(exc.detail),
            retryable=True,
            extra_headers=dict(exc.headers or {}),
        )
    except Exception as exc:  # noqa: BLE001
        set_span_error(span, exc)
        log_event(
            logger,
            logging.ERROR,
            "request.unhandled_exception",
            method=request_method,
            path=request.url.path,
        )
        raise
    finally:
        duration_seconds = perf_counter() - started_at
        route = request.scope.get("route")
        path_template = getattr(route, "path", request.url.path)
        status_code = getattr(getattr(request, "state", None), "response_status_code", None) or 500
        record_http_request(request_method, path_template, int(status_code), duration_seconds)
        HTTP_REQUESTS_IN_PROGRESS.labels(method=request_method, path=in_progress_path).dec()
        log_event(
            logger,
            logging.INFO,
            "request.finished",
            method=request_method,
            path=request.url.path,
            status_code=status_code,
            duration_ms=round(duration_seconds * 1000, 2),
        )
        span_cm.__exit__(None, None, None)
        reset_request_id(ctx_token)
        reset_trace_context(trace_tokens)
