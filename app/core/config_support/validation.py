import json
from pathlib import Path
from urllib.parse import urlparse

from .constants import SUPPORTED_BEARER_JWT_ALGORITHMS, SUPPORTED_OIDC_JWT_ALGORITHMS
from .model import Settings


def is_production_like(environment: str) -> bool:
    return environment.lower() in {"production", "prod"}


def looks_like_insecure_database_url(database_url: str) -> bool:
    parsed = urlparse(database_url)
    netloc = parsed.netloc
    if "@" in netloc and netloc.split("@", 1)[0] in {"postgres:postgres", "postgres"}:
        return True
    return "postgres:postgres@" in database_url


def selected_llm_free_request_limit(settings: Settings) -> int | None:
    if settings.llm_provider == "disabled":
        return None
    mapping = {
        "openai": settings.llm_free_daily_requests_openai,
        "gemini": settings.llm_free_daily_requests_gemini,
        "grok": settings.llm_free_daily_requests_grok,
        "claude": settings.llm_free_daily_requests_claude,
        "cloudflare_workers_ai": settings.llm_free_daily_requests_cloudflare_workers_ai,
    }
    return mapping[settings.llm_provider]


def resolve_llm_usage_redis_url(settings: Settings) -> str | None:
    return settings.llm_usage_redis_url or settings.abuse_redis_url


def resolve_llm_usage_counter_backend(settings: Settings) -> str:
    if settings.llm_usage_counter_backend == "in_memory":
        return "in_memory"
    if settings.llm_usage_counter_backend == "redis":
        return "redis"
    return "redis" if resolve_llm_usage_redis_url(settings) else "in_memory"


def parse_auth_algorithm_values(raw: str) -> list[str]:
    return [value.strip() for value in raw.split(",") if value.strip()]


def validate_auth_algorithm_settings(settings: Settings, errors: list[str]) -> None:
    algorithms = parse_auth_algorithm_values(settings.auth_jwt_allowed_algorithms)
    if not algorithms:
        errors.append("AUTH_JWT_ALLOWED_ALGORITHMS must include at least one algorithm")
        return
    if settings.auth_mode == "bearer_jwt":
        unsupported = [value for value in algorithms if value not in SUPPORTED_BEARER_JWT_ALGORITHMS]
        if unsupported:
            errors.append("AUTH_JWT_ALLOWED_ALGORITHMS contains unsupported bearer_jwt algorithms: " + ", ".join(unsupported))
    elif settings.auth_mode == "oidc_jwks":
        unsupported = [value for value in algorithms if value not in SUPPORTED_OIDC_JWT_ALGORITHMS]
        if unsupported:
            errors.append("AUTH_JWT_ALLOWED_ALGORITHMS contains unsupported oidc_jwks algorithms: " + ", ".join(unsupported))


def _validate_json_object(raw: str, *, invalid_json: str, invalid_shape: str, validator):
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        return [f"{invalid_json}: {exc.msg}"]
    return [] if validator(payload) else [invalid_shape]


