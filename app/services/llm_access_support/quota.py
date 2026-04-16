from __future__ import annotations

import importlib
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.config import LLMProvider, Settings, get_settings
from .common import (
    QuotaObservation,
    _extract_usage_mapping,
    _normalize_headers,
    _parse_reset_header,
    _safe_int,
    provider_default_model,
    provider_documented_daily_limit,
    provider_is_configured,
)


def _llm_module():
    return importlib.import_module("app.services.llm_access")


def _observation_from_openai_response(payload: Any, *, default_daily_limit: int | None = None) -> QuotaObservation | None:
    headers = _normalize_headers(payload)
    input_tokens, output_tokens = _extract_usage_mapping(payload)
    if not headers and input_tokens is None and output_tokens is None and default_daily_limit is None:
        return None
    return QuotaObservation(
        source="response_headers",
        requests_limit=_safe_int(headers.get("x-ratelimit-limit-requests")),
        requests_remaining=_safe_int(headers.get("x-ratelimit-remaining-requests")),
        requests_reset_at=_parse_reset_header(headers.get("x-ratelimit-reset-requests")),
        tokens_limit=_safe_int(headers.get("x-ratelimit-limit-tokens")),
        tokens_remaining=_safe_int(headers.get("x-ratelimit-remaining-tokens")),
        tokens_reset_at=_parse_reset_header(headers.get("x-ratelimit-reset-tokens")),
        daily_request_limit=default_daily_limit,
        usage_tokens_input=input_tokens,
        usage_tokens_output=output_tokens,
        raw_payload={"headers": headers},
    )


def _observation_from_anthropic_response(response) -> QuotaObservation | None:
    payload = response.json()
    input_tokens, output_tokens = _extract_usage_mapping(payload)
    raw_headers = getattr(response, "headers", {})
    headers = {str(key).lower(): value for key, value in raw_headers.items()} if hasattr(raw_headers, "items") else {}
    return QuotaObservation(
        source="response_headers",
        requests_limit=_safe_int(headers.get("anthropic-ratelimit-requests-limit")),
        requests_remaining=_safe_int(headers.get("anthropic-ratelimit-requests-remaining")),
        requests_reset_at=_parse_reset_header(headers.get("anthropic-ratelimit-requests-reset")),
        tokens_limit=_safe_int(headers.get("anthropic-ratelimit-tokens-limit")),
        tokens_remaining=_safe_int(headers.get("anthropic-ratelimit-tokens-remaining")),
        tokens_reset_at=_parse_reset_header(headers.get("anthropic-ratelimit-tokens-reset")),
        usage_tokens_input=input_tokens,
        usage_tokens_output=output_tokens,
        raw_payload={"headers": headers},
    )


def fetch_openai_usage_snapshot(settings: Settings | None = None) -> QuotaObservation | None:
    resolved_settings = settings or get_settings()
    api_key = resolved_settings.openai_api_key
    if not api_key:
        return None
    now = datetime.now(UTC)
    start = int((now - timedelta(days=1)).timestamp())
    end = int(now.timestamp())
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        response = _llm_module().httpx.get(
            "https://api.openai.com/v1/organization/usage/completions",
            params={"start_time": start, "end_time": end},
            headers=headers,
            timeout=20.0,
        )
        response.raise_for_status()
    except Exception:
        return None
    payload = response.json()
    results = payload.get("data") or []
    input_tokens = 0
    output_tokens = 0
    requests = 0
    for item in results:
        if not isinstance(item, dict):
            continue
        input_tokens += int(item.get("input_tokens") or 0)
        output_tokens += int(item.get("output_tokens") or 0)
        requests += int(item.get("num_model_requests") or 0)
    return QuotaObservation(
        source="usage_api",
        daily_requests_used=requests,
        usage_tokens_input=input_tokens,
        usage_tokens_output=output_tokens,
        raw_payload={"usage": payload},
    )


def _build_openai_compatible_probe_payload(model: str) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [{"role": "user", "content": 'Return the JSON object {"ok": true}.'}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "max_tokens": 32,
    }


