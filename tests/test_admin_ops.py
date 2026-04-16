from subprocess import TimeoutExpired

from fastapi.testclient import TestClient

from app.core.rate_limit import action_limit_profile, enforce_action_limit
from app.workers.default_handlers import build_default_job_handlers
from app.workers.job_runner import JobRunner


def _mgmt_headers(key: str, *, idempotency_key: str | None = None) -> dict[str, str]:
    headers = {"X-Management-Key": key}
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def test_operator_can_read_admin_ops_configs(client: TestClient, management_api_keys):
    operator_key = management_api_keys["operator"]
    response = client.get("/v1/admin/ops/abuse/config", headers=_mgmt_headers(operator_key))
    assert response.status_code == 200
    response = client.get("/v1/admin/ops/backups/config", headers=_mgmt_headers(operator_key))
    assert response.status_code == 200
    response = client.get("/v1/admin/ops/observability/status", headers=_mgmt_headers(operator_key))
    assert response.status_code == 200
    response = client.post("/v1/admin/ops/backups/drill/preview", headers=_mgmt_headers(operator_key))
    assert response.status_code == 200


def test_viewer_cannot_read_operator_admin_ops(client: TestClient, management_api_keys):
    viewer_key = management_api_keys["viewer"]
    response = client.get("/v1/admin/ops/abuse/config", headers=_mgmt_headers(viewer_key))
    assert response.status_code == 403


def test_admin_can_update_abuse_config_and_runtime_effect(client: TestClient, db_session, management_api_keys):
    admin_key = management_api_keys["admin"]
    response = client.put(
        "/v1/admin/ops/abuse/config",
        headers=_mgmt_headers(admin_key),
        json={"payload": {"cycle_create_limit_per_minute": 1, "rate_limit_algorithm": "fixed_window"}},
    )
    assert response.status_code == 200
    profile = action_limit_profile("cycle_create", user_id="user-1", tenant_id="tenant-free", role="operator")
    from types import SimpleNamespace
    req = SimpleNamespace(url=SimpleNamespace(path="/v1/cycles"), headers={}, client=SimpleNamespace(host="127.0.0.1"))
    enforce_action_limit(req, profile)
    try:
        enforce_action_limit(req, profile)
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 429
    else:
        raise AssertionError("expected second request to be rate limited")


def test_admin_updates_are_audited(client: TestClient, management_api_keys):
    admin_key = management_api_keys["admin"]
    response = client.put(
        "/v1/admin/ops/backups/config",
        headers=_mgmt_headers(admin_key),
        json={"payload": {"retention_keep_last": 3}},
    )
    assert response.status_code == 200
    events = client.get("/v1/admin/audit/events", headers=_mgmt_headers(admin_key)).json()["data"]["events"]
    assert any(event["event_type"] == "management.backup_config.updated" for event in events)


