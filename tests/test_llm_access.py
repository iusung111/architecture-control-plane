from types import SimpleNamespace

import httpx

from app.core.config import Settings, validate_runtime_settings
from app.schemas.llm import LLMInterpretationOutput
from app.services.llm_access import (
    ClaudeLLMAccess,
    CloudflareWorkersAILLMAccess,
    DisabledLLMAccess,
    GeminiLLMAccess,
    GrokLLMAccess,
    OpenAILLMAccess,
    build_llm_access,
    reset_llm_usage_counters,
)


class FakeResponses:
    def __init__(self, parsed=None, exc: Exception | None = None):
        self._parsed = parsed
        self._exc = exc

    def parse(self, **kwargs):
        assert kwargs["text_format"] is LLMInterpretationOutput
        if self._exc is not None:
            raise self._exc
        return SimpleNamespace(
            output_parsed=self._parsed,
            output_text=self._parsed.model_dump_json(),
        )


class FakeChatCompletions:
    def __init__(self, content: str):
        self._content = content
        self.captured = []

    def create(self, **kwargs):
        self.captured.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=self._content),
                )
            ]
        )


class FakeClient:
    def __init__(self, responses=None, content: str | None = None):
        self.responses = responses
        self.chat = SimpleNamespace(completions=FakeChatCompletions(content or ""))


class FakeClaudeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class FakeQuotaRedis:
    shared_values: dict[str, int] = {}
    shared_ttl: dict[str, int] = {}

    @classmethod
    def from_url(cls, _url: str, **_kwargs):
        return cls()

    def close(self) -> None:
        return None

    def set(self, key: str, value: str, *, ex: int | None = None, nx: bool = False):
        if nx and key in type(self).shared_values:
            return False
        type(self).shared_values[key] = int(value)
        if ex is not None:
            type(self).shared_ttl[key] = int(ex)
        return True

    def incr(self, key: str) -> int:
        next_value = int(type(self).shared_values.get(key, 0)) + 1
        type(self).shared_values[key] = next_value
        return next_value

    def expire(self, key: str, ttl: int) -> bool:
        type(self).shared_ttl[key] = int(ttl)
        return True


class FakeBrokenQuotaRedis(FakeQuotaRedis):
    def set(self, key: str, value: str, *, ex: int | None = None, nx: bool = False):
        del key, value, ex, nx
        raise RuntimeError("redis unavailable")


def _payload(**overrides):
    payload = {
        "intent": "diagnose",
        "confidence": 0.91,
        "reasoning_summary": "structured result",
        "candidate_plan": [{"step": 1, "action": "inspect"}],
        "evidence_requirements": ["pressure log"],
        "retryability_assessment": "retryable",
        "escalation_recommendation": "none",
    }
    payload.update(overrides)
    return LLMInterpretationOutput(**payload)


def setup_function() -> None:
    reset_llm_usage_counters()


def test_generate_returns_backend_unavailable_when_api_key_missing():
    access = OpenAILLMAccess(Settings(openai_api_key=None, llm_usage_mode="paid"))
    access._client = None

    result = access.generate(prompt_type="interpretation", prompt="test prompt")

    assert result.parsed_payload is None
    assert result.validation_errors == ["backend unavailable: OPENAI_API_KEY is not configured"]


def test_generate_uses_structured_parse():
    access = OpenAILLMAccess(Settings(openai_api_key="sk-test", llm_usage_mode="paid"))
    payload = _payload()
    access._client = FakeClient(responses=FakeResponses(parsed=payload))
    result = access.generate(prompt_type="interpretation", prompt="test prompt")

    assert result.validation_errors == []
    assert result.parsed_payload is not None
    assert result.parsed_payload["intent"] == "diagnose"
    assert result.parsed_payload["candidate_plan"][0]["action"] == "inspect"


def test_generate_returns_validation_error_when_structured_parse_fails():
    access = OpenAILLMAccess(Settings(openai_api_key="sk-test", llm_usage_mode="paid"))
    access._client = FakeClient(responses=FakeResponses(exc=RuntimeError("parse failure")))

    result = access.generate(prompt_type="interpretation", prompt="test prompt")

    assert result.parsed_payload is None
    assert result.validation_errors
    assert "structured output parse failed" in result.validation_errors[0]


