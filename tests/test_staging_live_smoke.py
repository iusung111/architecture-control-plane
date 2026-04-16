from pathlib import Path

import pytest

from scripts import staging_live_smoke


def test_staging_live_smoke_script_supports_quota_refresh_and_backup_drill() -> None:
    script = Path("scripts/staging_live_smoke.py").read_text()
    assert "STAGING_REFRESH_QUOTA_PROVIDERS" in script
    assert "acp_rate_limit_backend_healthy" in script
    assert "scripts/postgres_backup_restore.py" in script
    assert "STAGING_DATABASE_URL" in script
    assert "STAGING_DRILL_DATABASE_URL" in script
    assert "STAGING_EXPECT_OBJECT_STORE_UPLOAD" in script
    assert "STAGING_VERIFY_LIVE_ROUTING" in script
    assert "STAGING_TRIGGER_BACKUP_DRILL_VIA_API" in script
    assert "STAGING_BACKUP_DRILL_IDEMPOTENCY_KEY" in script
    assert "/v1/admin/audit/events" in script



def test_staging_live_smoke_workflow_supports_optional_backup_and_r2_secrets() -> None:
    workflow = Path(".github/workflows/staging-live-smoke.yml").read_text()
    assert "Install PostgreSQL client" in workflow
    assert "STAGING_REFRESH_QUOTA_PROVIDERS" in workflow
    assert "STAGING_DATABASE_URL" in workflow
    assert "STAGING_DRILL_DATABASE_URL" in workflow
    assert "STAGING_DRILL_TARGET_NAME" in workflow
    assert "BACKUP_R2_BUCKET" in workflow
    assert "STAGING_VERIFY_ADMIN_WRITE" in workflow
    assert 'if [ "$STAGING_TRIGGER_BACKUP_DRILL_VIA_API" = "true" ]' in workflow
    assert "STAGING_EXPECT_OBJECT_STORE_UPLOAD" in workflow
    assert "Upload staging smoke backup drill artifacts" in workflow



def test_staging_live_smoke_mentions_admin_ops_paths():
    script = Path("scripts/staging_live_smoke.py").read_text()
    assert "/v1/admin/ops/abuse/config" in script
    assert "/v1/admin/ops/backups/config" in script
    assert "/v1/admin/ops/backups/drill/run" in script
    assert "/v1/admin/ops/backups/drill/jobs/" in script
    assert "DELETE /v1/admin/ops/backups/drill/jobs/{job_id}" in script
    assert "STAGING_DRILL_TARGET_NAME" in script
    assert "/v1/admin/ops/observability/status" in script


def test_staging_live_smoke_allows_null_review_preview_without_review_provider() -> None:
    staging_live_smoke._assert_review_preview(
        {"review": None},
        [{"provider": "gemini", "configured": False, "enabled": False, "allow_review": False}],
    )


def test_staging_live_smoke_rejects_null_review_preview_with_review_provider() -> None:
    with pytest.raises(RuntimeError, match="omitted review decision"):
        staging_live_smoke._assert_review_preview(
            {"review": None},
            [{"provider": "gemini", "configured": True, "enabled": True, "allow_review": True}],
        )
