from __future__ import annotations

import importlib

from app.core.config import LLMProvider, Settings, get_settings
from app.schemas.llm import LLMInterpretationOutput
from .common import (
    LLMRawResult,
    _extract_chat_completion_text,
    _extract_claude_message_text,
    _parse_structured_json_payload,
    _resolve_cloudflare_ai_base_url,
    _system_prompt_for_schema,
    provider_documented_daily_limit,
)
from .quota import _observation_from_openai_response
from .usage_policy import _acquire_llm_usage_slot, _policy_block_result


def _llm_module():
    return importlib.import_module("app.services.llm_access")


class DisabledLLMAccess:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def generate(self, prompt_type: str, prompt: str) -> LLMRawResult:
        del prompt_type, prompt
        return LLMRawResult(
            backend_name="disabled",
            model="disabled",
            raw_text="",
            parsed_payload=None,
            validation_errors=["backend unavailable: LLM_PROVIDER=disabled"],
        )


class OpenAILLMAccess:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client = _llm_module().OpenAI(api_key=self._settings.openai_api_key) if self._settings.openai_api_key else None
        self._model = self._settings.openai_model

    def generate(self, prompt_type: str, prompt: str) -> LLMRawResult:
        policy_error = _acquire_llm_usage_slot(self._settings, "openai")
        if policy_error:
            return _policy_block_result("openai", self._model, policy_error)
        del prompt_type
        if self._client is None:
            return LLMRawResult(
                backend_name="openai",
                model=self._model,
                raw_text="",
                parsed_payload=None,
                validation_errors=["backend unavailable: OPENAI_API_KEY is not configured"],
            )

        try:
            response = self._client.responses.parse(
                model=self._model,
                input=prompt,
                text_format=LLMInterpretationOutput,
            )
            parsed = response.output_parsed
            raw_text = getattr(response, "output_text", "") or ""
            quota = _observation_from_openai_response(response)
            return LLMRawResult(
                backend_name="openai",
                model=self._model,
                raw_text=raw_text,
                parsed_payload=parsed.model_dump(mode="json"),
                validation_errors=[],
                quota_observation=quota.as_dict() if quota else None,
            )
        except Exception as exc:  # noqa: BLE001
            return LLMRawResult(
                backend_name="openai",
                model=self._model,
                raw_text="",
                parsed_payload=None,
                validation_errors=[f"structured output parse failed: {exc}"],
            )


class OpenAICompatibleChatLLMAccess:
    def __init__(
        self,
        *,
        settings: Settings,
        backend_name: LLMProvider,
        model: str,
        api_key: str | None,
        unavailable_message: str,
        base_url: str,
        default_daily_limit: int | None = None,
    ) -> None:
        self._settings = settings
        self._backend_name = backend_name
        self._model = model
        self._unavailable_message = unavailable_message
        self._default_daily_limit = default_daily_limit
        self._client = _llm_module().OpenAI(api_key=api_key, base_url=base_url) if api_key else None

    def generate(self, prompt_type: str, prompt: str) -> LLMRawResult:
        policy_error = _acquire_llm_usage_slot(self._settings, self._backend_name)
        if policy_error:
            return _policy_block_result(str(self._backend_name), self._model, policy_error)
        if self._client is None:
            return LLMRawResult(
                backend_name=str(self._backend_name),
                model=self._model,
                raw_text="",
                parsed_payload=None,
                validation_errors=[self._unavailable_message],
            )
        try:
            completion = self._client.chat.completions.create(
                model=self._model,
                temperature=0,
                messages=[
                    {"role": "system", "content": _system_prompt_for_schema(prompt_type)},
                    {"role": "user", "content": prompt},
                ],
            )
            raw_text = _extract_chat_completion_text(completion)
            parsed_payload = _parse_structured_json_payload(raw_text)
            quota = _observation_from_openai_response(completion, default_daily_limit=self._default_daily_limit)
            return LLMRawResult(
                backend_name=str(self._backend_name),
                model=self._model,
                raw_text=raw_text,
                parsed_payload=parsed_payload,
                validation_errors=[],
                quota_observation=quota.as_dict() if quota else None,
            )
        except Exception as exc:  # noqa: BLE001
            return LLMRawResult(
                backend_name=str(self._backend_name),
                model=self._model,
                raw_text="",
                parsed_payload=None,
                validation_errors=[f"structured output parse failed: {exc}"],
            )


