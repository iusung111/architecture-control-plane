from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.deps import get_db
from app.db.models import AuditEvent
from app.main import app


def _management_client(db_session, monkeypatch) -> TestClient:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    return client


def test_management_keys_json_allows_viewer_for_runbooks_and_denies_admin_routes(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("MANAGEMENT_ENDPOINTS_REQUIRE_API_KEY", "true")
    monkeypatch.setenv("MANAGEMENT_API_KEYS_JSON", '{"viewer-secret":"viewer","admin-secret":"admin"}')

    runbooks = client.get("/runbooks", headers={"X-Management-Key": "viewer-secret"})
    assert runbooks.status_code == 200

    admin = client.get("/v1/admin/llm/providers", headers={"X-Management-Key": "viewer-secret"})
    assert admin.status_code == 403
    assert admin.json()["error"]["message"] == "management role is insufficient"


def test_management_keys_json_allows_admin_for_admin_routes(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("MANAGEMENT_ENDPOINTS_REQUIRE_API_KEY", "true")
    monkeypatch.setenv("MANAGEMENT_API_KEYS_JSON", '{"viewer-secret":"viewer","admin-secret":"admin"}')
    monkeypatch.setenv("GEMINI_API_KEY", "gem-key")

    response = client.get("/v1/admin/llm/providers", headers={"X-Management-Key": "admin-secret"})
    assert response.status_code == 200
    assert response.json()["data"]["providers"]


def test_staging_live_smoke_assets_exist() -> None:
    workflow = Path(".github/workflows/staging-live-smoke.yml").read_text()
    docs = Path("docs/STAGING_LIVE_SMOKE.md").read_text()
    script = Path("scripts/staging_live_smoke.py").read_text()

    assert "STAGING_MANAGEMENT_VIEWER_KEY" in workflow
    assert "STAGING_MANAGEMENT_ADMIN_KEY" in workflow
    assert "staging live smoke" in docs.lower()
    assert "/v1/admin/llm/routing/preview" in script


def test_admin_llm_updates_are_audited(db_session, monkeypatch) -> None:
    monkeypatch.setenv("MANAGEMENT_ENDPOINTS_REQUIRE_API_KEY", "true")
    monkeypatch.setenv("MANAGEMENT_API_KEYS_JSON", '{"ops-secret":"operator","admin-secret":"admin"}')
    monkeypatch.setenv("GEMINI_API_KEY", "gem-key")

    client = _management_client(db_session, monkeypatch)
    try:
        response = client.put(
            "/v1/admin/llm/providers/gemini",
            headers={"X-Management-Key": "admin-secret"},
            json={"enabled": True, "allow_work": False, "priority": 210},
        )
        assert response.status_code == 200
        event = db_session.scalar(select(AuditEvent).where(AuditEvent.event_type == "management.llm_provider_policy.updated"))
        assert event is not None
        assert event.actor_id.startswith("management:admin:")
        assert event.event_payload["provider"] == "gemini"
        assert event.event_payload["requested_changes"]["priority"] == 210
        assert event.event_payload["management_role"] == "admin"
    finally:
        client.close()
        app.dependency_overrides.clear()


def test_operator_can_read_admin_llm_and_audit_but_cannot_mutate_admin_llm(db_session, monkeypatch) -> None:
    monkeypatch.setenv("MANAGEMENT_ENDPOINTS_REQUIRE_API_KEY", "true")
    monkeypatch.setenv("MANAGEMENT_API_KEYS_JSON", '{"ops-secret":"operator","admin-secret":"admin"}')
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")

    client = _management_client(db_session, monkeypatch)
    try:
        put_resp = client.put(
            "/v1/admin/llm/providers/openai",
            headers={"X-Management-Key": "admin-secret"},
            json={"enabled": True, "usage_mode": "paid", "priority": 150},
        )
        assert put_resp.status_code == 200

        list_resp = client.get("/v1/admin/llm/providers", headers={"X-Management-Key": "ops-secret"})
        assert list_resp.status_code == 200
        preview_resp = client.post(
            "/v1/admin/llm/routing/preview",
            headers={"X-Management-Key": "ops-secret"},
            json={"prompt_type": "review", "complexity": "medium", "review_required": True},
        )
        assert preview_resp.status_code == 200

        audit_resp = client.get("/v1/admin/audit/events", headers={"X-Management-Key": "ops-secret"})
        assert audit_resp.status_code == 200
        events = audit_resp.json()["data"]["events"]
        assert any(item["event_type"] == "management.llm_provider_policy.updated" for item in events)

        denied = client.put(
            "/v1/admin/llm/providers/openai",
            headers={"X-Management-Key": "ops-secret"},
            json={"enabled": False},
        )
        assert denied.status_code == 403
    finally:
        client.close()
        app.dependency_overrides.clear()


def test_operator_is_denied_backup_drill_trigger(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("MANAGEMENT_ENDPOINTS_REQUIRE_API_KEY", "true")
    monkeypatch.setenv("MANAGEMENT_API_KEYS_JSON", '{"ops-secret":"operator","admin-secret":"admin"}')

    response = client.post("/v1/admin/ops/backups/drill/run", headers={"X-Management-Key": "ops-secret", "Idempotency-Key": "rbac-backup-drill-1"}, json={"target_name": "default"})
    assert response.status_code == 403
