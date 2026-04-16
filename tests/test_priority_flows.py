from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import pytest

from app.ops.postgres_backup_restore_support.models import BackupArtifact, ObjectStoreConfig
from app.ops.postgres_backup_restore_support.object_store import (
    BackupIntegrityError,
    BackupMetadataError,
    BackupObjectStoreError,
    _resolve_backup_source,
    infer_metadata_reference_from_backup_reference,
    resolve_object_store_config,
    upload_backup_set,
    verify_backup_artifact_integrity,
)


def _headers(user: str = "user-1", tenant: str = "tenant-1") -> dict[str, str]:
    return {"X-User-Id": user, "X-Tenant-Id": tenant}


def _create_cycle(client, *, user: str, project_id: str, key: str) -> str:
    response = client.post(
        "/v1/cycles",
        headers={**_headers(user), "Idempotency-Key": key},
        json={"project_id": project_id, "user_input": f"payload-{key}"},
    )
    assert response.status_code == 201
    return response.json()["data"]["cycle_id"]


def test_cycle_result_requires_terminal_state(client) -> None:
    cycle_id = _create_cycle(client, user="result-owner", project_id="proj-result", key="result-guard")

    response = client.get(f"/v1/cycles/{cycle_id}/result", headers=_headers("result-owner"))

    assert response.status_code == 409
    assert "result not available" in response.json()["error"]["message"].lower()


def test_cycle_result_returns_not_found_for_missing_cycle(client) -> None:
    response = client.get("/v1/cycles/cycle-missing/result", headers=_headers("result-owner"))

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "cycle result not found"


def test_workspace_discussion_filter_mutations_enforce_owner_scope(client) -> None:
    created = client.post(
        "/v1/workspace/discussion-filters",
        headers=_headers("filter-owner"),
        json={"name": "triage", "project_id": "proj-a", "mention": "alice", "query": "failure"},
    )
    assert created.status_code == 200
    filter_id = created.json()["data"]["filter_id"]

    intruder_headers = _headers("filter-intruder")

    update = client.patch(
        f"/v1/workspace/discussion-filters/{filter_id}",
        headers=intruder_headers,
        json={"name": "owned", "project_id": "proj-a", "mention": "alice", "query": "timeout"},
    )
    favorite = client.post(
        f"/v1/workspace/discussion-filters/{filter_id}/favorite",
        headers=intruder_headers,
        json={"is_favorite": True},
    )
    used = client.post(f"/v1/workspace/discussion-filters/{filter_id}/use", headers=intruder_headers)
    deleted = client.delete(f"/v1/workspace/discussion-filters/{filter_id}", headers=intruder_headers)

    assert update.status_code == 403
    assert favorite.status_code == 403
    assert used.status_code == 403
    assert deleted.status_code == 403


def test_workspace_discussion_filter_mutations_return_not_found_for_unknown_filter(client) -> None:
    headers = _headers("filter-owner")

    update = client.patch(
        "/v1/workspace/discussion-filters/filter-missing",
        headers=headers,
        json={"name": "missing", "project_id": "proj-a", "mention": "alice", "query": "timeout"},
    )
    favorite = client.post(
        "/v1/workspace/discussion-filters/filter-missing/favorite",
        headers=headers,
        json={"is_favorite": True},
    )
    used = client.post("/v1/workspace/discussion-filters/filter-missing/use", headers=headers)
    deleted = client.delete("/v1/workspace/discussion-filters/filter-missing", headers=headers)

    assert update.status_code == 404
    assert favorite.status_code == 404
    assert used.status_code == 404
    assert deleted.status_code == 404


def test_resolve_object_store_config_uses_r2_defaults(monkeypatch) -> None:
    monkeypatch.setenv("BACKUP_R2_BUCKET", "bucket-a")
    monkeypatch.setenv("BACKUP_R2_PREFIX", "team/backups")
    monkeypatch.setenv("BACKUP_R2_ACCOUNT_ID", "acct-123")
    monkeypatch.setenv("BACKUP_R2_ACCESS_KEY_ID", "key-123")
    monkeypatch.setenv("BACKUP_R2_SECRET_ACCESS_KEY", "secret-123")

    config = resolve_object_store_config()

    assert config is not None
    assert config.bucket == "bucket-a"
    assert config.prefix == "team/backups"
    assert config.region == "auto"
    assert config.endpoint_url == "https://acct-123.r2.cloudflarestorage.com"
    assert config.access_key_id == "key-123"
    assert config.secret_access_key == "secret-123"


