from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

from app.core.config import get_settings

HTTP_REQUESTS_TOTAL = Counter(
    "acp_http_requests_total",
    "Total HTTP requests processed by the API",
    labelnames=("method", "path", "status_code"),
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "acp_http_request_duration_seconds",
    "HTTP request latency in seconds",
    labelnames=("method", "path", "status_code"),
)
HTTP_REQUESTS_IN_PROGRESS = Gauge(
    "acp_http_requests_in_progress",
    "HTTP requests currently in progress",
    labelnames=("method", "path"),
)
AUTH_FAILURES_TOTAL = Counter("acp_auth_failures_total", "Authentication failures by reason", labelnames=("reason",))
DB_LOCK_CONFLICTS_TOTAL = Counter("acp_db_lock_conflicts_total", "Database lock conflicts surfaced to the API")
JOB_EXECUTIONS_TOTAL = Counter(
    "acp_job_executions_total", "Worker job executions by job type and outcome", labelnames=("job_type", "outcome")
)
JOB_EXECUTION_DURATION_SECONDS = Histogram(
    "acp_job_execution_duration_seconds", "Worker job execution latency in seconds", labelnames=("job_type", "outcome")
)
OUTBOX_DELIVERIES_TOTAL = Counter(
    "acp_outbox_deliveries_total", "Outbox delivery attempts by event type and outcome", labelnames=("event_type", "outcome")
)
OUTBOX_DELIVERY_DURATION_SECONDS = Histogram(
    "acp_outbox_delivery_duration_seconds", "Outbox delivery latency in seconds", labelnames=("event_type", "outcome")
)
JOB_QUEUE_READY_AGE_SECONDS = Gauge(
    "acp_job_oldest_ready_age_seconds", "Age in seconds of the oldest ready-to-run job by job type", labelnames=("job_type",)
)
JOB_RUNNING_AGE_SECONDS = Gauge(
    "acp_job_oldest_running_age_seconds", "Age in seconds of the oldest claimed or running job by job type", labelnames=("job_type",)
)
JOB_QUEUE_DEPTH = Gauge("acp_job_queue_depth", "Current job counts by job type and state", labelnames=("job_type", "job_state"))
RATE_LIMIT_REJECTIONS_TOTAL = Counter(
    "acp_rate_limit_rejections_total", "Rejected requests due to abuse protection or quota limits", labelnames=("scope", "path")
)
RATE_LIMIT_BACKEND_ERRORS_TOTAL = Counter(
    "acp_rate_limit_backend_errors_total",
    "Rate limit backend errors by backend, operation, and error type",
    labelnames=("backend", "operation", "error_type"),
)
RATE_LIMIT_BACKEND_DECISIONS_TOTAL = Counter(
    "acp_rate_limit_backend_decisions_total",
    "Rate limit backend failure policy decisions by backend and scope",
    labelnames=("backend", "decision", "scope"),
)
RATE_LIMIT_BACKEND_HEALTH = Gauge(
    "acp_rate_limit_backend_healthy", "Rate limit backend health status by backend (1=healthy, 0=unhealthy)", labelnames=("backend",)
)
RATE_LIMIT_TENANT_EVENTS_TOTAL = Counter(
    "acp_rate_limit_tenant_events_total", "Tenant-level rate limit events by scope and decision", labelnames=("scope", "decision", "tenant")
)
RATE_LIMIT_PLAN_EVENTS_TOTAL = Counter(
    "acp_rate_limit_plan_events_total", "Tenant-plan rate limit events by scope and decision", labelnames=("scope", "decision", "plan")
)
SLO_EVENTS_TOTAL = Counter(
    "acp_slo_events_total", "SLO eligibility and outcome events by SLO and route group", labelnames=("slo", "route_group", "outcome")
)
SLO_TARGET_RATIO = Gauge("acp_slo_target_ratio", "Configured SLO target ratio by SLO", labelnames=("slo",))
SLO_LATENCY_THRESHOLD_SECONDS = Gauge("acp_slo_latency_threshold_seconds", "Configured API latency SLO threshold in seconds")


def _route_group(path: str) -> str:
    normalized = path.strip() or "/"
    if normalized in {"/healthz", "/readyz", "/metrics"}:
        return "system"
    if normalized.startswith("/v1/cycles"):
        return "cycles"
    if normalized.startswith("/v1/approvals"):
        return "approvals"
    first_segment = normalized.lstrip("/").split("/", 1)[0]
    return first_segment or "root"


def record_http_request(method: str, path: str, status_code: int, duration_seconds: float) -> None:
    labels = {"method": method, "path": path, "status_code": str(status_code)}
    HTTP_REQUESTS_TOTAL.labels(**labels).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(**labels).observe(duration_seconds)
    if path == "/metrics":
        return
    settings = get_settings()
    route_group = _route_group(path)
    SLO_EVENTS_TOTAL.labels(slo="api_availability", route_group=route_group, outcome="good" if status_code < 500 else "bad").inc()
    latency_good = status_code < 500 and duration_seconds <= settings.api_latency_slo_seconds
    SLO_EVENTS_TOTAL.labels(slo="api_latency", route_group=route_group, outcome="good" if latency_good else "bad").inc()


def record_auth_failure(reason: str) -> None:
    AUTH_FAILURES_TOTAL.labels(reason=reason.strip().lower().replace(" ", "_")[:100] or "unknown").inc()


def record_db_lock_conflict() -> None:
    DB_LOCK_CONFLICTS_TOTAL.inc()


def record_rate_limit_rejection(scope: str, path: str) -> None:
    RATE_LIMIT_REJECTIONS_TOTAL.labels(scope=scope, path=path).inc()


def record_rate_limit_backend_error(backend: str, operation: str, error_type: str) -> None:
    RATE_LIMIT_BACKEND_ERRORS_TOTAL.labels(backend=backend, operation=operation, error_type=error_type).inc()


def record_rate_limit_backend_decision(backend: str, decision: str, scope: str) -> None:
    RATE_LIMIT_BACKEND_DECISIONS_TOTAL.labels(backend=backend, decision=decision, scope=scope).inc()


def set_rate_limit_backend_health(backend: str, healthy: bool) -> None:
    RATE_LIMIT_BACKEND_HEALTH.labels(backend=backend).set(1 if healthy else 0)


def record_rate_limit_tenant_event(scope: str, decision: str, tenant: str | None) -> None:
    if tenant is not None:
        RATE_LIMIT_TENANT_EVENTS_TOTAL.labels(scope=scope, decision=decision, tenant=tenant).inc()


def record_rate_limit_plan_event(scope: str, decision: str, plan: str | None) -> None:
    if plan is not None:
        RATE_LIMIT_PLAN_EVENTS_TOTAL.labels(scope=scope, decision=decision, plan=plan).inc()


def record_job_execution(job_type: str, outcome: str, duration_seconds: float) -> None:
    JOB_EXECUTIONS_TOTAL.labels(job_type=job_type, outcome=outcome).inc()
    JOB_EXECUTION_DURATION_SECONDS.labels(job_type=job_type, outcome=outcome).observe(duration_seconds)


def record_outbox_delivery(event_type: str, outcome: str, duration_seconds: float) -> None:
    OUTBOX_DELIVERIES_TOTAL.labels(event_type=event_type, outcome=outcome).inc()
    OUTBOX_DELIVERY_DURATION_SECONDS.labels(event_type=event_type, outcome=outcome).observe(duration_seconds)
