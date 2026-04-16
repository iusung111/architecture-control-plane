from __future__ import annotations

from app.core.telemetry import (
    record_rate_limit_backend_error,
    set_rate_limit_backend_health,
)
from app.db.session import get_session_factory
from app.repositories.management_config import ManagementConfigRepository

from . import common

@common.lru_cache(maxsize=32)
def _parse_tenant_plan_assignments(raw: str) -> dict[str, str]:
    return _parse_json_mapping(raw, value_type=str)


@common.lru_cache(maxsize=32)
def _parse_tenant_plan_limits(raw: str) -> dict[str, dict[str, int]]:
    if not raw.strip():
        return {}
    data = common.json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("ABUSE_TENANT_PLAN_LIMITS_JSON must be a JSON object")
    parsed: dict[str, dict[str, int]] = {}
    for plan_name, value in data.items():
        if not isinstance(plan_name, str) or not isinstance(value, dict):
            raise ValueError("tenant plan limit overrides must be objects")
        parsed_limits: dict[str, int] = {}
        for scope, limit in value.items():
            if not isinstance(scope, str) or not isinstance(limit, int) or limit < 1:
                raise ValueError("tenant plan limits must be positive integers")
            parsed_limits[scope] = limit
        parsed[plan_name] = parsed_limits
    return parsed


def _parse_json_mapping(raw: str, *, value_type: type[str]) -> dict[str, str]:
    if not raw.strip():
        return {}
    data = common.json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("tenant plan assignments must be a JSON object")
    parsed: dict[str, str] = {}
    for key, value in data.items():
        if not isinstance(key, str) or not isinstance(value, value_type):
            raise ValueError("tenant plan assignments must be string-to-string mappings")
        parsed[key] = value
    return parsed


def _load_abuse_override_payload(settings: common.Settings) -> dict:
    now = common.time.time()
    with common._abuse_override_cache_lock:
        if common._abuse_override_cache is not None and now < common._abuse_override_cache_expires_at:
            return dict(common._abuse_override_cache)
        try:
            session = get_session_factory()()
            try:
                payload = ManagementConfigRepository(session).get_payload("abuse")
            finally:
                session.close()
        except Exception:
            payload = {}
        common._abuse_override_cache = payload
        common._abuse_override_cache_expires_at = now + settings.management_runtime_cache_ttl_seconds
        return dict(payload)


def set_inprocess_abuse_override_payload(payload: dict, settings: common.Settings | None = None) -> None:
    resolved_settings = settings or common.get_settings()
    with common._abuse_override_cache_lock:
        common._abuse_override_cache = dict(payload)
        common._abuse_override_cache_expires_at = common.time.time() + resolved_settings.management_runtime_cache_ttl_seconds


def invalidate_abuse_override_cache() -> None:
    with common._abuse_override_cache_lock:
        common._abuse_override_cache = None
        common._abuse_override_cache_expires_at = 0.0


def _effective_abuse_policy(settings: common.Settings) -> dict:
    overrides = _load_abuse_override_payload(settings)
    return {
        "algorithm": overrides.get("rate_limit_algorithm", settings.abuse_rate_limit_algorithm),
        "burst_multiplier": float(overrides.get("rate_limit_burst_multiplier", settings.abuse_rate_limit_burst_multiplier)),
        "failure_mode_api": overrides.get("failure_mode_api", settings.abuse_rate_limit_backend_failure_mode_api or settings.abuse_rate_limit_backend_failure_mode),
        "failure_mode_management": overrides.get("failure_mode_management", settings.abuse_rate_limit_backend_failure_mode_management or settings.abuse_rate_limit_backend_failure_mode),
        "global_requests_per_minute": int(overrides.get("global_requests_per_minute", settings.abuse_global_requests_per_minute)),
        "management_requests_per_minute": int(overrides.get("management_requests_per_minute", settings.abuse_management_requests_per_minute)),
        "cycle_create_limit_per_minute": int(overrides.get("cycle_create_limit_per_minute", settings.abuse_cycle_create_limit_per_minute)),
        "cycle_retry_limit_per_minute": int(overrides.get("cycle_retry_limit_per_minute", settings.abuse_cycle_retry_limit_per_minute)),
        "cycle_replan_limit_per_minute": int(overrides.get("cycle_replan_limit_per_minute", settings.abuse_cycle_replan_limit_per_minute)),
        "approval_confirm_limit_per_minute": int(overrides.get("approval_confirm_limit_per_minute", settings.abuse_approval_confirm_limit_per_minute)),
        "tenant_plan_default": overrides.get("tenant_plan_default", settings.abuse_tenant_plan_default),
        "tenant_plan_assignments_json": overrides.get("tenant_plan_assignments_json", settings.abuse_tenant_plan_assignments_json),
        "tenant_plan_limits_json": overrides.get("tenant_plan_limits_json", settings.abuse_tenant_plan_limits_json),
        "metrics_include_tenant_labels": bool(overrides.get("metrics_include_tenant_labels", settings.abuse_metrics_include_tenant_labels)),
        "metrics_tenant_label_mode": overrides.get("metrics_tenant_label_mode", settings.abuse_metrics_tenant_label_mode),
    }


