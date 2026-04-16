# architecture-control-plane scaffold

This scaffold is the executable companion to the latest control-plane architecture documents. It includes a production-oriented execution path: API, database migrations, job workers, outbox delivery, authentication modes, and an observability stack with Prometheus, Grafana, Tempo, and an OpenTelemetry Collector.

## What is included
- FastAPI application with cycle and approval routes, including cycle list filters and SSE status streaming
- Pydantic schemas and typed response envelopes
- SQLAlchemy models, repositories, and transactional services
- Alembic initial migration
- Default job handlers for verification, retry, replan, and approval resume
- Outbox webhook dispatcher with retry and dead-letter classification
- OpenAPI contract under `docs/contracts/openapi.yaml`
- Operations checklist under `docs/OPERATIONS_CHECKLIST.md`
- Docker Compose observability stack: Prometheus, Alertmanager, Grafana, Tempo, OpenTelemetry Collector

## Layout
- `app/api/` route layer and dependency wiring
- `app/services/` business logic and transaction orchestration
- `app/repositories/` persistence access
- `app/domain/` enums and state guards
- `app/db/` ORM models and session setup
- `app/core/` auth, logging, tracing, metrics
- `deploy/` collector, Prometheus, Grafana, and Tempo configuration
- `docs/contracts/` API and payload contracts
- `db_migrations/` database migration history
- `tests/` smoke, contract, runtime, and PostgreSQL integration tests

## Quick start
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

## Docker Compose
```bash
make docker-migrate
make docker-up
curl http://localhost:8000/healthz
curl -H "X-Management-Key: local-dev-management-key" http://localhost:8000/readyz
make observability-urls
make smoke-compose
make docker-logs
make docker-down
```

The compose stack starts these services:
- `postgres`
- `api`
- `worker-jobs`
- `worker-outbox`
- `webhook-sink`
- `mailpit`
- `alertmanager`
- `otel-collector`
- `tempo`
- `prometheus`
- `grafana`

Default local URLs:
- API: `http://localhost:8000`
- Webhook sink: `http://localhost:8081`
- Prometheus: `http://localhost:9090`
- Alertmanager: `http://localhost:9093`
- Mailpit: `http://localhost:8025`
- Grafana: `http://localhost:3000` (`admin/admin`)
- Tempo API: `http://localhost:3200`
- Worker jobs metrics: `http://localhost:9101/metrics`
- Worker outbox metrics: `http://localhost:9102/metrics`

## Common commands
```bash
make install
make lint
make test
make test-postgres
make run
make migrate
make run-jobs-once
make run-outbox-once
make smoke-compose
```

