from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import Job
from app.domain.enums import JobState, JobType


class JobRepository:
    def __init__(self, db: Session):
        self._db = db

    def enqueue(
        self,
        cycle_id: str | None,
        job_type: JobType,
        payload: dict,
        dedup_key: str,
        *,
        max_attempts: int = 5,
        priority: int = 100,
    ) -> Job:
        job = Job(
            job_id=str(uuid4()),
            cycle_id=cycle_id,
            job_type=job_type,
            job_state=JobState.PENDING,
            payload=payload,
            dedup_key=dedup_key,
            run_after=datetime.now(timezone.utc),
            max_attempts=max_attempts,
            priority=priority,
        )
        self._db.add(job)
        return job

    def get_by_dedup_key(self, dedup_key: str) -> Job | None:
        stmt = select(Job).where(Job.dedup_key == dedup_key)
        return self._db.execute(stmt).scalar_one_or_none()

    def claim_pending(self, worker_id: str, limit: int = 10) -> list[Job]:
        if self._supports_skip_locked():
            return self._claim_pending_with_skip_locked(worker_id=worker_id, limit=limit)
        return self._claim_pending_with_conditional_update(worker_id=worker_id, limit=limit)

    def _claim_pending_with_skip_locked(self, worker_id: str, limit: int) -> list[Job]:
        now = datetime.now(timezone.utc)
        eligible_states = (JobState.PENDING, JobState.FAILED)
        claimed = list(
            self._db.execute(
                select(Job)
                .where(Job.run_after <= now, Job.job_state.in_(eligible_states))
                .order_by(Job.priority.asc(), Job.created_at.asc())
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
            .scalars()
            .all()
        )

        for job in claimed:
            job.job_state = JobState.CLAIMED
            job.locked_at = now
            job.worker_id = worker_id
            job.updated_at = now
        if claimed:
            self._db.flush()
        return claimed

    def _claim_pending_with_conditional_update(self, worker_id: str, limit: int) -> list[Job]:
        now = datetime.now(timezone.utc)
        eligible_states = (JobState.PENDING, JobState.FAILED)
        candidate_ids = list(
            self._db.execute(
                select(Job.job_id)
                .where(Job.run_after <= now, Job.job_state.in_(eligible_states))
                .order_by(Job.priority.asc(), Job.created_at.asc())
                .limit(limit)
            )
            .scalars()
            .all()
        )

        claimed_ids: list[str] = []
        for job_id in candidate_ids:
            result = self._db.execute(
                update(Job)
                .where(Job.job_id == job_id, Job.job_state.in_(eligible_states))
                .values(
                    job_state=JobState.CLAIMED,
                    locked_at=now,
                    worker_id=worker_id,
                    updated_at=now,
                )
            )
            if result.rowcount == 1:
                claimed_ids.append(job_id)

        if not claimed_ids:
            return []

        return list(
            self._db.execute(
                select(Job)
                .where(Job.job_id.in_(claimed_ids))
                .order_by(Job.priority.asc(), Job.created_at.asc())
            )
            .scalars()
            .all()
        )

    def mark_running(self, job: Job, *, worker_id: str | None = None) -> None:
        now = datetime.now(timezone.utc)
        job.job_state = JobState.RUNNING
        job.locked_at = now
        if worker_id is not None:
            job.worker_id = worker_id
        job.updated_at = now

    def mark_succeeded(self, job: Job) -> None:
        job.job_state = JobState.SUCCEEDED
        job.locked_at = None
        job.worker_id = None
        job.last_error = None
        job.updated_at = datetime.now(timezone.utc)

    def mark_failed(self, job: Job, error: str, retryable: bool = True) -> None:
        now = datetime.now(timezone.utc)
        job.attempt_count += 1
        job.last_error = error
        job.updated_at = now
        job.locked_at = None
        job.worker_id = None
        if retryable and job.attempt_count < job.max_attempts:
            job.job_state = JobState.FAILED
            job.run_after = now + self._backoff_for_attempt(job.attempt_count)
        else:
            job.job_state = JobState.DEAD_LETTERED

    def mark_cancelled(self, job: Job, *, error: str = "backup drill cancelled by operator") -> None:
        now = datetime.now(timezone.utc)
        job.job_state = JobState.CANCELLED
        job.locked_at = None
        job.worker_id = None
        job.last_error = error
        job.updated_at = now

    def _supports_skip_locked(self) -> bool:
        bind = self._db.get_bind()
        return bind is not None and bind.dialect.name == 'postgresql'

    @staticmethod
    def _backoff_for_attempt(attempt_count: int) -> timedelta:
        if attempt_count <= 1:
            return timedelta(seconds=30)
        if attempt_count == 2:
            return timedelta(minutes=2)
        return timedelta(minutes=10)
