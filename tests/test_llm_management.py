from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.main import app
from app.services.llm_management import LLMRoutingService


def _management_client(db_session, monkeypatch) -> TestClient:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    return client


def test_llm_provider_listing_and_preview_use_distinct_review_provider_and_session(db_session, monkeypatch):
    monkeypatch.setenv("MANAGEMENT_ENDPOINTS_REQUIRE_API_KEY", "true")
    monkeypatch.setenv("MANAGEMENT_API_KEYS_JSON", '{"viewer-secret":"viewer","mgmt-secret":"admin"}')
    monkeypatch.setenv("GEMINI_API_KEY", "gem-key")
    monkeypatch.setenv("CLOUDFLARE_AI_API_TOKEN", "cf-token")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct-123")

    client = _management_client(db_session, monkeypatch)
    try:
        response = client.get("/v1/admin/llm/providers", headers={"X-Management-Key": "mgmt-secret"})
        assert response.status_code == 200
        providers = {item["provider"]: item for item in response.json()["data"]["providers"]}
        assert providers["gemini"]["enabled"] is True
        assert providers["cloudflare_workers_ai"]["enabled"] is True
        assert providers["cloudflare_workers_ai"]["allow_review"] is False

        preview = client.post(
            "/v1/admin/llm/routing/preview",
            headers={"X-Management-Key": "mgmt-secret"},
            json={"prompt_type": "review", "complexity": "low", "review_required": True},
        )
        assert preview.status_code == 200
        payload = preview.json()["data"]
        assert payload["assignment_group_id"]
        assert payload["work"]["provider"] == "cloudflare_workers_ai"
        assert payload["review"]["provider"] == "gemini"
        assert payload["review"]["provider"] != payload["work"]["provider"]
        assert payload["work"]["session_mode"] == "job_session"
        assert payload["review"]["session_mode"] == "fresh_review_session"
        assert payload["review"]["requires_fresh_session"] is True
        assert payload["review"]["session_id"] != payload["work"]["session_id"]
        assert payload["review"]["source_session_id"] == payload["work"]["session_id"]
    finally:
        client.close()
        app.dependency_overrides.clear()



