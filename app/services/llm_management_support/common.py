from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from app.core.config import LLMProvider, Settings, get_settings
from app.services.llm_access_support.common import UTC, datetime, provider_default_model, provider_documented_daily_limit, provider_free_limit, provider_is_configured
from app.services.llm_access_support.quota import fetch_provider_quota_snapshot
from app.repositories.llm import (
    LLMDailyUsageRepository,
    LLMProviderPolicyRepository,
    LLMProviderQuotaSnapshotRepository,
    LLMRoutingDecisionRepository,
    LLMScopeOverrideRepository,
)

LLMStage = Literal["work", "review"]
LLMComplexity = Literal["low", "medium", "high"]
LLMSessionMode = Literal["job_session", "fresh_review_session"]
LLMScopeType = Literal["tenant", "project"]
_ALLOWED_PROVIDERS: tuple[LLMProvider, ...] = (
    "openai",
    "gemini",
    "grok",
    "claude",
    "cloudflare_workers_ai",
)

_STAGE_COMPLEXITY_RANKS: dict[str, dict[str, list[LLMProvider]]] = {
    "work": {
        "low": ["cloudflare_workers_ai", "gemini", "grok", "claude", "openai"],
        "medium": ["gemini", "cloudflare_workers_ai", "grok", "claude", "openai"],
        "high": ["gemini", "claude", "openai", "grok", "cloudflare_workers_ai"],
    },
    "review": {
        "low": ["gemini", "openai", "grok", "claude", "cloudflare_workers_ai"],
        "medium": ["gemini", "openai", "claude", "grok", "cloudflare_workers_ai"],
        "high": ["openai", "gemini", "claude", "grok", "cloudflare_workers_ai"],
    },
}

@dataclass(slots=True)
class ProviderStatus:
    provider: str
    configured: bool
    enabled: bool
    allow_work: bool
    allow_review: bool
    usage_mode: str
    priority: int
    daily_limit: int | None
    used_today: int
    remaining_today: int | None
    model: str
    external_quota_source: str | None = None
    external_requests_limit: int | None = None
    external_requests_remaining: int | None = None
    external_tokens_limit: int | None = None
    external_tokens_remaining: int | None = None
    external_daily_limit: int | None = None
    external_daily_used: int | None = None
    external_daily_remaining: int | None = None
    external_spend_limit_usd: float | None = None
    external_spend_used_usd: float | None = None
    external_spend_remaining_usd: float | None = None
    external_usage_tokens_input: int | None = None
    external_usage_tokens_output: int | None = None
    external_observed_at: str | None = None
    effective_scope: str = "global"

@dataclass(slots=True)
class ScopeOverrideStatus:
    scope_type: str
    scope_id: str
    provider: str
    enabled_override: bool | None
    allow_work_override: bool | None
    allow_review_override: bool | None
    usage_mode_override: str | None
    priority_offset: int
    daily_request_limit_override: int | None

@dataclass(slots=True)
class RoutingDecision:
    stage: str
    complexity: str
    provider: str
    model: str
    usage_mode: str
    session_id: str
    session_mode: LLMSessionMode
    source_session_id: str | None
    requires_fresh_session: bool
    remaining_requests: int | None
    rationale: dict[str, object]

class LLMRoutingBase:
    def __init__(self, db: Session, settings: Settings | None = None):
        self._db = db
        self._settings = settings or get_settings()
        self._policies = LLMProviderPolicyRepository(db)
        self._overrides = LLMScopeOverrideRepository(db)
        self._quota = LLMProviderQuotaSnapshotRepository(db)
        self._usage = LLMDailyUsageRepository(db)
        self._decisions = LLMRoutingDecisionRepository(db)

    @staticmethod
    def _normalize_complexity(raw: str) -> LLMComplexity:
        lowered = str(raw or "medium").strip().lower()
        if lowered in {"low", "medium", "high"}:
            return lowered  # type: ignore[return-value]
        return "medium"

    @staticmethod
    def _default_priority(provider: LLMProvider) -> int:
        defaults = {
            "openai": 80,
            "gemini": 95,
            "grok": 75,
            "claude": 85,
            "cloudflare_workers_ai": 90,
        }
        return defaults[provider]

    @staticmethod
    def _eligible_for_stage(status: ProviderStatus, stage: LLMStage) -> bool:
        if not status.enabled:
            return False
        if stage == "work" and not status.allow_work:
            return False
        if stage == "review" and not status.allow_review:
            return False
        if (
            status.usage_mode == "free_only"
            and status.daily_limit is not None
            and status.remaining_today is not None
            and status.remaining_today <= 0
        ):
            return False
        if (
            status.external_daily_remaining is not None
            and status.external_daily_remaining <= 0
            and status.usage_mode == "free_only"
        ):
            return False
        if status.external_requests_remaining is not None and status.external_requests_remaining <= 0:
            return False
        return True


__all__ = [
    "LLMComplexity", "LLMProvider", "LLMScopeType", "LLMSessionMode", "LLMStage",
    "ProviderStatus", "RoutingDecision", "ScopeOverrideStatus", "LLMRoutingBase",
    "Settings", "UTC", "datetime", "_ALLOWED_PROVIDERS", "_STAGE_COMPLEXITY_RANKS",
    "fetch_provider_quota_snapshot", "get_settings", "provider_default_model",
    "provider_documented_daily_limit", "provider_free_limit", "provider_is_configured",
]
