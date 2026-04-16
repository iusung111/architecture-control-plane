from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .models import BackupArtifact, ObjectStoreConfig
from .crypto_retention import _now_utc


class BackupObjectStoreError(RuntimeError):
    """Raised when object-store upload/download workflows fail."""


class BackupMetadataError(BackupObjectStoreError):
    """Raised when backup metadata cannot be retrieved or parsed."""


class BackupIntegrityError(BackupObjectStoreError):
    """Raised when a backup artifact does not match metadata expectations."""


def _env_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _object_store_prefix(prefix: str | None, name: str) -> str:
    base = (prefix or "").strip("/")
    return f"{base}/{name}" if base else name


def is_s3_uri(value: str) -> bool:
    return value.startswith("s3://")


def parse_s3_uri(uri: str) -> tuple[str, str]:
    if not is_s3_uri(uri):
        raise ValueError(f"Not an s3 uri: {uri}")
    bucket, _, key = uri[5:].partition("/")
    return bucket, key


def format_s3_uri(bucket: str, key: str) -> str:
    return f"s3://{bucket}/{key}"


def infer_metadata_reference_from_backup_reference(reference: str) -> str:
    if reference.endswith(".dump.enc"):
        return reference[:-9] + ".dump.metadata.json"
    if reference.endswith(".enc"):
        return reference[:-4] + ".metadata.json"
    if ".dump" in reference:
        return reference.rsplit(".dump", 1)[0] + ".dump.metadata.json"
    return reference + ".metadata.json"


def _resolve_r2_endpoint(account_id: str | None) -> str | None:
    if not account_id:
        return None
    return f"https://{account_id}.r2.cloudflarestorage.com"


def _infer_object_store_provider(config: ObjectStoreConfig) -> str:
    if config.endpoint_url and "r2.cloudflarestorage.com" in config.endpoint_url:
        return "cloudflare-r2"
    return "s3-compatible"


def resolve_object_store_config(
    *,
    bucket: str | None = None,
    prefix: str | None = None,
    endpoint_url: str | None = None,
    region: str | None = None,
    access_key_id: str | None = None,
    secret_access_key: str | None = None,
    session_token: str | None = None,
    force_path_style: bool | None = None,
) -> ObjectStoreConfig | None:
    bucket = bucket or os.getenv("BACKUP_S3_BUCKET") or os.getenv("BACKUP_R2_BUCKET")
    prefix = prefix if prefix is not None else os.getenv("BACKUP_S3_PREFIX") or os.getenv("BACKUP_R2_PREFIX")
    endpoint_url = endpoint_url or os.getenv("BACKUP_S3_ENDPOINT_URL") or _resolve_r2_endpoint(os.getenv("BACKUP_R2_ACCOUNT_ID"))
    region = region or os.getenv("BACKUP_S3_REGION") or ("auto" if os.getenv("BACKUP_R2_BUCKET") else None)
    access_key_id = access_key_id or os.getenv("BACKUP_S3_ACCESS_KEY_ID") or os.getenv("BACKUP_R2_ACCESS_KEY_ID") or os.getenv("AWS_ACCESS_KEY_ID")
    secret_access_key = secret_access_key or os.getenv("BACKUP_S3_SECRET_ACCESS_KEY") or os.getenv("BACKUP_R2_SECRET_ACCESS_KEY") or os.getenv("AWS_SECRET_ACCESS_KEY")
    session_token = session_token or os.getenv("BACKUP_S3_SESSION_TOKEN") or os.getenv("AWS_SESSION_TOKEN")
    if force_path_style is None:
        force_path_style = _env_bool(os.getenv("BACKUP_S3_FORCE_PATH_STYLE"), default=False)
    if not bucket:
        return None
    return ObjectStoreConfig(
        bucket=bucket,
        prefix=prefix,
        endpoint_url=endpoint_url,
        region=region,
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
        session_token=session_token,
        force_path_style=bool(force_path_style),
    )


