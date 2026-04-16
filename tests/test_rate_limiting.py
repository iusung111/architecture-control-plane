from __future__ import annotations

import types

from fastapi.testclient import TestClient

from app.core import rate_limit as rate_limit_module
from app.core.config import Settings, get_settings, validate_runtime_settings
from app.core.rate_limit import InMemoryRateLimitBackend, RedisRateLimitBackend, get_rate_limit_backend_status, reset_rate_limits
from app.core.telemetry import (
    RATE_LIMIT_BACKEND_DECISIONS_TOTAL,
    RATE_LIMIT_BACKEND_ERRORS_TOTAL,
    RATE_LIMIT_BACKEND_HEALTH,
    RATE_LIMIT_PLAN_EVENTS_TOTAL,
    RATE_LIMIT_REJECTIONS_TOTAL,
    RATE_LIMIT_TENANT_EVENTS_TOTAL,
)


class FakeNoScriptError(Exception):
    pass


class FakeRedis:
    shared_windows: dict[str, tuple[int, int]] = {}
    scripts_loaded = False

    @classmethod
    def from_url(cls, _url: str, **_kwargs):
        return cls()

    def ping(self) -> bool:
        return True

    def close(self) -> None:
        return None

    def script_load(self, _script: str) -> str:
        type(self).scripts_loaded = True
        return "sha1"

    def evalsha(self, _sha: str, _numkeys: int, key: str, limit: int, window_seconds: int):
        if not type(self).scripts_loaded:
            raise FakeNoScriptError()
        current, ttl = type(self).shared_windows.get(key, (0, window_seconds))
        if current == 0:
            type(self).shared_windows[key] = (1, window_seconds)
            return [1, max(int(limit) - 1, 0), window_seconds]
        if current >= int(limit):
            return [0, 0, ttl]
        current += 1
        type(self).shared_windows[key] = (current, ttl)
        return [1, max(int(limit) - current, 0), ttl]


class FakeFailingRedis(FakeRedis):
    fail_on_ping = False
    fail_on_eval = False

    def ping(self) -> bool:
        if type(self).fail_on_ping:
            raise RuntimeError("redis unavailable")
        return True

    def evalsha(self, _sha: str, _numkeys: int, key: str, limit: int, window_seconds: int):
        if type(self).fail_on_eval:
            raise RuntimeError("redis eval failed")
        return super().evalsha(_sha, _numkeys, key, limit, window_seconds)



def _auth_headers(user_id: str = "user-1", *, tenant_id: str = "tenant-a") -> dict[str, str]:
    return {
        "x-user-id": user_id,
        "x-user-role": "operator",
        "x-tenant-id": tenant_id,
    }



