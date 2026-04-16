from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from app.ops.postgres_backup_restore import (
    BackupArtifact,
    ObjectStoreConfig,
    admin_database_url,
    backup_database,
    DEFAULT_COMMAND_TIMEOUT_SECONDS,
    build_backup_command,
    build_restore_command,
    decrypt_backup_file,
    encrypt_backup_file,
    format_s3_uri,
    infer_metadata_reference_from_backup_reference,
    parse_s3_uri,
    prune_backup_artifacts,
    rotate_backup_encryption_passphrase,
    resolve_object_store_config,
    restore_database,
    run_backup_restore_drill,
    sanitize_database_url,
    upload_backup_set,
)


def test_sanitize_database_url_redacts_password() -> None:
    assert (
        sanitize_database_url("postgresql+psycopg://user:secret@db.example.test:5432/control_plane")
        == "postgresql+psycopg://user:***@db.example.test:5432/control_plane"
    )


def test_admin_database_url_targets_postgres_database() -> None:
    assert (
        admin_database_url("postgresql+psycopg://user:secret@db.example.test:5432/control_plane")
        == "postgresql+psycopg://user:secret@db.example.test:5432/postgres"
    )


def test_build_backup_command_wraps_docker_compose_service() -> None:
    spec = build_backup_command(
        "postgresql+psycopg://user:secret@localhost:5432/control_plane",
        docker_compose_service="postgres",
    )
    assert spec.argv[:5] == ["docker", "compose", "exec", "-T", "-e"]
    assert "PGPASSWORD=secret" in spec.argv
    assert "pg_dump" in spec.argv
    assert spec.argv[-1] == "postgresql://user@localhost:5432/control_plane"
    assert "secret" not in spec.argv[-1]
    assert spec.source == "docker-compose:postgres"


def test_build_restore_command_direct_uses_pg_restore() -> None:
    spec = build_restore_command("postgresql+psycopg://user:secret@localhost:5432/control_plane")
    assert spec.argv[0] == "pg_restore"
    assert "--dbname" in spec.argv
    assert spec.argv[-1] == "postgresql://user@localhost:5432/control_plane"
    assert "secret" not in spec.argv[-1]
    assert spec.source == "direct"