def get_object_store_client(config: ObjectStoreConfig) -> Any:
    import boto3

    client_kwargs: dict[str, Any] = {}
    if config.endpoint_url:
        client_kwargs["endpoint_url"] = config.endpoint_url
    if config.region:
        client_kwargs["region_name"] = config.region
    if config.access_key_id:
        client_kwargs["aws_access_key_id"] = config.access_key_id
    if config.secret_access_key:
        client_kwargs["aws_secret_access_key"] = config.secret_access_key
    if config.session_token:
        client_kwargs["aws_session_token"] = config.session_token
    if config.force_path_style:
        client_kwargs["config"] = boto3.session.Config(s3={"addressing_style": "path"})
    return boto3.client("s3", **client_kwargs)


def upload_file_to_object_store(path: Path, *, config: ObjectStoreConfig, key: str, content_type: str | None = None) -> str:
    client = get_object_store_client(config)
    extra_args = {"ContentType": content_type} if content_type else None
    client.upload_file(str(path), config.bucket or "", key, ExtraArgs=extra_args)
    return format_s3_uri(config.bucket or "", key)


def delete_file_from_object_store(reference: str, *, config: ObjectStoreConfig | None = None) -> None:
    bucket, key = parse_s3_uri(reference)
    resolved_config = config or resolve_object_store_config(bucket=bucket)
    if resolved_config is None:
        raise ValueError("Object store configuration is required")
    client = get_object_store_client(resolved_config)
    client.delete_object(Bucket=bucket, Key=key)


def plan_backup_set_upload(artifact: BackupArtifact, *, config: ObjectStoreConfig, uploaded_at: str | None = None) -> dict[str, Any]:
    artifact_key = _object_store_prefix(config.prefix, artifact.dump_path.name)
    metadata_key = _object_store_prefix(config.prefix, artifact.metadata_path.name)
    return {
        "provider": _infer_object_store_provider(config),
        "bucket": config.bucket,
        "prefix": config.prefix,
        "endpoint_url": config.endpoint_url,
        "region": config.region,
        "artifact_uri": format_s3_uri(config.bucket or "", artifact_key),
        "metadata_uri": format_s3_uri(config.bucket or "", metadata_key),
        "uploaded_at": uploaded_at or _now_utc().isoformat(),
    }


def _write_metadata_with_object_store_reference(metadata_path: Path, metadata: dict[str, Any], object_store_info: dict[str, Any]) -> dict[str, Any]:
    updated_metadata = json.loads(json.dumps(metadata))
    updated_metadata["object_store"] = object_store_info
    metadata_path.write_text(json.dumps(updated_metadata, indent=2, sort_keys=True), encoding="utf-8")
    return updated_metadata


def verify_backup_artifact_integrity(path: Path, metadata: dict[str, Any]) -> None:
    from app.ops.postgres_backup_restore import _sha256_file

    expected_sha256 = metadata.get("artifact_sha256")
    if expected_sha256:
        actual_sha256 = _sha256_file(path)
        if actual_sha256 != expected_sha256:
            raise BackupIntegrityError(
                f"Backup artifact checksum mismatch for {path.name}: expected {expected_sha256}, got {actual_sha256}"
            )

    expected_size = metadata.get("artifact_size_bytes")
    if expected_size is not None and path.stat().st_size != int(expected_size):
        raise BackupIntegrityError(
            f"Backup artifact size mismatch for {path.name}: expected {expected_size}, got {path.stat().st_size}"
        )


def download_file_from_object_store(reference: str, *, destination_path: Path, config: ObjectStoreConfig | None = None) -> Path:
    bucket, key = parse_s3_uri(reference)
    resolved_config = config or resolve_object_store_config(bucket=bucket)
    if resolved_config is None:
        raise ValueError("Object store configuration is required")
    client = get_object_store_client(resolved_config)
    client.download_file(bucket, key, str(destination_path))
    return destination_path