def validate_runtime_settings(settings: Settings) -> list[str]:
    errors: list[str] = []
    if is_production_like(settings.environment):
        if settings.auth_mode == "header":
            errors.append("AUTH_MODE=header is not allowed in production")
        if settings.auth_header_fallback_enabled:
            errors.append("AUTH_HEADER_FALLBACK_ENABLED=true is not allowed in production")
        if settings.management_endpoints_require_api_key and not (settings.management_api_key or settings.management_api_keys_json):
            errors.append("MANAGEMENT_API_KEY or MANAGEMENT_API_KEYS_JSON is required when management endpoints require an API key")
        if not settings.management_endpoints_require_api_key:
            errors.append("MANAGEMENT_ENDPOINTS_REQUIRE_API_KEY=true is required in production")
        if looks_like_insecure_database_url(settings.database_url):
            errors.append("DATABASE_URL uses an insecure default credential set")
        if settings.notification_webhook_url and not settings.notification_webhook_signing_secret:
            errors.append("NOTIFICATION_WEBHOOK_SIGNING_SECRET is required in production when NOTIFICATION_WEBHOOK_URL is configured")
    elif settings.management_endpoints_require_api_key and not (settings.management_api_key or settings.management_api_keys_json):
        errors.append("MANAGEMENT_API_KEY or MANAGEMENT_API_KEYS_JSON is required when management endpoints require an API key")

    if settings.management_api_keys_json:
        errors.extend(_validate_json_object(
            settings.management_api_keys_json,
            invalid_json="MANAGEMENT_API_KEYS_JSON is not valid JSON",
            invalid_shape="MANAGEMENT_API_KEYS_JSON must be a JSON object of API key to role (viewer|operator|admin)",
            validator=lambda payload: isinstance(payload, dict) and all(
                isinstance(key, str) and key and isinstance(role, str) and role in {"viewer", "operator", "admin"}
                for key, role in payload.items()
            ),
        ))

    if settings.backup_drill_target_database_urls_json:
        errors.extend(_validate_json_object(
            settings.backup_drill_target_database_urls_json,
            invalid_json="BACKUP_DRILL_TARGET_DATABASE_URLS_JSON is not valid JSON",
            invalid_shape="BACKUP_DRILL_TARGET_DATABASE_URLS_JSON must be a JSON object of non-default target name to database URL",
            validator=lambda payload: isinstance(payload, dict) and all(
                isinstance(name, str) and name.strip() and name.strip().lower() != "default" and isinstance(url, str) and url.strip()
                for name, url in payload.items()
            ),
        ))

    if settings.auth_mode == "bearer_jwt" and not settings.auth_jwt_secret:
        errors.append("AUTH_JWT_SECRET is required when AUTH_MODE=bearer_jwt")

    if settings.abuse_tenant_plan_assignments_json:
        errors.extend(_validate_json_object(
            settings.abuse_tenant_plan_assignments_json,
            invalid_json="ABUSE_TENANT_PLAN_ASSIGNMENTS_JSON is not valid JSON",
            invalid_shape="ABUSE_TENANT_PLAN_ASSIGNMENTS_JSON must be a JSON object of string to string",
            validator=lambda payload: isinstance(payload, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in payload.items()),
        ))

    if settings.abuse_tenant_plan_limits_json:
        errors.extend(_validate_json_object(
            settings.abuse_tenant_plan_limits_json,
            invalid_json="ABUSE_TENANT_PLAN_LIMITS_JSON is not valid JSON",
            invalid_shape="ABUSE_TENANT_PLAN_LIMITS_JSON must map plan names to scope/limit objects",
            validator=lambda payload: isinstance(payload, dict) and all(
                isinstance(plan_name, str)
                and isinstance(overrides, dict)
                and all(isinstance(scope_name, str) and isinstance(limit, int) and limit >= 1 for scope_name, limit in overrides.items())
                for plan_name, overrides in payload.items()
            ),
        ))

    if settings.abuse_rate_limit_backend == "redis" and not settings.abuse_redis_url:
        errors.append("ABUSE_REDIS_URL is required when ABUSE_RATE_LIMIT_BACKEND=redis")

    if settings.secrets_dir and not Path(settings.secrets_dir).exists():
        errors.append("SECRETS_DIR path does not exist")
    if settings.secrets_dir and not Path(settings.secrets_dir).is_dir():
        errors.append("SECRETS_DIR path is not a directory")

    if settings.llm_usage_counter_backend == "redis" and not resolve_llm_usage_redis_url(settings):
        errors.append("LLM_USAGE_REDIS_URL or ABUSE_REDIS_URL is required when LLM_USAGE_COUNTER_BACKEND=redis")

    if settings.remote_workspace_github_enabled:
        required = {
            "REMOTE_WORKSPACE_GITHUB_REPOSITORY": settings.remote_workspace_github_repository,
            "REMOTE_WORKSPACE_GITHUB_WORKFLOW": settings.remote_workspace_github_workflow,
            "REMOTE_WORKSPACE_GITHUB_TOKEN": settings.remote_workspace_github_token,
            "REMOTE_WORKSPACE_CALLBACK_TOKEN": settings.remote_workspace_callback_token,
        }
        for name, value in required.items():
            if not value:
                errors.append(f"{name} is required when REMOTE_WORKSPACE_GITHUB_ENABLED=true")

    if settings.remote_workspace_persistent_enabled and not settings.remote_workspace_enabled:
        errors.append("REMOTE_WORKSPACE_ENABLED must be true when REMOTE_WORKSPACE_PERSISTENT_ENABLED=true")

    provider_requirements = {
        "openai": (settings.openai_api_key, "OPENAI_API_KEY is required when LLM_PROVIDER=openai"),
        "gemini": (settings.gemini_api_key, "GEMINI_API_KEY is required when LLM_PROVIDER=gemini"),
        "grok": (settings.grok_api_key, "GROK_API_KEY is required when LLM_PROVIDER=grok"),
        "claude": (settings.claude_api_key, "CLAUDE_API_KEY is required when LLM_PROVIDER=claude"),
        "cloudflare_workers_ai": (settings.cloudflare_ai_api_token, "CLOUDFLARE_AI_API_TOKEN is required when LLM_PROVIDER=cloudflare_workers_ai"),
    }
    missing_provider_requirement = provider_requirements.get(settings.llm_provider)
    if missing_provider_requirement and not missing_provider_requirement[0]:
        errors.append(missing_provider_requirement[1])

    if settings.llm_provider == "cloudflare_workers_ai" and not (settings.cloudflare_account_id or settings.cloudflare_ai_base_url):
        errors.append("CLOUDFLARE_ACCOUNT_ID or CLOUDFLARE_AI_BASE_URL is required when LLM_PROVIDER=cloudflare_workers_ai")

    if settings.llm_usage_mode == "free_only":
        free_limit = selected_llm_free_request_limit(settings)
        if settings.llm_provider != "disabled" and (free_limit is None or free_limit <= 0):
            errors.append(f"LLM_PROVIDER={settings.llm_provider} is blocked in LLM_USAGE_MODE=free_only; set LLM_USAGE_MODE=paid to allow billed usage")
        if settings.llm_provider != "disabled" and is_production_like(settings.environment):
            backend = resolve_llm_usage_counter_backend(settings)
            if backend != "redis":
                errors.append("LLM_USAGE_COUNTER_BACKEND=redis (or auto with LLM_USAGE_REDIS_URL/ABUSE_REDIS_URL) is required in production when LLM_USAGE_MODE=free_only")
            elif not resolve_llm_usage_redis_url(settings):
                errors.append("LLM_USAGE_REDIS_URL or ABUSE_REDIS_URL is required in production when LLM_USAGE_MODE=free_only")

    validate_auth_algorithm_settings(settings, errors)

    if settings.auth_mode == "oidc_jwks" and not (settings.auth_jwks_url or settings.auth_oidc_discovery_url or settings.auth_jwt_issuer):
        errors.append("OIDC auth requires AUTH_JWKS_URL, AUTH_OIDC_DISCOVERY_URL, or AUTH_JWT_ISSUER")
    if is_production_like(settings.environment) and settings.abuse_protection_enabled and settings.abuse_rate_limit_backend != "redis":
        errors.append("ABUSE_RATE_LIMIT_BACKEND=redis is required in production when abuse protection is enabled")
    if settings.notification_webhook_signing_secret and len(settings.notification_webhook_signing_secret.encode("utf-8")) < 16:
        errors.append("NOTIFICATION_WEBHOOK_SIGNING_SECRET must be at least 16 bytes")
    return errors
