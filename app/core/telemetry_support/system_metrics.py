from __future__ import annotations

import json
import threading
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import Job
from app.db.session import get_session_factory
from app.domain.enums import JobState, JobType

from . import common
from .metrics import JOB_QUEUE_DEPTH, JOB_QUEUE_READY_AGE_SECONDS, JOB_RUNNING_AGE_SECONDS, SLO_LATENCY_THRESHOLD_SECONDS, SLO_TARGET_RATIO


def start_metrics_http_server(port: int, state_provider: Callable[[], Mapping[str, Any]] | None = None) -> bool:
    settings = get_settings()
    if not settings.metrics_enabled or not settings.worker_metrics_enabled or port <= 0:
        return False
    with common._metrics_server_lock:
        if port in common._metrics_servers_started:
            return False

        class _MetricsHandler(BaseHTTPRequestHandler):
            def _write(self, status_code: int, payload: bytes, content_type: str) -> None:
                self.send_response(status_code)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self) -> None:  # noqa: N802
                if self.path in {"/metrics", "/"}:
                    payload, content_type = render_metrics()
                    self._write(200, payload, content_type)
                    return
                state = dict(state_provider() if state_provider is not None else {"status": "ok", "ready": True, "shutting_down": False})
                if self.path == "/healthz":
                    self._write(200, json.dumps({"status": state.get("status", "ok")}).encode("utf-8"), "application/json")
                    return
                if self.path == "/readyz":
                    ready = bool(state.get("ready", True))
                    self._write(200 if ready else 503, json.dumps({"status": "ready" if ready else "not_ready"}).encode("utf-8"), "application/json")
                    return
                if self.path == "/state":
                    self._write(200, json.dumps(state, default=str).encode("utf-8"), "application/json")
                    return
                self._write(404, b'{"detail":"not found"}', "application/json")

            def log_message(self, *_args) -> None:
                return

        server = ThreadingHTTPServer(("0.0.0.0", port), _MetricsHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        common._metrics_servers_started.add(port)
        return True


def _normalize_db_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _seconds_since(now: datetime, value: datetime | None) -> float:
    resolved = _normalize_db_datetime(value)
    if resolved is None:
        return 0.0
    return max(0.0, (now - resolved).total_seconds())


def _update_job_queue_metrics() -> None:
    for job_type in JobType:
        JOB_QUEUE_READY_AGE_SECONDS.labels(job_type=job_type.value).set(0)
        JOB_RUNNING_AGE_SECONDS.labels(job_type=job_type.value).set(0)
        for job_state in JobState:
            JOB_QUEUE_DEPTH.labels(job_type=job_type.value, job_state=job_state.value).set(0)
    try:
        session_factory = get_session_factory()
    except Exception:
        return
    try:
        with session_factory() as db:
            rows = db.execute(select(Job.job_type, Job.job_state, Job.run_after, Job.locked_at)).all()
    except Exception:
        return
    now = datetime.now(timezone.utc)
    ready_age_by_type: dict[str, float] = {}
    running_age_by_type: dict[str, float] = {}
    depth_by_type_state: dict[tuple[str, str], int] = {}
    for job_type, job_state, run_after, locked_at in rows:
        depth_key = (job_type, job_state)
        depth_by_type_state[depth_key] = depth_by_type_state.get(depth_key, 0) + 1
        if job_state in {JobState.PENDING.value, JobState.FAILED.value}:
            ready_age = _seconds_since(now, run_after)
            if ready_age > 0:
                ready_age_by_type[job_type] = max(ready_age_by_type.get(job_type, 0.0), ready_age)
        elif job_state in {JobState.CLAIMED.value, JobState.RUNNING.value}:
            running_age = _seconds_since(now, locked_at)
            if running_age > 0:
                running_age_by_type[job_type] = max(running_age_by_type.get(job_type, 0.0), running_age)
    for job_type, age_seconds in ready_age_by_type.items():
        JOB_QUEUE_READY_AGE_SECONDS.labels(job_type=job_type).set(age_seconds)
    for job_type, age_seconds in running_age_by_type.items():
        JOB_RUNNING_AGE_SECONDS.labels(job_type=job_type).set(age_seconds)
    for (job_type, job_state), depth in depth_by_type_state.items():
        JOB_QUEUE_DEPTH.labels(job_type=job_type, job_state=job_state).set(depth)


def _update_slo_config_metrics() -> None:
    settings = get_settings()
    SLO_TARGET_RATIO.labels(slo="api_availability").set(settings.api_availability_slo_target)
    SLO_TARGET_RATIO.labels(slo="api_latency").set(settings.api_latency_slo_target)
    SLO_LATENCY_THRESHOLD_SECONDS.set(settings.api_latency_slo_seconds)


def render_metrics() -> tuple[bytes, str]:
    _update_slo_config_metrics()
    _update_job_queue_metrics()
    return generate_latest(), CONTENT_TYPE_LATEST
