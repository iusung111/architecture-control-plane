import json
from datetime import datetime, timezone
from pathlib import Path

import yaml
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.telemetry import initialize_tracing, render_metrics, start_metrics_http_server
from app.db.base import Base
from app.db.models import Job
from app.domain.enums import JobState, JobType



def test_initialize_tracing_returns_false_without_otlp_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("OTEL_ENABLED", "true")
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    get_settings.cache_clear()

    assert initialize_tracing() is False

    monkeypatch.delenv("OTEL_ENABLED", raising=False)
    get_settings.cache_clear()



def test_start_metrics_http_server_skips_when_worker_metrics_disabled(monkeypatch) -> None:
    monkeypatch.setenv("METRICS_ENABLED", "true")
    monkeypatch.setenv("WORKER_METRICS_ENABLED", "false")
    get_settings.cache_clear()

    assert start_metrics_http_server(9123) is False

    monkeypatch.delenv("METRICS_ENABLED", raising=False)
    monkeypatch.delenv("WORKER_METRICS_ENABLED", raising=False)
    get_settings.cache_clear()



def test_render_metrics_exposes_job_queue_age_and_depth(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "metrics_jobs.db"
    database_url = f"sqlite+pysqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()

    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    with SessionLocal() as session:
        pending_job = Job(
            job_id="job-pending-1",
            cycle_id=None,
            job_type=JobType.BACKUP_RESTORE_DRILL,
            job_state=JobState.PENDING,
            payload={},
            dedup_key="dedup-pending-1",
        )
        running_job = Job(
            job_id="job-running-1",
            cycle_id=None,
            job_type=JobType.BACKUP_RESTORE_DRILL,
            job_state=JobState.RUNNING,
            payload={},
            dedup_key="dedup-running-1",
        )
        pending_job.run_after = datetime(2000, 1, 1, tzinfo=timezone.utc)
        running_job.locked_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
        session.add_all([pending_job, running_job])
        session.commit()

    payload, _ = render_metrics()
    metrics_text = payload.decode("utf-8")
    assert 'acp_job_oldest_ready_age_seconds{job_type="backup_restore_drill"}' in metrics_text
    assert 'acp_job_oldest_running_age_seconds{job_type="backup_restore_drill"}' in metrics_text
    assert "acp_job_queue_depth" in metrics_text
    assert 'job_type="backup_restore_drill"' in metrics_text
    assert 'job_state="pending"' in metrics_text
    assert 'job_state="running"' in metrics_text

    engine.dispose()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    get_settings.cache_clear()



def test_observability_stack_assets_are_present() -> None:
    required_files = [
        "deploy/otel/otel-collector-config.yaml",
        "deploy/prometheus/prometheus.yml",
        "deploy/prometheus/alerts/acp-alerts.yml",
        "deploy/prometheus/alerts/acp-alerts.src.yml",
        "deploy/prometheus/alerts/runbook-map.yml",
        "deploy/alertmanager/alertmanager.src.yml",
        "deploy/alertmanager/alertmanager.yml",
        "deploy/grafana/provisioning/datasources/datasources.yml",
        "deploy/grafana/provisioning/dashboards/dashboards.yml",
        "deploy/grafana/dashboards/acp-observability.json",
        "deploy/tempo.yaml",
        "docs/runbooks/INDEX.md",
        "scripts/render_alert_rules.py",
        "scripts/render_alertmanager_config.py",
    ]

    for relative_path in required_files:
        assert Path(relative_path).exists(), relative_path



def test_docker_compose_includes_observability_services() -> None:
    compose_text = Path("docker-compose.yml").read_text()
    for service_name in ("otel-collector", "tempo", "prometheus", "grafana", "alertmanager", "mailpit"):
        assert service_name in compose_text



def test_prometheus_config_references_alert_rules_and_alertmanager() -> None:
    prometheus_text = Path("deploy/prometheus/prometheus.yml").read_text()
    assert "rule_files:" in prometheus_text
    assert "/etc/prometheus/alerts/acp-alerts.yml" in prometheus_text
    assert "alertmanagers:" in prometheus_text
    assert '"alertmanager:9093"' in prometheus_text



def test_generated_alert_rules_include_runbook_urls() -> None:
    alert_doc = yaml.safe_load(Path("deploy/prometheus/alerts/acp-alerts.yml").read_text())
    alert_rules = [
        rule
        for group in alert_doc["groups"]
        for rule in group["rules"]
        if "alert" in rule
    ]
    assert alert_rules
    for rule in alert_rules:
        annotations = rule.get("annotations", {})
        assert annotations.get("runbook_url", "").startswith("http://localhost:8000/runbooks/")
        assert annotations.get("runbook_slug")



def test_dashboard_contains_slo_panels() -> None:
    dashboard = json.loads(Path("deploy/grafana/dashboards/acp-observability.json").read_text())
    panel_titles = {panel["title"] for panel in dashboard["panels"]}
    assert "API availability burn rate" in panel_titles
    assert "API latency burn rate" in panel_titles
    assert "Rate limit backend health" in panel_titles
    assert "Rate limit fail-open decisions / sec" in panel_titles
    assert "Tenant rate-limit rejections / sec" in panel_titles
    assert "Tenant plan rate-limit rejections / sec" in panel_titles



def test_generated_alertmanager_config_includes_email_receiver() -> None:
    config = yaml.safe_load(Path("deploy/alertmanager/alertmanager.yml").read_text())
    receivers = {receiver["name"]: receiver for receiver in config["receivers"]}
    email_receiver = receivers["email-default"]
    email_cfg = email_receiver["email_configs"][0]
    assert email_cfg["to"] == "team@example.com"
    assert config["global"]["smtp_smarthost"] == "mailpit:1025"
    route_receivers = [route["receiver"] for route in config["route"].get("routes", [])]
    assert "email-default" in route_receivers


def test_smoke_script_checks_mailpit_email_routing() -> None:
    smoke_text = Path("scripts/docker_compose_smoke.sh").read_text()
    assert "http://localhost:8025/api/v1/messages" in smoke_text
    assert "ACPApiAvailabilityErrorBudgetFastBurn" in smoke_text
    assert "team@example.com" in smoke_text


def test_generated_alert_rules_include_rate_limit_backend_alerts() -> None:
    alert_doc = yaml.safe_load(Path("deploy/prometheus/alerts/acp-alerts.yml").read_text())
    alert_names = {rule["alert"] for group in alert_doc["groups"] for rule in group["rules"] if "alert" in rule}
    assert "ACPRateLimitBackendUnhealthy" in alert_names
    assert "ACPRateLimitFailOpenBypass" in alert_names
    assert "ACPJobQueueBacklog" in alert_names
    assert "ACPBackupDrillRunningTooLong" in alert_names