def test_run_command_helpers_forward_timeout(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_subprocess_run(argv, *, check, env, timeout, stdout=None, stdin=None):
        captured["argv"] = argv
        captured["check"] = check
        captured["env"] = env
        captured["timeout"] = timeout
        captured["stdout_is_set"] = stdout is not None
        captured["stdin_is_set"] = stdin is not None
        return None

    monkeypatch.setattr("app.ops.postgres_backup_restore.subprocess.run", fake_subprocess_run)
    spec = build_backup_command("postgresql+psycopg://user:secret@localhost:5432/control_plane")
    output_path = tmp_path / "artifact.dump"
    from app.ops.postgres_backup_restore import run_command_to_file, run_command_from_file
    run_command_to_file(spec, output_path)
    assert captured["timeout"] == DEFAULT_COMMAND_TIMEOUT_SECONDS
    assert captured["stdout_is_set"] is True

    input_path = tmp_path / "artifact.restore"
    input_path.write_bytes(b"artifact")
    run_command_from_file(spec, input_path, timeout_seconds=42)
    assert captured["timeout"] == 42
    assert captured["stdin_is_set"] is True


def test_encrypt_decrypt_backup_round_trip(tmp_path: Path) -> None:
    source = tmp_path / "backup.dump"
    source.write_bytes(b"example-backup-payload" * 16)

    encrypted_path, metadata = encrypt_backup_file(source, passphrase="correct horse battery staple")
    restored_path = decrypt_backup_file(
        encrypted_path,
        passphrase="correct horse battery staple",
        encryption_metadata=metadata,
        destination_path=tmp_path / "restored.dump",
    )

    assert encrypted_path.suffix == ".enc"
    assert metadata["encrypted"] is True
    assert restored_path.read_bytes() == source.read_bytes()


def test_backup_database_writes_metadata_and_encrypts(monkeypatch, tmp_path: Path) -> None:
    def fake_run(spec, output_path: Path, *, timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS) -> None:
        assert timeout_seconds == DEFAULT_COMMAND_TIMEOUT_SECONDS
        output_path.write_bytes(b"backup-bytes")

    monkeypatch.setattr("app.ops.postgres_backup_restore.run_command_to_file", fake_run)

    artifact = backup_database(
        "postgresql+psycopg://user:secret@db.example.test:5432/control_plane",
        output_dir=tmp_path,
        label="nightly",
        encryption_passphrase="drill-passphrase",
    )

    assert artifact.dump_path.exists()
    assert artifact.dump_path.suffix == ".enc"
    assert artifact.metadata_path.exists()
    metadata = json.loads(artifact.metadata_path.read_text())
    assert metadata["database_url"] == "postgresql+psycopg://user:***@db.example.test:5432/control_plane"
    assert metadata["label"] == "nightly"
    assert metadata["encrypted"] is True
    assert metadata["artifact_size_bytes"] == artifact.dump_path.stat().st_size


def test_backup_database_sanitizes_label_for_filename(monkeypatch, tmp_path: Path) -> None:
    def fake_run(spec, output_path: Path, *, timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS) -> None:
        output_path.write_bytes(b"backup-bytes")

    monkeypatch.setattr("app.ops.postgres_backup_restore.run_command_to_file", fake_run)

    artifact = backup_database(
        "postgresql+psycopg://user:secret@db.example.test:5432/control_plane",
        output_dir=tmp_path,
        label="../../nightly drill\x00",
    )

    assert artifact.dump_path.parent == tmp_path
    assert ".." not in artifact.dump_path.name
    assert "/" not in artifact.dump_path.name
    assert artifact.metadata["label"] == "../../nightly drill\x00"


def test_rotate_backup_encryption_passphrase_rewrites_metadata(tmp_path: Path) -> None:
    source = tmp_path / "backup.dump"
    source.write_bytes(b"example-backup-payload" * 8)
    encrypted_path, metadata = encrypt_backup_file(source, passphrase="old-passphrase")
    metadata_path = tmp_path / "backup.metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "created_at": datetime(2026, 1, 10, tzinfo=UTC).isoformat(),
                "artifact_path": str(encrypted_path),
                "encrypted": True,
                **metadata,
            }
        ),
        encoding="utf-8",
    )

    rotated = rotate_backup_encryption_passphrase(
        encrypted_path,
        current_passphrase="old-passphrase",
        new_passphrase="new-passphrase",
    )

    rotated_metadata = json.loads(rotated.metadata_path.read_text(encoding="utf-8"))
    restored_path = decrypt_backup_file(
        rotated.dump_path,
        passphrase="new-passphrase",
        encryption_metadata=rotated_metadata,
        destination_path=tmp_path / "restored-after-rotation.dump",
    )

    assert restored_path.read_bytes() == source.read_bytes()
    assert rotated_metadata["rotation"]["previous_artifact_path"] == str(encrypted_path)
    assert rotated_metadata["artifact_sha256"] == rotated.metadata["artifact_sha256"]


def test_prune_backup_artifacts_respects_keep_last_and_age(tmp_path: Path) -> None:
    timestamps = [
        datetime(2026, 1, 10, tzinfo=UTC),
        datetime(2026, 1, 9, tzinfo=UTC),
        datetime(2025, 12, 1, tzinfo=UTC),
    ]
    for index, created_at in enumerate(timestamps, start=1):
        artifact = tmp_path / f"2026010{index}_control_plane.dump.enc"
        artifact.write_bytes(f"artifact-{index}".encode())
        metadata = tmp_path / f"2026010{index}_control_plane.metadata.json"
        metadata.write_text(
            json.dumps(
                {
                    "created_at": created_at.isoformat(),
                    "artifact_path": str(artifact),
                }
            ),
            encoding="utf-8",
        )

    result = prune_backup_artifacts(
        tmp_path,
        keep_last=1,
        max_age_days=7,
        now=datetime(2026, 1, 10, tzinfo=UTC),
    )

    assert len(result.pruned_sets) == 1
    assert not (tmp_path / "20260103_control_plane.dump.enc").exists()
    assert (tmp_path / "20260101_control_plane.dump.enc").exists()
    assert (tmp_path / "20260102_control_plane.dump.enc").exists()


def test_parse_and_infer_s3_references() -> None:
    bucket, key = parse_s3_uri("s3://backups/control-plane/20260101.dump.enc")
    assert bucket == "backups"
    assert key == "control-plane/20260101.dump.enc"
    assert infer_metadata_reference_from_backup_reference(
        "s3://backups/control-plane/20260101.dump.enc"
    ) == "s3://backups/control-plane/20260101.dump.metadata.json"


