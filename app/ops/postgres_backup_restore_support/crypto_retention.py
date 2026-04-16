from __future__ import annotations

import base64
import hashlib
import importlib
import json
import secrets
import struct
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from .models import (
    BACKUP_FILE_MAGIC,
    DEFAULT_ENCRYPTION_CHUNK_SIZE,
    DEFAULT_ENCRYPTION_KDF_ITERATIONS,
    BackupArtifact,
    ObjectStoreConfig,
    RetentionResult,
)


def _module():
    return importlib.import_module("app.ops.postgres_backup_restore")


def _b64encode(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"))


def _derive_encryption_key(*, passphrase: str, salt: bytes, iterations: int) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iterations)
    return kdf.derive(passphrase.encode("utf-8"))


def encrypt_backup_file(
    source_path: Path,
    *,
    passphrase: str,
    destination_path: Path | None = None,
    chunk_size: int = DEFAULT_ENCRYPTION_CHUNK_SIZE,
    iterations: int = DEFAULT_ENCRYPTION_KDF_ITERATIONS,
) -> tuple[Path, dict[str, Any]]:
    target = destination_path or source_path.with_suffix(source_path.suffix + ".enc")
    salt = secrets.token_bytes(16)
    nonce_prefix = secrets.token_bytes(8)
    key = _derive_encryption_key(passphrase=passphrase, salt=salt, iterations=iterations)
    aesgcm = AESGCM(key)
    chunk_count = 0
    total_plaintext_bytes = 0
    with source_path.open("rb") as src, target.open("wb") as dst:
        dst.write(BACKUP_FILE_MAGIC)
        while True:
            chunk = src.read(chunk_size)
            if not chunk:
                break
            nonce = nonce_prefix + struct.pack(">I", chunk_count)
            ciphertext = aesgcm.encrypt(nonce, chunk, struct.pack(">I", chunk_count))
            dst.write(struct.pack(">I", len(ciphertext)))
            dst.write(ciphertext)
            total_plaintext_bytes += len(chunk)
            chunk_count += 1
    return target, {
        "encrypted": True,
        "encryption": {
            "algorithm": "AES-256-GCM",
            "file_format": BACKUP_FILE_MAGIC.decode("ascii"),
            "kdf": "PBKDF2-HMAC-SHA256",
            "kdf_iterations": iterations,
            "salt_b64": _b64encode(salt),
            "nonce_prefix_b64": _b64encode(nonce_prefix),
            "chunk_size": chunk_size,
            "chunk_count": chunk_count,
            "plaintext_size_bytes": total_plaintext_bytes,
        },
    }


def decrypt_backup_file(
    source_path: Path,
    *,
    passphrase: str,
    encryption_metadata: dict[str, Any],
    destination_path: Path | None = None,
) -> Path:
    target = destination_path or source_path.with_suffix("")
    encryption = encryption_metadata.get("encryption") or {}
    iterations = int(encryption["kdf_iterations"])
    salt = _b64decode(str(encryption["salt_b64"]))
    nonce_prefix = _b64decode(str(encryption["nonce_prefix_b64"]))
    key = _derive_encryption_key(passphrase=passphrase, salt=salt, iterations=iterations)
    aesgcm = AESGCM(key)
    with source_path.open("rb") as src, target.open("wb") as dst:
        magic = src.read(len(BACKUP_FILE_MAGIC))
        if magic != BACKUP_FILE_MAGIC:
            raise ValueError("Backup artifact is not in the expected encrypted format")
        chunk_index = 0
        while True:
            length_bytes = src.read(4)
            if not length_bytes:
                break
            if len(length_bytes) != 4:
                raise ValueError("Corrupt encrypted backup artifact")
            (ciphertext_length,) = struct.unpack(">I", length_bytes)
            ciphertext = src.read(ciphertext_length)
            if len(ciphertext) != ciphertext_length:
                raise ValueError("Corrupt encrypted backup artifact")
            nonce = nonce_prefix + struct.pack(">I", chunk_index)
            plaintext = aesgcm.decrypt(nonce, ciphertext, struct.pack(">I", chunk_index))
            dst.write(plaintext)
            chunk_index += 1
    return target


def load_backup_metadata(metadata_path: Path) -> dict[str, Any]:
    return json.loads(metadata_path.read_text(encoding="utf-8"))


