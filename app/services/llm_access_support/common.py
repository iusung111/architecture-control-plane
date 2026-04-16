from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.config import LLMProvider, Settings
from app.schemas.llm import LLMInterpretationOutput


@dataclass(slots=True)
class QuotaObservation:
    source: str
    requests_limit: int | None = None
    requests_remaining: int | None = None
    requests_reset_at: datetime | None = None
    tokens_limit: int | None = None
    tokens_remaining: int | None = None
    tokens_reset_at: datetime | None = None
    daily_request_limit: int | None = None
    daily_requests_used: int | None = None
    daily_requests_remaining: int | None = None
    spend_limit_usd: float | None = None
    spend_used_usd: float | None = None
    spend_remaining_usd: float | None = None
    usage_tokens_input: int | None = None
    usage_tokens_output: int | None = None
    raw_payload: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "requests_limit": self.requests_limit,
            "requests_remaining": self.requests_remaining,
            "requests_reset_at": self.requests_reset_at.isoformat() if self.requests_reset_at else None,
            "tokens_limit": self.tokens_limit,
            "tokens_remaining": self.tokens_remaining,
            "tokens_reset_at": self.tokens_reset_at.isoformat() if self.tokens_reset_at else None,
            "daily_request_limit": self.daily_request_limit,
            "daily_requests_used": self.daily_requests_used,
            "daily_requests_remaining": self.daily_requests_remaining,
            "spend_limit_usd": self.spend_limit_usd,
            "spend_used_usd": self.spend_used_usd,
            "spend_remaining_usd": self.spend_remaining_usd,
            "usage_tokens_input": self.usage_tokens_input,
            "usage_tokens_output": self.usage_tokens_output,
            "raw_payload": self.raw_payload or {},
        }

    def merged_with(self, other: "QuotaObservation | None", *, source: str | None = None) -> "QuotaObservation":
        if other is None:
            return self

        def choose(primary, secondary):
            return primary if primary is not None else secondary

        merged_raw: dict[str, Any] = {}
        if self.raw_payload:
            merged_raw.update(self.raw_payload)
        if other.raw_payload:
            for key, value in other.raw_payload.items():
                if key in merged_raw and isinstance(merged_raw[key], dict) and isinstance(value, dict):
                    merged_raw[key] = {**merged_raw[key], **value}
                else:
                    merged_raw[key] = value

        return QuotaObservation(
            source=source or f"{self.source}+{other.source}",
            requests_limit=choose(self.requests_limit, other.requests_limit),
            requests_remaining=choose(self.requests_remaining, other.requests_remaining),
            requests_reset_at=choose(self.requests_reset_at, other.requests_reset_at),
            tokens_limit=choose(self.tokens_limit, other.tokens_limit),
            tokens_remaining=choose(self.tokens_remaining, other.tokens_remaining),
            tokens_reset_at=choose(self.tokens_reset_at, other.tokens_reset_at),
            daily_request_limit=choose(self.daily_request_limit, other.daily_request_limit),
            daily_requests_used=choose(self.daily_requests_used, other.daily_requests_used),
            daily_requests_remaining=choose(self.daily_requests_remaining, other.daily_requests_remaining),
            spend_limit_usd=choose(self.spend_limit_usd, other.spend_limit_usd),
            spend_used_usd=choose(self.spend_used_usd, other.spend_used_usd),
            spend_remaining_usd=choose(self.spend_remaining_usd, other.spend_remaining_usd),
            usage_tokens_input=choose(self.usage_tokens_input, other.usage_tokens_input),
            usage_tokens_output=choose(self.usage_tokens_output, other.usage_tokens_output),
            raw_payload=merged_raw,
        )


@dataclass(slots=True)
class LLMRawResult:
    backend_name: str
    model: str
    raw_text: str
    parsed_payload: dict | None
    validation_errors: list[str]
    quota_observation: dict[str, Any] | None = None


def provider_default_model(settings: Settings, provider: LLMProvider) -> str:
    return {
        "disabled": "disabled",
        "openai": settings.openai_model,
        "gemini": settings.gemini_model,
        "grok": settings.grok_model,
        "claude": settings.claude_model,
        "cloudflare_workers_ai": settings.cloudflare_ai_model,
    }[provider]


