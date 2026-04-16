from __future__ import annotations

from app.core.telemetry import record_rate_limit_backend_decision, record_rate_limit_plan_event, record_rate_limit_rejection, record_rate_limit_tenant_event, set_rate_limit_backend_health

from . import common
from .backends import InMemoryRateLimitBackend, RedisRateLimitBackend
from .policy import _backend_config_key, _effective_abuse_policy, _normalize_tenant_label, _resolve_failure_mode, _resolve_scope_limit, _resolve_tenant_plan, _update_backend_status, invalidate_abuse_override_cache


def initialize_rate_limit_backend(settings: common.Settings | None = None) -> None:
    resolved_settings = settings or common.get_settings()
    backend = _get_rate_limit_backend(resolved_settings)
    try:
        backend.initialize()
    except Exception as exc:
        _update_backend_status(backend=resolved_settings.abuse_rate_limit_backend, settings=resolved_settings, healthy=False, error=exc, record_error_metric=True, operation="initialize")
        startup_fail_mode = _resolve_failure_mode("global_request", resolved_settings)
        decision = "allow_on_backend_failure" if startup_fail_mode == "open" else "reject_on_backend_failure"
        record_rate_limit_backend_decision(resolved_settings.abuse_rate_limit_backend, decision, "startup")
        if startup_fail_mode == "closed":
            raise
        return
    _update_backend_status(backend=resolved_settings.abuse_rate_limit_backend, settings=resolved_settings, healthy=True, record_error_metric=False, operation="initialize")


def get_rate_limit_backend_status() -> common.RateLimitBackendStatus:
    with common._backend_status_lock:
        status = common._backend_status
        return common.RateLimitBackendStatus(
            backend=status.backend,
            algorithm=status.algorithm,
            api_fail_mode=status.api_fail_mode,
            management_fail_mode=status.management_fail_mode,
            healthy=status.healthy,
            last_error=status.last_error,
            last_error_at=status.last_error_at,
            last_success_at=status.last_success_at,
        )


def reset_rate_limits() -> None:
    with common._rate_limit_backend_lock:
        if common._rate_limit_backend is not None:
            common._rate_limit_backend.reset()
        common._rate_limit_backend = None
        common._rate_limit_backend_config_key = None
    with common._backend_status_lock:
        common._backend_status = common.RateLimitBackendStatus(backend="in_memory", algorithm="fixed_window", api_fail_mode="open", management_fail_mode="closed", healthy=True)
    invalidate_abuse_override_cache()
    set_rate_limit_backend_health("in_memory", True)
    set_rate_limit_backend_health("redis", True)


def _build_rate_limit_backend(settings: common.Settings) -> common.RateLimitBackend:
    return RedisRateLimitBackend(settings) if settings.abuse_rate_limit_backend == "redis" else InMemoryRateLimitBackend(settings)


def _get_rate_limit_backend(settings: common.Settings) -> common.RateLimitBackend:
    config_key = _backend_config_key(settings)
    with common._rate_limit_backend_lock:
        if common._rate_limit_backend is None or common._rate_limit_backend_config_key != config_key:
            if common._rate_limit_backend is not None:
                common._rate_limit_backend.reset()
            common._rate_limit_backend = _build_rate_limit_backend(settings)
            common._rate_limit_backend_config_key = config_key
        return common._rate_limit_backend


