from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path

from .models import DEFAULT_COMMAND_TIMEOUT_SECONDS


def _module():
    return importlib.import_module("app.ops.postgres_backup_restore")


def _resolve_database_url(argument_value: str | None, env_name: str) -> str:
    database_url = argument_value or os.getenv(env_name)
    if not database_url:
        raise SystemExit(f"Missing database url. Provide --database-url or set {env_name}.")
    return database_url


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backup, restore, and verify PostgreSQL databases")
    subparsers = parser.add_subparsers(dest="command", required=True)

    backup_parser = subparsers.add_parser("backup", help="Create a PostgreSQL backup")
    backup_parser.add_argument("--database-url")
    backup_parser.add_argument("--output-dir", default=os.getenv("BACKUP_OUTPUT_DIR", "backups"))
    backup_parser.add_argument("--label")
    backup_parser.add_argument("--docker-compose-service", default=os.getenv("BACKUP_COMPOSE_SERVICE"))
    backup_parser.add_argument("--encryption-passphrase", default=os.getenv("BACKUP_ENCRYPTION_PASSPHRASE"))
    backup_parser.add_argument("--prune-keep-last", type=int, default=int(os.getenv("BACKUP_RETENTION_KEEP_LAST", "0") or 0))
    backup_parser.add_argument("--prune-max-age-days", type=int, default=(int(os.getenv("BACKUP_RETENTION_MAX_AGE_DAYS")) if os.getenv("BACKUP_RETENTION_MAX_AGE_DAYS") else None))
    backup_parser.add_argument("--object-store-bucket", default=os.getenv("BACKUP_S3_BUCKET"))
    backup_parser.add_argument("--object-store-prefix", default=os.getenv("BACKUP_S3_PREFIX"))
    backup_parser.add_argument("--object-store-endpoint-url", default=os.getenv("BACKUP_S3_ENDPOINT_URL"))
    backup_parser.add_argument("--object-store-region", default=os.getenv("BACKUP_S3_REGION"))
    backup_parser.add_argument("--object-store-access-key-id", default=os.getenv("BACKUP_S3_ACCESS_KEY_ID") or os.getenv("AWS_ACCESS_KEY_ID"))
    backup_parser.add_argument("--object-store-secret-access-key", default=os.getenv("BACKUP_S3_SECRET_ACCESS_KEY") or os.getenv("AWS_SECRET_ACCESS_KEY"))
    backup_parser.add_argument("--object-store-session-token", default=os.getenv("BACKUP_S3_SESSION_TOKEN") or os.getenv("AWS_SESSION_TOKEN"))
    backup_parser.add_argument("--object-store-force-path-style", action="store_true", default=False)
    backup_parser.add_argument("--command-timeout-seconds", type=int, default=int(os.getenv("BACKUP_COMMAND_TIMEOUT_SECONDS", str(DEFAULT_COMMAND_TIMEOUT_SECONDS))))

    restore_parser = subparsers.add_parser("restore", help="Restore a PostgreSQL backup")
    restore_parser.add_argument("--database-url")
    restore_parser.add_argument("--backup-file", required=True)
    restore_parser.add_argument("--docker-compose-service", default=os.getenv("BACKUP_COMPOSE_SERVICE"))
    restore_parser.add_argument("--recreate-target-database", action="store_true")
    restore_parser.add_argument("--encryption-passphrase", default=os.getenv("BACKUP_ENCRYPTION_PASSPHRASE"))
    restore_parser.add_argument("--object-store-bucket", default=os.getenv("BACKUP_S3_BUCKET"))
    restore_parser.add_argument("--object-store-prefix", default=os.getenv("BACKUP_S3_PREFIX"))
    restore_parser.add_argument("--object-store-endpoint-url", default=os.getenv("BACKUP_S3_ENDPOINT_URL"))
    restore_parser.add_argument("--object-store-region", default=os.getenv("BACKUP_S3_REGION"))
    restore_parser.add_argument("--object-store-access-key-id", default=os.getenv("BACKUP_S3_ACCESS_KEY_ID") or os.getenv("AWS_ACCESS_KEY_ID"))
    restore_parser.add_argument("--object-store-secret-access-key", default=os.getenv("BACKUP_S3_SECRET_ACCESS_KEY") or os.getenv("AWS_SECRET_ACCESS_KEY"))
    restore_parser.add_argument("--object-store-session-token", default=os.getenv("BACKUP_S3_SESSION_TOKEN") or os.getenv("AWS_SESSION_TOKEN"))
    restore_parser.add_argument("--object-store-force-path-style", action="store_true", default=False)
    restore_parser.add_argument("--command-timeout-seconds", type=int, default=int(os.getenv("BACKUP_COMMAND_TIMEOUT_SECONDS", str(DEFAULT_COMMAND_TIMEOUT_SECONDS))))

    drill_parser = subparsers.add_parser("drill", help="Run a backup + restore drill")
    drill_parser.add_argument("--source-database-url")
    drill_parser.add_argument("--target-database-url")
    drill_parser.add_argument("--output-dir", default=os.getenv("BACKUP_OUTPUT_DIR", "backups/drills"))
    drill_parser.add_argument("--label")
    drill_parser.add_argument("--docker-compose-service", default=os.getenv("BACKUP_COMPOSE_SERVICE"))
    drill_parser.add_argument("--report-file")
    drill_parser.add_argument("--encryption-passphrase", default=os.getenv("BACKUP_ENCRYPTION_PASSPHRASE"))
    drill_parser.add_argument("--prune-keep-last", type=int, default=int(os.getenv("BACKUP_RETENTION_KEEP_LAST", "0") or 0))
    drill_parser.add_argument("--prune-max-age-days", type=int, default=(int(os.getenv("BACKUP_RETENTION_MAX_AGE_DAYS")) if os.getenv("BACKUP_RETENTION_MAX_AGE_DAYS") else None))
    drill_parser.add_argument("--object-store-bucket", default=os.getenv("BACKUP_S3_BUCKET"))
    drill_parser.add_argument("--object-store-prefix", default=os.getenv("BACKUP_S3_PREFIX"))
    drill_parser.add_argument("--object-store-endpoint-url", default=os.getenv("BACKUP_S3_ENDPOINT_URL"))
    drill_parser.add_argument("--object-store-region", default=os.getenv("BACKUP_S3_REGION"))
    drill_parser.add_argument("--object-store-access-key-id", default=os.getenv("BACKUP_S3_ACCESS_KEY_ID") or os.getenv("AWS_ACCESS_KEY_ID"))
    drill_parser.add_argument("--object-store-secret-access-key", default=os.getenv("BACKUP_S3_SECRET_ACCESS_KEY") or os.getenv("AWS_SECRET_ACCESS_KEY"))
    drill_parser.add_argument("--object-store-session-token", default=os.getenv("BACKUP_S3_SESSION_TOKEN") or os.getenv("AWS_SESSION_TOKEN"))
    drill_parser.add_argument("--object-store-force-path-style", action="store_true", default=False)
    drill_parser.add_argument("--restore-from-object-store", action="store_true", default=False)
    drill_parser.add_argument("--command-timeout-seconds", type=int, default=int(os.getenv("BACKUP_COMMAND_TIMEOUT_SECONDS", str(DEFAULT_COMMAND_TIMEOUT_SECONDS))))

    prune_parser = subparsers.add_parser("prune", help="Prune old backup artifacts according to retention settings")
    prune_parser.add_argument("--output-dir", default=os.getenv("BACKUP_OUTPUT_DIR", "backups"))
    prune_parser.add_argument("--keep-last", type=int, default=int(os.getenv("BACKUP_RETENTION_KEEP_LAST", "0") or 0))
    prune_parser.add_argument("--max-age-days", type=int, default=(int(os.getenv("BACKUP_RETENTION_MAX_AGE_DAYS")) if os.getenv("BACKUP_RETENTION_MAX_AGE_DAYS") else None))

    rotate_parser = subparsers.add_parser("rotate-passphrase", help="Re-encrypt an existing backup with a new passphrase")
    rotate_parser.add_argument("--backup-file", required=True)
    rotate_parser.add_argument("--current-passphrase", default=os.getenv("BACKUP_ENCRYPTION_PASSPHRASE"))
    rotate_parser.add_argument("--new-passphrase", default=os.getenv("BACKUP_NEW_ENCRYPTION_PASSPHRASE"))
    rotate_parser.add_argument("--output-dir")
    rotate_parser.add_argument("--reupload-object-store", action="store_true")
    rotate_parser.add_argument("--object-store-bucket", default=os.getenv("BACKUP_S3_BUCKET"))
    rotate_parser.add_argument("--object-store-prefix", default=os.getenv("BACKUP_S3_PREFIX"))
    rotate_parser.add_argument("--object-store-endpoint-url", default=os.getenv("BACKUP_S3_ENDPOINT_URL"))
    rotate_parser.add_argument("--object-store-region", default=os.getenv("BACKUP_S3_REGION"))
    rotate_parser.add_argument("--object-store-access-key-id", default=os.getenv("BACKUP_S3_ACCESS_KEY_ID") or os.getenv("AWS_ACCESS_KEY_ID"))
    rotate_parser.add_argument("--object-store-secret-access-key", default=os.getenv("BACKUP_S3_SECRET_ACCESS_KEY") or os.getenv("AWS_SECRET_ACCESS_KEY"))
    rotate_parser.add_argument("--object-store-session-token", default=os.getenv("BACKUP_S3_SESSION_TOKEN") or os.getenv("AWS_SESSION_TOKEN"))
    rotate_parser.add_argument("--object-store-force-path-style", action="store_true", default=False)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    object_store = _module().resolve_object_store_config(
        bucket=getattr(args, "object_store_bucket", None),
        prefix=getattr(args, "object_store_prefix", None),
        endpoint_url=getattr(args, "object_store_endpoint_url", None),
        region=getattr(args, "object_store_region", None),
        access_key_id=getattr(args, "object_store_access_key_id", None),
        secret_access_key=getattr(args, "object_store_secret_access_key", None),
        session_token=getattr(args, "object_store_session_token", None),
        force_path_style=getattr(args, "object_store_force_path_style", None),
    )
    if args.command == "backup":
        database_url = _resolve_database_url(args.database_url, "DATABASE_URL")
        artifact = _module().backup_database(database_url, output_dir=Path(args.output_dir), label=args.label, docker_compose_service=args.docker_compose_service, encryption_passphrase=args.encryption_passphrase, prune_keep_last=args.prune_keep_last or None, prune_max_age_days=args.prune_max_age_days, object_store=object_store, command_timeout_seconds=args.command_timeout_seconds)
        print(json.dumps(artifact.metadata, indent=2, sort_keys=True))
        return 0
    if args.command == "restore":
        database_url = _resolve_database_url(args.database_url, "TARGET_DATABASE_URL")
        report = _module().restore_database(database_url, backup_file=args.backup_file, docker_compose_service=args.docker_compose_service, recreate_target_database=args.recreate_target_database, encryption_passphrase=args.encryption_passphrase, object_store=object_store, command_timeout_seconds=args.command_timeout_seconds)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "drill":
        source_database_url = _resolve_database_url(args.source_database_url, "DATABASE_URL")
        target_database_url = _resolve_database_url(args.target_database_url, "DRILL_DATABASE_URL")
        report = _module().run_backup_restore_drill(source_database_url, target_database_url, output_dir=Path(args.output_dir), label=args.label, docker_compose_service=args.docker_compose_service, report_file=Path(args.report_file) if args.report_file else None, encryption_passphrase=args.encryption_passphrase, prune_keep_last=args.prune_keep_last or None, prune_max_age_days=args.prune_max_age_days, object_store=object_store, restore_from_object_store=args.restore_from_object_store, command_timeout_seconds=args.command_timeout_seconds)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "prune":
        retention = _module().prune_backup_artifacts(Path(args.output_dir), keep_last=args.keep_last or None, max_age_days=args.max_age_days)
        print(json.dumps({"deleted_files": retention.deleted_files, "kept_sets": retention.kept_sets, "pruned_sets": retention.pruned_sets}, indent=2, sort_keys=True))
        return 0
    if args.command == "rotate-passphrase":
        if not args.current_passphrase:
            raise SystemExit("Missing current passphrase. Provide --current-passphrase or set BACKUP_ENCRYPTION_PASSPHRASE.")
        if not args.new_passphrase:
            raise SystemExit("Missing new passphrase. Provide --new-passphrase or set BACKUP_NEW_ENCRYPTION_PASSPHRASE.")
        artifact = _module().rotate_backup_encryption_passphrase(args.backup_file, current_passphrase=args.current_passphrase, new_passphrase=args.new_passphrase, output_dir=Path(args.output_dir) if args.output_dir else None, object_store=object_store, reupload_object_store=args.reupload_object_store)
        print(json.dumps(artifact.metadata, indent=2, sort_keys=True))
        return 0
    parser.error(f"Unsupported command: {args.command}")
    return 2
