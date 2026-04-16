# Operations deployment checklist

## 1. Configuration
- Set `DATABASE_URL` to the production PostgreSQL endpoint.
- Set `AUTH_MODE=oidc_jwks` or `AUTH_MODE=bearer_jwt` in production.
- Configure `AUTH_JWKS_URL` for IdP-backed OIDC, or set `AUTH_OIDC_DISCOVERY_URL` / an HTTP(S) `AUTH_JWT_ISSUER` so the service can auto-discover the `jwks_uri`. For shared-secret JWT, configure `AUTH_JWT_SECRET`.
- Keep `AUTH_OIDC_REQUIRE_HTTPS=true` unless the deployment is an explicitly local loopback test.
- Set `AUTH_JWT_ISSUER` and `AUTH_JWT_AUDIENCE` to match the identity provider.
- Set `NOTIFICATION_WEBHOOK_URL` if outbox delivery must leave the service boundary.
- Confirm `OPENAI_API_KEY` only if live LLM integration is enabled.
- Set `OTEL_ENABLED=true` and `OTEL_EXPORTER_OTLP_ENDPOINT` when traces should leave the process.

## 2. Database
- Run `alembic upgrade head` before sending traffic.
- Confirm `/readyz` returns HTTP 200 after migrations complete.
- Verify backup and restore procedures for the PostgreSQL cluster.
- Run `make drill-backup-restore` (or `make drill-backup-restore-compose`) on a schedule and archive the generated drill report JSON.

## 3. Workers
- Run at least one `jobs` worker and one `outbox` worker.
- Enable worker metrics ports so Prometheus can scrape them.
- Confirm worker logs contain `job.succeeded` and `outbox.delivered` events after a smoke request.
- Inspect `dead_lettered` rows before declaring the deployment healthy.

## 4. Security
- Disable header fallback in production: `AUTH_HEADER_FALLBACK_ENABLED=false`.
- Rotate JWT secrets or OIDC client credentials through the secret manager, not committed files. Prefer mounted secret files with `*_FILE` or `SECRETS_DIR` references.
- Restrict webhook destinations and TLS certificates according to the deployment environment.
- Verify the OIDC issuer JWKS endpoint is reachable from the application runtime.

## 5. Observability
- Confirm Prometheus scrapes `api:8000`, `worker-jobs:9101`, and `worker-outbox:9102`.
- Confirm Alertmanager is reachable from Prometheus and that the sample route can POST to the configured receiver.
- Confirm traces appear in Tempo after sending a smoke request.
- Confirm Grafana shows the `Architecture Control Plane Overview` dashboard and that burn-rate panels render for API availability and API latency.
- Confirm job backlog metrics (`acp_job_oldest_ready_age_seconds`, `acp_job_oldest_running_age_seconds`, `acp_job_queue_depth`) are present on the worker metrics scrape.
- Confirm `x-request-id` and `traceparent` are present on API responses.

## 6. Smoke test
- `GET /healthz` returns `200 {"status":"ok"}`.
- `GET /readyz` returns `200 {"status":"ready"}`.
- Create a cycle, run a worker pass, and confirm the result endpoint returns a terminal state.
- Confirm at least one audit event row exists for the smoke request.
- Confirm at least one trace for the smoke request is visible in Tempo.

## 7. Rollback signals
- Repeated `request.unhandled_exception` log events.
- Job dead-letter growth during the first minutes after deploy.
- `ACPJobQueueBacklog` or `ACPBackupDrillRunningTooLong` firing without a planned maintenance reason.
- Outbox dead-letter growth or persistent 5xx webhook responses.
- `/readyz` failing after deployment.
- Prometheus scrape targets turning unhealthy.

## Compose smoke expectations
- `make smoke-compose` should drive a cycle through approval and verify webhook delivery for `approval.requested`, `approval.approved`, and `cycle.completed`.
- Prometheus and Grafana should be reachable after `make docker-up`, and the Prometheus rules page should show the ACP recording/alert rules as loaded.
- Check `docker compose logs webhook-sink worker-outbox otel-collector prometheus grafana` if smoke or dashboards fail.

## 8. Runbooks
- Refresh generated runbook links with `python scripts/render_alert_rules.py` if alert names or base URLs change.
- Verify `GET /runbooks` returns the published runbook list and that each alert in Prometheus has a `runbook_url` annotation.
- Review `docs/runbooks/INDEX.md` after alert rule changes.


## Alert routing checks
- Re-render Alertmanager config with `python scripts/render_alertmanager_config.py` after changing recipients or SMTP settings.
- Verify `deploy/alertmanager/alertmanager.yml` contains the intended `to:` address.
- Confirm critical alerts and `notify=email` alerts route to the email receiver.
- For local compose runs, verify Mailpit is reachable at `http://localhost:8025`.
- Send a synthetic alert through Alertmanager and confirm both webhook and email delivery paths.


## Additional production hardening
- Verify `MANAGEMENT_ENDPOINTS_REQUIRE_API_KEY=true` and that `/readyz`, `/metrics`, and `/runbooks` are only reachable with `X-Management-Key`. Exempt `/readyz` and `/metrics` from shared management rate limits so probes and Prometheus scrapes are not throttled.
- Run migrations as a separate step or one-shot job before deploying API replicas.
- Confirm worker `/readyz` endpoints return HTTP 200 before routing traffic or considering the stack healthy.
- Review database pool and timeout settings against expected concurrency before rollout.
- Run `python scripts/release_readiness.py` with production-equivalent environment variables before promotion; runtime validation reads the active shell env, while repo quality gates run with repo runtime vars scrubbed to avoid secret-bearing deploy envs changing unit-test defaults. Use `ACP_RELEASE_RUN_POSTGRES_INTEGRATION=1` and `ACP_RELEASE_RUN_COMPOSE_SMOKE=1` when those gates are required for the release.