def test_global_rate_limit_returns_429_and_retry_after(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("ABUSE_GLOBAL_REQUESTS_PER_MINUTE", "2")
    get_settings.cache_clear()

    for _ in range(2):
        response = client.get("/v1/cycles/non-existent", headers=_auth_headers())
        assert response.status_code == 404

    limited = client.get("/v1/cycles/non-existent", headers=_auth_headers())

    assert limited.status_code == 429
    assert limited.headers["Retry-After"]
    body = limited.json()
    assert body["error"]["code"] == "too_many_requests"
    assert body["error"]["retryable"] is True



def test_create_cycle_rate_limit_is_scoped_per_actor(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("ABUSE_GLOBAL_REQUESTS_PER_MINUTE", "100")
    monkeypatch.setenv("ABUSE_CYCLE_CREATE_LIMIT_PER_MINUTE", "1")
    get_settings.cache_clear()

    payload = {
        "project_id": "proj-rate-limit",
        "user_input": "draft control plan",
        "tenant_id": "tenant-a",
    }

    first = client.post(
        "/v1/cycles",
        json=payload,
        headers={**_auth_headers("user-a"), "Idempotency-Key": "create-rate-limit-1"},
    )
    assert first.status_code == 201

    limited = client.post(
        "/v1/cycles",
        json={**payload, "project_id": "proj-rate-limit-2"},
        headers={**_auth_headers("user-a"), "Idempotency-Key": "create-rate-limit-2"},
    )
    assert limited.status_code == 429

    different_actor = client.post(
        "/v1/cycles",
        json={**payload, "project_id": "proj-rate-limit-3"},
        headers={**_auth_headers("user-b"), "Idempotency-Key": "create-rate-limit-3"},
    )
    assert different_actor.status_code == 201



def test_management_endpoint_rate_limit_is_enforced(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("MANAGEMENT_ENDPOINTS_REQUIRE_API_KEY", "true")
    monkeypatch.setenv("MANAGEMENT_API_KEY", "ops-secret")
    monkeypatch.setenv("ABUSE_GLOBAL_REQUESTS_PER_MINUTE", "100")
    monkeypatch.setenv("ABUSE_MANAGEMENT_REQUESTS_PER_MINUTE", "1")
    get_settings.cache_clear()

    first = client.get("/readyz", headers={"X-Management-Key": "ops-secret"})
    assert first.status_code == 200

    metrics = client.get("/metrics", headers={"X-Management-Key": "ops-secret"})
    assert metrics.status_code == 200

    first_runbooks = client.get("/runbooks", headers={"X-Management-Key": "ops-secret"})
    assert first_runbooks.status_code == 200

    limited = client.get("/runbooks", headers={"X-Management-Key": "ops-secret"})
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "too_many_requests"



def test_rate_limit_rejection_metric_is_emitted(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("ABUSE_GLOBAL_REQUESTS_PER_MINUTE", "2")
    get_settings.cache_clear()

    assert client.get("/v1/cycles/non-existent", headers=_auth_headers()).status_code == 404
    assert client.get("/v1/cycles/non-existent", headers=_auth_headers()).status_code == 404
    assert client.get("/v1/cycles/non-existent", headers=_auth_headers()).status_code == 429

    metric = RATE_LIMIT_REJECTIONS_TOTAL.labels(scope="global_request", path="/v1/cycles/non-existent")
    assert metric._value.get() >= 1





def test_rate_limit_backend_uses_split_failure_modes_for_api_and_management(client: TestClient, monkeypatch) -> None:
    FakeFailingRedis.shared_windows = {}
    FakeFailingRedis.scripts_loaded = True
    FakeFailingRedis.fail_on_ping = False
    FakeFailingRedis.fail_on_eval = True
    monkeypatch.setattr(rate_limit_module, "_import_redis_module", lambda: FakeFailingRedis)
    monkeypatch.setattr(
        RedisRateLimitBackend,
        "_redis_exceptions",
        staticmethod(lambda: types.SimpleNamespace(NoScriptError=FakeNoScriptError)),
    )
    monkeypatch.setenv("ABUSE_RATE_LIMIT_BACKEND", "redis")
    monkeypatch.setenv("ABUSE_REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("ABUSE_RATE_LIMIT_BACKEND_FAILURE_MODE_API", "open")
    monkeypatch.setenv("ABUSE_RATE_LIMIT_BACKEND_FAILURE_MODE_MANAGEMENT", "closed")
    monkeypatch.setenv("MANAGEMENT_ENDPOINTS_REQUIRE_API_KEY", "true")
    monkeypatch.setenv("MANAGEMENT_API_KEY", "ops-secret")
    get_settings.cache_clear()
    rate_limit_module.initialize_rate_limit_backend(get_settings())

    api_response = client.get("/v1/cycles/non-existent", headers=_auth_headers())
    management_response = client.get("/runbooks", headers={"X-Management-Key": "ops-secret"})

    assert api_response.status_code == 404
    assert management_response.status_code == 503
    status = get_rate_limit_backend_status()
    assert status.api_fail_mode == "open"
    assert status.management_fail_mode == "closed"


def test_rate_limit_tenant_metric_is_recorded_when_enabled(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("ABUSE_GLOBAL_REQUESTS_PER_MINUTE", "100")
    monkeypatch.setenv("ABUSE_CYCLE_CREATE_LIMIT_PER_MINUTE", "1")
    monkeypatch.setenv("ABUSE_METRICS_INCLUDE_TENANT_LABELS", "true")
    monkeypatch.setenv("ABUSE_METRICS_TENANT_LABEL_MODE", "hashed")
    get_settings.cache_clear()

    payload = {"project_id": "proj-tenant-metric", "user_input": "draft", "tenant_id": "tenant-metric"}
    headers = {**_auth_headers("user-a", tenant_id="tenant-metric"), "Idempotency-Key": "tenant-metric-1"}
    assert client.post("/v1/cycles", json=payload, headers=headers).status_code == 201
    limited = client.post(
        "/v1/cycles",
        json={**payload, "project_id": "proj-tenant-metric-2"},
        headers={**_auth_headers("user-a", tenant_id="tenant-metric"), "Idempotency-Key": "tenant-metric-2"},
    )
    assert limited.status_code == 429

    metric_tenant = rate_limit_module._normalize_tenant_label("tenant-metric", get_settings())
    assert metric_tenant is not None
    metric = RATE_LIMIT_TENANT_EVENTS_TOTAL.labels(scope="cycle_create", decision="rejected", tenant=metric_tenant)
    assert metric._value.get() >= 1


def test_redis_rate_limit_backend_shares_counters_across_backend_instances(monkeypatch) -> None:
    FakeRedis.shared_windows = {}
    FakeRedis.scripts_loaded = False
    monkeypatch.setattr(rate_limit_module, "_import_redis_module", lambda: FakeRedis)
    monkeypatch.setattr(
        RedisRateLimitBackend,
        "_redis_exceptions",
        staticmethod(lambda: types.SimpleNamespace(NoScriptError=FakeNoScriptError)),
    )

    settings = Settings(abuse_rate_limit_backend="redis", abuse_redis_url="redis://redis:6379/0")
    backend_a = RedisRateLimitBackend(settings)
    backend_b = RedisRateLimitBackend(settings)
    backend_a.initialize()
    backend_b.initialize()

    result_a = backend_a.check(scope="global_request", identifier="actor-a", limit=2, window_seconds=60)
    result_b = backend_b.check(scope="global_request", identifier="actor-a", limit=2, window_seconds=60)
    limited = backend_a.check(scope="global_request", identifier="actor-a", limit=2, window_seconds=60)

    assert result_a.allowed is True
    assert result_b.allowed is True
    assert limited.allowed is False



def test_rate_limit_backend_fail_open_allows_requests_when_redis_fails(client: TestClient, monkeypatch) -> None:
    FakeFailingRedis.shared_windows = {}
    FakeFailingRedis.scripts_loaded = True
    FakeFailingRedis.fail_on_ping = False
    FakeFailingRedis.fail_on_eval = True
    monkeypatch.setattr(rate_limit_module, "_import_redis_module", lambda: FakeFailingRedis)
    monkeypatch.setattr(
        RedisRateLimitBackend,
        "_redis_exceptions",
        staticmethod(lambda: types.SimpleNamespace(NoScriptError=FakeNoScriptError)),
    )
    monkeypatch.setenv("ABUSE_RATE_LIMIT_BACKEND", "redis")
    monkeypatch.setenv("ABUSE_REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("ABUSE_RATE_LIMIT_BACKEND_FAILURE_MODE", "open")
    get_settings.cache_clear()
    rate_limit_module.initialize_rate_limit_backend(get_settings())

    response = client.get("/v1/cycles/non-existent", headers=_auth_headers())

    assert response.status_code == 404
    decision_metric = RATE_LIMIT_BACKEND_DECISIONS_TOTAL.labels(
        backend="redis",
        decision="allow_on_backend_failure",
        scope="global_request",
    )
    assert decision_metric._value.get() >= 1
    error_metric = RATE_LIMIT_BACKEND_ERRORS_TOTAL.labels(
        backend="redis",
        operation="check",
        error_type="RuntimeError",
    )
    assert error_metric._value.get() >= 1
    assert RATE_LIMIT_BACKEND_HEALTH.labels(backend="redis")._value.get() == 0
    status = get_rate_limit_backend_status()
    assert status.backend == "redis"
    assert status.healthy is False
    assert "redis eval failed" in (status.last_error or "")



def test_rate_limit_backend_fail_closed_rejects_requests_when_redis_fails(client: TestClient, monkeypatch) -> None:
    FakeFailingRedis.shared_windows = {}
    FakeFailingRedis.scripts_loaded = True
    FakeFailingRedis.fail_on_ping = False
    FakeFailingRedis.fail_on_eval = True
    monkeypatch.setattr(rate_limit_module, "_import_redis_module", lambda: FakeFailingRedis)
    monkeypatch.setattr(
        RedisRateLimitBackend,
        "_redis_exceptions",
        staticmethod(lambda: types.SimpleNamespace(NoScriptError=FakeNoScriptError)),
    )
    monkeypatch.setenv("ABUSE_RATE_LIMIT_BACKEND", "redis")
    monkeypatch.setenv("ABUSE_REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("ABUSE_RATE_LIMIT_BACKEND_FAILURE_MODE", "closed")
    monkeypatch.setenv("ABUSE_RATE_LIMIT_BACKEND_FAILURE_RETRY_AFTER_SECONDS", "7")
    get_settings.cache_clear()
    rate_limit_module.initialize_rate_limit_backend(get_settings())

    response = client.get("/v1/cycles/non-existent", headers=_auth_headers())

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "7"
    assert response.json()["error"]["code"] == "rate_limit_backend_unavailable"
    decision_metric = RATE_LIMIT_BACKEND_DECISIONS_TOTAL.labels(
        backend="redis",
        decision="reject_on_backend_failure",
        scope="global_request",
    )
    assert decision_metric._value.get() >= 1



def test_initialize_rate_limit_backend_respects_fail_open_policy(monkeypatch) -> None:
    FakeFailingRedis.fail_on_ping = True
    FakeFailingRedis.fail_on_eval = False
    monkeypatch.setattr(rate_limit_module, "_import_redis_module", lambda: FakeFailingRedis)
    monkeypatch.setattr(
        RedisRateLimitBackend,
        "_redis_exceptions",
        staticmethod(lambda: types.SimpleNamespace(NoScriptError=FakeNoScriptError)),
    )
    settings = Settings(
        abuse_rate_limit_backend="redis",
        abuse_redis_url="redis://redis:6379/0",
        abuse_rate_limit_backend_failure_mode="open",
    )

    rate_limit_module.initialize_rate_limit_backend(settings)

    assert get_rate_limit_backend_status().healthy is False



def test_initialize_rate_limit_backend_respects_fail_closed_policy(monkeypatch) -> None:
    FakeFailingRedis.fail_on_ping = True
    FakeFailingRedis.fail_on_eval = False
    monkeypatch.setattr(rate_limit_module, "_import_redis_module", lambda: FakeFailingRedis)
    monkeypatch.setattr(rate_limit_module, "reset_rate_limits", rate_limit_module.reset_rate_limits)
    settings = Settings(
        abuse_rate_limit_backend="redis",
        abuse_redis_url="redis://redis:6379/0",
        abuse_rate_limit_backend_failure_mode="closed",
    )

    import pytest

    with pytest.raises(RuntimeError, match="redis unavailable"):
        rate_limit_module.initialize_rate_limit_backend(settings)



def test_validate_runtime_settings_requires_redis_url_when_backend_selected() -> None:
    errors = validate_runtime_settings(Settings(abuse_rate_limit_backend="redis", abuse_redis_url=None))

    assert "ABUSE_REDIS_URL is required when ABUSE_RATE_LIMIT_BACKEND=redis" in errors



def test_reset_rate_limits_releases_backend(monkeypatch) -> None:
    FakeRedis.shared_windows = {}
    FakeRedis.scripts_loaded = False
    monkeypatch.setattr(rate_limit_module, "_import_redis_module", lambda: FakeRedis)
    monkeypatch.setattr(
        RedisRateLimitBackend,
        "_redis_exceptions",
        staticmethod(lambda: types.SimpleNamespace(NoScriptError=FakeNoScriptError)),
    )
    monkeypatch.setenv("ABUSE_RATE_LIMIT_BACKEND", "redis")
    monkeypatch.setenv("ABUSE_REDIS_URL", "redis://redis:6379/0")
    get_settings.cache_clear()

    rate_limit_module.initialize_rate_limit_backend(get_settings())
    reset_rate_limits()

    assert rate_limit_module._rate_limit_backend is None
    assert get_rate_limit_backend_status().healthy is True


def test_in_memory_token_bucket_refills_over_time() -> None:
    settings = Settings(abuse_rate_limit_algorithm="token_bucket", abuse_rate_limit_burst_multiplier=1.0)
    backend = InMemoryRateLimitBackend(settings)
    current = [0.0]
    backend._time_fn = lambda: current[0]  # type: ignore[attr-defined]

    assert backend.check(scope="cycle_create", identifier="actor-a", limit=2, window_seconds=60).allowed is True
    assert backend.check(scope="cycle_create", identifier="actor-a", limit=2, window_seconds=60).allowed is True

    denied = backend.check(scope="cycle_create", identifier="actor-a", limit=2, window_seconds=60)
    assert denied.allowed is False
    assert denied.retry_after_seconds == 30

    current[0] = 30.0
    allowed_again = backend.check(scope="cycle_create", identifier="actor-a", limit=2, window_seconds=60)
    assert allowed_again.allowed is True


def test_tenant_plan_limit_override_is_applied_to_action_scope(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("ABUSE_GLOBAL_REQUESTS_PER_MINUTE", "100")
    monkeypatch.setenv("ABUSE_CYCLE_CREATE_LIMIT_PER_MINUTE", "5")
    monkeypatch.setenv("ABUSE_TENANT_PLAN_ASSIGNMENTS_JSON", '{"tenant-free": "free", "tenant-pro": "pro"}')
    monkeypatch.setenv(
        "ABUSE_TENANT_PLAN_LIMITS_JSON",
        '{"free": {"cycle_create": 1}, "pro": {"cycle_create": 3}}',
    )
    get_settings.cache_clear()

    free_headers = {**_auth_headers("user-free", tenant_id="tenant-free"), "Idempotency-Key": "plan-free-1"}
    assert client.post(
        "/v1/cycles",
        json={"project_id": "plan-free-1", "user_input": "draft", "tenant_id": "tenant-free"},
        headers=free_headers,
    ).status_code == 201
    limited = client.post(
        "/v1/cycles",
        json={"project_id": "plan-free-2", "user_input": "draft", "tenant_id": "tenant-free"},
        headers={**_auth_headers("user-free", tenant_id="tenant-free"), "Idempotency-Key": "plan-free-2"},
    )
    assert limited.status_code == 429

    assert client.post(
        "/v1/cycles",
        json={"project_id": "plan-pro-1", "user_input": "draft", "tenant_id": "tenant-pro"},
        headers={**_auth_headers("user-pro", tenant_id="tenant-pro"), "Idempotency-Key": "plan-pro-1"},
    ).status_code == 201
    assert client.post(
        "/v1/cycles",
        json={"project_id": "plan-pro-2", "user_input": "draft", "tenant_id": "tenant-pro"},
        headers={**_auth_headers("user-pro", tenant_id="tenant-pro"), "Idempotency-Key": "plan-pro-2"},
    ).status_code == 201

    metric = RATE_LIMIT_PLAN_EVENTS_TOTAL.labels(scope="cycle_create", decision="rejected", plan="free")
    assert metric._value.get() >= 1


def test_validate_runtime_settings_rejects_invalid_tenant_plan_json() -> None:
    errors = validate_runtime_settings(
        Settings(abuse_tenant_plan_assignments_json='["bad"]', abuse_tenant_plan_limits_json='{"free": {"cycle_create": 0}}')
    )

    assert any("ABUSE_TENANT_PLAN_ASSIGNMENTS_JSON" in error for error in errors)
    assert any("ABUSE_TENANT_PLAN_LIMITS_JSON" in error for error in errors)