## Environment
- `DATABASE_URL` defaults to `postgresql+psycopg://postgres:postgres@localhost:5432/control_plane`
- `LLM_PROVIDER` can be `disabled`, `openai`, `gemini`, `grok`, `claude`, or `cloudflare_workers_ai`
- `LLM_USAGE_MODE` defaults to `free_only`; set `LLM_USAGE_MODE=paid` to explicitly allow billed usage for providers without a built-in free-only cap
- `LLM_USAGE_COUNTER_BACKEND=auto|redis|in_memory` controls how free-tier daily caps are shared across replicas; use `redis` (or `auto` with a Redis URL) for multi-instance deployments
- `LLM_USAGE_REDIS_URL` optionally overrides `ABUSE_REDIS_URL` for shared LLM free-tier counters
- OpenAI uses `OPENAI_API_KEY` and `OPENAI_MODEL`
- Gemini uses `GEMINI_API_KEY`, `GEMINI_BASE_URL`, and `GEMINI_MODEL`
- Grok uses `GROK_API_KEY`, `GROK_BASE_URL`, and `GROK_MODEL`
- Claude uses `CLAUDE_API_KEY`, `CLAUDE_BASE_URL`, `CLAUDE_MODEL`, and `CLAUDE_API_VERSION`
- Cloudflare Workers AI uses `CLOUDFLARE_AI_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID` (or `CLOUDFLARE_AI_BASE_URL`), and `CLOUDFLARE_AI_MODEL`
- `APPROVAL_EXPIRY_HOURS` defaults to `24`
- `AUTH_MODE` can be `header`, `bearer_jwt`, or `oidc_jwks`
- `AUTH_JWT_SECRET` is required when `AUTH_MODE=bearer_jwt`
- `AUTH_JWKS_URL` can be set directly for `AUTH_MODE=oidc_jwks`; otherwise the service can auto-discover `jwks_uri` from `AUTH_OIDC_DISCOVERY_URL` or from `AUTH_JWT_ISSUER/.well-known/openid-configuration` when the issuer is an HTTP(S) URL
- `AUTH_OIDC_REQUIRE_HTTPS=true` enforces HTTPS discovery metadata and JWKS endpoints except loopback URLs used for local testing
- `AUTH_JWT_ALLOWED_ALGORITHMS` should match `AUTH_MODE`: use `HS256`/`HS384`/`HS512` for `bearer_jwt`, and use `RS256`/`RS384`/`RS512`/`ES256`/`ES384`/`ES512`/`EdDSA` for `oidc_jwks`
- `AUTH_HEADER_FALLBACK_ENABLED=false` is required in production
- `MANAGEMENT_ENDPOINTS_REQUIRE_API_KEY=true` with `MANAGEMENT_API_KEYS_JSON={"viewer-key":"viewer","ops-key":"operator","admin-key":"admin"}` should protect `/readyz`, `/metrics`, and `/runbooks` in production
- `METRICS_ENABLED=true` exposes Prometheus metrics on `GET /metrics`
- `WORKER_METRICS_ENABLED=true` enables `--metrics-port` on worker processes
- `API_AVAILABILITY_SLO_TARGET`, `API_LATENCY_SLO_TARGET`, and `API_LATENCY_SLO_SECONDS` control the built-in SLO event classification that Prometheus alert rules consume
- `OTEL_ENABLED=true` enables OTLP trace export
- `OTEL_EXPORTER_OTLP_ENDPOINT` should point to an OTLP/HTTP traces endpoint such as `http://otel-collector:4318/v1/traces`
- `OTEL_SERVICE_NAME` overrides the default service name derived from `APP_NAME`
- `OTEL_TRACES_SAMPLER_RATIO` controls parent-based trace sampling
- `NOTIFICATION_WEBHOOK_URL` enables real webhook delivery for the outbox consumer

### Secret-loading patterns

Sensitive settings may be supplied as plain environment variables, `*_FILE` references, or through a shared `SECRETS_DIR` directory mount. At runtime, `*_FILE` overrides win over `SECRETS_DIR`, and both override plain environment values.

Examples:

- `DATABASE_URL_FILE=/var/run/acp-secrets/DATABASE_URL`
- `AUTH_JWT_SECRET_FILE=/var/run/acp-secrets/AUTH_JWT_SECRET`
- `SECRETS_DIR=/var/run/acp-secrets`

Restart the API and worker processes after secret rotation so the cached runtime settings refresh.

## Readiness, metrics, and operations
- `GET /healthz` checks process liveness
- `GET /readyz` checks database readiness via `SELECT 1` and should be called with `X-Management-Key` when management protection is enabled
- `GET /metrics` exposes Prometheus text metrics when enabled and should be protected with `X-Management-Key` in production
- Worker CLI supports `--metrics-port` for a scrape endpoint per worker process
- HTTP responses include `x-request-id` and `traceparent` headers for correlation
- `docs/OPERATIONS_CHECKLIST.md` contains the deployment and rollback checklist
- `GET /runbooks` and `GET /runbooks/{slug}` expose local alert runbooks behind the management key, and `docs/runbooks/INDEX.md` is the generated runbook catalog

## OpenTelemetry, Prometheus, and Grafana
- `deploy/otel/otel-collector-config.yaml` receives OTLP traces and forwards them to Tempo
- `deploy/prometheus/prometheus.yml` scrapes the API and worker metrics endpoints, sends alerts to Alertmanager, and loads alert/recording rules from `deploy/prometheus/alerts/acp-alerts.yml`
- `deploy/alertmanager/alertmanager.yml` is the rendered Alertmanager route/receiver config, and `deploy/alertmanager/alertmanager.src.yml` is the source used by `python scripts/render_alertmanager_config.py`
- `deploy/grafana/provisioning/` provisions Prometheus and Tempo datasources automatically
- `deploy/grafana/dashboards/acp-observability.json` is the starter dashboard for HTTP, auth, SLO burn rate, job, and outbox metrics

