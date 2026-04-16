from __future__ import annotations


def __getattr__(name: str):
    tracing_names = {
        "_start_otel_span",
        "get_current_otel_traceparent",
        "get_trace_context",
        "initialize_tracing",
        "reset_trace_context",
        "set_span_attribute",
        "set_span_error",
        "set_span_http_status",
        "set_trace_context_from_traceparent",
        "shutdown_tracing",
        "start_child_trace",
        "start_request_trace",
        "timed_span",
    }
    metrics_names = {
        "AUTH_FAILURES_TOTAL",
        "DB_LOCK_CONFLICTS_TOTAL",
        "HTTP_REQUESTS_IN_PROGRESS",
        "HTTP_REQUESTS_TOTAL",
        "HTTP_REQUEST_DURATION_SECONDS",
        "JOB_EXECUTIONS_TOTAL",
        "JOB_EXECUTION_DURATION_SECONDS",
        "JOB_QUEUE_DEPTH",
        "JOB_QUEUE_READY_AGE_SECONDS",
        "JOB_RUNNING_AGE_SECONDS",
        "OUTBOX_DELIVERIES_TOTAL",
        "OUTBOX_DELIVERY_DURATION_SECONDS",
        "RATE_LIMIT_BACKEND_DECISIONS_TOTAL",
        "RATE_LIMIT_BACKEND_ERRORS_TOTAL",
        "RATE_LIMIT_BACKEND_HEALTH",
        "RATE_LIMIT_PLAN_EVENTS_TOTAL",
        "RATE_LIMIT_REJECTIONS_TOTAL",
        "RATE_LIMIT_TENANT_EVENTS_TOTAL",
        "SLO_EVENTS_TOTAL",
        "SLO_LATENCY_THRESHOLD_SECONDS",
        "SLO_TARGET_RATIO",
        "record_auth_failure",
        "record_db_lock_conflict",
        "record_http_request",
        "record_job_execution",
        "record_outbox_delivery",
        "record_rate_limit_backend_decision",
        "record_rate_limit_backend_error",
        "record_rate_limit_plan_event",
        "record_rate_limit_rejection",
        "record_rate_limit_tenant_event",
        "set_rate_limit_backend_health",
    }
    system_metrics_names = {
        "render_metrics",
        "start_metrics_http_server",
    }
    if name in tracing_names:
        from .telemetry_support import tracing
        return getattr(tracing, name)
    if name in metrics_names:
        from .telemetry_support import metrics
        return getattr(metrics, name)
    if name in system_metrics_names:
        from .telemetry_support import system_metrics
        return getattr(system_metrics, name)
    raise AttributeError(name)
