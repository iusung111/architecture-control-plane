from __future__ import annotations

import importlib

from . import common
from .policy import _effective_abuse_policy, _refill_token_bucket, _token_bucket_capacity, _token_bucket_refill_rate, _token_bucket_retry_after_seconds


def _import_redis_module():
    module = importlib.import_module("app.core.rate_limit")
    override = getattr(module, "_import_redis_module", None)
    if override is not None and override is not _import_redis_module:
        return override()
    return importlib.import_module("redis").Redis


class InMemoryRateLimitBackend:
    backend_name = "in_memory"

    def __init__(self, settings: common.Settings) -> None:
        self._settings = settings
        self._lock = common.threading.Lock()
        self._windows: dict[str, common._WindowEntry] = {}
        self._token_buckets: dict[str, common._TokenBucketEntry] = {}
        self._time_fn = common.time.monotonic

    def initialize(self) -> None:
        return

    def reset(self) -> None:
        with self._lock:
            self._windows.clear()
            self._token_buckets.clear()

    def check(self, *, scope: str, identifier: str, limit: int, window_seconds: int) -> common.RateLimitResult:
        if self._settings.abuse_rate_limit_algorithm == "token_bucket":
            return self._check_token_bucket(scope=scope, identifier=identifier, limit=limit, window_seconds=window_seconds)
        return self._check_fixed_window(scope=scope, identifier=identifier, limit=limit, window_seconds=window_seconds)

    def _check_fixed_window(self, *, scope: str, identifier: str, limit: int, window_seconds: int) -> common.RateLimitResult:
        key = f"{scope}:{identifier}"
        current_time = self._time_fn()
        with self._lock:
            entry = self._windows.get(key)
            if entry is None or current_time >= entry.started_at + window_seconds:
                self._windows[key] = common._WindowEntry(started_at=current_time, count=1)
                return common.RateLimitResult(allowed=True, retry_after_seconds=0, remaining=max(limit - 1, 0))
            if entry.count >= limit:
                retry_after = common.math.ceil((entry.started_at + window_seconds) - current_time)
                return common.RateLimitResult(allowed=False, retry_after_seconds=max(retry_after, 1), remaining=0)
            entry.count += 1
            return common.RateLimitResult(allowed=True, retry_after_seconds=0, remaining=max(limit - entry.count, 0))

    def _check_token_bucket(self, *, scope: str, identifier: str, limit: int, window_seconds: int) -> common.RateLimitResult:
        key = f"{scope}:{identifier}"
        now = self._time_fn()
        capacity = _token_bucket_capacity(limit, self._settings)
        refill_rate = _token_bucket_refill_rate(limit, window_seconds)
        with self._lock:
            entry = self._token_buckets.get(key)
            if entry is None:
                entry = common._TokenBucketEntry(last_refill_at=now, tokens=float(capacity))
                self._token_buckets[key] = entry
            _refill_token_bucket(entry, now, capacity, refill_rate)
            if entry.tokens < 1.0:
                retry_after = _token_bucket_retry_after_seconds(entry.tokens, refill_rate)
                return common.RateLimitResult(allowed=False, retry_after_seconds=retry_after, remaining=max(int(common.math.floor(entry.tokens)), 0))
            entry.tokens -= 1.0
            return common.RateLimitResult(allowed=True, retry_after_seconds=0, remaining=max(int(common.math.floor(entry.tokens)), 0))


class RedisRateLimitBackend:
    backend_name = "redis"

    def __init__(self, settings: common.Settings) -> None:
        self._settings = settings
        self._client = None
        self._script_shas: dict[str, str] = {}
        self._lock = common.threading.RLock()

    def initialize(self) -> None:
        client = self._get_client()
        client.ping()
        self._ensure_script_loaded(client, str(_effective_abuse_policy(self._settings)["algorithm"]))

    def reset(self) -> None:
        with self._lock:
            if self._client is not None:
                self._client.close()
            self._client = None
            self._script_shas = {}

    def check(self, *, scope: str, identifier: str, limit: int, window_seconds: int) -> common.RateLimitResult:
        client = self._get_client()
        algorithm = str(_effective_abuse_policy(self._settings)["algorithm"])
        sha = self._ensure_script_loaded(client, algorithm)
        try:
            result = self._eval_token_bucket(client, sha, scope, identifier, limit, window_seconds) if algorithm == "token_bucket" else self._eval_fixed_window(client, sha, scope, identifier, limit, window_seconds)
        except self._redis_exceptions().NoScriptError:
            sha = self._load_script(client, algorithm)
            result = self._eval_token_bucket(client, sha, scope, identifier, limit, window_seconds) if algorithm == "token_bucket" else self._eval_fixed_window(client, sha, scope, identifier, limit, window_seconds)
        return common.RateLimitResult(allowed=bool(int(result[0])), retry_after_seconds=max(int(result[2]), 0), remaining=max(int(result[1]), 0))

    def _eval_fixed_window(self, client, sha: str, scope: str, identifier: str, limit: int, window_seconds: int):
        return client.evalsha(sha, 1, self._format_key(scope, identifier), limit, window_seconds)

    def _eval_token_bucket(self, client, sha: str, scope: str, identifier: str, limit: int, window_seconds: int):
        key_base = self._format_key(scope, identifier)
        capacity = _token_bucket_capacity(limit, self._settings)
        refill_rate = _token_bucket_refill_rate(limit, window_seconds)
        ttl_seconds = max(int(common.math.ceil(window_seconds * self._settings.abuse_rate_limit_burst_multiplier)), window_seconds)
        return client.evalsha(sha, 2, f"{key_base}:tokens", f"{key_base}:ts", capacity, refill_rate, common.time.time(), ttl_seconds)

    def _format_key(self, scope: str, identifier: str) -> str:
        prefix = self._settings.abuse_redis_key_prefix.rstrip(":")
        return f"{prefix}:{scope}:{identifier}"

    def _get_client(self):
        with self._lock:
            if self._client is None:
                redis_module = _import_redis_module()
                self._client = redis_module.from_url(
                    self._settings.abuse_redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_timeout=self._settings.abuse_redis_socket_timeout_seconds,
                    socket_connect_timeout=self._settings.abuse_redis_connect_timeout_seconds,
                    health_check_interval=self._settings.abuse_redis_health_check_interval_seconds,
                )
            return self._client

    def _ensure_script_loaded(self, client, algorithm: str) -> str:
        with self._lock:
            if algorithm not in self._script_shas:
                self._script_shas[algorithm] = self._load_script(client, algorithm)
            return self._script_shas[algorithm]

    def _load_script(self, client, algorithm: str) -> str:
        sha = client.script_load(common._TOKEN_BUCKET_REDIS_SCRIPT if algorithm == "token_bucket" else common._FIXED_WINDOW_REDIS_SCRIPT)
        self._script_shas[algorithm] = sha
        return sha

    @staticmethod
    def _redis_exceptions():
        return importlib.import_module("redis").exceptions
