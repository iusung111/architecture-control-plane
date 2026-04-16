from __future__ import annotations

import threading
from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.auth import AuthContext
from app.db.base import Base
from app.db.models import AuditEvent, Cycle, Job, NotificationOutbox
from app.domain.enums import CycleState, JobState, JobType, OutboxDeliveryState, UserStatus
from app.repositories.audit import AuditEventRepository
from app.repositories.cycles import CycleRepository
from app.repositories.jobs import JobRepository
from app.repositories.outbox import OutboxRepository
from app.services.cycles import CycleWriteService
from app.services.unit_of_work import SqlAlchemyUnitOfWork
from app.schemas.cycles import CreateCycleRequest


@pytest.fixture()
def sqlite_file_session_factory(tmp_path: Path) -> Generator[sessionmaker[Session], None, None]:
    db_path = tmp_path / "concurrency.db"
    engine = create_engine(
        f"sqlite+pysqlite:///{db_path}",
        connect_args={"check_same_thread": False, "timeout": 10},
        future=True,
    )
    with engine.begin() as conn:
        conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        conn.exec_driver_sql("PRAGMA busy_timeout=10000")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    try:
        yield factory
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _make_cycle_write_service(db: Session) -> CycleWriteService:
    return CycleWriteService(
        cycle_repo=CycleRepository(db),
        job_repo=JobRepository(db),
        outbox_repo=OutboxRepository(db),
        audit_repo=AuditEventRepository(db),
        uow=SqlAlchemyUnitOfWork(db),
    )


@pytest.fixture()
def seeded_retry_cycle(sqlite_file_session_factory: sessionmaker[Session]) -> str:
    session = sqlite_file_session_factory()
    try:
        cycle = Cycle(
            cycle_id="cycle-race-1",
            tenant_id="tenant-a",
            project_id="proj-1",
            owner_user_id="user-1",
            current_state=CycleState.VERIFICATION_FAILED,
            user_status=UserStatus.ACTION_REQUIRED,
            latest_iteration_no=3,
            idempotency_key="seed-idem",
            request_fingerprint="seed-fingerprint",
        )
        session.add(cycle)
        session.commit()
        return cycle.cycle_id
    finally:
        session.close()


def test_create_cycle_deduplicates_across_two_sessions_on_same_idempotency_key(
    sqlite_file_session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    barrier = threading.Barrier(2)
    original_get_by_idempotency = CycleRepository.get_by_idempotency
    sync_lock = threading.Lock()
    miss_count = 0

    def patched_get_by_idempotency(self, owner_user_id: str, tenant_scope: str, project_id: str, idempotency_key: str):
        nonlocal miss_count
        result = original_get_by_idempotency(self, owner_user_id, tenant_scope, project_id, idempotency_key)
        should_wait = False
        with sync_lock:
            if idempotency_key == "idem-race-create" and result is None and miss_count < 2:
                miss_count += 1
                should_wait = True
        if should_wait:
            barrier.wait(timeout=5)
        return result

    monkeypatch.setattr(CycleRepository, "get_by_idempotency", patched_get_by_idempotency)

    payload = CreateCycleRequest(project_id="proj-1", user_input="same concurrent request", tenant_id="tenant-a")
    auth = AuthContext(user_id="user-1", role="operator", tenant_id="tenant-a")
    results: list[tuple[bool, dict]] = []
    errors: list[BaseException] = []
    result_lock = threading.Lock()

    def worker() -> None:
        session = sqlite_file_session_factory()
        try:
            outcome = _make_cycle_write_service(session).create_cycle(payload, idempotency_key="idem-race-create", auth=auth)
            with result_lock:
                results.append(outcome)
        except BaseException as exc:  # pragma: no cover - surfaced via assertion below
            with result_lock:
                errors.append(exc)
        finally:
            session.close()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert len(results) == 2
    assert sorted(created for created, _ in results) == [False, True]

    cycle_ids = {payload["cycle_id"] for _, payload in results}
    assert len(cycle_ids) == 1

    verification_session = sqlite_file_session_factory()
    try:
        assert verification_session.scalar(select(func.count()).select_from(Cycle)) == 1
        assert (
            verification_session.scalar(
                select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type == "cycle.created")
            )
            == 1
        )
    finally:
        verification_session.close()