## Webhook security

- Verify `NOTIFICATION_WEBHOOK_SIGNING_SECRET` is configured and rotated through secret management.
- Confirm downstream webhook receivers validate HMAC signatures, timestamp freshness, and nonce replay protection.
- In production, do not run notification delivery without a signing secret.

## Container security

- Ensure production images run as the non-root `app` user.
- Prefer read-only root filesystem and drop Linux capabilities at the orchestrator layer where supported.


## Abuse protection

- Verify `ABUSE_*` limits match expected tenant and operator traffic.
- If `ABUSE_RATE_LIMIT_ALGORITHM=token_bucket`, confirm `ABUSE_RATE_LIMIT_BURST_MULTIPLIER` matches the intended burst allowance.
- If tenant plans are enabled, review `ABUSE_TENANT_PLAN_ASSIGNMENTS_JSON` and `ABUSE_TENANT_PLAN_LIMITS_JSON` against the current contract.
- Confirm `429` responses include `Retry-After`.
- Confirm `acp_rate_limit_rejections_total` is scraped and alerted when unexpectedly high.
- In production, set `ABUSE_RATE_LIMIT_BACKEND=redis` and confirm `ABUSE_REDIS_URL` points at a reachable shared Redis service.
- Verify all API replicas share the same Redis key prefix and database.


## Backup and restore drill automation
- `make backup-db` writes a custom-format `pg_dump` artifact and metadata JSON under `backups/` by default.
- `make restore-db BACKUP_FILE=... TARGET_DATABASE_URL=... RECREATE_TARGET_DATABASE=1` restores a backup into a target PostgreSQL database.
- `make drill-backup-restore` performs backup, target database recreation, restore, and verification in one command.
- `make drill-backup-restore-compose` is the local Docker Compose convenience path and assumes the compose PostgreSQL service is published on `localhost:5432`.
- Review the generated drill report for `missing_tables`, row counts, artifact hash, and runtime duration before closing the drill.


## Backup and restore operations
- [ ] Backup encryption passphrase is stored in a secret manager and rotated on an agreed schedule.
- [ ] Retention values (`BACKUP_RETENTION_KEEP_LAST`, `BACKUP_RETENTION_MAX_AGE_DAYS`) match policy.
- [ ] Latest scheduled drill artifact/report is available and reviewed.
- [ ] Restore drill evidence is archived with timestamp, operator, and target database.


## Backup object storage checks
- Verify `BACKUP_S3_BUCKET` and credentials are injected from a secret manager.
- Verify scheduled drills can restore from object storage when `BACKUP_OBJECT_STORE_VERIFY_RESTORE=true`.
- Keep object store lifecycle expiration aligned with `BACKUP_RETENTION_MAX_AGE_DAYS`.


## Rate limit backend checks

- Confirm `ABUSE_RATE_LIMIT_BACKEND=redis` in production.
- Confirm the intended split between `ABUSE_RATE_LIMIT_BACKEND_FAILURE_MODE_API` and `ABUSE_RATE_LIMIT_BACKEND_FAILURE_MODE_MANAGEMENT`.
- Verify `acp_rate_limit_backend_healthy{backend="redis"}` is 1.
- Alert on `acp_rate_limit_backend_decisions_total{decision="allow_on_backend_failure"}` if API fail-open is enabled.
- If tenant labels are enabled, inspect `acp_rate_limit_tenant_events_total` for hot tenants or abuse concentration.
- Review `acp_rate_limit_plan_events_total` for plan-specific throttling hotspots or mis-sized quotas.


## Staging live smoke
- Run `python scripts/staging_live_smoke.py` against the deployed staging URL before promoting changes.
- If live provider credentials are configured in staging, set `STAGING_REFRESH_QUOTA_PROVIDERS` and confirm refresh populates `external_observed_at` for the selected providers.
- If staging database credentials are available, run the optional staging backup drill and archive the emitted report/artifacts. For admin API-triggered drills, send an `Idempotency-Key`, monitor the reported stage progression, watch `acp_job_oldest_running_age_seconds{job_type="backup_restore_drill"}`, and cancel the queued job if the wrong target was selected before execution begins.
- Verify viewer and admin management keys both work with their intended scopes.


## Management RBAC audit

- Verify `MANAGEMENT_API_KEYS_JSON` is configured with separate `viewer`, `operator`, and `admin` keys.
- Review recent management write events via `/v1/admin/audit/events`.
- Confirm LLM policy and scope override changes record the acting management role and request ID.

- Verify operator can read `/v1/admin/ops/abuse/config`, `/v1/admin/ops/backups/config`, and `/v1/admin/ops/observability/status`. Verify only admin keys can trigger `/v1/admin/ops/backups/drill/run`, and only with a pre-registered target name.



## Kubernetes rollout sequence

- Apply `deploy/kubernetes/` only after replacing the placeholder secrets and image references, or after wiring `external-secret.example.yaml` to your platform store.
- Run `deploy/kubernetes/migrate-job.yaml` separately and wait for `job/acp-migrate` to complete before treating the rollout as healthy.
- After migration success, verify `deployment/acp-api`, `deployment/acp-worker-jobs`, and `deployment/acp-worker-outbox` are available.
- Confirm the API readiness probe succeeds with `MANAGEMENT_PROBE_KEY` sourced from `acp-secrets`.


- After rotating Kubernetes-mounted secrets, restart the API and worker deployments so cached runtime settings reload.
