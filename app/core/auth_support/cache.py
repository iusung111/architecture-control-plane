from time import time
from typing import Any

_JWKS_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_DISCOVERY_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def clear_auth_caches() -> None:
    _JWKS_CACHE.clear()
    _DISCOVERY_CACHE.clear()


def get_cached(cache: dict[str, tuple[float, dict[str, Any]]], key: str) -> dict[str, Any] | None:
    cached = cache.get(key)
    now = time()
    if cached and cached[0] > now:
        return cached[1]
    return None


def set_cached(cache: dict[str, tuple[float, dict[str, Any]]], key: str, ttl_seconds: int, payload: dict[str, Any]) -> None:
    _ = time
    cache[key] = (time() + ttl_seconds, payload)
