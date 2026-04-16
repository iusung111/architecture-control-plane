from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from time import perf_counter

from sqlalchemy.orm import Session

from app.core.logging import get_logger, log_event
from app.core.telemetry import record_job_execution, timed_span
from app.db.models import Job
from app.repositories.jobs import JobRepository

logger = get_logger(__name__)


class JobExecutionError(Exception):
    def __init__(self, message: str, *, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


class JobCancelledError(Exception):
    pass


JobHandler = Callable[[Job], None]


@dataclass(slots=True)
class JobRunnerResult:
    claimed_job_ids: list[str]
    processed: int
    succeeded: int
    failed: int
    dead_lettered: int


class JobRunner:
    def __init__(self, db: Session, handlers: Mapping[str, JobHandler] | None = None):
        self._db = db
        self._jobs = JobRepository(db)
        self._handlers = dict(handlers or {})

    def run_once(self, worker_id: str, limit: int = 10) -> JobRunnerResult:
        claimed = self._jobs.claim_pending(worker_id=worker_id, limit=limit)
        succeeded = 0
        failed = 0
        dead_lettered = 0

        for job in claimed:
            traceparent_header = job.payload.get("traceparent") if isinstance(job.payload, dict) else None
            with timed_span(
                traceparent_header,
                name=f"job {job.job_type}",
                kind="consumer",
                attributes={
                    "messaging.system": "acp-jobs",
                    "messaging.operation": "process",
                    "job.id": job.job_id,
                    "job.type": job.job_type,
                    "worker.id": worker_id,
                },
            ):
                started_at = perf_counter()
                log_event(logger, logging.INFO, "job.claimed", job_id=job.job_id, job_type=job.job_type, worker_id=worker_id)
                self._jobs.mark_running(job, worker_id=worker_id)
                handler = self._handlers.get(job.job_type)
                if handler is None:
                    self._jobs.mark_failed(job, error=f"No handler registered for job_type={job.job_type}", retryable=False)
                else:
                    try:
                        handler(job)
                        if job.job_state != "cancelled":
                            self._jobs.mark_succeeded(job)
                    except JobCancelledError as exc:
                        self._jobs.mark_cancelled(job, error=str(exc))
                    except JobExecutionError as exc:
                        self._jobs.mark_failed(job, error=str(exc), retryable=exc.retryable)
                    except Exception as exc:  # noqa: BLE001
                        self._jobs.mark_failed(job, error=str(exc), retryable=True)

                duration_seconds = perf_counter() - started_at
                if job.job_state == "succeeded":
                    outcome = "succeeded"
                    succeeded += 1
                    log_event(logger, logging.INFO, "job.succeeded", job_id=job.job_id, job_type=job.job_type)
                elif job.job_state == "dead_lettered":
                    outcome = "dead_lettered"
                    dead_lettered += 1
                    log_event(logger, logging.ERROR, "job.dead_lettered", job_id=job.job_id, job_type=job.job_type, last_error=job.last_error)
                elif job.job_state == "cancelled":
                    outcome = "cancelled"
                    log_event(logger, logging.INFO, "job.cancelled", job_id=job.job_id, job_type=job.job_type, last_error=job.last_error)
                else:
                    outcome = "failed"
                    failed += 1
                    log_event(logger, logging.WARNING, "job.failed", job_id=job.job_id, job_type=job.job_type, last_error=job.last_error)
                record_job_execution(job.job_type, outcome, duration_seconds)

        self._db.commit()
        return JobRunnerResult(
            claimed_job_ids=[job.job_id for job in claimed],
            processed=len(claimed),
            succeeded=succeeded,
            failed=failed,
            dead_lettered=dead_lettered,
        )