def _check_rate_limit(*, scope: str, identifier: str, limit_per_minute: int, window_seconds: int, settings: common.Settings, tenant_label: str | None = None, plan_name: str | None = None) -> common.RateLimitResult:
    backend = _get_rate_limit_backend(settings)
    try:
        result = backend.check(scope=scope, identifier=identifier, limit=limit_per_minute, window_seconds=window_seconds)
    except Exception as exc:
        _update_backend_status(backend=settings.abuse_rate_limit_backend, settings=settings, healthy=False, error=exc, record_error_metric=True, operation="check")
        fail_mode = _resolve_failure_mode(scope, settings)
        if fail_mode == "open":
            record_rate_limit_backend_decision(settings.abuse_rate_limit_backend, "allow_on_backend_failure", scope)
            record_rate_limit_tenant_event(scope, "allow_on_backend_failure", tenant_label)
            record_rate_limit_plan_event(scope, "allow_on_backend_failure", plan_name)
            return common.RateLimitResult(allowed=True, retry_after_seconds=0, remaining=max(limit_per_minute - 1, 0))
        record_rate_limit_backend_decision(settings.abuse_rate_limit_backend, "reject_on_backend_failure", scope)
        record_rate_limit_tenant_event(scope, "reject_on_backend_failure", tenant_label)
        record_rate_limit_plan_event(scope, "reject_on_backend_failure", plan_name)
        raise common.RateLimitBackendUnavailable(scope=scope, retry_after_seconds=settings.abuse_rate_limit_backend_failure_retry_after_seconds)
    _update_backend_status(backend=settings.abuse_rate_limit_backend, settings=settings, healthy=True, record_error_metric=False, operation="check")
    return result


def _enforce(scope: str, identifier: str, limit_per_minute: int, path: str | None = None, tenant_id: str | None = None, plan_name: str | None = None) -> None:
    settings = common.get_settings()
    if not settings.abuse_protection_enabled or limit_per_minute <= 0:
        return
    tenant_label = _normalize_tenant_label(tenant_id, settings)
    if plan_name is None and tenant_id is not None:
        plan_name = _resolve_tenant_plan(tenant_id, settings)
    result = _check_rate_limit(scope=scope, identifier=identifier, limit_per_minute=limit_per_minute, window_seconds=common._WINDOW_SECONDS, settings=settings, tenant_label=tenant_label, plan_name=plan_name)
    if result.allowed:
        return
    record_rate_limit_rejection(scope, path or "unknown")
    record_rate_limit_tenant_event(scope, "rejected", tenant_label)
    record_rate_limit_plan_event(scope, "rejected", plan_name)
    raise common.RateLimitExceeded(scope=scope, retry_after_seconds=result.retry_after_seconds)


def _client_identifier(request: common.Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        first = forwarded_for.split(",", 1)[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"


def enforce_global_request_limit(request: common.Request) -> None:
    settings = common.get_settings()
    if request.url.path == "/healthz":
        return
    tenant_id = request.headers.get("x-tenant-id")
    resolution = _resolve_scope_limit("global_request", int(_effective_abuse_policy(settings)["global_requests_per_minute"]), tenant_id, settings)
    _enforce("global_request", _client_identifier(request), resolution.limit_per_minute, request.url.path, tenant_id, resolution.plan_name)


def enforce_management_request_limit(request: common.Request, presented_key: str | None) -> None:
    settings = common.get_settings()
    _enforce("management_request", presented_key or _client_identifier(request), int(_effective_abuse_policy(settings)["management_requests_per_minute"]), request.url.path, None, None)


def actor_identifier(*, user_id: str, tenant_id: str | None, role: str) -> str:
    return f"{tenant_id or '__global__'}:{role}:{user_id}"


def action_limit_profile(scope: str, *, user_id: str, tenant_id: str | None, role: str) -> common.ActionRateLimitProfile:
    settings = common.get_settings()
    default_limit = int(_effective_abuse_policy(settings)[f"{scope}_limit_per_minute"])
    resolution = _resolve_scope_limit(scope, default_limit, tenant_id, settings)
    return common.ActionRateLimitProfile(scope=scope, limit_per_minute=resolution.limit_per_minute, identifier=actor_identifier(user_id=user_id, tenant_id=tenant_id, role=role), tenant_id=tenant_id, plan_name=resolution.plan_name)


def enforce_action_limit(request: common.Request, profile: common.ActionRateLimitProfile) -> None:
    _enforce(profile.scope, profile.identifier, profile.limit_per_minute, request.url.path, profile.tenant_id, profile.plan_name)