def test_admin_can_queue_backup_drill_and_read_pending_status(client: TestClient, management_api_keys, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("BACKUP_DRILL_TARGET_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/restore_target")
    get_settings.cache_clear()
    admin_key = management_api_keys["admin"]

    response = client.post(
        "/v1/admin/ops/backups/drill/run",
        headers=_mgmt_headers(admin_key, idempotency_key="backup-drill-pending-1"),
        json={"target_name": "default", "label": "test-drill"},
    )
    assert response.status_code == 202
    data = response.json()["data"]
    assert data["target_name"] == "default"
    assert data["accepted"] is True
    assert data["state"] == "pending"
    assert data["stage"] == "queued"
    assert data["deduplicated"] is False
    assert data["status_url"].endswith(f"/{data['job_id']}")

    status_response = client.get(data["status_url"], headers=_mgmt_headers(management_api_keys["operator"]))
    assert status_response.status_code == 200
    status_data = status_response.json()["data"]
    assert status_data["job_id"] == data["job_id"]
    assert status_data["state"] == "pending"
    assert status_data["stage"] == "queued"
    assert status_data["report"] is None

    events = client.get("/v1/admin/audit/events", headers=_mgmt_headers(admin_key)).json()["data"]["events"]
    assert any(event["event_type"] == "management.backup_drill.triggered" for event in events)


def test_admin_backup_drill_job_completes_via_worker_and_status_endpoint(client: TestClient, db_session, management_api_keys, monkeypatch):
    from app.core.config import get_settings
    from app.services import management_config as management_config_module

    monkeypatch.setenv("BACKUP_DRILL_TARGET_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/restore_target")
    get_settings.cache_clear()
    captured: dict[str, object] = {}

    def fake_run_backup_restore_drill(source_database_url, target_database_url, **kwargs):
        captured["source_database_url"] = source_database_url
        captured["target_database_url"] = target_database_url
        captured.update(kwargs)
        return {
            "started_at": "2026-01-01T00:00:00+00:00",
            "completed_at": "2026-01-01T00:00:01+00:00",
            "duration_seconds": 1.0,
            "source_database_url": "postgresql+psycopg://postgres:***@localhost:5432/control_plane",
            "target_database_url": "postgresql+psycopg://postgres:***@localhost:5432/restore_target",
            "backup": {"artifact_path": "backups/test.dump"},
            "restore": {"backup_file": "backups/test.dump"},
            "verification": {"missing_tables": []},
            "status": "ok",
            "report_file": "backups/report.json",
        }

    monkeypatch.setattr(management_config_module, "run_backup_restore_drill", fake_run_backup_restore_drill)
    admin_key = management_api_keys["admin"]
    response = client.post(
        "/v1/admin/ops/backups/drill/run",
        headers=_mgmt_headers(admin_key, idempotency_key="backup-drill-worker-1"),
        json={"target_name": "default", "label": "test-drill"},
    )
    assert response.status_code == 202
    job_id = response.json()["data"]["job_id"]

    run_result = JobRunner(db_session, handlers=build_default_job_handlers(db_session)).run_once(worker_id="worker-backup", limit=10)
    assert run_result.succeeded == 1

    status_response = client.get(f"/v1/admin/ops/backups/drill/jobs/{job_id}", headers=_mgmt_headers(management_api_keys["operator"]))
    assert status_response.status_code == 200
    status_data = status_response.json()["data"]
    assert status_data["state"] == "succeeded"
    assert status_data["stage"] == "completed"
    assert status_data["report"]["target_name"] == "default"
    assert status_data["report"]["status"] == "ok"
    assert captured["target_database_url"] == "postgresql+psycopg://postgres:postgres@localhost:5432/restore_target"
    assert captured["label"] == "test-drill"

    events = client.get("/v1/admin/audit/events", headers=_mgmt_headers(admin_key)).json()["data"]["events"]
    assert any(event["event_type"] == "management.backup_drill.completed" for event in events)


def test_admin_backup_drill_rejects_unknown_target_name(client: TestClient, management_api_keys, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("BACKUP_DRILL_TARGET_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/restore_target")
    get_settings.cache_clear()
    admin_key = management_api_keys["admin"]
    response = client.post(
        "/v1/admin/ops/backups/drill/run",
        headers=_mgmt_headers(admin_key, idempotency_key="backup-drill-invalid-target-1"),
        json={"target_name": "missing-target"},
    )
    assert response.status_code == 422
    assert "unknown target_name" in response.json()["error"]["message"]


def test_operator_cannot_trigger_backup_drill(client: TestClient, management_api_keys):
    operator_key = management_api_keys["operator"]
    response = client.post(
        "/v1/admin/ops/backups/drill/run",
        headers=_mgmt_headers(operator_key, idempotency_key="backup-drill-forbidden-1"),
        json={"target_name": "default"},
    )
    assert response.status_code == 403


def test_admin_backup_drill_timeout_dead_letters_job(client: TestClient, db_session, management_api_keys, monkeypatch):
    from app.core.config import get_settings
    from app.services import management_config as management_config_module

    monkeypatch.setenv("BACKUP_DRILL_TARGET_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/restore_target")
    get_settings.cache_clear()

    def fake_run_backup_restore_drill(source_database_url, target_database_url, **kwargs):
        del source_database_url, target_database_url, kwargs
        raise TimeoutExpired(cmd=["pg_dump"], timeout=7)

    monkeypatch.setattr(management_config_module, "run_backup_restore_drill", fake_run_backup_restore_drill)
    admin_key = management_api_keys["admin"]
    response = client.post(
        "/v1/admin/ops/backups/drill/run",
        headers=_mgmt_headers(admin_key, idempotency_key="backup-drill-timeout-1"),
        json={"target_name": "default"},
    )
    assert response.status_code == 202
    job_id = response.json()["data"]["job_id"]

    run_result = JobRunner(db_session, handlers=build_default_job_handlers(db_session)).run_once(worker_id="worker-backup", limit=10)
    assert run_result.dead_lettered == 1

    status_response = client.get(f"/v1/admin/ops/backups/drill/jobs/{job_id}", headers=_mgmt_headers(management_api_keys["operator"]))
    assert status_response.status_code == 200
    status_data = status_response.json()["data"]
    assert status_data["state"] == "dead_lettered"
    assert status_data["stage"] == "failed"
    assert status_data["last_error"] == "backup drill timed out after 7 seconds"

    events = client.get("/v1/admin/audit/events", headers=_mgmt_headers(admin_key)).json()["data"]["events"]
    assert any(event["event_type"] == "management.backup_drill.failed" for event in events)


def test_admin_backup_drill_reuses_existing_job_for_same_idempotency_key(client: TestClient, management_api_keys, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("BACKUP_DRILL_TARGET_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/restore_target")
    get_settings.cache_clear()
    admin_key = management_api_keys["admin"]
    headers = _mgmt_headers(admin_key, idempotency_key="backup-drill-dedup-1")

    first = client.post(
        "/v1/admin/ops/backups/drill/run",
        headers=headers,
        json={"target_name": "default", "label": "test-drill"},
    )
    second = client.post(
        "/v1/admin/ops/backups/drill/run",
        headers=headers,
        json={"target_name": "default", "label": "test-drill"},
    )

    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json()["data"]["job_id"] == first.json()["data"]["job_id"]
    assert second.json()["data"]["deduplicated"] is True



def test_admin_can_cancel_pending_backup_drill_job(client: TestClient, management_api_keys, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("BACKUP_DRILL_TARGET_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/restore_target")
    get_settings.cache_clear()
    admin_key = management_api_keys["admin"]
    response = client.post(
        "/v1/admin/ops/backups/drill/run",
        headers=_mgmt_headers(admin_key, idempotency_key="backup-drill-cancel-1"),
        json={"target_name": "default"},
    )
    assert response.status_code == 202
    job_id = response.json()["data"]["job_id"]

    cancel = client.delete(f"/v1/admin/ops/backups/drill/jobs/{job_id}", headers=_mgmt_headers(admin_key))
    assert cancel.status_code == 200
    status_data = cancel.json()["data"]
    assert status_data["state"] == "cancelled"
    assert status_data["stage"] == "cancelled"
    assert status_data["cancellation_requested"] is True

    fetched = client.get(f"/v1/admin/ops/backups/drill/jobs/{job_id}", headers=_mgmt_headers(management_api_keys["operator"]))
    assert fetched.status_code == 200
    assert fetched.json()["data"]["state"] == "cancelled"

    events = client.get("/v1/admin/audit/events", headers=_mgmt_headers(admin_key)).json()["data"]["events"]
    assert any(event["event_type"] == "management.backup_drill.cancel_requested" for event in events)
