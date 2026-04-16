from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.main import app


def _management_client(db_session) -> TestClient:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)



def test_admin_llm_provider_refresh_update_and_scope_error_paths(db_session, monkeypatch):
    monkeypatch.setenv("MANAGEMENT_ENDPOINTS_REQUIRE_API_KEY", "true")
    monkeypatch.setenv("MANAGEMENT_API_KEYS_JSON", '{"viewer-secret":"viewer","mgmt-secret":"admin"}')
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")

    client = _management_client(db_session)
    try:
        update = client.put(
            "/v1/admin/llm/providers/openai",
            headers={"X-Management-Key": "mgmt-secret"},
            json={"enabled": True, "allow_work": True, "allow_review": False, "usage_mode": "paid", "priority": 175},
        )
        assert update.status_code == 200
        assert update.json()["data"]["provider"] == "openai"
        assert update.json()["data"]["priority"] == 175

        refreshed = client.post(
            "/v1/admin/llm/providers/openai/refresh-quota",
            headers={"X-Management-Key": "mgmt-secret"},
        )
        assert refreshed.status_code == 200
        assert refreshed.json()["data"]["provider"] == "openai"

        unknown_refresh = client.post(
            "/v1/admin/llm/providers/not-a-provider/refresh-quota",
            headers={"X-Management-Key": "mgmt-secret"},
        )
        assert unknown_refresh.status_code == 404
        assert "unsupported provider" in unknown_refresh.json()["error"]["message"]

        unknown_update = client.put(
            "/v1/admin/llm/providers/not-a-provider",
            headers={"X-Management-Key": "mgmt-secret"},
            json={"enabled": True},
        )
        assert unknown_update.status_code == 404
        assert "unsupported provider" in unknown_update.json()["error"]["message"]

        unsupported_scope_list = client.get(
            "/v1/admin/llm/scopes/org/acme",
            headers={"X-Management-Key": "mgmt-secret"},
        )
        assert unsupported_scope_list.status_code == 404
        assert unsupported_scope_list.json()["error"]["message"] == "unsupported scope_type 'org'"

        unsupported_scope_upsert = client.put(
            "/v1/admin/llm/scopes/org/acme/providers/openai",
            headers={"X-Management-Key": "mgmt-secret"},
            json={"enabled_override": True},
        )
        assert unsupported_scope_upsert.status_code == 404
        assert unsupported_scope_upsert.json()["error"]["message"] == "unsupported scope_type 'org'"

        events = client.get("/v1/admin/audit/events", headers={"X-Management-Key": "mgmt-secret"}).json()["data"]["events"]
        event_types = {event["event_type"] for event in events}
        assert "management.llm_provider_policy.updated" in event_types
        assert "management.llm_provider_quota.refreshed" in event_types
    finally:
        client.close()
        app.dependency_overrides.clear()