Trace flow in Compose:
1. API and workers export OTLP/HTTP traces to `otel-collector`
2. Collector batches and forwards traces to `tempo`
3. Grafana uses `tempo` as the trace datasource
4. Prometheus scrapes `/metrics` from the API and worker metrics ports
5. Prometheus evaluates burn-rate alerts and other operational rules from `deploy/prometheus/alerts/acp-alerts.yml`
6. Alertmanager groups and forwards alerts according to `deploy/alertmanager/alertmanager.yml`

Runbook links are generated by `python scripts/render_alert_rules.py`, which injects `runbook_url` annotations into the final Prometheus rule file and refreshes `docs/runbooks/INDEX.md`.

## PostgreSQL integration tests
The default test suite runs entirely on SQLite. To run the PostgreSQL path, start a reachable PostgreSQL instance and then run:

```bash
export RUN_POSTGRES_INTEGRATION=1
export TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/control_plane_test
pytest -q tests/test_postgres_integration.py
```

## CI
- GitHub Actions workflow: `.github/workflows/ci.yml`
- Checks: `ruff check .`, `pytest -q`, dedicated PostgreSQL integration, and compose smoke


## Alertmanager email routing
- All alerts route to the webhook sink receiver.
- `severity=critical` alerts route to the default email receiver.
- Alerts labeled `notify=email` also route to the default email receiver.
- The default email recipient placeholder is `team@example.com`; set a team-owned mailbox before production use.

To change recipients or SMTP settings, render the config again:

```bash
export ALERTMANAGER_DEFAULT_EMAIL_TO=team@example.com
export ALERTMANAGER_SMTP_FROM=architecture-control-plane-alerts@example.com
export ALERTMANAGER_SMTP_SMARTHOST=smtp.example.com:587
export ALERTMANAGER_SMTP_REQUIRE_TLS=true
export ALERTMANAGER_SMTP_AUTH_USERNAME=...
export ALERTMANAGER_SMTP_AUTH_PASSWORD=...
python scripts/render_alertmanager_config.py
```

For local Docker Compose runs, Mailpit acts as the SMTP sink and web UI so `make smoke-compose` can verify email delivery end-to-end.

## Backup and restore drill
Use `scripts/postgres_backup_restore.py` to create custom-format PostgreSQL backups, restore them into a target database, and run an automated restore drill with verification.

Examples:

```bash
make backup-db DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/control_plane
BACKUP_FILE=backups/<artifact>.dump TARGET_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/control_plane_restore make restore-db RECREATE_TARGET_DATABASE=1
make drill-backup-restore DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/control_plane DRILL_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/control_plane_restore_drill
```

For local Docker Compose, the easiest path is to keep `postgres` published on `localhost:5432` and run:

```bash
make drill-backup-restore-compose
```

The drill writes a `.dump`, a matching `.metadata.json`, and a restore-drill report JSON under `backups/` by default.

## Production hardening implemented
- Startup now fails fast in production when insecure auth or management settings are used.
- Management endpoints (`/readyz`, `/metrics`, `/runbooks`) can require `X-Management-Key`.
- API startup is separated from migrations; use `make migrate` or `make docker-migrate` before rollout.
- PostgreSQL engines now apply pool sizing, connect timeout, statement timeout, and idle-in-transaction timeout settings.
- Worker CLI exposes `/healthz`, `/readyz`, `/state`, and `/metrics` on the `--metrics-port` endpoint and drains on SIGTERM/SIGINT.


## Webhook signing

Outbox webhook delivery signs requests with HMAC-SHA256 when `NOTIFICATION_WEBHOOK_SIGNING_SECRET` is set. Receivers should verify `X-ACP-Timestamp`, `X-ACP-Nonce`, and `X-ACP-Signature`, and reject stale or replayed deliveries. The local `webhook-sink` service in Docker Compose validates the signature using the shared secret.