def _backend_config_key(settings: common.Settings) -> tuple[str, str | None, str, str, float]:
    policy = _effective_abuse_policy(settings)
    return (
        settings.abuse_rate_limit_backend,
        settings.abuse_redis_url,
        settings.abuse_redis_key_prefix,
        str(policy["algorithm"]),
        float(policy["burst_multiplier"]),
    )


def _resolve_failure_mode(scope: str, settings: common.Settings) -> str:
    return str(_effective_abuse_policy(settings)["failure_mode_management" if scope == "management_request" else "failure_mode_api"])


def _normalize_tenant_label(tenant_id: str | None, settings: common.Settings) -> str | None:
    policy = _effective_abuse_policy(settings)
    if not bool(policy["metrics_include_tenant_labels"]):
        return None
    raw = tenant_id or "__global__"
    if str(policy["metrics_tenant_label_mode"]) == "exact":
        return raw
    return common.hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def _resolve_tenant_plan(tenant_id: str | None, settings: common.Settings) -> str | None:
    if not tenant_id:
        return None
    assignments = _parse_tenant_plan_assignments(str(_effective_abuse_policy(settings)["tenant_plan_assignments_json"]))
    return assignments.get(tenant_id, str(_effective_abuse_policy(settings)["tenant_plan_default"]))


def _resolve_scope_limit(scope: str, default_limit: int, tenant_id: str | None, settings: common.Settings) -> common.ScopeLimitResolution:
    plan_name = _resolve_tenant_plan(tenant_id, settings)
    if plan_name is None:
        return common.ScopeLimitResolution(limit_per_minute=default_limit, plan_name=None)
    overrides = _parse_tenant_plan_limits(str(_effective_abuse_policy(settings)["tenant_plan_limits_json"]))
    return common.ScopeLimitResolution(limit_per_minute=overrides.get(plan_name, {}).get(scope, default_limit), plan_name=plan_name)


def _token_bucket_capacity(limit: int, settings: common.Settings) -> int:
    return max(int(common.math.ceil(limit * float(_effective_abuse_policy(settings)["burst_multiplier"]))), 1)


def _token_bucket_refill_rate(limit: int, window_seconds: int) -> float:
    return max(limit / max(window_seconds, 1), 1e-9)


def _refill_token_bucket(entry: common._TokenBucketEntry, now: float, capacity: int, refill_rate: float) -> None:
    if now > entry.last_refill_at:
        delta = now - entry.last_refill_at
        entry.tokens = min(float(capacity), entry.tokens + delta * refill_rate)
        entry.last_refill_at = now


def _token_bucket_retry_after_seconds(tokens: float, refill_rate: float) -> int:
    return max(int(common.math.ceil((1.0 - max(tokens, 0.0)) / refill_rate)), 1)


def _update_backend_status(*, backend: str, settings: common.Settings, healthy: bool, error: Exception | None = None, record_error_metric: bool, operation: str) -> None:
    now = common.time.time()
    with common._backend_status_lock:
        last_error = common._backend_status.last_error
        last_error_at = common._backend_status.last_error_at
        if error is not None:
            last_error = f"{type(error).__name__}: {error}"
            last_error_at = now
        last_success_at = common._backend_status.last_success_at
        if healthy:
            last_success_at = now
            if common._backend_status.healthy and error is None:
                last_error = common._backend_status.last_error
                last_error_at = common._backend_status.last_error_at
        common._backend_status = common.RateLimitBackendStatus(
            backend=backend,
            algorithm=str(_effective_abuse_policy(settings)["algorithm"]),
            api_fail_mode=_resolve_failure_mode("global_request", settings),
            management_fail_mode=_resolve_failure_mode("management_request", settings),
            healthy=healthy,
            last_error=(None if healthy and error is None else last_error),
            last_error_at=(None if healthy and error is None else last_error_at),
            last_success_at=last_success_at,
        )
    set_rate_limit_backend_health(backend, healthy)
    if error is not None and record_error_metric:
        record_rate_limit_backend_error(backend, operation, type(error).__name__)