def test_upload_backup_set_records_prefixed_artifact_and_metadata(monkeypatch, tmp_path) -> None:
    calls: list[tuple[Path, str, str | None]] = []

    def fake_upload(path: Path, *, config: ObjectStoreConfig, key: str, content_type: str | None = None) -> str:
        calls.append((path, key, content_type))
        return f"s3://{config.bucket}/{key}"

    fixed_time = datetime(2026, 4, 16, 1, 2, 3, tzinfo=timezone.utc)

    monkeypatch.setattr("app.ops.postgres_backup_restore.upload_file_to_object_store", fake_upload)
    monkeypatch.setattr("app.ops.postgres_backup_restore_support.object_store._now_utc", lambda: fixed_time)

    dump_path = tmp_path / "backup.dump.enc"
    dump_path.write_text("encrypted", encoding="utf-8")
    metadata_path = tmp_path / "backup.dump.metadata.json"
    metadata_path.write_text("{}", encoding="utf-8")

    artifact = BackupArtifact(
        dump_path=dump_path,
        metadata_path=metadata_path,
        metadata={"version": 1},
    )
    config = ObjectStoreConfig(bucket="bucket-a", prefix="daily", endpoint_url="https://acct.r2.cloudflarestorage.com")

    uploaded = upload_backup_set(artifact, config=config)

    assert calls == [
        (dump_path, "daily/backup.dump.enc", "application/octet-stream"),
        (metadata_path, "daily/backup.dump.metadata.json", "application/json"),
    ]
    assert uploaded["provider"] == "cloudflare-r2"
    assert uploaded["artifact_uri"] == "s3://bucket-a/daily/backup.dump.enc"
    assert uploaded["metadata_uri"] == "s3://bucket-a/daily/backup.dump.metadata.json"
    assert uploaded["uploaded_at"] == fixed_time.isoformat()


def test_resolve_backup_source_downloads_artifact_and_metadata_for_s3(monkeypatch, tmp_path) -> None:
    download_calls: list[str] = []

    def fake_download(reference: str, *, destination_path: Path, config=None) -> Path:
        download_calls.append(reference)
        destination_path.write_text(reference, encoding="utf-8")
        return destination_path

    def fake_metadata_loader(path: Path) -> dict[str, str]:
        return {"loaded_from": path.name}

    monkeypatch.setattr("app.ops.postgres_backup_restore.download_file_from_object_store", fake_download)
    monkeypatch.setattr("app.ops.postgres_backup_restore.load_backup_metadata", fake_metadata_loader)

    reference = "s3://bucket-a/archives/backup.dump.enc"
    artifact_path, metadata, backup_ref, metadata_ref, temporary_directory = _resolve_backup_source(reference)

    assert artifact_path.name == "backup.dump.enc"
    assert metadata == {"loaded_from": "backup.dump.metadata.json"}
    assert backup_ref == reference
    assert metadata_ref == infer_metadata_reference_from_backup_reference(reference)
    assert download_calls == [reference, metadata_ref]
    assert temporary_directory is not None
    temporary_directory.cleanup()




def test_upload_backup_set_cleans_up_artifact_when_metadata_upload_fails(monkeypatch, tmp_path) -> None:
    uploads: list[str] = []
    deletions: list[str] = []

    def fake_upload(path: Path, *, config: ObjectStoreConfig, key: str, content_type: str | None = None) -> str:
        uploads.append(key)
        if content_type == "application/json":
            raise RuntimeError("metadata upload failed")
        return f"s3://{config.bucket}/{key}"

    def fake_delete(reference: str, *, config: ObjectStoreConfig | None = None) -> None:
        deletions.append(reference)

    monkeypatch.setattr("app.ops.postgres_backup_restore.upload_file_to_object_store", fake_upload)
    monkeypatch.setattr("app.ops.postgres_backup_restore.delete_file_from_object_store", fake_delete)

    dump_path = tmp_path / "backup.dump.enc"
    dump_path.write_text("encrypted", encoding="utf-8")
    metadata_path = tmp_path / "backup.dump.metadata.json"
    metadata_path.write_text("{}", encoding="utf-8")
    artifact = BackupArtifact(dump_path=dump_path, metadata_path=metadata_path, metadata={"version": 1})
    config = ObjectStoreConfig(bucket="bucket-a", prefix="daily")

    with pytest.raises(BackupObjectStoreError, match="Failed to upload backup set"):
        upload_backup_set(artifact, config=config)

    assert uploads == ["daily/backup.dump.enc", "daily/backup.dump.metadata.json"]
    assert deletions == [
        "s3://bucket-a/daily/backup.dump.enc",
        "s3://bucket-a/daily/backup.dump.metadata.json",
    ]


def test_resolve_backup_source_raises_metadata_error_for_invalid_s3_metadata(monkeypatch) -> None:
    def fake_download(reference: str, *, destination_path: Path, config=None) -> Path:
        destination_path.write_text(reference, encoding="utf-8")
        return destination_path

    def fake_metadata_loader(path: Path) -> dict[str, str]:
        raise __import__("json").JSONDecodeError("bad", "{}", 0)

    monkeypatch.setattr("app.ops.postgres_backup_restore.download_file_from_object_store", fake_download)
    monkeypatch.setattr("app.ops.postgres_backup_restore.load_backup_metadata", fake_metadata_loader)

    reference = "s3://bucket-a/archives/backup.dump.enc"
    with pytest.raises(BackupMetadataError, match="invalid JSON"):
        _resolve_backup_source(reference)


def test_verify_backup_artifact_integrity_rejects_checksum_mismatch(monkeypatch, tmp_path) -> None:
    artifact_path = tmp_path / "backup.dump.enc"
    artifact_path.write_text("encrypted", encoding="utf-8")

    monkeypatch.setattr("app.ops.postgres_backup_restore._sha256_file", lambda path: "actual-sha")

    with pytest.raises(BackupIntegrityError, match="checksum mismatch"):
        verify_backup_artifact_integrity(
            artifact_path,
            {"artifact_sha256": "expected-sha", "artifact_size_bytes": artifact_path.stat().st_size},
        )
