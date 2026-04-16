from datetime import timedelta, timezone

from app.domain.enums import JobState, JobType, OutboxDeliveryState
from app.repositories.jobs import JobRepository
from app.repositories.outbox import OutboxRepository
from app.workers.job_runner import JobExecutionError, JobRunner
from app.workers.outbox_consumer import OutboxConsumer, OutboxDeliveryError


def _as_utc(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def test_job_claim_pending_is_single_claim(db_session):
    repo = JobRepository(db_session)
    job = repo.enqueue(cycle_id='cycle_1', job_type=JobType.RETRY_CYCLE, payload={}, dedup_key='dedup-1')
    db_session.commit()

    claimed_first = repo.claim_pending(worker_id='worker-a', limit=10)
    db_session.flush()
    claimed_second = repo.claim_pending(worker_id='worker-b', limit=10)

    assert [j.job_id for j in claimed_first] == [job.job_id]
    assert claimed_second == []
    assert claimed_first[0].job_state == JobState.CLAIMED


def test_job_mark_failed_applies_backoff_and_releases_lock(db_session):
    repo = JobRepository(db_session)
    repo.enqueue(cycle_id='cycle_1', job_type=JobType.RETRY_CYCLE, payload={}, dedup_key='dedup-2')
    db_session.commit()

    claimed = repo.claim_pending(worker_id='worker-a', limit=1)
    job = claimed[0]
    before = job.run_after
    repo.mark_failed(job, error='boom', retryable=True)

    assert job.job_state == JobState.FAILED
    assert job.locked_at is None
    assert job.worker_id is None
    assert _as_utc(job.run_after) > _as_utc(before)


def test_job_dead_letters_when_max_attempts_reached(db_session):
    repo = JobRepository(db_session)
    job = repo.enqueue(cycle_id='cycle_1', job_type=JobType.RETRY_CYCLE, payload={}, dedup_key='dedup-3', max_attempts=1)
    db_session.commit()

    claimed = repo.claim_pending(worker_id='worker-a', limit=1)
    repo.mark_failed(claimed[0], error='fatal', retryable=True)

    assert job.job_state == JobState.DEAD_LETTERED
    assert job.attempt_count == 1


def test_failed_job_can_be_reclaimed_after_backoff(db_session):
    repo = JobRepository(db_session)
    job = repo.enqueue(cycle_id='cycle_1', job_type=JobType.RETRY_CYCLE, payload={}, dedup_key='dedup-4')
    db_session.commit()

    claimed = repo.claim_pending(worker_id='worker-a', limit=1)
    repo.mark_failed(claimed[0], error='retry me', retryable=True)
    job.run_after = job.run_after - timedelta(hours=1)
    db_session.commit()

    reclaimed = repo.claim_pending(worker_id='worker-b', limit=1)
    assert [item.job_id for item in reclaimed] == [job.job_id]
    assert reclaimed[0].job_state == JobState.CLAIMED


def test_outbox_claim_pending_is_single_claim(db_session):
    repo = OutboxRepository(db_session)
    item = repo.add(cycle_id='cycle_1', event_type='cycle.created', payload={'x': 1})
    db_session.commit()

    claimed_first = repo.claim_pending(limit=10)
    db_session.flush()
    claimed_second = repo.claim_pending(limit=10)

    assert [i.outbox_id for i in claimed_first] == [item.outbox_id]
    assert claimed_second == []
    assert claimed_first[0].delivery_state == OutboxDeliveryState.CLAIMED


def test_outbox_mark_failed_applies_backoff(db_session):
    repo = OutboxRepository(db_session)
    repo.add(cycle_id='cycle_1', event_type='cycle.created', payload={'x': 1})
    db_session.commit()

    claimed = repo.claim_pending(limit=1)
    item = claimed[0]
    before = item.next_attempt_at
    repo.mark_failed(item, error='downstream failed')

    assert item.delivery_state == OutboxDeliveryState.FAILED
    assert item.retry_count == 1
    assert _as_utc(item.next_attempt_at) > _as_utc(before)


def test_outbox_dead_letters_when_max_attempts_reached(db_session):
    repo = OutboxRepository(db_session)
    item = repo.add(cycle_id='cycle_1', event_type='cycle.created', payload={'x': 1}, max_attempts=1)
    db_session.commit()

    claimed = repo.claim_pending(limit=1)
    repo.mark_failed(claimed[0], error='fatal', retryable=True)

    assert item.delivery_state == OutboxDeliveryState.DEAD_LETTERED
    assert item.dead_lettered_at is not None


def test_job_runner_dispatches_handler_and_marks_running_then_succeeded(db_session):
    repo = JobRepository(db_session)
    job = repo.enqueue(cycle_id='cycle-1', job_type=JobType.RETRY_CYCLE, payload={'x': 1}, dedup_key='runner-1')
    db_session.commit()

    seen_states: list[str] = []

    def handler(received_job):
        seen_states.append(received_job.job_state)

    runner = JobRunner(db_session, handlers={JobType.RETRY_CYCLE: handler})
    result = runner.run_once(worker_id='worker-a', limit=10)
    db_session.refresh(job)

    assert result.processed == 1
    assert result.succeeded == 1
    assert seen_states == [JobState.RUNNING]
    assert job.job_state == JobState.SUCCEEDED


def test_job_runner_dead_letters_when_handler_missing(db_session):
    repo = JobRepository(db_session)
    job = repo.enqueue(cycle_id='cycle-1', job_type=JobType.REPLAN_CYCLE, payload={}, dedup_key='runner-2')
    db_session.commit()

    runner = JobRunner(db_session, handlers={})
    result = runner.run_once(worker_id='worker-a', limit=10)
    db_session.refresh(job)

    assert result.dead_lettered == 1
    assert job.job_state == JobState.DEAD_LETTERED
    assert 'No handler registered' in job.last_error


def test_job_runner_marks_retryable_failures_as_failed(db_session):
    repo = JobRepository(db_session)
    job = repo.enqueue(cycle_id='cycle-1', job_type=JobType.RETRY_CYCLE, payload={}, dedup_key='runner-3')
    db_session.commit()

    def handler(_job):
        raise JobExecutionError('transient boom', retryable=True)

    runner = JobRunner(db_session, handlers={JobType.RETRY_CYCLE: handler})
    result = runner.run_once(worker_id='worker-a', limit=10)
    db_session.refresh(job)

    assert result.failed == 1
    assert job.job_state == JobState.FAILED
    assert job.attempt_count == 1


def test_outbox_consumer_delivers_with_handler(db_session):
    repo = OutboxRepository(db_session)
    item = repo.add(cycle_id='cycle-1', event_type='cycle.created', payload={'x': 1})
    db_session.commit()

    delivered_payloads: list[dict] = []

    def handler(received_item):
        delivered_payloads.append(received_item.payload)

    consumer = OutboxConsumer(db_session, handlers={'cycle.created': handler})
    result = consumer.deliver_once(limit=10)
    db_session.refresh(item)

    assert result.processed == 1
    assert result.delivered_ids == [item.outbox_id]
    assert delivered_payloads == [{'x': 1}]
    assert item.delivery_state == OutboxDeliveryState.DELIVERED


def test_outbox_consumer_marks_retryable_failures_as_failed(db_session):
    repo = OutboxRepository(db_session)
    item = repo.add(cycle_id='cycle-1', event_type='cycle.created', payload={'x': 1})
    db_session.commit()

    def handler(_item):
        raise OutboxDeliveryError('email provider timeout', retryable=True)

    consumer = OutboxConsumer(db_session, handlers={'cycle.created': handler})
    result = consumer.deliver_once(limit=10)
    db_session.refresh(item)

    assert result.failed == 1
    assert item.delivery_state == OutboxDeliveryState.FAILED
    assert item.retry_count == 1


def test_outbox_consumer_dead_letters_when_handler_missing(db_session):
    repo = OutboxRepository(db_session)
    item = repo.add(cycle_id='cycle-1', event_type='cycle.created', payload={'x': 1})
    db_session.commit()

    consumer = OutboxConsumer(db_session, handlers={})
    result = consumer.deliver_once(limit=10)
    db_session.refresh(item)

    assert result.dead_lettered == 1
    assert item.delivery_state == OutboxDeliveryState.DEAD_LETTERED
    assert item.dead_lettered_at is not None
