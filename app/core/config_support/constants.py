from typing import Literal

LLMProvider = Literal[
    "disabled",
    "openai",
    "gemini",
    "grok",
    "claude",
    "cloudflare_workers_ai",
]
LLMUsageMode = Literal["free_only", "paid"]
SUPPORTED_BEARER_JWT_ALGORITHMS = {"HS256", "HS384", "HS512"}
SUPPORTED_OIDC_JWT_ALGORITHMS = {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512", "EdDSA"}

SECRET_FILE_ENV_FIELD_MAP: dict[str, str] = {
    "DATABASE_URL": "database_url",
    "LLM_USAGE_REDIS_URL": "llm_usage_redis_url",
    "OPENAI_API_KEY": "openai_api_key",
    "GEMINI_API_KEY": "gemini_api_key",
    "GROK_API_KEY": "grok_api_key",
    "CLAUDE_API_KEY": "claude_api_key",
    "CLOUDFLARE_AI_API_TOKEN": "cloudflare_ai_api_token",
    "AUTH_JWT_SECRET": "auth_jwt_secret",
    "AUTH_JWKS_URL": "auth_jwks_url",
    "AUTH_OIDC_DISCOVERY_URL": "auth_oidc_discovery_url",
    "MANAGEMENT_API_KEY": "management_api_key",
    "MANAGEMENT_API_KEYS_JSON": "management_api_keys_json",
    "ABUSE_REDIS_URL": "abuse_redis_url",
    "NOTIFICATION_WEBHOOK_URL": "notification_webhook_url",
    "NOTIFICATION_WEBHOOK_SIGNING_SECRET": "notification_webhook_signing_secret",
    "BACKUP_ENCRYPTION_PASSPHRASE": "backup_encryption_passphrase",
    "BACKUP_DRILL_TARGET_DATABASE_URL": "backup_drill_target_database_url",
    "BACKUP_DRILL_TARGET_DATABASE_URLS_JSON": "backup_drill_target_database_urls_json",
}