def provider_free_limit(settings: Settings, provider: LLMProvider) -> int | None:
    return {
        "disabled": None,
        "openai": settings.llm_free_daily_requests_openai,
        "gemini": settings.llm_free_daily_requests_gemini,
        "grok": settings.llm_free_daily_requests_grok,
        "claude": settings.llm_free_daily_requests_claude,
        "cloudflare_workers_ai": settings.llm_free_daily_requests_cloudflare_workers_ai,
    }[provider]


def provider_documented_daily_limit(settings: Settings, provider: LLMProvider) -> int | None:
    return provider_free_limit(settings, provider)


def provider_is_configured(settings: Settings, provider: LLMProvider) -> bool:
    return {
        "disabled": True,
        "openai": bool(settings.openai_api_key),
        "gemini": bool(settings.gemini_api_key),
        "grok": bool(settings.grok_api_key),
        "claude": bool(settings.claude_api_key),
        "cloudflare_workers_ai": bool(settings.cloudflare_ai_api_token and _resolve_cloudflare_ai_base_url(settings)),
    }[provider]


def _system_prompt_for_schema(prompt_type: str) -> str:
    return (
        "You are a strict structured-output assistant. "
        f"Return valid JSON only for prompt_type={prompt_type}. "
        "Do not wrap the JSON in markdown fences. "
        "The JSON must match this schema: "
        f"{json.dumps(LLMInterpretationOutput.model_json_schema(), ensure_ascii=False)}"
    )


def _parse_structured_json_payload(raw_text: str) -> dict[str, Any]:
    candidate = raw_text.strip()
    fenced_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", candidate, flags=re.DOTALL)
    if fenced_match:
        candidate = fenced_match.group(1).strip()
    payload = json.loads(candidate)
    parsed = LLMInterpretationOutput.model_validate(payload)
    return parsed.model_dump(mode="json")


def _extract_chat_completion_text(completion: Any) -> str:
    choices = getattr(completion, "choices", None) or []
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    if message is None:
        return ""
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(str(item.get("text") or item.get("content") or ""))
            elif hasattr(item, "text"):
                text_parts.append(str(getattr(item, "text")))
        return "\n".join(part for part in text_parts if part)
    return str(content)


def _extract_claude_message_text(payload: dict[str, Any]) -> str:
    parts = payload.get("content") or []
    chunks: list[str] = []
    for part in parts:
        if isinstance(part, dict) and part.get("type") == "text":
            chunks.append(str(part.get("text") or ""))
    return "\n".join(chunk for chunk in chunks if chunk)


def _resolve_cloudflare_ai_base_url(settings: Settings) -> str | None:
    if settings.cloudflare_ai_base_url:
        return settings.cloudflare_ai_base_url.rstrip("/")
    if settings.cloudflare_account_id:
        return f"https://api.cloudflare.com/client/v4/accounts/{settings.cloudflare_account_id}/ai/v1"
    return None


def _extract_usage_mapping(payload: Any) -> tuple[int | None, int | None]:
    usage = getattr(payload, "usage", None)
    if usage is None and isinstance(payload, dict):
        usage = payload.get("usage")
    if usage is None:
        return None, None
    if hasattr(usage, "input_tokens") or hasattr(usage, "output_tokens"):
        return getattr(usage, "input_tokens", None), getattr(usage, "output_tokens", None)
    if isinstance(usage, dict):
        input_tokens = usage.get("prompt_tokens") or usage.get("input_tokens")
        output_tokens = usage.get("completion_tokens") or usage.get("output_tokens")
        return input_tokens, output_tokens
    return None, None


def _safe_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _parse_reset_header(value: Any) -> datetime | None:
    if value in {None, ""}:
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    text = str(value).strip().lower()
    now = datetime.now(UTC)
    if text.endswith("ms"):
        try:
            return now + timedelta(milliseconds=float(text[:-2]))
        except ValueError:
            return None
    if text.endswith("s") and text[:-1].replace(".", "", 1).isdigit():
        return now + timedelta(seconds=float(text[:-1]))
    if text.isdigit():
        return now + timedelta(seconds=float(text))
    try:
        parsed = datetime.fromisoformat(text.replace("z", "+00:00"))
        return parsed.astimezone(UTC)
    except ValueError:
        return None


def _normalize_headers(payload: Any) -> dict[str, Any]:
    response = getattr(payload, "response", None)
    headers = getattr(response, "headers", None)
    if headers is None and hasattr(payload, "headers"):
        headers = getattr(payload, "headers")
    if headers is None:
        return {}
    if hasattr(headers, "items"):
        return {str(key).lower(): value for key, value in headers.items()}
    return {}