def test_build_llm_access_selects_supported_providers():
    assert isinstance(build_llm_access(Settings(llm_provider="disabled")), DisabledLLMAccess)
    assert isinstance(
        build_llm_access(Settings(llm_provider="gemini", gemini_api_key="gem-key")),
        GeminiLLMAccess,
    )
    assert isinstance(
        build_llm_access(Settings(llm_provider="grok", grok_api_key="xai-key", llm_usage_mode="paid")),
        GrokLLMAccess,
    )
    assert isinstance(
        build_llm_access(Settings(llm_provider="claude", claude_api_key="claude-key", llm_usage_mode="paid")),
        ClaudeLLMAccess,
    )
    assert isinstance(
        build_llm_access(
            Settings(
                llm_provider="cloudflare_workers_ai",
                cloudflare_ai_api_token="cf-token",
                cloudflare_account_id="acct-123",
            )
        ),
        CloudflareWorkersAILLMAccess,
    )


def test_gemini_generate_parses_openai_compatible_json(monkeypatch):
    captured: dict[str, str] = {}

    def fake_openai(*, api_key: str | None = None, base_url: str | None = None, **kwargs):
        captured["api_key"] = api_key or ""
        captured["base_url"] = base_url or ""
        del kwargs
        payload = _payload(reasoning_summary="gemini result")
        return FakeClient(content=f"```json\n{payload.model_dump_json()}\n```")

    monkeypatch.setattr("app.services.llm_access.OpenAI", fake_openai)
    access = GeminiLLMAccess(Settings(gemini_api_key="gem-key"))

    result = access.generate(prompt_type="interpretation", prompt="Return JSON")

    assert captured["api_key"] == "gem-key"
    assert captured["base_url"] == "https://generativelanguage.googleapis.com/v1beta/openai/"
    assert result.validation_errors == []
    assert result.parsed_payload is not None
    assert result.parsed_payload["reasoning_summary"] == "gemini result"


def test_grok_generate_parses_openai_compatible_json(monkeypatch):
    captured: dict[str, str] = {}

    def fake_openai(*, api_key: str | None = None, base_url: str | None = None, **kwargs):
        captured["api_key"] = api_key or ""
        captured["base_url"] = base_url or ""
        del kwargs
        payload = _payload(reasoning_summary="portable structured output")
        return FakeClient(content=f"```json\n{payload.model_dump_json()}\n```")

    monkeypatch.setattr("app.services.llm_access.OpenAI", fake_openai)
    access = GrokLLMAccess(Settings(grok_api_key="xai-key", grok_model="grok-4", llm_usage_mode="paid"))

    result = access.generate(prompt_type="interpretation", prompt="Return JSON")

    assert captured["api_key"] == "xai-key"
    assert captured["base_url"] == "https://api.x.ai/v1"
    assert result.validation_errors == []
    assert result.parsed_payload is not None
    assert result.parsed_payload["reasoning_summary"] == "portable structured output"


def test_cloudflare_workers_ai_uses_account_openai_compatible_base_url(monkeypatch):
    captured: dict[str, str] = {}

    def fake_openai(*, api_key: str | None = None, base_url: str | None = None, **kwargs):
        captured["api_key"] = api_key or ""
        captured["base_url"] = base_url or ""
        del kwargs
        payload = _payload(intent="plan", confidence=0.88, reasoning_summary="workers ai result")
        return FakeClient(content=payload.model_dump_json())

    monkeypatch.setattr("app.services.llm_access.OpenAI", fake_openai)
    access = CloudflareWorkersAILLMAccess(
        Settings(
            cloudflare_ai_api_token="cf-token",
            cloudflare_account_id="acct-123",
            cloudflare_ai_model="@cf/openai/gpt-oss-120b",
        )
    )

    result = access.generate(prompt_type="interpretation", prompt="Return JSON")

    assert captured["api_key"] == "cf-token"
    assert captured["base_url"] == "https://api.cloudflare.com/client/v4/accounts/acct-123/ai/v1"
    assert result.validation_errors == []
    assert result.parsed_payload is not None
    assert result.parsed_payload["intent"] == "plan"