## Container hardening

The runtime image now uses a multi-stage build and runs as a non-root `app` user. The build stage contains compilation tooling; the runtime stage copies only the installed virtualenv and runtime files.


## Abuse protection

The API includes built-in abuse controls with selectable rate-limit algorithms. Configure global and per-action limits with `ABUSE_*` settings.

- Global per-client request rate: `ABUSE_GLOBAL_REQUESTS_PER_MINUTE`
- Management endpoint rate: `ABUSE_MANAGEMENT_REQUESTS_PER_MINUTE`
- Per-actor action limits for create/retry/replan/approval confirm
- `ABUSE_RATE_LIMIT_ALGORITHM=fixed_window|token_bucket` to switch between simple fixed windows and smoother token-bucket refill behaviour
- `ABUSE_RATE_LIMIT_BURST_MULTIPLIER` to allow controlled bursts when using token buckets
- Tenant plan overrides via `ABUSE_TENANT_PLAN_ASSIGNMENTS_JSON` and `ABUSE_TENANT_PLAN_LIMITS_JSON`

Use `ABUSE_RATE_LIMIT_BACKEND=redis` with `ABUSE_REDIS_URL` for multi-instance shared counters. In production, the runtime validator now requires the Redis backend when abuse protection is enabled.

Rejected requests return HTTP `429` with a `Retry-After` header and increment `acp_rate_limit_rejections_total`. Plan-aware events also emit `acp_rate_limit_plan_events_total`, and tenant-level events can emit `acp_rate_limit_tenant_events_total` when tenant labels are enabled.


## Backup encryption and retention
Use `BACKUP_ENCRYPTION_PASSPHRASE` to encrypt backup artifacts, and `BACKUP_RETENTION_KEEP_LAST` / `BACKUP_RETENTION_MAX_AGE_DAYS` to prune old artifacts.

```bash
BACKUP_ENCRYPTION_PASSPHRASE="strong-passphrase" BACKUP_RETENTION_KEEP_LAST=7 BACKUP_RETENTION_MAX_AGE_DAYS=30 make backup-db
make prune-backups BACKUP_OUTPUT_DIR=backups BACKUP_RETENTION_KEEP_LAST=7 BACKUP_RETENTION_MAX_AGE_DAYS=30
BACKUP_FILE=backups/20260414T030000Z_control_plane.dump.enc BACKUP_ENCRYPTION_PASSPHRASE="old-pass" BACKUP_NEW_ENCRYPTION_PASSPHRASE="new-pass" make rotate-backup-passphrase
```

A scheduled GitHub Actions workflow is included at `.github/workflows/backup-restore-drill.yml`.


## Backup object storage
Cloudflare R2 is the recommended default. Set `BACKUP_R2_ACCOUNT_ID`, `BACKUP_R2_BUCKET`, `BACKUP_R2_ACCESS_KEY_ID`, and `BACKUP_R2_SECRET_ACCESS_KEY` to use the R2 S3-compatible endpoint automatically. The generic `BACKUP_S3_*` settings remain available for AWS S3, MinIO, and other S3-compatible stores. When `BACKUP_OBJECT_STORE_VERIFY_RESTORE=true`, drills restore from the uploaded `s3://...` artifact instead of the local file so the remote recovery path is exercised too.

Generate a matching lifecycle policy JSON with:

```bash
make render-s3-lifecycle-policy BACKUP_RETENTION_MAX_AGE_DAYS=30 BACKUP_S3_PREFIX=control-plane/backups
```


## LLM providers
The LLM access layer supports six backends:
- `disabled`: safe default that never calls an external provider
- `openai`: native OpenAI structured parsing via the Responses API
- `gemini`: Google Gemini over the OpenAI-compatible `https://generativelanguage.googleapis.com/v1beta/openai/` base URL
- `grok`: xAI Grok over the OpenAI-compatible `https://api.x.ai/v1` base URL
- `claude`: Anthropic Claude via the Messages API
- `cloudflare_workers_ai`: Cloudflare Workers AI over the OpenAI-compatible account endpoint