def rotate_backup_encryption_passphrase(
    backup_reference: Path | str,
    *,
    current_passphrase: str,
    new_passphrase: str,
    output_dir: Path | None = None,
    object_store: ObjectStoreConfig | None = None,
    reupload_object_store: bool = False,
) -> BackupArtifact:
    artifact_path, metadata, original_reference, metadata_reference, temporary_download_dir = _module()._resolve_backup_source(
        backup_reference,
        object_store=object_store,
    )
    if not metadata.get("encrypted"):
        raise ValueError("Backup artifact is not encrypted and cannot be rewrapped")
    original_artifact_path = str(metadata.get("artifact_path") or original_reference)
    original_metadata_reference = metadata_reference
    local_rotation = not _module().is_s3_uri(str(original_reference))
    target_dir = output_dir or (artifact_path.parent if local_rotation else Path("backups/rotated"))
    target_dir = _module()._ensure_output_dir(target_dir)
    if local_rotation and output_dir is None:
        destination_path = Path(original_reference)
        destination_metadata_path = Path(metadata_reference or _module().infer_metadata_reference_from_backup_reference(str(original_reference)))
    else:
        stem = artifact_path.name[:-4] if artifact_path.name.endswith(".enc") else artifact_path.stem
        destination_path = target_dir / f"{stem}.rotated.enc"
        destination_metadata_path = target_dir / f"{Path(stem).stem}.metadata.json"

    temporary_plaintext: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix="acp-rotate-", suffix=".dump", delete=False) as handle:
            temporary_plaintext = Path(handle.name)
        decrypt_backup_file(
            artifact_path,
            passphrase=current_passphrase,
            encryption_metadata=metadata,
            destination_path=temporary_plaintext,
        )
        destination_path, fresh_encryption = encrypt_backup_file(
            temporary_plaintext,
            passphrase=new_passphrase,
            destination_path=destination_path,
        )
        rotation_metadata = json.loads(json.dumps(metadata))
        rotation_metadata.update(fresh_encryption)
        rotation_metadata["artifact_path"] = str(destination_path)
        rotation_metadata["artifact_sha256"] = _sha256_file(destination_path)
        rotation_metadata["artifact_size_bytes"] = destination_path.stat().st_size
        rotation_metadata["rotated_at"] = _now_utc().isoformat()
        rotation_metadata["rotation"] = {
            "previous_artifact_path": original_artifact_path,
            "previous_metadata_path": original_metadata_reference,
            "local_rotation": local_rotation,
            "reupload_object_store": reupload_object_store,
        }
        destination_metadata_path.write_text(json.dumps(rotation_metadata, indent=2, sort_keys=True), encoding="utf-8")
        artifact = BackupArtifact(dump_path=destination_path, metadata_path=destination_metadata_path, metadata=rotation_metadata)
        if reupload_object_store:
            object_store_block = rotation_metadata.get("object_store") or {}
            artifact_uri = object_store_block.get("artifact_uri")
            metadata_uri = object_store_block.get("metadata_uri")
            if not artifact_uri or not metadata_uri:
                raise ValueError("reupload_object_store requested but metadata has no object_store URIs")
            resolved_object_store = object_store or _module().resolve_object_store_config(bucket=_module().parse_s3_uri(artifact_uri)[0])
            if resolved_object_store is None:
                raise ValueError("Object store configuration is required for reupload")
            _module().upload_file_to_object_store(destination_path, config=resolved_object_store, key=_module().parse_s3_uri(artifact_uri)[1], content_type="application/octet-stream")
            _module().upload_file_to_object_store(destination_metadata_path, config=resolved_object_store, key=_module().parse_s3_uri(metadata_uri)[1], content_type="application/json")
            rotation_metadata["object_store"] = {**object_store_block, "uploaded_at": _now_utc().isoformat()}
            destination_metadata_path.write_text(json.dumps(rotation_metadata, indent=2, sort_keys=True), encoding="utf-8")
        return artifact
    finally:
        if temporary_plaintext is not None and temporary_plaintext.exists():
            temporary_plaintext.unlink()
        if temporary_download_dir is not None:
            temporary_download_dir.cleanup()


def prune_backup_artifacts(
    output_dir: Path,
    *,
    keep_last: int | None = None,
    max_age_days: int | None = None,
    now: datetime | None = None,
) -> RetentionResult:
    metadata_files = sorted(output_dir.glob("*.metadata.json"))
    if not metadata_files:
        return RetentionResult(deleted_files=[], kept_sets=[], pruned_sets=[])

    reference_time = now or _now_utc()
    backup_sets: list[dict[str, Any]] = []
    for metadata_path in metadata_files:
        metadata = load_backup_metadata(metadata_path)
        created_at = datetime.fromisoformat(str(metadata["created_at"]))
        artifact_path = Path(str(metadata["artifact_path"]))
        backup_sets.append({"metadata_path": metadata_path, "artifact_path": artifact_path, "created_at": created_at, "set_name": metadata_path.stem.replace(".metadata", "")})

    backup_sets.sort(key=lambda item: item["created_at"], reverse=True)
    keep_last = max(0, keep_last or 0)
    cutoff = reference_time - timedelta(days=max_age_days) if max_age_days is not None and max_age_days >= 0 else None

    deleted_files: list[str] = []
    kept_sets: list[str] = []
    pruned_sets: list[str] = []
    for index, backup_set in enumerate(backup_sets):
        keep_due_to_count = index < keep_last if keep_last else False
        keep_due_to_age = cutoff is None or backup_set["created_at"] >= cutoff
        if keep_due_to_count or keep_due_to_age:
            kept_sets.append(str(backup_set["artifact_path"]))
            continue
        pruned_sets.append(str(backup_set["artifact_path"]))
        for path in (backup_set["artifact_path"], backup_set["metadata_path"]):
            if path.exists():
                path.unlink()
                deleted_files.append(str(path))

    return RetentionResult(deleted_files=deleted_files, kept_sets=kept_sets, pruned_sets=pruned_sets)


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _timestamp_token(moment: datetime | None = None) -> str:
    value = moment or _now_utc()
    return value.strftime("%Y%m%dT%H%M%SZ")


def _ensure_output_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