def test_resolve_object_store_config_uses_bucket_and_env(monkeypatch) -> None:
    monkeypatch.setenv("BACKUP_S3_BUCKET", "acp-backups")
    monkeypatch.setenv("BACKUP_S3_PREFIX", "control-plane")
    monkeypatch.setenv("BACKUP_S3_FORCE_PATH_STYLE", "true")
    config = resolve_object_store_config()
    assert config == ObjectStoreConfig(bucket="acp-backups", prefix="control-plane", force_path_style=True)




def test_resolve_object_store_config_supports_r2_shortcuts(monkeypatch) -> None:
    monkeypatch.delenv("BACKUP_S3_BUCKET", raising=False)
    monkeypatch.setenv("BACKUP_R2_ACCOUNT_ID", "abc123")
    monkeypatch.setenv("BACKUP_R2_BUCKET", "acp-r2")
    monkeypatch.setenv("BACKUP_R2_PREFIX", "control-plane/backups")
    monkeypatch.setenv("BACKUP_R2_ACCESS_KEY_ID", "r2-access")
    monkeypatch.setenv("BACKUP_R2_SECRET_ACCESS_KEY", "r2-secret")

    config = resolve_object_store_config()

    assert config == ObjectStoreConfig(
        bucket="acp-r2",
        prefix="control-plane/backups",
        endpoint_url="https://abc123.r2.cloudflarestorage.com",
        region="auto",
        access_key_id="r2-access",
        secret_access_key="r2-secret",
        force_path_style=False,
    )

def test_upload_backup_set_records_remote_uris(monkeypatch, tmp_path: Path) -> None:
    uploaded: list[tuple[str, str, str]] = []

    def fake_upload(path: Path, *, config: ObjectStoreConfig, key: str, content_type: str | None = None) -> str:
        uploaded.append((path.name, key, content_type or ""))
        return format_s3_uri(config.bucket or "missing", key)

    monkeypatch.setattr("app.ops.postgres_backup_restore.upload_file_to_object_store", fake_upload)
    artifact_path = tmp_path / "artifact.dump.enc"
    metadata_path = tmp_path / "artifact.dump.metadata.json"
    artifact_path.write_bytes(b"artifact")
    metadata_path.write_text("{}", encoding="utf-8")
    result = upload_backup_set(
        BackupArtifact(dump_path=artifact_path, metadata_path=metadata_path, metadata={}),
        config=ObjectStoreConfig(bucket="acp-backups", prefix="daily"),
    )
    assert result["artifact_uri"] == "s3://acp-backups/daily/artifact.dump.enc"
    assert result["metadata_uri"] == "s3://acp-backups/daily/artifact.dump.metadata.json"
    assert result["provider"] == "s3-compatible"
    assert uploaded[0][2] == "application/octet-stream"
    assert uploaded[1][2] == "application/json"


def test_backup_database_uploads_to_object_store(monkeypatch, tmp_path: Path) -> None:
    def fake_run(spec, output_path: Path, *, timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS) -> None:
        assert timeout_seconds == DEFAULT_COMMAND_TIMEOUT_SECONDS
        output_path.write_bytes(b"backup-bytes")

    uploads: list[str] = []

    def fake_upload(path: Path, *, config: ObjectStoreConfig, key: str, content_type: str | None = None) -> str:
        uploads.append(key)
        return format_s3_uri(config.bucket or "missing", key)

    monkeypatch.setattr("app.ops.postgres_backup_restore.run_command_to_file", fake_run)
    monkeypatch.setattr("app.ops.postgres_backup_restore.upload_file_to_object_store", fake_upload)

    artifact = backup_database(
        "postgresql+psycopg://user:secret@db.example.test:5432/control_plane",
        output_dir=tmp_path,
        encryption_passphrase="drill-passphrase",
        object_store=ObjectStoreConfig(bucket="acp-backups", prefix="nightly"),
    )

    assert artifact.metadata["object_store"]["artifact_uri"].startswith("s3://acp-backups/nightly/")
    assert artifact.metadata["object_store"]["metadata_uri"].endswith(".metadata.json")
    assert len(uploads) == 2  # artifact + metadata upload


