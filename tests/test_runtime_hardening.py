from __future__ import annotations

import socket
import urllib.request
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings, validate_runtime_settings
from app.core.telemetry import start_metrics_http_server
from app.db.session import dispose_db_resources, get_engine
from app.main import app


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
    dispose_db_resources()



def test_validate_runtime_settings_rejects_insecure_production_defaults() -> None:
    settings = Settings(
        environment="production",
        auth_mode="header",
        auth_header_fallback_enabled=True,
        database_url="postgresql+psycopg://postgres:postgres@localhost:5432/control_plane",
    )

    errors = validate_runtime_settings(settings)

    assert "AUTH_MODE=header is not allowed in production" in errors
    assert "AUTH_HEADER_FALLBACK_ENABLED=true is not allowed in production" in errors
    assert "MANAGEMENT_ENDPOINTS_REQUIRE_API_KEY=true is required in production" in errors
    assert "DATABASE_URL uses an insecure default credential set" in errors



def test_validate_runtime_settings_requires_redis_backend_in_production() -> None:
    settings = Settings(
        environment="production",
        auth_mode="oidc_jwks",
        auth_header_fallback_enabled=False,
        auth_jwks_url="https://issuer.example/.well-known/jwks.json",
        management_endpoints_require_api_key=True,
        management_api_key="ops-secret",
        database_url="postgresql+psycopg://service:secret@db.example.test:5432/control_plane",
        abuse_rate_limit_backend="in_memory",
    )

    errors = validate_runtime_settings(settings)

    assert "ABUSE_RATE_LIMIT_BACKEND=redis is required in production when abuse protection is enabled" in errors