def test_claude_generate_uses_messages_api(monkeypatch):
    captured: dict[str, object] = {}

    def fake_post(url: str, *, headers: dict, json: dict, timeout: float):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        payload = _payload(reasoning_summary="claude result")
        return FakeClaudeResponse(
            {
                "content": [
                    {
                        "type": "text",
                        "text": payload.model_dump_json(),
                    }
                ]
            }
        )

    monkeypatch.setattr("app.services.llm_access.httpx.post", fake_post)
    access = ClaudeLLMAccess(
        Settings(
            llm_provider="claude",
            claude_api_key="claude-key",
            claude_model="claude-3-5-haiku-latest",
            llm_usage_mode="paid",
        )
    )

    result = access.generate(prompt_type="interpretation", prompt="Return JSON")

    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["headers"]["x-api-key"] == "claude-key"
    assert captured["headers"]["anthropic-version"] == "2023-06-01"
    assert captured["json"]["model"] == "claude-3-5-haiku-latest"
    assert result.validation_errors == []
    assert result.parsed_payload is not None
    assert result.parsed_payload["reasoning_summary"] == "claude result"


def test_free_only_policy_blocks_paid_only_providers_by_default():
    errors = validate_runtime_settings(Settings(llm_provider="claude", claude_api_key="claude-key"))

    assert (
        "LLM_PROVIDER=claude is blocked in LLM_USAGE_MODE=free_only; set LLM_USAGE_MODE=paid to allow billed usage"
        in errors
    )


def test_free_only_policy_enforces_daily_cap_for_gemini(monkeypatch):
    def fake_openai(*, api_key: str | None = None, base_url: str | None = None, **kwargs):
        del api_key, base_url, kwargs
        payload = _payload(reasoning_summary="gemini result")
        return FakeClient(content=payload.model_dump_json())

    monkeypatch.setattr("app.services.llm_access.OpenAI", fake_openai)
    access = GeminiLLMAccess(
        Settings(
            gemini_api_key="gem-key",
            llm_usage_mode="free_only",
            llm_free_daily_requests_gemini=1,
        )
    )

    first = access.generate(prompt_type="interpretation", prompt="first")
    second = access.generate(prompt_type="interpretation", prompt="second")

    assert first.validation_errors == []
    assert second.parsed_payload is None
    assert second.validation_errors == [
        "free-tier daily request cap reached for provider 'gemini' (1 requests/day)"
    ]


def test_free_only_policy_uses_redis_backed_shared_counter(monkeypatch):
    FakeQuotaRedis.shared_values = {}
    FakeQuotaRedis.shared_ttl = {}

    def fake_openai(*, api_key: str | None = None, base_url: str | None = None, **kwargs):
        del api_key, base_url, kwargs
        payload = _payload(reasoning_summary="gemini result")
        return FakeClient(content=payload.model_dump_json())

    monkeypatch.setattr("app.services.llm_access.OpenAI", fake_openai)
    monkeypatch.setattr("app.services.llm_access._import_redis_module", lambda: FakeQuotaRedis)
    settings = Settings(
        gemini_api_key="gem-key",
        llm_usage_mode="free_only",
        llm_free_daily_requests_gemini=1,
        llm_usage_counter_backend="redis",
        llm_usage_redis_url="redis://quota.example:6379/1",
    )

    first = GeminiLLMAccess(settings).generate(prompt_type="interpretation", prompt="first")
    reset_llm_usage_counters()
    second = GeminiLLMAccess(settings).generate(prompt_type="interpretation", prompt="second")

    assert first.validation_errors == []
    assert second.parsed_payload is None
    assert second.validation_errors == [
        "free-tier daily request cap reached for provider 'gemini' (1 requests/day)"
    ]
    assert any(key.startswith("acp:llm:usage:gemini:") for key in FakeQuotaRedis.shared_values)


