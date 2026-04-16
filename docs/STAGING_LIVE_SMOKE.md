# Staging Live Smoke

Use this package to validate a deployed staging environment with real secrets, management keys, live LLM quota refresh, and an optional backup/restore drill.

## Required secrets

- `STAGING_BASE_URL`
- `STAGING_MANAGEMENT_VIEWER_KEY`
- `STAGING_MANAGEMENT_OPERATOR_KEY`

## Optional secrets and environment

- `STAGING_USER_ID`
- `STAGING_USER_ROLE`
- `STAGING_TENANT_ID`
- `STAGING_TIMEOUT_SECONDS`
- `STAGING_REFRESH_QUOTA_PROVIDERS` — comma-separated providers to refresh via `/v1/admin/llm/providers/{provider}/refresh-quota`
- `STAGING_VERIFY_ADMIN_WRITE=true|false` — optionally verify an admin-only no-op write path
- `STAGING_EXPECT_OBJECT_STORE_UPLOAD=true|false` — require backup drill to produce `object_store.artifact_uri`
- `STAGING_VERIFY_METRICS=true|false`
- `STAGING_VERIFY_LIVE_ROUTING=true|false` — use admin scope override write + operator preview to verify project override affects live routing
- `STAGING_LIVE_ROUTING_PROVIDER` — optional provider name to force during live routing verification
- `STAGING_TRIGGER_BACKUP_DRILL_VIA_API=true|false` — trigger the drill through `/v1/admin/ops/backups/drill/run` instead of running the local script
- `STAGING_DATABASE_URL` — source database URL for a direct local backup/restore drill (`scripts/postgres_backup_restore.py drill`)
- `STAGING_DRILL_DATABASE_URL` — restore target database URL for the direct local drill
- `STAGING_DRILL_TARGET_NAME` — pre-registered restore target name for `/v1/admin/ops/backups/drill/run`
- `BACKUP_ENCRYPTION_PASSPHRASE`
- `BACKUP_R2_*` or `BACKUP_S3_*`
- `BACKUP_OBJECT_STORE_VERIFY_RESTORE=true|false`

## What it verifies

Core API checks:
- `GET /readyz` with a viewer management key
- `GET /runbooks` with a viewer management key
- `GET /metrics` with a viewer management key and presence of `acp_rate_limit_backend_healthy`
- `GET /v1/admin/llm/providers` with an operator management key
- `POST /v1/admin/llm/routing/preview` with an operator management key
- `GET /v1/admin/audit/events` with an operator management key
- optional admin-only write verification when `STAGING_VERIFY_ADMIN_WRITE=true`
- optional live routing override verification when `STAGING_VERIFY_LIVE_ROUTING=true`
- optional backup drill trigger via `/v1/admin/ops/backups/drill/run` with an admin key, `Idempotency-Key`, and `STAGING_DRILL_TARGET_NAME` when `STAGING_TRIGGER_BACKUP_DRILL_VIA_API=true`, followed by polling `/v1/admin/ops/backups/drill/jobs/{job_id}` until completion or optional cancellation
- `POST /v1/cycles` and `GET /v1/cycles/{cycle_id}` with a staging user identity

Optional live-provider checks:
- `POST /v1/admin/llm/providers/{provider}/refresh-quota` for each provider listed in `STAGING_REFRESH_QUOTA_PROVIDERS`
- verifies that `external_observed_at` is populated after refresh

Optional backup/restore checks:
- runs `python scripts/postgres_backup_restore.py drill`
- supports encrypted artifacts and optional object-store upload
- supports remote restore verification when `BACKUP_OBJECT_STORE_VERIFY_RESTORE=true`

## Run locally

```bash
export STAGING_BASE_URL=https://staging.example.com
export STAGING_MANAGEMENT_VIEWER_KEY=...
export STAGING_MANAGEMENT_OPERATOR_KEY=...
export STAGING_MANAGEMENT_ADMIN_KEY=... # optional unless STAGING_VERIFY_ADMIN_WRITE=true
export STAGING_REFRESH_QUOTA_PROVIDERS=gemini,openai
python scripts/staging_live_smoke.py
```

To include a direct local backup drill:

```bash
export STAGING_DATABASE_URL=postgresql+psycopg://...
export STAGING_DRILL_DATABASE_URL=postgresql+psycopg://...
export BACKUP_ENCRYPTION_PASSPHRASE=...
export BACKUP_R2_ACCOUNT_ID=...
export BACKUP_R2_BUCKET=...
export BACKUP_R2_ACCESS_KEY_ID=...
export BACKUP_R2_SECRET_ACCESS_KEY=...
export BACKUP_OBJECT_STORE_VERIFY_RESTORE=true
python scripts/staging_live_smoke.py
```

## GitHub Actions

Trigger `.github/workflows/staging-live-smoke.yml` with the same secrets. When `STAGING_TRIGGER_BACKUP_DRILL_VIA_API=true`, the workflow now pre-validates that `STAGING_MANAGEMENT_ADMIN_KEY` is present, uses the admin API with `STAGING_DRILL_TARGET_NAME` and an `Idempotency-Key`, receives a queued job ID, and polls the drill status endpoint until the worker completes. Direct database URLs are not required in this mode. Direct database URLs remain optional only for the local script drill path. The workflow uploads any backup-drill artifacts produced under `backups/staging-live-smoke`.
