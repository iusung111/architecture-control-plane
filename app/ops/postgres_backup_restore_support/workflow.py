from __future__ import annotations

import importlib
import json
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy.engine import make_url

from .models import BackupArtifact, DEFAULT_COMMAND_TIMEOUT_SECONDS, ObjectStoreConfig


def _module():
    return importlib.import_module("app.ops.postgres_backup_restore")


def _safe_label_component(label: str | None) -> str:
    if not label:
        return ""
    sanitized = "".join(character if character.isalnum() or character in {"-", "_"} else "-" for character in label)
    sanitized = sanitized.strip("-_")
    return sanitized or "label"


def backup_database(
    database_url: str,
    *,
    output_dir: Path,
    label: str | None = None,
    docker_compose_service: str | None = None,
    encryption_passphrase: str | None = None,
    prune_keep_last: int | None = None,
    prune_max_age_days: int | None = None,
    object_store: ObjectStoreConfig | None = None,
    command_timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS,
    progress_callback: Callable[[str], None] | None = None,
) -> BackupArtifact:
    output_dir = _module()._ensure_output_dir(output_dir)
    timestamp = _module()._timestamp_token()
    label_suffix = f"_{_safe_label_component(label)}" if label else ""
    dump_path = output_dir / f"{timestamp}_{_module()._database_slug(database_url)}{label_suffix}.dump"
    metadata_path = output_dir / f"{dump_path.stem}.metadata.json"

    spec = _module().build_backup_command(database_url, docker_compose_service=docker_compose_service)
    if progress_callback is not None:
        progress_callback("dumping")
    _module().run_command_to_file(spec, dump_path, timeout_seconds=command_timeout_seconds)

    artifact_path = dump_path
    encryption_block: dict[str, Any] = {"encrypted": False}
    if encryption_passphrase:
        artifact_path, encryption_block = _module().encrypt_backup_file(dump_path, passphrase=encryption_passphrase)
        dump_path.unlink()

    metadata = {
        "created_at": _module()._now_utc().isoformat(),
        "database_url": _module().sanitize_database_url(database_url),
        "database_name": make_url(database_url).database,
        "artifact_path": str(artifact_path),
        "artifact_sha256": _module()._sha256_file(artifact_path),
        "artifact_size_bytes": artifact_path.stat().st_size,
        "label": label,
        "source": spec.source,
        "format": "pg_dump_custom",
        **encryption_block,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")

    artifact = BackupArtifact(dump_path=artifact_path, metadata_path=metadata_path, metadata=metadata)
    if object_store:
        if progress_callback is not None:
            progress_callback("uploading")
        object_store_info = _module().upload_backup_set(artifact, config=object_store)
        metadata["object_store"] = object_store_info

    if prune_keep_last is not None or prune_max_age_days is not None:
        retention = _module().prune_backup_artifacts(output_dir, keep_last=prune_keep_last, max_age_days=prune_max_age_days)
        metadata["retention"] = {
            "keep_last": prune_keep_last,
            "max_age_days": prune_max_age_days,
            "deleted_files": retention.deleted_files,
            "pruned_sets": retention.pruned_sets,
        }
        metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")

    return BackupArtifact(dump_path=artifact_path, metadata_path=metadata_path, metadata=metadata)


def restore_database(
    database_url: str,
    *,
    backup_file: Path | str,
    docker_compose_service: str | None = None,
    recreate_target_database: bool = False,
    encryption_passphrase: str | None = None,
    object_store: ObjectStoreConfig | None = None,
    command_timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS,
    progress_callback: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    if recreate_target_database:
        _module().recreate_database(database_url)
    spec = _module().build_restore_command(database_url, docker_compose_service=docker_compose_service)
    temporary_plaintext: Path | None = None
    restore_source, metadata, original_reference, metadata_reference, temporary_download_dir = _module()._resolve_backup_source(backup_file, object_store=object_store)
    try:
        _module().verify_backup_artifact_integrity(restore_source, metadata)
        if metadata.get("encrypted"):
            if not encryption_passphrase:
                raise ValueError("Encrypted backup requires an encryption passphrase")
            with tempfile.NamedTemporaryFile(prefix="acp-restore-", suffix=".dump", delete=False) as handle:
                temporary_plaintext = Path(handle.name)
            restore_source = _module().decrypt_backup_file(
                restore_source,
                passphrase=encryption_passphrase,
                encryption_metadata=metadata,
                destination_path=temporary_plaintext,
            )
        if progress_callback is not None:
            progress_callback("restoring")
        _module().run_command_from_file(spec, restore_source, timeout_seconds=command_timeout_seconds)
        return {
            "restored_at": _module()._now_utc().isoformat(),
            "database_url": _module().sanitize_database_url(database_url),
            "backup_file": str(original_reference),
            "backup_metadata_file": metadata_reference,
            "source": spec.source,
            "encrypted": bool(metadata.get("encrypted")),
        }
    finally:
        if temporary_plaintext is not None and temporary_plaintext.exists():
            temporary_plaintext.unlink()
        if temporary_download_dir is not None:
            temporary_download_dir.cleanup()


def run_backup_restore_drill(
    source_database_url: str,
    target_database_url: str,
    *,
    output_dir: Path,
    label: str | None = None,
    docker_compose_service: str | None = None,
    report_file: Path | None = None,
    encryption_passphrase: str | None = None,
    prune_keep_last: int | None = None,
    prune_max_age_days: int | None = None,
    object_store: ObjectStoreConfig | None = None,
    restore_from_object_store: bool = False,
    command_timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS,
    progress_callback: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    output_dir = _module()._ensure_output_dir(output_dir)
    report_path = report_file or output_dir / f"{_module()._timestamp_token()}_{_module()._database_slug(source_database_url)}_drill_report.json"

    if progress_callback is not None:
        progress_callback("backup")
    backup = _module().backup_database(
        source_database_url,
        output_dir=output_dir,
        label=label,
        docker_compose_service=docker_compose_service,
        encryption_passphrase=encryption_passphrase,
        prune_keep_last=prune_keep_last,
        prune_max_age_days=prune_max_age_days,
        object_store=object_store,
        command_timeout_seconds=command_timeout_seconds,
    )
    backup_reference = backup.metadata.get("object_store", {}).get("artifact_uri") if restore_from_object_store else None
    backup_reference = backup_reference or backup.dump_path

    if progress_callback is not None:
        progress_callback("restore")
    restore = _module().restore_database(
        target_database_url,
        backup_file=backup_reference,
        docker_compose_service=docker_compose_service,
        recreate_target_database=True,
        encryption_passphrase=encryption_passphrase,
        object_store=object_store,
        command_timeout_seconds=command_timeout_seconds,
    )
    verification = _module().verify_restored_database(target_database_url)
    report = {
        "status": "ok",
        "source_database_url": _module().sanitize_database_url(source_database_url),
        "target_database_url": _module().sanitize_database_url(target_database_url),
        "backup": backup.metadata,
        "restore": restore,
        "verification": verification,
        "report_file": str(report_path),
        "completed_at": _module()._now_utc().isoformat(),
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report