def test_free_only_policy_blocks_when_redis_quota_backend_is_unavailable(monkeypatch):
    def fake_openai(*, api_key: str | None = None, base_url: str | None = None, **kwargs):
        del api_key, base_url, kwargs
        payload = _payload(reasoning_summary="gemini result")
        return FakeClient(content=payload.model_dump_json())

    monkeypatch.setattr("app.services.llm_access.OpenAI", fake_openai)
    monkeypatch.setattr("app.services.llm_access._import_redis_module", lambda: FakeBrokenQuotaRedis)
    settings = Settings(
        gemini_api_key="gem-key",
        llm_usage_mode="free_only",
        llm_free_daily_requests_gemini=1,
        llm_usage_counter_backend="redis",
        llm_usage_redis_url="redis://quota.example:6379/1",
    )

    result = GeminiLLMAccess(settings).generate(prompt_type="interpretation", prompt="blocked")

    assert result.parsed_payload is None
    assert result.validation_errors
    assert result.validation_errors[0].startswith("LLM usage quota backend unavailable for provider 'gemini':")


def test_paid_mode_lifts_provider_block_for_claude():
    errors = validate_runtime_settings(
        Settings(
            llm_provider="claude",
            claude_api_key="claude-key",
            llm_usage_mode="paid",
        )
    )

    assert not errors


def test_claude_http_error_returns_validation_error(monkeypatch):
    def fake_post(url: str, *, headers: dict, json: dict, timeout: float):
        del url, headers, json, timeout
        raise httpx.HTTPStatusError(
            "bad request",
            request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
            response=httpx.Response(400),
        )

    monkeypatch.setattr("app.services.llm_access.httpx.post", fake_post)
    access = ClaudeLLMAccess(
        Settings(llm_provider="claude", claude_api_key="claude-key", llm_usage_mode="paid")
    )

    result = access.generate(prompt_type="interpretation", prompt="Return JSON")

    assert result.parsed_payload is None
    assert result.validation_errors
    assert "structured output parse failed" in result.validation_errors[0]


def test_openai_compatible_generate_records_quota_headers(monkeypatch):
    class Headers(dict):
        def items(self):
            return super().items()

    client = FakeClient(content=_payload().model_dump_json())
    client.chat.completions.create = lambda **kwargs: SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=_payload().model_dump_json()))],
        response=SimpleNamespace(
            headers=Headers(
                {
                    "x-ratelimit-limit-requests": "500",
                    "x-ratelimit-remaining-requests": "498",
                    "x-ratelimit-limit-tokens": "10000",
                    "x-ratelimit-remaining-tokens": "9000",
                }
            )
        ),
        usage={"prompt_tokens": 12, "completion_tokens": 8},
    )

    def fake_openai(*, api_key: str | None = None, base_url: str | None = None, **kwargs):
        del api_key, base_url, kwargs
        return client

    monkeypatch.setattr("app.services.llm_access.OpenAI", fake_openai)
    access = GeminiLLMAccess(Settings(gemini_api_key="gem-key"))

    result = access.generate(prompt_type="interpretation", prompt="Return JSON")

    assert result.quota_observation is not None
    assert result.quota_observation["requests_remaining"] == 498
    assert result.quota_observation["tokens_remaining"] == 9000
    assert result.quota_observation["usage_tokens_input"] == 12
    assert result.quota_observation["daily_request_limit"] == 1000



def test_claude_generate_records_quota_headers(monkeypatch):
    class QuotaClaudeResponse(FakeClaudeResponse):
        def __init__(self, payload: dict):
            super().__init__(payload)
            self.headers = {
                "anthropic-ratelimit-requests-limit": "50",
                "anthropic-ratelimit-requests-remaining": "47",
                "anthropic-ratelimit-tokens-limit": "30000",
                "anthropic-ratelimit-tokens-remaining": "28000",
            }

    def fake_post(url: str, *, headers: dict, json: dict, timeout: float):
        del url, headers, json, timeout
        payload = _payload(reasoning_summary="claude result")
        return QuotaClaudeResponse(
            {
                "content": [{"type": "text", "text": payload.model_dump_json()}],
                "usage": {"input_tokens": 20, "output_tokens": 10},
            }
        )

    monkeypatch.setattr("app.services.llm_access.httpx.post", fake_post)
    access = ClaudeLLMAccess(Settings(llm_provider="claude", claude_api_key="claude-key", llm_usage_mode="paid"))

    result = access.generate(prompt_type="interpretation", prompt="Return JSON")

    assert result.quota_observation is not None
    assert result.quota_observation["requests_remaining"] == 47
    assert result.quota_observation["tokens_remaining"] == 28000
    assert result.quota_observation["usage_tokens_input"] == 20