def _observation_from_httpx_json_response(
    response,
    *,
    default_daily_limit: int | None = None,
    source: str = "probe_headers",
) -> QuotaObservation | None:
    try:
        payload = response.json()
    except Exception:
        payload = {}
    header_observation = _observation_from_openai_response(response, default_daily_limit=default_daily_limit)
    input_tokens, output_tokens = _extract_usage_mapping(payload)
    json_observation = QuotaObservation(
        source="response_json",
        usage_tokens_input=input_tokens,
        usage_tokens_output=output_tokens,
        daily_requests_used=1 if default_daily_limit is not None else None,
        daily_requests_remaining=(default_daily_limit - 1) if default_daily_limit is not None else None,
        raw_payload={"response": payload},
    )
    if header_observation is None:
        return json_observation
    return header_observation.merged_with(json_observation, source=source)


def fetch_openai_probe_snapshot(settings: Settings | None = None) -> QuotaObservation | None:
    resolved_settings = settings or get_settings()
    if not resolved_settings.openai_api_key:
        return None
    try:
        response = _llm_module().httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {resolved_settings.openai_api_key}"},
            json=_build_openai_compatible_probe_payload(resolved_settings.openai_model),
            timeout=20.0,
        )
        response.raise_for_status()
    except Exception:
        return None
    observation = _observation_from_httpx_json_response(
        response,
        default_daily_limit=provider_documented_daily_limit(resolved_settings, "openai"),
        source="probe_headers",
    )
    if observation is not None:
        observation.daily_requests_used = None
        observation.daily_requests_remaining = None
    return observation


def fetch_openai_compatible_probe_snapshot(
    *,
    settings: Settings,
    provider: LLMProvider,
    api_key: str | None,
    base_url: str | None,
) -> QuotaObservation | None:
    if not api_key or not base_url:
        return None
    try:
        response = _llm_module().httpx.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=_build_openai_compatible_probe_payload(provider_default_model(settings, provider)),
            timeout=20.0,
        )
        response.raise_for_status()
    except Exception:
        return None
    return _observation_from_httpx_json_response(
        response,
        default_daily_limit=provider_documented_daily_limit(settings, provider),
        source=f"probe_headers:{provider}",
    )


def fetch_anthropic_probe_snapshot(settings: Settings | None = None) -> QuotaObservation | None:
    resolved_settings = settings or get_settings()
    if not resolved_settings.claude_api_key:
        return None
    try:
        response = _llm_module().httpx.post(
            f"{resolved_settings.claude_base_url.rstrip('/')}/v1/messages",
            headers={
                "x-api-key": resolved_settings.claude_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": resolved_settings.claude_model,
                "max_tokens": 32,
                "messages": [{"role": "user", "content": 'Return the JSON object {"ok": true}.'}],
            },
            timeout=20.0,
        )
        response.raise_for_status()
    except Exception:
        return None
    return _observation_from_anthropic_response(response)


def fetch_provider_quota_snapshot(settings: Settings, provider: LLMProvider) -> QuotaObservation | None:
    if not provider_is_configured(settings, provider):
        return None
    if provider == "openai":
        probe = fetch_openai_probe_snapshot(settings)
        usage = fetch_openai_usage_snapshot(settings)
        if probe and usage:
            return probe.merged_with(usage, source="usage_api+probe_headers")
        return probe or usage
    if provider == "gemini":
        return fetch_openai_compatible_probe_snapshot(
            settings=settings,
            provider=provider,
            api_key=settings.gemini_api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        )
    if provider == "grok":
        return fetch_openai_compatible_probe_snapshot(
            settings=settings,
            provider=provider,
            api_key=settings.grok_api_key,
            base_url=settings.grok_base_url,
        )
    if provider == "cloudflare_workers_ai":
        return fetch_openai_compatible_probe_snapshot(
            settings=settings,
            provider=provider,
            api_key=settings.cloudflare_ai_api_token,
            base_url=_llm_module()._resolve_cloudflare_ai_base_url(settings),
        )
    if provider == "claude":
        return fetch_anthropic_probe_snapshot(settings)
    return None
