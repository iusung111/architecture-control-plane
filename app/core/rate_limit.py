from __future__ import annotations

import importlib


def _import_redis_module():
    redis_module = importlib.import_module("redis")
    return redis_module.Redis


def __getattr__(name: str):
    common_names = {
        "ActionRateLimitProfile",
        "RateLimitBackendStatus",
        "RateLimitBackendUnavailable",
        "RateLimitExceeded",
        "_backend_status",
        "_rate_limit_backend",
        "_rate_limit_backend_config_key",
    }
    backend_names = {
        "InMemoryRateLimitBackend",
        "RedisRateLimitBackend",
    }
    enforcement_names = {
        "action_limit_profile",
        "enforce_action_limit",
        "enforce_global_request_limit",
        "enforce_management_request_limit",
        "get_rate_limit_backend_status",
        "initialize_rate_limit_backend",
        "reset_rate_limits",
    }
    policy_names = {
        "_normalize_tenant_label",
        "invalidate_abuse_override_cache",
        "set_inprocess_abuse_override_payload",
    }
    if name in common_names:
        from .rate_limit_support import common
        return getattr(common, name)
    if name in backend_names:
        from .rate_limit_support import backends
        return getattr(backends, name)
    if name in enforcement_names:
        from .rate_limit_support import enforcement
        return getattr(enforcement, name)
    if name in policy_names:
        from .rate_limit_support import policy
        return getattr(policy, name)
    raise AttributeError(name)