def test_restore_database_downloads_from_object_store(monkeypatch, tmp_path: Path) -> None:
    downloaded: list[str] = []

    def fake_download(reference: str, *, destination_path: Path, config: ObjectStoreConfig | None = None) -> Path:
        downloaded.append(reference)
        if reference.endswith(".metadata.json"):
            destination_path.write_text(json.dumps({"encrypted": False}), encoding="utf-8")
        else:
            destination_path.write_bytes(b"artifact")
        return destination_path

    called: list[Path] = []

    def fake_run_from_file(spec, input_path: Path, *, timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS) -> None:
        called.append(input_path)
        assert timeout_seconds == DEFAULT_COMMAND_TIMEOUT_SECONDS

    monkeypatch.setattr("app.ops.postgres_backup_restore.download_file_from_object_store", fake_download)
    monkeypatch.setattr("app.ops.postgres_backup_restore.run_command_from_file", fake_run_from_file)
    report = restore_database(
        "postgresql+psycopg://user:secret@db.example.test:5432/control_plane_restore",
        backup_file="s3://acp-backups/daily/backup.dump.enc",
        object_store=ObjectStoreConfig(bucket="acp-backups"),
    )
    assert downloaded[0] == "s3://acp-backups/daily/backup.dump.enc"
    assert downloaded[1] == "s3://acp-backups/daily/backup.dump.metadata.json"
    assert called and called[0].name == "backup.dump.enc"
    assert report["backup_file"] == "s3://acp-backups/daily/backup.dump.enc"


def test_run_backup_restore_drill_writes_report(monkeypatch, tmp_path: Path) -> None:
    dump_path = tmp_path / "seed.dump.enc"
    meta_path = tmp_path / "seed.metadata.json"
    dump_path.write_bytes(b"seed")
    meta_path.write_text(
        json.dumps(
            {
                "artifact_path": str(dump_path),
                "encrypted": True,
                "object_store": {"artifact_uri": "s3://acp-backups/seed.dump.enc"},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "app.ops.postgres_backup_restore.backup_database",
        lambda *args, **kwargs: BackupArtifact(
            dump_path=dump_path,
            metadata_path=meta_path,
            metadata={
                "artifact_path": str(dump_path),
                "source": "test",
                "encrypted": True,
                "object_store": {"artifact_uri": "s3://acp-backups/seed.dump.enc"},
            },
        ),
    )
    restore_calls: list[str | Path] = []

    def fake_restore(*args, **kwargs):
        restore_calls.append(kwargs["backup_file"])
        return {"restored_at": "2026-01-01T00:00:00+00:00", "source": "test"}

    monkeypatch.setattr("app.ops.postgres_backup_restore.restore_database", fake_restore)
    monkeypatch.setattr(
        "app.ops.postgres_backup_restore.verify_restored_database",
        lambda *args, **kwargs: {
            "required_tables": ["cycles"],
            "present_tables": ["cycles"],
            "missing_tables": [],
            "row_counts": {"cycles": 1},
        },
    )

    report = run_backup_restore_drill(
        "postgresql+psycopg://user:secret@db.example.test:5432/control_plane",
        "postgresql+psycopg://user:secret@db.example.test:5432/control_plane_restore_drill",
        output_dir=tmp_path,
        label="drill",
        encryption_passphrase="drill-passphrase",
        prune_keep_last=7,
        prune_max_age_days=30,
        object_store=ObjectStoreConfig(bucket="acp-backups"),
        restore_from_object_store=True,
    )

    report_path = Path(report["report_file"])
    assert report_path.exists()
    stored = json.loads(report_path.read_text())
    assert stored["status"] == "ok"
    assert stored["verification"]["row_counts"]["cycles"] == 1
    assert restore_calls == ["s3://acp-backups/seed.dump.enc"]


def test_makefile_contains_backup_restore_targets() -> None:
    makefile = Path("Makefile").read_text(encoding="utf-8")
    assert "backup-db:" in makefile
    assert "restore-db:" in makefile
    assert "drill-backup-restore:" in makefile
    assert "drill-backup-restore-compose:" in makefile
    assert "prune-backups:" in makefile
    assert "rotate-backup-passphrase:" in makefile
    assert "render-s3-lifecycle-policy:" in makefile


def test_scheduled_backup_restore_workflow_exists() -> None:
    workflow = Path(".github/workflows/backup-restore-drill.yml").read_text(encoding="utf-8")
    assert "schedule:" in workflow
    assert "workflow_dispatch:" in workflow
    assert "upload-artifact" in workflow
    assert "BACKUP_ENCRYPTION_PASSPHRASE" in workflow
    assert "BACKUP_S3_BUCKET" in workflow
    assert "BACKUP_OBJECT_STORE_VERIFY_RESTORE=true" in workflow


def test_s3_lifecycle_policy_script_and_output_exist() -> None:
    script = Path("scripts/render_s3_lifecycle_policy.py")
    policy = Path("deploy/object_storage/s3-lifecycle-policy.json")
    assert script.exists()
    parsed = json.loads(policy.read_text(encoding="utf-8"))
    assert parsed["Rules"][0]["Expiration"]["Days"] >= 1