def test_llm_provider_policy_update_changes_selection(db_session, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gem-key")
    service = LLMRoutingService(db_session)

    updated = service.update_policy(
        "gemini",
        enabled=True,
        allow_work=False,
        allow_review=True,
        usage_mode="free_only",
        priority=200,
        daily_request_limit_override=2,
    )
    service.update_policy(
        "openai",
        enabled=True,
        allow_work=True,
        allow_review=True,
        usage_mode="paid",
        priority=150,
    )
    assert updated.allow_work is False
    assert updated.daily_limit == 2

    preview = service.preview_assignment(prompt_type="verification", complexity="high", review_required=True)
    assert preview["work"]["provider"] == "openai"
    assert preview["review"]["provider"] == "gemini"
    assert preview["review"]["session_id"] != preview["work"]["session_id"]
    assert preview["review"]["source_session_id"] == preview["work"]["session_id"]



def test_llm_assignment_records_usage_and_review_uses_fresh_session_even_on_same_provider_fallback(db_session, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gem-key")
    service = LLMRoutingService(db_session)
    service.update_policy(
        "gemini",
        enabled=True,
        allow_work=True,
        allow_review=True,
        usage_mode="free_only",
        priority=100,
        daily_request_limit_override=5,
    )
    for provider in ["openai", "grok", "claude", "cloudflare_workers_ai"]:
        service.update_policy(
            provider, enabled=False, allow_work=False, allow_review=False, usage_mode="free_only", priority=1
        )

    assignment = service.assign_for_job(
        cycle_id="cycle-1",
        prompt_type="verification",
        complexity="medium",
        review_required=True,
    )
    assert assignment["work"]["provider"] == "gemini"
    assert assignment["review"]["provider"] == "gemini"
    assert assignment["review"]["rationale"]["same_provider_fallback"] is True
    assert assignment["review"]["requires_fresh_session"] is True
    assert assignment["review"]["session_id"] != assignment["work"]["session_id"]
    assert assignment["review"]["source_session_id"] == assignment["work"]["session_id"]

    statuses = {item.provider: item for item in service.list_provider_statuses()}
    assert statuses["gemini"].used_today == 2
    assert statuses["gemini"].remaining_today == 3


def test_llm_scope_override_changes_preview_for_project_and_tenant(db_session, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gem-key")
    service = LLMRoutingService(db_session)

    service.update_policy(
        "openai",
        enabled=True,
        allow_work=True,
        allow_review=True,
        usage_mode="paid",
        priority=120,
    )
    service.update_policy(
        "gemini",
        enabled=True,
        allow_work=True,
        allow_review=True,
        usage_mode="free_only",
        priority=100,
    )

    service.upsert_scope_override(
        scope_type="tenant",
        scope_id="tenant-a",
        provider="gemini",
        enabled_override=False,
    )
    service.upsert_scope_override(
        scope_type="project",
        scope_id="proj-1",
        provider="openai",
        priority_offset=50,
    )

    preview = service.preview_assignment(
        prompt_type="verification",
        complexity="medium",
        review_required=True,
        tenant_id="tenant-a",
        project_id="proj-1",
    )

    assert preview["work"]["provider"] == "openai"
    assert preview["work"]["rationale"]["effective_scope"] == "project"
    overrides = service.list_scope_overrides("tenant", "tenant-a")
    assert overrides[0].provider == "gemini"
    assert overrides[0].enabled_override is False



def test_llm_provider_quota_refresh_uses_openai_usage_api(db_session, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")

    class FakeGetResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": [
                    {"input_tokens": 120, "output_tokens": 45, "num_model_requests": 3},
                    {"input_tokens": 80, "output_tokens": 20, "num_model_requests": 2},
                ]
            }

    class FakePostResponse:
        headers = {
            "x-ratelimit-limit-requests": "5000",
            "x-ratelimit-remaining-requests": "4999",
            "x-ratelimit-limit-tokens": "40000",
            "x-ratelimit-remaining-tokens": "39980",
        }

        def raise_for_status(self):
            return None

        def json(self):
            return {"usage": {"prompt_tokens": 20, "completion_tokens": 5}}

    def fake_get(url: str, *, params: dict, headers: dict, timeout: float):
        assert url == "https://api.openai.com/v1/organization/usage/completions"
        assert headers["Authorization"] == "Bearer openai-key"
        assert params["start_time"] < params["end_time"]
        assert timeout == 20.0
        return FakeGetResponse()

    def fake_post(url: str, *, headers: dict, json: dict, timeout: float):
        assert url == "https://api.openai.com/v1/chat/completions"
        assert headers["Authorization"] == "Bearer openai-key"
        assert json["model"]
        assert timeout == 20.0
        return FakePostResponse()

    monkeypatch.setattr("app.services.llm_access.httpx.get", fake_get)
    monkeypatch.setattr("app.services.llm_access.httpx.post", fake_post)
    service = LLMRoutingService(db_session)
    status = service.refresh_provider_quota("openai")

    assert status.external_quota_source == "usage_api+probe_headers"
    assert status.external_daily_used == 5
    assert status.external_usage_tokens_input == 20
    assert status.external_usage_tokens_output == 5
    assert status.external_requests_remaining == 4999
    assert status.external_tokens_remaining == 39980



def test_llm_provider_quota_refresh_supports_gemini_probe(db_session, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gem-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash-lite")

    class FakeResponse:
        headers = {
            "x-ratelimit-limit-requests": "15",
            "x-ratelimit-remaining-requests": "14",
            "x-ratelimit-limit-tokens": "1000000",
            "x-ratelimit-remaining-tokens": "999000",
        }

        def raise_for_status(self):
            return None

        def json(self):
            return {"usage": {"prompt_tokens": 10, "completion_tokens": 2}}

    def fake_post(url: str, *, headers: dict, json: dict, timeout: float):
        assert url.endswith("/chat/completions")
        assert headers["Authorization"] == "Bearer gem-key"
        assert json["model"] == "gemini-2.5-flash-lite"
        assert timeout == 20.0
        return FakeResponse()

    monkeypatch.setattr("app.services.llm_access.httpx.post", fake_post)
    service = LLMRoutingService(db_session)
    status = service.refresh_provider_quota("gemini")

    assert status.external_quota_source == "probe_headers:gemini"
    assert status.external_requests_limit == 15
    assert status.external_requests_remaining == 14
    assert status.external_daily_limit == 1000
    assert status.external_daily_remaining == 999



def test_admin_llm_scope_override_endpoints(db_session, monkeypatch):
    monkeypatch.setenv("MANAGEMENT_ENDPOINTS_REQUIRE_API_KEY", "true")
    monkeypatch.setenv("MANAGEMENT_API_KEYS_JSON", '{"viewer-secret":"viewer","mgmt-secret":"admin"}')
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")

    client = _management_client(db_session, monkeypatch)
    try:
        put_resp = client.put(
            "/v1/admin/llm/scopes/project/proj-9/providers/openai",
            headers={"X-Management-Key": "mgmt-secret"},
            json={"enabled_override": True, "priority_offset": 25, "usage_mode_override": "paid"},
        )
        assert put_resp.status_code == 200
        get_resp = client.get(
            "/v1/admin/llm/scopes/project/proj-9",
            headers={"X-Management-Key": "mgmt-secret"},
        )
        assert get_resp.status_code == 200
        overrides = get_resp.json()["data"]["overrides"]
        assert overrides[0]["provider"] == "openai"
        assert overrides[0]["priority_offset"] == 25
    finally:
        client.close()
        app.dependency_overrides.clear()