def upload_backup_set(artifact: BackupArtifact, *, config: ObjectStoreConfig) -> dict[str, Any]:
    from app.ops.postgres_backup_restore import delete_file_from_object_store, upload_file_to_object_store

    upload_info = plan_backup_set_upload(artifact, config=config)
    metadata = _write_metadata_with_object_store_reference(artifact.metadata_path, artifact.metadata, upload_info)
    upload_artifact_succeeded = False
    try:
        upload_file_to_object_store(
            artifact.dump_path,
            config=config,
            key=parse_s3_uri(upload_info["artifact_uri"])[1],
            content_type="application/octet-stream",
        )
        upload_artifact_succeeded = True
        upload_file_to_object_store(
            artifact.metadata_path,
            config=config,
            key=parse_s3_uri(upload_info["metadata_uri"])[1],
            content_type="application/json",
        )
        artifact.metadata.clear()
        artifact.metadata.update(metadata)
        return upload_info
    except Exception as exc:
        cleanup_errors: list[str] = []
        for should_cleanup, uri in ((upload_artifact_succeeded, upload_info["artifact_uri"]), (True, upload_info["metadata_uri"])):
            if not should_cleanup:
                continue
            try:
                delete_file_from_object_store(uri, config=config)
            except Exception as cleanup_exc:  # pragma: no cover - best effort only
                cleanup_errors.append(str(cleanup_exc))
        detail = f"Failed to upload backup set to object store: artifact={upload_info['artifact_uri']} metadata={upload_info['metadata_uri']}"
        if cleanup_errors:
            detail = f"{detail}; cleanup_errors={cleanup_errors}"
        raise BackupObjectStoreError(detail) from exc


def _resolve_backup_source(
    backup_reference: str | Path,
    *,
    object_store: ObjectStoreConfig | None = None,
) -> tuple[Path, dict[str, Any], str, str | None, tempfile.TemporaryDirectory[str] | None]:
    from app.ops.postgres_backup_restore import download_file_from_object_store, load_backup_metadata

    reference = str(backup_reference)
    temporary_directory: tempfile.TemporaryDirectory[str] | None = None
    if is_s3_uri(reference):
        temporary_directory = tempfile.TemporaryDirectory(prefix="acp-backup-download-")
        tmp_dir = Path(temporary_directory.name)
        metadata_reference = infer_metadata_reference_from_backup_reference(reference)
        try:
            local_artifact = download_file_from_object_store(reference, destination_path=tmp_dir / Path(parse_s3_uri(reference)[1]).name, config=object_store)
        except Exception as exc:
            temporary_directory.cleanup()
            raise BackupObjectStoreError(f"Failed to download backup artifact from object store: {reference}") from exc
        try:
            local_metadata = download_file_from_object_store(metadata_reference, destination_path=tmp_dir / Path(parse_s3_uri(metadata_reference)[1]).name, config=object_store)
            metadata = load_backup_metadata(local_metadata)
            return local_artifact, metadata, reference, metadata_reference, temporary_directory
        except FileNotFoundError as exc:
            temporary_directory.cleanup()
            raise BackupMetadataError(f"Backup metadata missing for {reference}: expected {metadata_reference}") from exc
        except json.JSONDecodeError as exc:
            temporary_directory.cleanup()
            raise BackupMetadataError(f"Backup metadata is invalid JSON for {reference}: {metadata_reference}") from exc
        except Exception as exc:
            temporary_directory.cleanup()
            raise BackupObjectStoreError(f"Failed to resolve backup metadata from object store: {metadata_reference}") from exc

    local_artifact = Path(reference)
    metadata_path = local_artifact.with_suffix("").with_suffix(".metadata.json") if local_artifact.suffix == ".enc" else local_artifact.with_suffix(".metadata.json")
    if not metadata_path.exists():
        return local_artifact, {}, reference, None, None
    try:
        metadata = load_backup_metadata(metadata_path)
    except json.JSONDecodeError as exc:
        raise BackupMetadataError(f"Backup metadata is invalid JSON for {reference}: {metadata_path}") from exc
    return local_artifact, metadata, reference, str(metadata_path), None
