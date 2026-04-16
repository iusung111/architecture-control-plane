from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_VERIFY_TABLES = (
    "alembic_version",
    "cycles",
    "cycle_iterations",
    "jobs",
    "notifications_outbox",
    "audit_events",
)

BACKUP_FILE_MAGIC = b"ACPBK1"
DEFAULT_ENCRYPTION_CHUNK_SIZE = 1024 * 1024
DEFAULT_ENCRYPTION_KDF_ITERATIONS = 390000
DEFAULT_COMMAND_TIMEOUT_SECONDS = 1800

@dataclass(frozen=True)
class CommandSpec:
    argv: list[str]
    env: dict[str, str]
    source: str


@dataclass(frozen=True)
class BackupArtifact:
    dump_path: Path
    metadata_path: Path
    metadata: dict[str, Any]


@dataclass(frozen=True)
class RetentionResult:
    deleted_files: list[str]
    kept_sets: list[str]
    pruned_sets: list[str]


@dataclass(frozen=True)
class ObjectStoreConfig:
    bucket: str | None = None
    prefix: str | None = None
    endpoint_url: str | None = None
    region: str | None = None
    access_key_id: str | None = None
    secret_access_key: str | None = None
    session_token: str | None = None
    force_path_style: bool = False

