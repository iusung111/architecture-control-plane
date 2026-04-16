from __future__ import annotations

from subprocess import TimeoutExpired

from fastapi.testclient import TestClient

from app.api.deps import get_management_config_service
from app.main import app
from app.services.management_config import ManagementConfigResponse


def _mgmt_headers(api_key: str, *, idempotency_key: str | None = None) -> dict[str, str]:
    headers = {"X-Management-Key": api_key}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    return headers


class _TimeoutConfigService:
    def get_abuse_config(self):
        return ManagementConfigResponse(
            namespace="test",
            effective={"enabled": True},
            overrides={},
            applies_immediately=True,
            applies_on_restart=False,
        )

    get_backup_config = get_abuse_config
    get_observability_config = get_abuse_config

    def update_abuse_config(self, payload):
        del payload
        raise TimeoutExpired(cmd=["backup"], timeout=11)

    def update_backup_config(self, payload):
        del payload
        raise TimeoutExpired(cmd=["backup"], timeout=17)

    def update_observability_config(self, payload):
        del payload
        raise TimeoutExpired(cmd=["backup"], timeout=23)

    def get_backup_drill_job_status(self, job_id):
        del job_id
        return None

    def cancel_backup_drill(self, job_id):
        del job_id
        return None



def test_admin_ops_timeout_and_not_found_paths(client: TestClient, management_api_keys):
    app.dependency_overrides[get_management_config_service] = lambda: _TimeoutConfigService()
    admin_headers = _mgmt_headers(management_api_keys["admin"])
    operator_headers = _mgmt_headers(management_api_keys["operator"])
    try:
        abuse = client.put("/v1/admin/ops/abuse/config", headers=admin_headers, json={"payload": {"enabled": False}})
        assert abuse.status_code == 504
        assert abuse.json()["error"]["message"] == "backup drill timed out after 11 seconds"

        backups = client.put(
            "/v1/admin/ops/backups/config",
            headers=admin_headers,
            json={"payload": {"retention_keep_last": 5}},
        )
        assert backups.status_code == 504
        assert backups.json()["error"]["message"] == "backup drill timed out after 17 seconds"

        observability = client.put(
            "/v1/admin/ops/observability/config",
            headers=admin_headers,
            json={"payload": {"metrics_enabled": False}},
        )
        assert observability.status_code == 504
        assert observability.json()["error"]["message"] == "backup drill timed out after 23 seconds"

        missing_status = client.get("/v1/admin/ops/backups/drill/jobs/missing-job", headers=operator_headers)
        assert missing_status.status_code == 404
        assert missing_status.json()["error"]["message"] == "backup drill job not found"

        missing_cancel = client.delete("/v1/admin/ops/backups/drill/jobs/missing-job", headers=admin_headers)
        assert missing_cancel.status_code == 404
        assert missing_cancel.json()["error"]["message"] == "backup drill job not found"
    finally:
        app.dependency_overrides.pop(get_management_config_service, None)
