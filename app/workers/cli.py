from __future__ import annotations

import argparse
import json
import signal
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from app.core.config import ensure_runtime_settings_valid, get_settings
from app.core.logging import configure_logging
from app.core.telemetry import initialize_tracing, shutdown_tracing, start_metrics_http_server
from app.db.session import get_session_factory
from app.workers.default_handlers import build_default_job_handlers, build_default_outbox_handlers
from app.workers.job_runner import JobRunner
from app.workers.outbox_consumer import OutboxConsumer


@dataclass(slots=True)
class WorkerRuntimeState:
    target: str
    worker_id: str
    loop_enabled: bool
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_iteration_started_at: str | None = None
    last_iteration_finished_at: str | None = None
    last_result: dict[str, object] | None = None
    last_error: str | None = None
    active: bool = False
    ready: bool = True
    shutting_down: bool = False

    def mark_iteration_started(self) -> None:
        self.active = True
        self.last_error = None
        self.last_iteration_started_at = datetime.now(timezone.utc).isoformat()

    def mark_iteration_finished(self, payload: dict[str, object]) -> None:
        self.active = False
        self.last_result = payload
        self.last_iteration_finished_at = datetime.now(timezone.utc).isoformat()

    def mark_error(self, error: Exception) -> None:
        self.active = False
        self.last_error = str(error)
        self.last_iteration_finished_at = datetime.now(timezone.utc).isoformat()

    def begin_shutdown(self) -> None:
        self.shutting_down = True
        self.ready = False

    def snapshot(self) -> dict[str, object]:
        state = asdict(self)
        state["status"] = "draining" if self.shutting_down else ("busy" if self.active else "idle")
        return state



def _run_jobs(limit: int, worker_id: str) -> dict[str, object]:
    session = get_session_factory()()
    try:
        result = JobRunner(session, handlers=build_default_job_handlers(session)).run_once(
            worker_id=worker_id,
            limit=limit,
        )
        return asdict(result)
    finally:
        session.close()



def _run_outbox(limit: int) -> dict[str, object]:
    session = get_session_factory()()
    try:
        result = OutboxConsumer(session, handlers=build_default_outbox_handlers()).deliver_once(limit=limit)
        return asdict(result)
    finally:
        session.close()



def main() -> None:
    configure_logging()
    settings = get_settings()
    ensure_runtime_settings_valid(settings)
    initialize_tracing()
    parser = argparse.ArgumentParser(description="Run control-plane workers")
    parser.add_argument("target", choices=["jobs", "outbox"])
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--worker-id", default="worker-cli")
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--sleep-seconds", type=float, default=2.0)
    parser.add_argument("--metrics-port", type=int, default=0)
    args = parser.parse_args()

    shutdown_event = threading.Event()
    state = WorkerRuntimeState(target=args.target, worker_id=args.worker_id, loop_enabled=args.loop)

    def _handle_shutdown(_signum, _frame) -> None:  # type: ignore[no-untyped-def]
        state.begin_shutdown()
        shutdown_event.set()

    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)

    if args.metrics_port > 0:
        start_metrics_http_server(args.metrics_port, state.snapshot)

    try:
        while not shutdown_event.is_set():
            try:
                state.mark_iteration_started()
                if args.target == "jobs":
                    payload = _run_jobs(limit=args.limit, worker_id=args.worker_id)
                else:
                    payload = _run_outbox(limit=args.limit)
                state.mark_iteration_finished(payload)
                print(json.dumps(payload, ensure_ascii=False, default=str), flush=True)
            except Exception as exc:  # noqa: BLE001
                state.mark_error(exc)
                raise

            if not args.loop:
                return
            shutdown_event.wait(timeout=max(args.sleep_seconds, 0.1))
    finally:
        state.begin_shutdown()
        shutdown_tracing()


if __name__ == "__main__":
    main()