`LLM_USAGE_MODE=free_only` is the default. In that mode, the service only permits providers with an explicit free-tier request cap configured. Providers such as OpenAI, Grok, and Claude stay blocked until you set `LLM_USAGE_MODE=paid`. In production, the runtime validator now requires a shared Redis-backed counter (`LLM_USAGE_COUNTER_BACKEND=redis` or `auto` with `LLM_USAGE_REDIS_URL`/`ABUSE_REDIS_URL`) so the cap stays consistent across replicas.

Gemini, Grok, and Cloudflare Workers AI use a strict JSON-only prompt and validate the returned payload against `app/schemas/llm.py`. Claude applies the same schema validation after reading the Messages API text blocks.

The dynamic LLM routing layer now supports:
- provider policy management via `/v1/admin/llm/providers`
- provider quota refresh via `/v1/admin/llm/providers/{provider}/refresh-quota`
- tenant/project-specific provider overrides via `/v1/admin/llm/scopes/{scope_type}/{scope_id}`
- routing previews with scope context via `/v1/admin/llm/routing/preview?tenant_id=...&project_id=...`

Project-specific overrides take precedence over tenant-specific overrides. OpenAI refresh now combines the Usage API with a lightweight probe request so per-minute headers and daily usage can both be captured. Gemini, Grok, and Cloudflare Workers AI use lightweight OpenAI-compatible probe requests to capture live rate-limit headers where available, and Claude uses a minimal Messages API probe for the same purpose.


## Shared rate limit backend failure policy

When `ABUSE_RATE_LIMIT_BACKEND=redis`, backend errors can be handled in two modes:

- `ABUSE_RATE_LIMIT_BACKEND_FAILURE_MODE_API=open`: allow general API requests and record `acp_rate_limit_backend_decisions_total{decision="allow_on_backend_failure"}`.
- `ABUSE_RATE_LIMIT_BACKEND_FAILURE_MODE_MANAGEMENT=closed`: reject `/readyz`, `/metrics`, and `/runbooks*` with `503 rate_limit_backend_unavailable` when Redis is unavailable.
- `ABUSE_METRICS_INCLUDE_TENANT_LABELS=true` enables tenant-level abuse metrics; prefer `ABUSE_METRICS_TENANT_LABEL_MODE=hashed` in production.
- Tenant plan overrides can set different limits for `global_request`, `cycle_create`, `cycle_retry`, `cycle_replan`, and `approval_confirm`.

Watch these metrics in Prometheus/Grafana:

- `acp_rate_limit_backend_healthy`
- `acp_rate_limit_backend_errors_total`
- `acp_rate_limit_backend_decisions_total`
- `acp_rate_limit_plan_events_total`
- `acp_job_oldest_ready_age_seconds`
- `acp_job_oldest_running_age_seconds{job_type="backup_restore_drill"}`
- `acp_job_queue_depth`

Prometheus ships warning alerts for queue backlog (`ACPJobQueueBacklog`) and long-running backup drill jobs (`ACPBackupDrillRunningTooLong`). Refresh generated runbook links with `python scripts/render_alert_rules.py` after editing the alert rules.

## Staging live smoke

Use `python scripts/staging_live_smoke.py` or the `staging-live-smoke` GitHub Actions workflow to validate a deployed staging environment with real management keys. The staging package checks viewer/operator/admin management RBAC, LLM routing preview, optional live quota refresh for selected providers, optional live routing override verification, `/metrics` rate-limit backend health, and can optionally trigger an encrypted backup/restore drill either locally or through the admin ops API using a pre-registered backup drill target name and then poll the queued drill job until completion. See `docs/STAGING_LIVE_SMOKE.md`.

User-facing cycle APIs now include `GET /v1/cycles` for filtered recent work retrieval and `GET /v1/cycles/{cycle_id}/events` for server-sent event streaming of cycle snapshots, heartbeats, and terminal results.


## Management audit

