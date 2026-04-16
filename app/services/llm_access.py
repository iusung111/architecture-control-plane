from __future__ import annotations

import importlib

import httpx
from openai import OpenAI

from app.services.llm_access_support.common import (
    LLMRawResult,
    QuotaObservation,
    _resolve_cloudflare_ai_base_url,
    provider_default_model,
    provider_documented_daily_limit,
    provider_free_limit,
    provider_is_configured,
)
from app.services.llm_access_support.providers import (
    ClaudeLLMAccess,
    CloudflareWorkersAILLMAccess,
    DisabledLLMAccess,
    GeminiLLMAccess,
    GrokLLMAccess,
    OpenAICompatibleChatLLMAccess,
    OpenAILLMAccess,
    build_llm_access,
)
from app.services.llm_access_support.quota import (
    _observation_from_anthropic_response,
    _observation_from_openai_response,
    fetch_anthropic_probe_snapshot,
    fetch_openai_compatible_probe_snapshot,
    fetch_openai_probe_snapshot,
    fetch_openai_usage_snapshot,
    fetch_provider_quota_snapshot,
)
from app.services.llm_access_support.usage_policy import _acquire_llm_usage_slot, reset_llm_usage_counters


def _import_redis_module():
    redis_module = importlib.import_module("redis")
    return redis_module.Redis


__all__ = [
    "ClaudeLLMAccess",
    "CloudflareWorkersAILLMAccess",
    "DisabledLLMAccess",
    "GeminiLLMAccess",
    "GrokLLMAccess",
    "LLMRawResult",
    "OpenAI",
    "OpenAICompatibleChatLLMAccess",
    "OpenAILLMAccess",
    "QuotaObservation",
    "_acquire_llm_usage_slot",
    "_import_redis_module",
    "_observation_from_anthropic_response",
    "_observation_from_openai_response",
    "_resolve_cloudflare_ai_base_url",
    "build_llm_access",
    "fetch_anthropic_probe_snapshot",
    "fetch_openai_compatible_probe_snapshot",
    "fetch_openai_probe_snapshot",
    "fetch_openai_usage_snapshot",
    "fetch_provider_quota_snapshot",
    "httpx",
    "provider_default_model",
    "provider_documented_daily_limit",
    "provider_free_limit",
    "provider_is_configured",
    "reset_llm_usage_counters",
]
