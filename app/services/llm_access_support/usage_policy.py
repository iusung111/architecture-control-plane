from __future__ import annotations

import importlib
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.config import LLMProvider, Settings
from .common import LLMRawResult, provider_free_limit


@dataclass(slots=True)
class _LLMDailyCounter:
    day_key: str
    count: int


_usage_lock = threading.Lock()
_usage_counters: dict[str, _LLMDailyCounter] = {}
_usage_redis_clients_lock = threading.Lock()
_usage_redis_clients: dict[str, Any] = {}


def reset_llm_usage_counters() -> None:
    with _usage_lock:
        _usage_counters.clear()
    with _usage_redis_clients_lock:
        clients = list(_usage_redis_clients.values())
        _usage_redis_clients.clear()
    for client in clients:
        close = getattr(client, "close", None)
        if callable(close):
            close()


def _provider_free_daily_request_limit(settings: Settings, provider: LLMProvider) -> int | None:
    return provider_free_limit(settings, provider)


def _acquire_llm_usage_slot(settings: Settings, provider: LLMProvider) -> str | None:
    if settings.llm_usage_mode != "free_only":
        return None
    free_limit = _provider_free_daily_request_limit(settings, provider)
    if free_limit is None or free_limit <= 0:
        return (
            f"usage policy blocked provider '{provider}' in free_only mode; "
            "set LLM_USAGE_MODE=paid to allow billed usage"
        )
    if _resolve_llm_usage_counter_backend(settings) == "redis":
        return _acquire_llm_usage_slot_redis(settings, provider, free_limit)
    return _acquire_llm_usage_slot_in_memory(provider, free_limit)


def _resolve_llm_usage_counter_backend(settings: Settings) -> str:
    if settings.llm_usage_counter_backend == "in_memory":
        return "in_memory"
    if settings.llm_usage_counter_backend == "redis":
        return "redis"
    return "redis" if _resolve_llm_usage_redis_url(settings) else "in_memory"


def _resolve_llm_usage_redis_url(settings: Settings) -> str | None:
    return settings.llm_usage_redis_url or settings.abuse_redis_url


def _seconds_until_next_utc_day() -> int:
    now = datetime.now(UTC)
    tomorrow = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
    return max(int((tomorrow - now).total_seconds()), 1)


def _llm_usage_counter_key(settings: Settings, provider: LLMProvider, day_key: str) -> str:
    prefix = settings.llm_usage_redis_key_prefix or "llm_usage"
    return f"{prefix}:{provider}:{day_key}"


def _get_llm_usage_redis_client(settings: Settings):
    redis_url = _resolve_llm_usage_redis_url(settings)
    if not redis_url:
        raise RuntimeError("LLM usage redis url is not configured")
    with _usage_redis_clients_lock:
        existing = _usage_redis_clients.get(redis_url)
        if existing is not None:
            return existing
        llm_access_module = importlib.import_module("app.services.llm_access")
        redis_cls = llm_access_module._import_redis_module()
        client = redis_cls.from_url(redis_url, decode_responses=True)
        _usage_redis_clients[redis_url] = client
        return client


def _acquire_llm_usage_slot_in_memory(provider: LLMProvider, free_limit: int) -> str | None:
    day_key = datetime.now(UTC).date().isoformat()
    with _usage_lock:
        counter = _usage_counters.get(provider)
        if counter is None or counter.day_key != day_key:
            _usage_counters[provider] = _LLMDailyCounter(day_key=day_key, count=1)
            return None
        counter.count += 1
        if counter.count > free_limit:
            return f"free-tier daily request cap reached for provider '{provider}' ({free_limit} requests/day)"
    return None


def _acquire_llm_usage_slot_redis(settings: Settings, provider: LLMProvider, free_limit: int) -> str | None:
    day_key = datetime.now(UTC).date().isoformat()
    key = _llm_usage_counter_key(settings, provider, day_key)
    ttl_seconds = _seconds_until_next_utc_day()
    try:
        client = _get_llm_usage_redis_client(settings)
        created = client.set(key, "1", ex=ttl_seconds, nx=True)
        if created:
            return None
        current_count = int(client.incr(key))
        if current_count == 1:
            client.expire(key, ttl_seconds)
        if current_count > free_limit:
            return f"free-tier daily request cap reached for provider '{provider}' ({free_limit} requests/day)"
        return None
    except Exception as exc:  # noqa: BLE001
        return f"LLM usage quota backend unavailable for provider '{provider}': {exc}"


def _policy_block_result(backend_name: str, model: str, message: str) -> LLMRawResult:
    return LLMRawResult(
        backend_name=backend_name,
        model=model,
        raw_text="",
        parsed_payload=None,
        validation_errors=[message],
    )