- Recent management write events are available at `GET /v1/admin/audit/events`.
- `viewer` keys can access protected read-only management endpoints such as `/runbooks` and `/readyz`.
- `operator` keys can read management audit events.
- `admin` keys are required for `/v1/admin/llm/*` mutations.


Staging live smoke now expects a separate `STAGING_MANAGEMENT_OPERATOR_KEY` for read-only admin operations (provider list, routing preview, audit view). `STAGING_MANAGEMENT_ADMIN_KEY` is only needed when `STAGING_VERIFY_ADMIN_WRITE=true`.


## Management ops RBAC

Operator keys can read `/v1/admin/ops/abuse/config`, `/v1/admin/ops/backups/config`, `/v1/admin/ops/observability/status`, and `/v1/admin/ops/backups/drill/jobs/{job_id}` status. Admin keys are required for write changes, including `/v1/admin/ops/backups/drill/run` and `DELETE /v1/admin/ops/backups/drill/jobs/{job_id}`. Backup drill triggers should send an `Idempotency-Key` header so repeated submissions reuse the same queued job.



### Kubernetes base artifacts

A production-oriented Kubernetes base now lives under `deploy/kubernetes/`. Sensitive runtime values are now mounted as files and consumed through `*_FILE` environment variables; see `docs/SECRET_MANAGEMENT.md` and `deploy/kubernetes/external-secret.example.yaml` for the intended production pattern.
Use it as a starting point for clusters that already provide PostgreSQL, Redis, ingress, and monitoring.
Apply the runtime base separately from the migration job so schema changes remain a deliberate operational step.

- runtime base: `kubectl apply -k deploy/kubernetes`
- migrations: `kubectl apply -f deploy/kubernetes/migrate-job.yaml -n architecture-control-plane`
- detailed instructions: `deploy/kubernetes/README.md`



## Live workbench

- `GET /v1/cycles/board` and `GET /v1/cycles/board/events` expose a board-style grouped view and live board stream for recent cycles.
- `GET /v1/cycles/{cycle_id}/timeline` merges audit, job, approval, iteration, and receipt activity into a single timeline.
- `GET /v1/workspace/overview` summarizes project-level workload, recent comments, and workspace totals for the authenticated user.
- `GET /v1/workspace/discussions` and `POST /v1/workspace/discussions` add project-scoped workspace discussion notes and handoff context.
- `GET /v1/agents/profiles` renders persona-style agent cards derived from live cycle/job state.
- `GET /v1/runtime/panel` exposes queue/outbox/runtime signals for the current workspace scope.
- `GET /v1/runtime/registrations` and `POST /v1/runtime/registrations` provide a lightweight runtime/daemon heartbeat panel without adding a separate registry table.
- `GET /v1/cycles/{cycle_id}/comments` and `POST /v1/cycles/{cycle_id}/comments` provide lightweight collaboration comments without adding a separate discussion store.
- `GET /v1/cycles/{cycle_id}/card` returns an issue-style detail payload with summary, previews, active jobs, approvals, and suggested agents.
- `GET /workbench` serves a browser-based live workbench with board, workspace, discussions, agent, runtime, card detail, comments, activity timeline, and real-time workflow panels.


## Remote workspace phase 1

- Goal: capture remote run intent and parked workspace state without paying for always-on compute.
- Default executor: `planning` (records snapshot + run intent only).
- Future executor path: configure `REMOTE_WORKSPACE_GITHUB_REPOSITORY` and `REMOTE_WORKSPACE_GITHUB_WORKFLOW` for a GitHub Actions-backed remote runner in Phase 2.
- Workbench now includes a remote workspace panel and an audit explorer panel.


# Phase 4 optional persistent workspace
REMOTE_WORKSPACE_PERSISTENT_ENABLED=false
REMOTE_WORKSPACE_PERSISTENT_PROVIDER=manual
REMOTE_WORKSPACE_PERSISTENT_MAX_ACTIVE_SESSIONS=1
REMOTE_WORKSPACE_PERSISTENT_IDLE_TIMEOUT_MINUTES=120
REMOTE_WORKSPACE_PERSISTENT_TTL_HOURS=8