class GeminiLLMAccess(OpenAICompatibleChatLLMAccess):
    def __init__(self, settings: Settings | None = None) -> None:
        resolved_settings = settings or get_settings()
        super().__init__(
            settings=resolved_settings,
            backend_name="gemini",
            model=resolved_settings.gemini_model,
            api_key=resolved_settings.gemini_api_key,
            unavailable_message="backend unavailable: GEMINI_API_KEY is not configured",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            default_daily_limit=provider_documented_daily_limit(resolved_settings, "gemini"),
        )


class GrokLLMAccess(OpenAICompatibleChatLLMAccess):
    def __init__(self, settings: Settings | None = None) -> None:
        resolved_settings = settings or get_settings()
        super().__init__(
            settings=resolved_settings,
            backend_name="grok",
            model=resolved_settings.grok_model,
            api_key=resolved_settings.grok_api_key,
            unavailable_message="backend unavailable: GROK_API_KEY is not configured",
            base_url=resolved_settings.grok_base_url,
            default_daily_limit=provider_documented_daily_limit(resolved_settings, "grok"),
        )


class CloudflareWorkersAILLMAccess(OpenAICompatibleChatLLMAccess):
    def __init__(self, settings: Settings | None = None) -> None:
        resolved_settings = settings or get_settings()
        base_url = _resolve_cloudflare_ai_base_url(resolved_settings)
        api_key = resolved_settings.cloudflare_ai_api_token
        unavailable_message = (
            "backend unavailable: CLOUDFLARE_AI_API_TOKEN and "
            "CLOUDFLARE_ACCOUNT_ID or CLOUDFLARE_AI_BASE_URL must be configured"
        )
        if api_key and base_url:
            super().__init__(
                settings=resolved_settings,
                backend_name="cloudflare_workers_ai",
                model=resolved_settings.cloudflare_ai_model,
                api_key=api_key,
                unavailable_message=unavailable_message,
                base_url=base_url,
                default_daily_limit=provider_documented_daily_limit(resolved_settings, "cloudflare_workers_ai"),
            )
        else:
            super().__init__(
                settings=resolved_settings,
                backend_name="cloudflare_workers_ai",
                model=resolved_settings.cloudflare_ai_model,
                api_key=None,
                unavailable_message=unavailable_message,
                base_url="https://api.cloudflare.invalid",
                default_daily_limit=provider_documented_daily_limit(resolved_settings, "cloudflare_workers_ai"),
            )


class ClaudeLLMAccess:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._model = self._settings.claude_model
        self._api_key = self._settings.claude_api_key
        self._base_url = self._settings.claude_base_url.removesuffix("/v1/messages").rstrip("/")

    def generate(self, prompt_type: str, prompt: str) -> LLMRawResult:
        policy_error = _acquire_llm_usage_slot(self._settings, "claude")
        if policy_error:
            return _policy_block_result("claude", self._model, policy_error)
        if not self._api_key:
            return LLMRawResult(
                backend_name="claude",
                model=self._model,
                raw_text="",
                parsed_payload=None,
                validation_errors=["backend unavailable: CLAUDE_API_KEY is not configured"],
            )
        try:
            response = _llm_module().httpx.post(
                f"{self._base_url}/v1/messages",
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self._model,
                    "max_tokens": 1000,
                    "system": _system_prompt_for_schema(prompt_type),
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=30.0,
            )
            response.raise_for_status()
            payload = response.json()
            raw_text = _extract_claude_message_text(payload)
            parsed_payload = _parse_structured_json_payload(raw_text)
            quota = _llm_module()._observation_from_anthropic_response(response)
            return LLMRawResult(
                backend_name="claude",
                model=self._model,
                raw_text=raw_text,
                parsed_payload=parsed_payload,
                validation_errors=[],
                quota_observation=quota.as_dict() if quota else None,
            )
        except Exception as exc:  # noqa: BLE001
            return LLMRawResult(
                backend_name="claude",
                model=self._model,
                raw_text="",
                parsed_payload=None,
                validation_errors=[f"structured output parse failed: {exc}"],
            )


def build_llm_access(settings: Settings | None = None):
    resolved_settings = settings or get_settings()
    provider = resolved_settings.llm_provider
    if provider == "openai":
        return OpenAILLMAccess(resolved_settings)
    if provider == "gemini":
        return GeminiLLMAccess(resolved_settings)
    if provider == "grok":
        return GrokLLMAccess(resolved_settings)
    if provider == "claude":
        return ClaudeLLMAccess(resolved_settings)
    if provider == "cloudflare_workers_ai":
        return CloudflareWorkersAILLMAccess(resolved_settings)
    return DisabledLLMAccess(resolved_settings)
