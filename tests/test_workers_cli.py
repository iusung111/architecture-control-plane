from __future__ import annotations

import argparse
from dataclasses import dataclass

import pytest

from app.workers import cli


class _FakeSession:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


@dataclass(slots=True)
class _RunnerResult:
    processed: int = 1
    succeeded: int = 1
    failed: int = 0
    dead_lettered: int = 0


@dataclass(slots=True)
class _OutboxResult:
    processed: int = 1
    delivered_ids: list[str] | None = None
    failed: int = 0
    dead_lettered: int = 0



def test_worker_runtime_state_tracks_iterations_and_errors():
    state = cli.WorkerRuntimeState(target="jobs", worker_id="worker-1", loop_enabled=False)

    state.mark_iteration_started()
    assert state.active is True
    assert state.last_iteration_started_at is not None

    state.mark_iteration_finished({"processed": 1})
    snapshot = state.snapshot()
    assert snapshot["status"] == "idle"
    assert snapshot["last_result"] == {"processed": 1}

    state.mark_error(RuntimeError("boom"))
    assert state.last_error == "boom"
    assert state.snapshot()["status"] == "idle"

    state.begin_shutdown()
    draining = state.snapshot()
    assert draining["status"] == "draining"
    assert draining["ready"] is False



def test_run_jobs_and_outbox_close_sessions(monkeypatch):
    job_session = _FakeSession()
    outbox_session = _FakeSession()
    sessions = iter([job_session, outbox_session])

    def fake_session_factory():
        return lambda: next(sessions)

    class FakeJobRunner:
        def __init__(self, session, handlers):
            assert session is job_session
            assert handlers == {"jobs": "handler"}

        def run_once(self, *, worker_id, limit):
            assert worker_id == "worker-x"
            assert limit == 7
            return _RunnerResult(processed=2, succeeded=2)

    class FakeOutboxConsumer:
        def __init__(self, session, handlers):
            assert session is outbox_session
            assert handlers == {"outbox": "handler"}

        def deliver_once(self, *, limit):
            assert limit == 3
            return _OutboxResult(processed=1, delivered_ids=["evt-1"])

    monkeypatch.setattr(cli, "get_session_factory", fake_session_factory)
    monkeypatch.setattr(cli, "build_default_job_handlers", lambda session: {"jobs": "handler"})
    monkeypatch.setattr(cli, "build_default_outbox_handlers", lambda: {"outbox": "handler"})
    monkeypatch.setattr(cli, "JobRunner", FakeJobRunner)
    monkeypatch.setattr(cli, "OutboxConsumer", FakeOutboxConsumer)

    assert cli._run_jobs(limit=7, worker_id="worker-x") == {
        "processed": 2,
        "succeeded": 2,
        "failed": 0,
        "dead_lettered": 0,
    }
    assert job_session.closed is True

    assert cli._run_outbox(limit=3) == {
        "processed": 1,
        "delivered_ids": ["evt-1"],
        "failed": 0,
        "dead_lettered": 0,
    }
    assert outbox_session.closed is True



def test_worker_main_runs_single_job_iteration_and_shuts_down(monkeypatch, capsys):
    calls: list[tuple[str, object]] = []

    monkeypatch.setattr(cli, "configure_logging", lambda: calls.append(("logging", None)))
    monkeypatch.setattr(cli, "get_settings", lambda: object())
    monkeypatch.setattr(cli, "ensure_runtime_settings_valid", lambda settings: calls.append(("validated", settings)))
    monkeypatch.setattr(cli, "initialize_tracing", lambda: calls.append(("tracing", None)))
    monkeypatch.setattr(cli, "shutdown_tracing", lambda: calls.append(("shutdown", None)))
    monkeypatch.setattr(cli, "start_metrics_http_server", lambda port, snapshot: calls.append(("metrics", port, snapshot()["status"])))
    monkeypatch.setattr(cli, "_run_jobs", lambda limit, worker_id: {"processed": limit, "worker_id": worker_id})
    monkeypatch.setattr(cli, "signal", type("S", (), {"SIGTERM": 15, "SIGINT": 2, "signal": staticmethod(lambda sig, handler: calls.append(("signal", sig, callable(handler))))}))
    monkeypatch.setattr(
        argparse.ArgumentParser,
        "parse_args",
        lambda self: argparse.Namespace(target="jobs", limit=4, worker_id="worker-cli", loop=False, sleep_seconds=0.5, metrics_port=9000),
    )

    cli.main()
    stdout = capsys.readouterr().out.strip()
    assert '"processed": 4' in stdout
    assert '"worker_id": "worker-cli"' in stdout
    assert ("metrics", 9000, "idle") in calls
    assert ("shutdown", None) in calls



def test_worker_main_marks_error_then_reraises(monkeypatch):
    monkeypatch.setattr(cli, "configure_logging", lambda: None)
    monkeypatch.setattr(cli, "get_settings", lambda: object())
    monkeypatch.setattr(cli, "ensure_runtime_settings_valid", lambda settings: None)
    monkeypatch.setattr(cli, "initialize_tracing", lambda: None)
    shutdown_called: list[bool] = []
    monkeypatch.setattr(cli, "shutdown_tracing", lambda: shutdown_called.append(True))
    monkeypatch.setattr(cli, "signal", type("S", (), {"SIGTERM": 15, "SIGINT": 2, "signal": staticmethod(lambda sig, handler: None)}))
    monkeypatch.setattr(
        argparse.ArgumentParser,
        "parse_args",
        lambda self: argparse.Namespace(target="outbox", limit=2, worker_id="worker-cli", loop=False, sleep_seconds=0.5, metrics_port=0),
    )

    def boom(limit):
        assert limit == 2
        raise RuntimeError("outbox exploded")

    monkeypatch.setattr(cli, "_run_outbox", boom)

    with pytest.raises(RuntimeError, match="outbox exploded"):
        cli.main()

    assert shutdown_called == [True]
