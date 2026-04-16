from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .constants import LLMProvider, LLMUsageMode


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "architecture-control-plane"
    environment: str = "development"
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/control_plane"
    db_pool_size: int = Field(default=10, ge=1)
    db_max_overflow: int = Field(default=20, ge=0)
    db_pool_timeout_seconds: float = Field(default=30.0, gt=0.0)
    db_pool_recycle_seconds: int = Field(default=1800, ge=0)
    db_connect_timeout_seconds: int = Field(default=5, ge=1)
    db_statement_timeout_ms: int = Field(default=30000, ge=1)
    db_idle_in_transaction_session_timeout_ms: int = Field(default=60000, ge=1)

    llm_provider: LLMProvider = "disabled"
    llm_usage_mode: LLMUsageMode = "free_only"
    llm_usage_counter_backend: str = "auto"
    llm_usage_redis_url: str | None = None
    llm_usage_redis_key_prefix: str = "acp:llm:usage"
    llm_free_daily_requests_openai: int = Field(default=0, ge=0)
    llm_free_daily_requests_gemini: int = Field(default=1000, ge=0)
    llm_free_daily_requests_grok: int = Field(default=0, ge=0)
    llm_free_daily_requests_claude: int = Field(default=0, ge=0)
    llm_free_daily_requests_cloudflare_workers_ai: int = Field(default=25, ge=0)

    openai_api_key: str | None = None
    openai_model: str = "gpt-5"

    gemini_api_key: str | None = None
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    gemini_model: str = "gemini-2.5-flash-lite"

    grok_api_key: str | None = None
    grok_base_url: str = "https://api.x.ai/v1"
    grok_model: str = "grok-4"

    claude_api_key: str | None = None
    claude_base_url: str = "https://api.anthropic.com/v1/messages"
    claude_model: str = "claude-3-5-haiku-latest"
    claude_api_version: str = "2023-06-01"
    claude_max_tokens: int = Field(default=2048, ge=1)
    claude_beta: str | None = None

    cloudflare_ai_api_token: str | None = None
    cloudflare_account_id: str | None = None
    cloudflare_ai_base_url: str | None = None
    cloudflare_ai_model: str = "@cf/openai/gpt-oss-120b"

    approval_expiry_hours: int = 24

    auth_mode: str = "header"
    auth_header_fallback_enabled: bool = True
    auth_jwt_secret: str | None = None
    auth_jwt_issuer: str = "architecture-control-plane"
    auth_jwt_audience: str = "architecture-control-plane-api"
    auth_required_role_claim: str = "role"
    auth_jwks_url: str | None = None
    auth_oidc_discovery_url: str | None = None
    auth_oidc_discovery_cache_ttl_seconds: int = 300
    auth_oidc_require_https: bool = True
    auth_jwks_cache_ttl_seconds: int = 300
    auth_jwt_allowed_algorithms: str = "HS256,RS256"
    auth_jwt_leeway_seconds: int = 30

    management_api_key: str | None = None
    management_api_keys_json: str | None = None
    management_endpoints_require_api_key: bool = False
    management_runtime_cache_ttl_seconds: int = Field(default=5, ge=1)

    abuse_protection_enabled: bool = True
    abuse_rate_limit_backend: str = "in_memory"
    abuse_rate_limit_algorithm: str = "fixed_window"
    abuse_rate_limit_burst_multiplier: float = Field(default=1.0, ge=1.0, le=10.0)
    abuse_rate_limit_backend_failure_mode: str = "open"
    abuse_rate_limit_backend_failure_mode_api: str | None = None
    abuse_rate_limit_backend_failure_mode_management: str | None = None
    abuse_rate_limit_backend_failure_retry_after_seconds: int = Field(default=5, ge=1)
    abuse_redis_url: str | None = None
    abuse_redis_key_prefix: str = "acp:ratelimit"
    abuse_redis_socket_timeout_seconds: float = Field(default=1.0, gt=0.0)
    abuse_redis_connect_timeout_seconds: float = Field(default=1.0, gt=0.0)
    abuse_redis_health_check_interval_seconds: int = Field(default=30, ge=0)
    abuse_global_requests_per_minute: int = Field(default=240, ge=1)
    abuse_management_requests_per_minute: int = Field(default=60, ge=1)
    abuse_cycle_create_limit_per_minute: int = Field(default=30, ge=1)
    abuse_cycle_retry_limit_per_minute: int = Field(default=20, ge=1)
    abuse_cycle_replan_limit_per_minute: int = Field(default=20, ge=1)
    abuse_approval_confirm_limit_per_minute: int = Field(default=30, ge=1)
    abuse_tenant_plan_default: str = "standard"
    abuse_tenant_plan_assignments_json: str = "{}"
    abuse_tenant_plan_limits_json: str = "{}"
    abuse_metrics_include_tenant_labels: bool = False
    abuse_metrics_tenant_label_mode: str = "hashed"

    metrics_enabled: bool = True
    worker_metrics_enabled: bool = True
    api_availability_slo_target: float = Field(default=0.995, gt=0.0, lt=1.0)
    api_latency_slo_target: float = Field(default=0.95, gt=0.0, lt=1.0)
    api_latency_slo_seconds: float = Field(default=1.0, gt=0.0)

    otel_enabled: bool = False
    otel_service_name: str | None = None
    otel_service_namespace: str = "architecture-control-plane"
    otel_service_version: str = "0.1.0"
    otel_exporter_otlp_endpoint: str | None = None
    otel_exporter_otlp_headers: str | None = None
    otel_traces_sampler_ratio: float = Field(default=1.0, ge=0.0, le=1.0)

    notification_webhook_url: str | None = None
    notification_timeout_seconds: float = Field(default=5.0, ge=0.1, le=60.0)
    notification_webhook_signing_secret: str | None = None
    notification_webhook_timestamp_tolerance_seconds: int = Field(default=300, ge=1)

    backup_output_dir: str = "backups"
    backup_retention_keep_last: int = Field(default=7, ge=0)
    backup_retention_max_age_days: int = Field(default=30, ge=0)
    backup_object_store_verify_restore: bool = False
    backup_encryption_passphrase: str | None = None
    backup_compose_service: str | None = None
    backup_drill_target_database_url: str | None = None
    backup_drill_target_database_urls_json: str = "{}"
    backup_default_label_prefix: str | None = None
    backup_command_timeout_seconds: int = Field(default=1800, ge=1)

    remote_workspace_enabled: bool = True
    remote_workspace_default_executor: str = "planning"
    remote_workspace_github_enabled: bool = False
    remote_workspace_github_repository: str | None = None
    remote_workspace_github_workflow: str | None = None
    remote_workspace_github_ref: str = "main"
    remote_workspace_github_api_base_url: str = "https://api.github.com"
    remote_workspace_github_token: str | None = None
    remote_workspace_callback_url: str | None = None
    remote_workspace_callback_token: str | None = None
    remote_workspace_dispatch_timeout_seconds: float = Field(default=10.0, gt=0.0)
    remote_workspace_execution_timeout_seconds: int = Field(default=1800, ge=30)
    remote_workspace_daily_request_limit: int = Field(default=20, ge=1)
    remote_workspace_max_parallel_requests: int = Field(default=2, ge=1)
    remote_workspace_persistent_enabled: bool = False
    remote_workspace_persistent_provider: str = "manual"
    remote_workspace_persistent_max_active_sessions: int = Field(default=1, ge=1)
    remote_workspace_persistent_idle_timeout_minutes: int = Field(default=120, ge=5)
    remote_workspace_persistent_ttl_hours: int = Field(default=8, ge=1)

    secrets_file_env_enabled: bool = True
    secrets_dir: str | None = None
