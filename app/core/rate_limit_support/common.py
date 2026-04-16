from __future__ import annotations

import hashlib
import json
import math
import threading
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

from fastapi import HTTPException, Request

from app.core.config import Settings, get_settings

__all__ = [
    "ACTION_SCOPE_TO_SETTING",
    "ActionRateLimitProfile",
    "HTTPException",
    "RateLimitBackend",
    "RateLimitBackendStatus",
    "RateLimitBackendUnavailable",
    "RateLimitExceeded",
    "RateLimitResult",
    "Request",
    "ScopeLimitResolution",
    "Settings",
    "_FIXED_WINDOW_REDIS_SCRIPT",
    "_TOKEN_BUCKET_REDIS_SCRIPT",
    "_TokenBucketEntry",
    "_WINDOW_SECONDS",
    "_WindowEntry",
    "_abuse_override_cache",
    "_abuse_override_cache_expires_at",
    "_abuse_override_cache_lock",
    "_backend_status",
    "_backend_status_lock",
    "_rate_limit_backend",
    "_rate_limit_backend_config_key",
    "_rate_limit_backend_lock",
    "dataclass",
    "get_settings",
    "hashlib",
    "json",
    "lru_cache",
    "math",
    "threading",
    "time",
]


_WINDOW_SECONDS = 60
_FIXED_WINDOW_REDIS_SCRIPT = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local window_seconds = tonumber(ARGV[2])
local current = redis.call('GET', key)
if not current then
  redis.call('SET', key, 1, 'EX', window_seconds)
  return {1, limit - 1, window_seconds}
end
current = tonumber(current)
local ttl = redis.call('TTL', key)
if current >= limit then
  if ttl == nil or ttl < 0 then
    redis.call('EXPIRE', key, window_seconds)
    ttl = window_seconds
  end
  return {0, 0, ttl}
end
current = redis.call('INCR', key)
if ttl == nil or ttl < 0 then
  redis.call('EXPIRE', key, window_seconds)
  ttl = window_seconds
else
  ttl = redis.call('TTL', key)
end
return {1, limit - current, ttl}
""".strip()
_TOKEN_BUCKET_REDIS_SCRIPT = """
local tokens_key = KEYS[1]
local ts_key = KEYS[2]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local ttl_seconds = tonumber(ARGV[4])
local tokens = tonumber(redis.call('GET', tokens_key))
if tokens == nil then
  tokens = capacity
end
local last_refill = tonumber(redis.call('GET', ts_key))
if last_refill == nil then
  last_refill = now
end
if now > last_refill then
  local delta = now - last_refill
  tokens = math.min(capacity, tokens + (delta * refill_rate))
end
if tokens < 1 then
  local retry_after = math.ceil((1 - tokens) / refill_rate)
  local expiry = math.max(ttl_seconds, retry_after)
  redis.call('SET', tokens_key, tokens, 'EX', expiry)
  redis.call('SET', ts_key, now, 'EX', expiry)
  return {0, retry_after, math.floor(tokens)}
end
tokens = tokens - 1
redis.call('SET', tokens_key, tokens, 'EX', ttl_seconds)
redis.call('SET', ts_key, now, 'EX', ttl_seconds)
return {1, 0, math.floor(tokens)}
""".strip()


@dataclass(slots=True)
class RateLimitResult:
    allowed: bool
    retry_after_seconds: int
    remaining: int


class RateLimitExceeded(HTTPException):
    def __init__(self, *, scope: str, retry_after_seconds: int, message: str = "rate limit exceeded") -> None:
        headers = {"Retry-After": str(max(retry_after_seconds, 1))}
        super().__init__(status_code=429, detail=message, headers=headers)
        self.scope = scope
        self.retry_after_seconds = max(retry_after_seconds, 1)


class RateLimitBackendUnavailable(HTTPException):
    def __init__(self, *, scope: str, retry_after_seconds: int, message: str = "rate limit backend unavailable") -> None:
        headers = {"Retry-After": str(max(retry_after_seconds, 1))}
        super().__init__(status_code=503, detail=message, headers=headers)
        self.scope = scope
        self.retry_after_seconds = max(retry_after_seconds, 1)


@dataclass(slots=True)
class ActionRateLimitProfile:
    scope: str
    limit_per_minute: int
    identifier: str
    tenant_id: str | None = None
    plan_name: str | None = None


@dataclass(slots=True)
class RateLimitBackendStatus:
    backend: str
    algorithm: str
    api_fail_mode: str
    management_fail_mode: str
    healthy: bool
    last_error: str | None = None
    last_error_at: float | None = None
    last_success_at: float | None = None


@dataclass(slots=True)
class ScopeLimitResolution:
    limit_per_minute: int
    plan_name: str | None


ACTION_SCOPE_TO_SETTING = {
    "cycle_create": "abuse_cycle_create_limit_per_minute",
    "cycle_retry": "abuse_cycle_retry_limit_per_minute",
    "cycle_replan": "abuse_cycle_replan_limit_per_minute",
    "approval_confirm": "abuse_approval_confirm_limit_per_minute",
}


class RateLimitBackend(Protocol):
    def initialize(self) -> None: ...
    def reset(self) -> None: ...
    def check(self, *, scope: str, identifier: str, limit: int, window_seconds: int) -> RateLimitResult: ...


@dataclass(slots=True)
class _WindowEntry:
    started_at: float
    count: int


@dataclass(slots=True)
class _TokenBucketEntry:
    last_refill_at: float
    tokens: float


_rate_limit_backend: RateLimitBackend | None = None
_rate_limit_backend_config_key: tuple[str, str | None, str, str, float] | None = None
_rate_limit_backend_lock = threading.RLock()
_backend_status_lock = threading.RLock()
_backend_status = RateLimitBackendStatus(
    backend="in_memory",
    algorithm="fixed_window",
    api_fail_mode="open",
    management_fail_mode="closed",
    healthy=True,
)

_abuse_override_cache: dict | None = None
_abuse_override_cache_expires_at = 0.0
_abuse_override_cache_lock = threading.RLock()