def test_application_startup_succeeds_on_valid_production_configuration(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("AUTH_MODE", "oidc_jwks")
    monkeypatch.setenv("AUTH_JWKS_URL", "https://issuer.example/.well-known/jwks.json")
    monkeypatch.setenv("AUTH_JWT_ALLOWED_ALGORITHMS", "RS256")
    monkeypatch.setenv("AUTH_HEADER_FALLBACK_ENABLED", "false")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://service:secret@db.example.test:5432/control_plane")
    monkeypatch.setenv("MANAGEMENT_ENDPOINTS_REQUIRE_API_KEY", "true")
    monkeypatch.setenv("MANAGEMENT_API_KEY", "ops-secret")
    monkeypatch.setenv("ABUSE_RATE_LIMIT_BACKEND", "redis")
    monkeypatch.setenv("ABUSE_REDIS_URL", "redis://redis.example.test:6379/0")
    monkeypatch.setenv("NOTIFICATION_WEBHOOK_URL", "https://hooks.example.test/control-plane")
    monkeypatch.setenv("NOTIFICATION_WEBHOOK_SIGNING_SECRET", "0123456789abcdef")
    get_settings.cache_clear()

    with TestClient(app) as runtime_client:
        runbooks = runtime_client.get("/runbooks", headers={"X-Management-Key": "ops-secret"})

    assert runbooks.status_code == 200
    assert runbooks.json()["count"] >= 1


def test_application_startup_fails_fast_on_invalid_production_configuration(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("AUTH_MODE", "header")
    monkeypatch.setenv("AUTH_HEADER_FALLBACK_ENABLED", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/control_plane")
    monkeypatch.delenv("MANAGEMENT_API_KEY", raising=False)
    monkeypatch.setenv("MANAGEMENT_ENDPOINTS_REQUIRE_API_KEY", "false")
    get_settings.cache_clear()

    with pytest.raises(RuntimeError, match="invalid runtime configuration"):
        with TestClient(app):
            pass



def test_management_endpoints_require_api_key_when_enabled(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("MANAGEMENT_ENDPOINTS_REQUIRE_API_KEY", "true")
    monkeypatch.setenv("MANAGEMENT_API_KEY", "ops-secret")
    get_settings.cache_clear()

    unauthorized = client.get("/metrics")
    assert unauthorized.status_code == 401
    assert unauthorized.json()["error"]["message"] == "missing or invalid management API key"

    ready = client.get("/readyz", headers={"X-Management-Key": "ops-secret"})
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready"}

    runbooks = client.get("/runbooks", headers={"X-Management-Key": "ops-secret"})
    assert runbooks.status_code == 200
    assert runbooks.json()["count"] >= 1



def test_postgres_engine_includes_connect_timeout_and_pool_tuning(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@db.example.test:5432/control_plane")
    monkeypatch.setenv("DB_CONNECT_TIMEOUT_SECONDS", "7")
    monkeypatch.setenv("DB_POOL_SIZE", "15")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "9")
    monkeypatch.setenv("DB_POOL_TIMEOUT_SECONDS", "11")
    monkeypatch.setenv("DB_POOL_RECYCLE_SECONDS", "120")
    get_settings.cache_clear()

    engine = get_engine()

    assert engine.url.query["connect_timeout"] == "7"
    assert getattr(engine.pool, "_max_overflow") == 9
    assert getattr(engine.pool, "_timeout") == 11
    assert getattr(engine.pool, "_recycle") == 120



def test_worker_management_http_server_exposes_readiness_and_state(monkeypatch) -> None:
    monkeypatch.setenv("METRICS_ENABLED", "true")
    monkeypatch.setenv("WORKER_METRICS_ENABLED", "true")
    get_settings.cache_clear()

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    assert start_metrics_http_server(
        port,
        lambda: {"status": "idle", "ready": True, "shutting_down": False, "worker_id": "worker-a"},
    ) is True

    with urllib.request.urlopen(f"http://127.0.0.1:{port}/readyz", timeout=5) as response:
        assert response.status == 200
        assert response.read().decode("utf-8") == '{"status": "ready"}'

    with urllib.request.urlopen(f"http://127.0.0.1:{port}/state", timeout=5) as response:
        payload = response.read().decode("utf-8")
        assert '"worker_id": "worker-a"' in payload
        assert '"ready": true' in payload



def test_compose_separates_migration_from_api_startup() -> None:
    compose_text = Path("docker-compose.yml").read_text()
    dockerfile_text = Path("Dockerfile").read_text()

    assert "migrate:" in compose_text
    assert "command: alembic upgrade head" in compose_text
    assert "service_completed_successfully" in compose_text
    assert "alembic upgrade head && uvicorn" not in compose_text
    assert 'CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]' in dockerfile_text
    assert "redis:" in compose_text
    assert "ABUSE_RATE_LIMIT_BACKEND: redis" in compose_text
    assert "ABUSE_RATE_LIMIT_ALGORITHM: token_bucket" in compose_text
    assert "ABUSE_RATE_LIMIT_BURST_MULTIPLIER: 1.5" in compose_text
    assert "ABUSE_RATE_LIMIT_BACKEND_FAILURE_MODE: open" in compose_text
    assert "ABUSE_RATE_LIMIT_BACKEND_FAILURE_MODE_API: open" in compose_text
    assert "ABUSE_RATE_LIMIT_BACKEND_FAILURE_MODE_MANAGEMENT: closed" in compose_text
    assert "ABUSE_RATE_LIMIT_BACKEND_FAILURE_RETRY_AFTER_SECONDS: 5" in compose_text
    assert "ABUSE_REDIS_URL: redis://redis:6379/0" in compose_text


def test_validate_runtime_settings_requires_notification_signing_secret_in_production() -> None:
    settings = Settings(
        environment="production",
        auth_mode="oidc_jwks",
        auth_header_fallback_enabled=False,
        auth_jwks_url="https://issuer.example/.well-known/jwks.json",
        management_endpoints_require_api_key=True,
        management_api_key="ops-secret",
        database_url="postgresql+psycopg://service:secret@db.example.test:5432/control_plane",
        notification_webhook_url="https://hooks.example.test/control-plane",
        notification_webhook_signing_secret=None,
    )

    errors = validate_runtime_settings(settings)

    assert "NOTIFICATION_WEBHOOK_SIGNING_SECRET is required in production when NOTIFICATION_WEBHOOK_URL is configured" in errors


def test_compose_configures_signed_webhook_delivery_and_mail_sink() -> None:
    compose_text = Path("docker-compose.yml").read_text()

    assert "WEBHOOK_SINK_HMAC_SECRET" in compose_text
    assert "NOTIFICATION_WEBHOOK_SIGNING_SECRET" in compose_text


def test_dockerfile_uses_multistage_non_root_runtime() -> None:
    dockerfile_text = Path("Dockerfile").read_text()

    assert "FROM python:3.11-slim AS builder" in dockerfile_text
    assert "FROM python:3.11-slim AS runtime" in dockerfile_text
    assert "USER app" in dockerfile_text


def test_validate_runtime_settings_requires_selected_llm_provider_credentials() -> None:
    gemini_errors = validate_runtime_settings(
        Settings(llm_provider="gemini", gemini_api_key=None, llm_usage_mode="free_only")
    )
    grok_errors = validate_runtime_settings(
        Settings(llm_provider="grok", grok_api_key=None, llm_usage_mode="paid")
    )
    claude_errors = validate_runtime_settings(
        Settings(llm_provider="claude", claude_api_key=None, llm_usage_mode="paid")
    )
    cf_errors = validate_runtime_settings(
        Settings(
            llm_provider="cloudflare_workers_ai",
            cloudflare_ai_api_token=None,
            cloudflare_account_id=None,
            cloudflare_ai_base_url=None,
            llm_usage_mode="free_only",
        )
    )

    assert "GEMINI_API_KEY is required when LLM_PROVIDER=gemini" in gemini_errors
    assert "GROK_API_KEY is required when LLM_PROVIDER=grok" in grok_errors
    assert "CLAUDE_API_KEY is required when LLM_PROVIDER=claude" in claude_errors
    assert "CLOUDFLARE_AI_API_TOKEN is required when LLM_PROVIDER=cloudflare_workers_ai" in cf_errors
    assert (
        "CLOUDFLARE_ACCOUNT_ID or CLOUDFLARE_AI_BASE_URL is required when LLM_PROVIDER=cloudflare_workers_ai"
        in cf_errors
    )


def test_validate_runtime_settings_accepts_well_formed_tenant_plan_json() -> None:
    settings = Settings(
        abuse_tenant_plan_assignments_json='{"tenant-free": "free"}',
        abuse_tenant_plan_limits_json='{"free": {"cycle_create": 1, "global_request": 10}}',
    )

    errors = validate_runtime_settings(settings)

    assert not any("ABUSE_TENANT_PLAN_" in error for error in errors)


def test_validate_runtime_settings_accepts_management_api_keys_json() -> None:
    settings = Settings(
        environment="production",
        management_endpoints_require_api_key=True,
        management_api_keys_json='{"viewer-secret": "viewer", "admin-secret": "admin"}',
    )

    errors = validate_runtime_settings(settings)

    assert not any("MANAGEMENT_API_KEYS_JSON" in error for error in errors)
    assert not any("MANAGEMENT_API_KEY or MANAGEMENT_API_KEYS_JSON" in error for error in errors)


def test_validate_runtime_settings_rejects_non_hmac_bearer_algorithms() -> None:
    settings = Settings(auth_mode="bearer_jwt", auth_jwt_secret="top-secret", auth_jwt_allowed_algorithms="RS256")

    errors = validate_runtime_settings(settings)

    assert "AUTH_JWT_ALLOWED_ALGORITHMS contains unsupported bearer_jwt algorithms: RS256" in errors


def test_validate_runtime_settings_requires_shared_llm_quota_backend_in_production() -> None:
    settings = Settings(
        environment="production",
        auth_mode="oidc_jwks",
        auth_header_fallback_enabled=False,
        auth_jwks_url="https://issuer.example/.well-known/jwks.json",
        management_endpoints_require_api_key=True,
        management_api_key="ops-secret",
        database_url="postgresql+psycopg://service:secret@db.example.test:5432/control_plane",
        abuse_rate_limit_backend="redis",
        abuse_redis_url="redis://redis.example.test:6379/0",
        llm_provider="gemini",
        gemini_api_key="gem-key",
        llm_usage_mode="free_only",
        llm_usage_counter_backend="in_memory",
    )

    errors = validate_runtime_settings(settings)

    assert (
        "LLM_USAGE_COUNTER_BACKEND=redis (or auto with LLM_USAGE_REDIS_URL/ABUSE_REDIS_URL) is required in production when LLM_USAGE_MODE=free_only"
        in errors
    )


def test_validate_runtime_settings_accepts_shared_llm_quota_backend_via_abuse_redis_url() -> None:
    settings = Settings(
        environment="production",
        auth_mode="oidc_jwks",
        auth_header_fallback_enabled=False,
        auth_jwks_url="https://issuer.example/.well-known/jwks.json",
        management_endpoints_require_api_key=True,
        management_api_key="ops-secret",
        database_url="postgresql+psycopg://service:secret@db.example.test:5432/control_plane",
        abuse_rate_limit_backend="redis",
        abuse_redis_url="redis://redis.example.test:6379/0",
        llm_provider="gemini",
        gemini_api_key="gem-key",
        llm_usage_mode="free_only",
        llm_usage_counter_backend="auto",
    )

    errors = validate_runtime_settings(settings)

    assert not any("LLM_USAGE_COUNTER_BACKEND=" in error for error in errors)
    assert not any("LLM_USAGE_REDIS_URL or ABUSE_REDIS_URL is required in production" in error for error in errors)


def test_validate_runtime_settings_rejects_symmetric_oidc_algorithms() -> None:
    settings = Settings(
        auth_mode="oidc_jwks",
        auth_jwks_url="https://issuer.example/.well-known/jwks.json",
        auth_jwt_allowed_algorithms="HS256",
    )

    errors = validate_runtime_settings(settings)

    assert "AUTH_JWT_ALLOWED_ALGORITHMS contains unsupported oidc_jwks algorithms: HS256" in errors



def test_readme_documents_mode_specific_jwt_algorithms() -> None:
    readme_text = Path("README.md").read_text()

    assert "use `HS256`/`HS384`/`HS512` for `bearer_jwt`" in readme_text
    assert "use `RS256`/`RS384`/`RS512`/`ES256`/`ES384`/`ES512`/`EdDSA` for `oidc_jwks`" in readme_text
    assert "LLM_USAGE_COUNTER_BACKEND=auto|redis|in_memory" in readme_text
    assert "LLM_USAGE_REDIS_URL" in readme_text



def test_env_example_defaults_to_bearer_safe_jwt_algorithm_example() -> None:
    env_text = Path(".env.example").read_text()

    assert "# AUTH_MODE=bearer_jwt -> use HS256,HS384,HS512" in env_text
    assert "# AUTH_MODE=oidc_jwks -> use RS256,RS384,RS512,ES256,ES384,ES512,EdDSA" in env_text
    assert "AUTH_JWT_ALLOWED_ALGORITHMS=HS256" in env_text
    assert "LLM_USAGE_COUNTER_BACKEND=auto" in env_text
    assert "LLM_USAGE_REDIS_URL=" in env_text


def test_get_settings_supports_file_backed_secret_env(monkeypatch, tmp_path: Path) -> None:
    secret_file = tmp_path / "database_url"
    secret_file.write_text("postgresql+psycopg://svc:secret@db.example.test:5432/control_plane\n", encoding="utf-8")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://ignored:ignored@localhost:5432/ignored")
    monkeypatch.setenv("DATABASE_URL_FILE", str(secret_file))
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.database_url == "postgresql+psycopg://svc:secret@db.example.test:5432/control_plane"


def test_get_settings_supports_shared_secrets_dir(monkeypatch, tmp_path: Path) -> None:
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    (secrets_dir / "AUTH_JWT_SECRET").write_text("file-secret\n", encoding="utf-8")
    monkeypatch.setenv("SECRETS_DIR", str(secrets_dir))
    monkeypatch.setenv("AUTH_JWT_SECRET", "env-secret")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.auth_jwt_secret == "file-secret"


def test_get_settings_prefers_explicit_secret_file_over_shared_directory(monkeypatch, tmp_path: Path) -> None:
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    (secrets_dir / "AUTH_JWT_SECRET").write_text("dir-secret\n", encoding="utf-8")
    explicit = tmp_path / "auth_secret.txt"
    explicit.write_text("explicit-secret\n", encoding="utf-8")
    monkeypatch.setenv("SECRETS_DIR", str(secrets_dir))
    monkeypatch.setenv("AUTH_JWT_SECRET_FILE", str(explicit))
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.auth_jwt_secret == "explicit-secret"


def test_get_settings_rejects_missing_secret_file(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTH_JWT_SECRET_FILE", str(tmp_path / "missing-secret"))
    get_settings.cache_clear()

    with pytest.raises(RuntimeError, match="AUTH_JWT_SECRET_FILE path does not exist"):
        get_settings()


def test_secret_management_docs_cover_file_backed_loading() -> None:
    readme = Path("README.md").read_text()
    env_example = Path(".env.example").read_text()
    secret_doc = Path("docs/SECRET_MANAGEMENT.md").read_text()

    assert "*_FILE" in readme
    assert "SECRETS_DIR" in readme
    assert "DATABASE_URL_FILE=/var/run/acp-secrets/DATABASE_URL" in env_example
    assert "Supported file-backed secrets" in secret_doc
