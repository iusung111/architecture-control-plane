.PHONY: install lint test test-postgres run migrate run-jobs-once run-outbox-once docker-up docker-down docker-logs smoke-compose observability-urls render-alert-rules render-alertmanager-config render-s3-lifecycle-policy docker-migrate backup-db restore-db drill-backup-restore drill-backup-restore-compose prune-backups rotate-backup-passphrase release-readiness

install:
	pip install -e .[dev]

lint:
	ruff check .

test:
	pytest

test-postgres:
	RUN_POSTGRES_INTEGRATION=1 TEST_DATABASE_URL=$${TEST_DATABASE_URL:-postgresql+psycopg://postgres:postgres@localhost:5432/control_plane_test} pytest -q tests/test_postgres_integration.py

run:
	uvicorn app.main:app --reload

migrate:
	alembic upgrade head

run-jobs-once:
	python -m app.workers.cli jobs --limit 20

run-outbox-once:
	python -m app.workers.cli outbox --limit 50

render-alert-rules:
	python scripts/render_alert_rules.py

render-alertmanager-config:
	python scripts/render_alertmanager_config.py

render-s3-lifecycle-policy:
	python scripts/render_s3_lifecycle_policy.py

docker-up:
	docker compose up --build -d

docker-migrate:
	docker compose run --rm migrate

backup-db:
	python scripts/postgres_backup_restore.py backup --output-dir $${BACKUP_OUTPUT_DIR:-backups} $${BACKUP_LABEL:+--label $$BACKUP_LABEL} $${BACKUP_COMPOSE_SERVICE:+--docker-compose-service $$BACKUP_COMPOSE_SERVICE} $${BACKUP_ENCRYPTION_PASSPHRASE:+--encryption-passphrase $$BACKUP_ENCRYPTION_PASSPHRASE} $${BACKUP_RETENTION_KEEP_LAST:+--prune-keep-last $$BACKUP_RETENTION_KEEP_LAST} $${BACKUP_RETENTION_MAX_AGE_DAYS:+--prune-max-age-days $$BACKUP_RETENTION_MAX_AGE_DAYS}

restore-db:
	python scripts/postgres_backup_restore.py restore --backup-file $${BACKUP_FILE:?Set BACKUP_FILE=/path/to/backup.dump} $${TARGET_DATABASE_URL:+--database-url $$TARGET_DATABASE_URL} $${BACKUP_COMPOSE_SERVICE:+--docker-compose-service $$BACKUP_COMPOSE_SERVICE} $${RECREATE_TARGET_DATABASE:+--recreate-target-database} $${BACKUP_ENCRYPTION_PASSPHRASE:+--encryption-passphrase $$BACKUP_ENCRYPTION_PASSPHRASE}

drill-backup-restore:
	python scripts/postgres_backup_restore.py drill --output-dir $${BACKUP_OUTPUT_DIR:-backups/drills} $${BACKUP_LABEL:+--label $$BACKUP_LABEL} $${DRILL_DATABASE_URL:+--target-database-url $$DRILL_DATABASE_URL} $${BACKUP_COMPOSE_SERVICE:+--docker-compose-service $$BACKUP_COMPOSE_SERVICE} $${BACKUP_ENCRYPTION_PASSPHRASE:+--encryption-passphrase $$BACKUP_ENCRYPTION_PASSPHRASE} $${BACKUP_RETENTION_KEEP_LAST:+--prune-keep-last $$BACKUP_RETENTION_KEEP_LAST} $${BACKUP_RETENTION_MAX_AGE_DAYS:+--prune-max-age-days $$BACKUP_RETENTION_MAX_AGE_DAYS}

drill-backup-restore-compose:
	DATABASE_URL=$${DATABASE_URL:-postgresql+psycopg://postgres:postgres@localhost:5432/control_plane} DRILL_DATABASE_URL=$${DRILL_DATABASE_URL:-postgresql+psycopg://postgres:postgres@localhost:5432/control_plane_restore_drill} BACKUP_COMPOSE_SERVICE=$${BACKUP_COMPOSE_SERVICE:-postgres} python scripts/postgres_backup_restore.py drill --output-dir $${BACKUP_OUTPUT_DIR:-backups/drills} $${BACKUP_LABEL:+--label $$BACKUP_LABEL} $${BACKUP_ENCRYPTION_PASSPHRASE:+--encryption-passphrase $$BACKUP_ENCRYPTION_PASSPHRASE} $${BACKUP_RETENTION_KEEP_LAST:+--prune-keep-last $$BACKUP_RETENTION_KEEP_LAST} $${BACKUP_RETENTION_MAX_AGE_DAYS:+--prune-max-age-days $$BACKUP_RETENTION_MAX_AGE_DAYS}

docker-down:
	docker compose down -v

docker-logs:
	docker compose logs -f api worker-jobs worker-outbox postgres otel-collector prometheus alertmanager grafana tempo webhook-sink mailpit migrate

smoke-compose:
	bash scripts/docker_compose_smoke.sh

observability-urls:
	@echo "Grafana:      http://localhost:3000 (admin/admin)"
	@echo "Prometheus:   http://localhost:9090"
	@echo "Alertmanager: http://localhost:9093"
	@echo "Mailpit:      http://localhost:8025"
	@echo "Tempo API:    http://localhost:3200"
	@echo "API:          http://localhost:8000"
	@echo "Runbooks:     http://localhost:8000/runbooks"
	@echo "Worker job metrics:    http://localhost:9101/metrics"
	@echo "Worker outbox metrics: http://localhost:9102/metrics"

prune-backups:
	python scripts/postgres_backup_restore.py prune --output-dir $${BACKUP_OUTPUT_DIR:-backups} $${BACKUP_RETENTION_KEEP_LAST:+--keep-last $$BACKUP_RETENTION_KEEP_LAST} $${BACKUP_RETENTION_MAX_AGE_DAYS:+--max-age-days $$BACKUP_RETENTION_MAX_AGE_DAYS}

rotate-backup-passphrase:
	python scripts/postgres_backup_restore.py rotate-passphrase --backup-file $${BACKUP_FILE:?Set BACKUP_FILE=/path/to/backup.dump.enc} $${BACKUP_ENCRYPTION_PASSPHRASE:+--current-passphrase $$BACKUP_ENCRYPTION_PASSPHRASE} $${BACKUP_NEW_ENCRYPTION_PASSPHRASE:+--new-passphrase $$BACKUP_NEW_ENCRYPTION_PASSPHRASE} $${BACKUP_OUTPUT_DIR:+--output-dir $$BACKUP_OUTPUT_DIR} $${BACKUP_REUPLOAD_OBJECT_STORE:+--reupload-object-store}


staging-live-smoke:
	python scripts/staging_live_smoke.py

release-readiness:
	python scripts/release_readiness.py $${ACP_RELEASE_ARGS}
