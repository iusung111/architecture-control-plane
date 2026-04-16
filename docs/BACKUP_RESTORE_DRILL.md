# Backup and restore drill

## Goals
- Produce a reproducible PostgreSQL backup artifact.
- Restore the artifact into a clean drill database.
- Verify critical tables exist and capture row counts.
- Record a JSON drill report that can be archived as evidence.

## Commands
```bash
BACKUP_ENCRYPTION_PASSPHRASE='<strong-passphrase>' BACKUP_RETENTION_KEEP_LAST=7 BACKUP_RETENTION_MAX_AGE_DAYS=30 make backup-db DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/control_plane

BACKUP_FILE=backups/<artifact>.dump.enc BACKUP_ENCRYPTION_PASSPHRASE='<strong-passphrase>' TARGET_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/control_plane_restore make restore-db RECREATE_TARGET_DATABASE=1

BACKUP_ENCRYPTION_PASSPHRASE='<strong-passphrase>' BACKUP_RETENTION_KEEP_LAST=7 BACKUP_RETENTION_MAX_AGE_DAYS=30 make drill-backup-restore DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/control_plane DRILL_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/control_plane_restore_drill

make prune-backups BACKUP_OUTPUT_DIR=backups BACKUP_RETENTION_KEEP_LAST=7 BACKUP_RETENTION_MAX_AGE_DAYS=30
```

## Local Docker Compose path
```bash
make docker-up
make drill-backup-restore-compose
```

## Artifacts
Each backup writes:
- `<timestamp>_<database>.dump.enc` when encryption is enabled
- `<timestamp>_<database>.dump` when encryption is disabled
- `<timestamp>_<database>.metadata.json`

Metadata records the artifact SHA-256, encryption algorithm/KDF parameters, and retention actions.

Each drill writes:
- a backup artifact and metadata
- `<timestamp>_backup_restore_drill_report.json`

## Verification
The drill verifies these tables by default:
- `alembic_version`
- `cycles`
- `cycle_iterations`
- `jobs`
- `notifications_outbox`
- `audit_events`

## Notes
- `--docker-compose-service postgres` streams `pg_dump`/`pg_restore` through the compose PostgreSQL container so the host does not need local PostgreSQL client tools.
- Database recreation uses direct PostgreSQL connectivity to the target URL. Ensure the host can reach that PostgreSQL endpoint.

## Encryption and retention
- Use `BACKUP_ENCRYPTION_PASSPHRASE` for AES-256-GCM encryption at rest.
- Store the passphrase in a secret manager or CI secret, never in git.
- Retention is applied after each backup/drill when `BACKUP_RETENTION_KEEP_LAST` and/or `BACKUP_RETENTION_MAX_AGE_DAYS` are set.
- `make prune-backups` can be run as a standalone cleanup step.

## Scheduled drill
A scheduled GitHub Actions workflow runs a weekly backup/restore drill against a disposable PostgreSQL service container, uploads the encrypted artifact and JSON report, and exercises the same CLI used for manual drills.


## Cloudflare R2 or S3-compatible object storage
Set `BACKUP_R2_ACCOUNT_ID`, `BACKUP_R2_BUCKET`, `BACKUP_R2_ACCESS_KEY_ID`, and `BACKUP_R2_SECRET_ACCESS_KEY` for the recommended Cloudflare R2 path, or use the generic `BACKUP_S3_*` settings for other S3-compatible object stores. Uploaded backups include both the artifact and metadata JSON after each backup/drill.

- Uploaded metadata records `object_store.artifact_uri` and `object_store.metadata_uri`.
- `BACKUP_OBJECT_STORE_VERIFY_RESTORE=true` makes drills restore from the uploaded `s3://...` artifact, not the local file.
- Generate a provider lifecycle policy JSON with `python scripts/render_s3_lifecycle_policy.py`.