def test_retry_cycle_deduplicates_across_two_sessions_on_same_idempotency_key(
    sqlite_file_session_factory: sessionmaker[Session], seeded_retry_cycle: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    barrier = threading.Barrier(2)
    original_get_by_dedup_key = JobRepository.get_by_dedup_key
    sync_lock = threading.Lock()
    miss_count = 0
    target_dedup_key = f"retry_cycle:{seeded_retry_cycle}:3:idem-race-retry"

    def patched_get_by_dedup_key(self, dedup_key: str):
        nonlocal miss_count
        result = original_get_by_dedup_key(self, dedup_key)
        should_wait = False
        with sync_lock:
            if dedup_key == target_dedup_key and result is None and miss_count < 2:
                miss_count += 1
                should_wait = True
        if should_wait:
            barrier.wait(timeout=5)
        return result

    monkeypatch.setattr(JobRepository, "get_by_dedup_key", patched_get_by_dedup_key)

    auth = AuthContext(user_id="user-1", role="operator", tenant_id="tenant-a")
    results: list[dict] = []
    errors: list[BaseException] = []
    result_lock = threading.Lock()

    def worker() -> None:
        session = sqlite_file_session_factory()
        try:
            outcome = _make_cycle_write_service(session).retry_cycle(
                seeded_retry_cycle,
                reason="retry the failed verification",
                idempotency_key="idem-race-retry",
                auth=auth,
            )
            with result_lock:
                results.append(outcome)
        except BaseException as exc:  # pragma: no cover - surfaced via assertion below
            with result_lock:
                errors.append(exc)
        finally:
            session.close()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert len(results) == 2
    assert {payload["job_id"] for payload in results} == {results[0]["job_id"]}
    assert {payload["state"] for payload in results} == {CycleState.RETRY_SCHEDULED}

    verification_session = sqlite_file_session_factory()
    try:
        assert verification_session.scalar(select(func.count()).select_from(Job)) == 1
        assert (
            verification_session.scalar(
                select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type == "cycle.retry_requested")
            )
            == 1
        )
    finally:
        verification_session.close()


def test_job_claim_pending_only_returns_one_claim_across_two_sessions(
    sqlite_file_session_factory: sessionmaker[Session],
) -> None:
    setup_session = sqlite_file_session_factory()
    try:
        repo = JobRepository(setup_session)
        job = repo.enqueue(cycle_id="cycle-1", job_type=JobType.RETRY_CYCLE, payload={}, dedup_key="claim-race-job")
        setup_session.commit()
        job_id = job.job_id
    finally:
        setup_session.close()

    start = threading.Event()
    results: dict[str, list[str]] = {}
    errors: list[BaseException] = []
    result_lock = threading.Lock()

    def worker(worker_id: str) -> None:
        session = sqlite_file_session_factory()
        try:
            start.wait(timeout=5)
            claimed = JobRepository(session).claim_pending(worker_id=worker_id, limit=1)
            session.commit()
            with result_lock:
                results[worker_id] = [item.job_id for item in claimed]
        except BaseException as exc:  # pragma: no cover - surfaced via assertion below
            with result_lock:
                errors.append(exc)
        finally:
            session.close()

    threads = [threading.Thread(target=worker, args=("worker-a",)), threading.Thread(target=worker, args=("worker-b",))]
    for thread in threads:
        thread.start()
    start.set()
    for thread in threads:
        thread.join()

    assert errors == []
    claimed_lists = list(results.values())
    assert sorted(len(items) for items in claimed_lists) == [0, 1]
    assert {item for items in claimed_lists for item in items} == {job_id}

    verification_session = sqlite_file_session_factory()
    try:
        claimed_job = verification_session.get(Job, job_id)
        assert claimed_job is not None
        assert claimed_job.job_state == JobState.CLAIMED
        assert claimed_job.worker_id in {"worker-a", "worker-b"}
    finally:
        verification_session.close()


def test_outbox_claim_pending_only_returns_one_claim_across_two_sessions(
    sqlite_file_session_factory: sessionmaker[Session],
) -> None:
    setup_session = sqlite_file_session_factory()
    try:
        repo = OutboxRepository(setup_session)
        item = repo.add(cycle_id="cycle-1", event_type="cycle.created", payload={"x": 1})
        setup_session.commit()
        outbox_id = item.outbox_id
    finally:
        setup_session.close()

    start = threading.Event()
    results: list[list[str]] = []
    errors: list[BaseException] = []
    result_lock = threading.Lock()

    def worker() -> None:
        session = sqlite_file_session_factory()
        try:
            start.wait(timeout=5)
            claimed = OutboxRepository(session).claim_pending(limit=1)
            session.commit()
            with result_lock:
                results.append([item.outbox_id for item in claimed])
        except BaseException as exc:  # pragma: no cover - surfaced via assertion below
            with result_lock:
                errors.append(exc)
        finally:
            session.close()

    threads = [threading.Thread(target=worker), threading.Thread(target=worker)]
    for thread in threads:
        thread.start()
    start.set()
    for thread in threads:
        thread.join()

    assert errors == []
    assert sorted(len(items) for items in results) == [0, 1]
    assert {item for items in results for item in items} == {outbox_id}

    verification_session = sqlite_file_session_factory()
    try:
        claimed_item = verification_session.get(NotificationOutbox, outbox_id)
        assert claimed_item is not None
        assert claimed_item.delivery_state == OutboxDeliveryState.CLAIMED
    finally:
        verification_session.close()
