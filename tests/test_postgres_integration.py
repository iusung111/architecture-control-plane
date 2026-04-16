from __future__ import annotations

import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_db
from app.core.config import get_settings
from app.db.base import Base
from app.db.models import Approval, Cycle, Job, NotificationOutbox
from app.domain.enums import CycleState, JobState, JobType, OutboxDeliveryState
from app.main import app
from app.repositories.approvals import ApprovalRepository
from app.repositories.cycles import CycleRepository
from app.repositories.jobs import JobRepository
from app.repositories.outbox import OutboxRepository
from app.workers.default_handlers import build_default_job_handlers
from app.workers.job_runner import JobRunner
from app.workers.outbox_consumer import OutboxConsumer

pytestmark = pytest.mark.postgres_integration


def _postgres_integration_enabled() -> bool:
    return os.getenv("RUN_POSTGRES_INTEGRATION", "0") == "1"


def _test_database_url() -> str:
    return os.getenv("TEST_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/control_plane_test")


def _admin_database_url(database_url: str) -> str:
    return database_url.rsplit("/", 1)[0] + "/postgres"


def _database_name(database_url: str) -> str:
    return database_url.rsplit("/", 1)[1].split("?", 1)[0]


@pytest.fixture(scope="module")
def postgres_engine():
    if not _postgres_integration_enabled():
        pytest.skip("RUN_POSTGRES_INTEGRATION is not enabled")

    database_url = _test_database_url()
    admin_url = _admin_database_url(database_url)
    database_name = _database_name(database_url)

    try:
        with psycopg.connect(admin_url.replace("+psycopg", ""), autocommit=True) as admin_conn:
            with admin_conn.cursor() as cur:
                cur.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()",
                    (database_name,),
                )
                cur.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
                cur.execute(f'CREATE DATABASE "{database_name}"')
    except psycopg.Error as exc:
        pytest.skip(f"PostgreSQL is not reachable: {exc}")

    old_database_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = database_url
    get_settings.cache_clear()

    alembic_cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "db_migrations"))
    alembic_cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(alembic_cfg, "head")

    engine = create_engine(database_url, future=True)
    try:
        yield engine
    finally:
        engine.dispose()
        if old_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old_database_url
        get_settings.cache_clear()
        with psycopg.connect(admin_url.replace("+psycopg", ""), autocommit=True) as admin_conn:
            with admin_conn.cursor() as cur:
                cur.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()",
                    (database_name,),
                )
                cur.execute(f'DROP DATABASE IF EXISTS "{database_name}"')


@pytest.fixture(scope="module")
def postgres_session_factory(postgres_engine):
    return sessionmaker(bind=postgres_engine, autoflush=False, autocommit=False, expire_on_commit=False)


@pytest.fixture()
def postgres_db_session(postgres_session_factory) -> Session:
    session = postgres_session_factory()
    table_names = ", ".join(f'"{table.name}"' for table in reversed(Base.metadata.sorted_tables))
    session.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))
    session.commit()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def postgres_client(postgres_db_session: Session) -> TestClient:
    def override_get_db():
        yield postgres_db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_postgres_readiness_and_runtime_flow(postgres_client: TestClient, postgres_db_session: Session) -> None:
    ready = postgres_client.get("/readyz")
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready"}

    create = postgres_client.post(
        "/v1/cycles",
        headers={"X-User-Id": "pg-owner", "Idempotency-Key": f"pg-create-{uuid4().hex}"},
        json={"project_id": "pg-proj", "user_input": "complete automatically"},
    )
    assert create.status_code == 201
    cycle_id = create.json()["data"]["cycle_id"]

    run_result = JobRunner(postgres_db_session, handlers=build_default_job_handlers(postgres_db_session)).run_once(
        worker_id="pg-worker",
        limit=10,
    )
    assert run_result.succeeded >= 1

    summary = postgres_client.get(f"/v1/cycles/{cycle_id}", headers={"X-User-Id": "pg-owner"})
    assert summary.status_code == 200
    assert summary.json()["data"]["state"] == CycleState.TERMINALIZED

    result = postgres_client.get(f"/v1/cycles/{cycle_id}/result", headers={"X-User-Id": "pg-owner"})
    assert result.status_code == 200
    assert result.json()["data"]["final_state"] == CycleState.TERMINALIZED


def test_postgres_claim_and_outbox_delivery_semantics(postgres_client: TestClient, postgres_db_session: Session) -> None:
    create = postgres_client.post(
        "/v1/cycles",
        headers={"X-User-Id": "pg-owner-2", "Idempotency-Key": f"pg-create-{uuid4().hex}"},
        json={"project_id": "pg-proj-2", "user_input": "complete automatically"},
    )
    assert create.status_code == 201
    cycle_id = create.json()["data"]["cycle_id"]

    job_repo_result = JobRunner(postgres_db_session, handlers={}).run_once(worker_id="pg-worker-empty", limit=10)
    assert job_repo_result.processed == 1
    job = postgres_db_session.execute(select(Job).where(Job.cycle_id == cycle_id)).scalar_one()
    assert job.job_state in {JobState.FAILED, JobState.DEAD_LETTERED}

    item = NotificationOutbox(
        outbox_id=uuid4().hex,
        cycle_id=cycle_id,
        event_type="cycle.completed",
        payload={"cycle_id": cycle_id},
        delivery_state=OutboxDeliveryState.PENDING,
    )
    postgres_db_session.add(item)
    postgres_db_session.commit()

    outbox_result = OutboxConsumer(postgres_db_session, handlers={}).deliver_once(limit=20)
    assert outbox_result.processed >= 1
    postgres_db_session.refresh(item)
    assert item.delivery_state == OutboxDeliveryState.DEAD_LETTERED


def test_postgres_job_claim_uses_skip_locked(postgres_session_factory) -> None:
    seed_session = postgres_session_factory()
    job = JobRepository(seed_session).enqueue(
        cycle_id=None,
        job_type=JobType.RUN_VERIFICATION,
        payload={"cycle_id": "pg-lock-job"},
        dedup_key=f"pg-lock-job-{uuid4().hex}",
    )
    seed_session.commit()
    seed_session.close()

    session_a = postgres_session_factory()
    session_b = postgres_session_factory()
    try:
        claimed_a = JobRepository(session_a).claim_pending(worker_id="worker-a", limit=1)
        assert [item.job_id for item in claimed_a] == [job.job_id]

        session_b.execute(text("SET LOCAL lock_timeout = '250ms'"))
        claimed_b = JobRepository(session_b).claim_pending(worker_id="worker-b", limit=1)
        assert claimed_b == []

        session_a.commit()
        refreshed = session_b.execute(select(Job).where(Job.job_id == job.job_id)).scalar_one()
        assert refreshed.job_state == JobState.CLAIMED
        assert refreshed.worker_id == "worker-a"
    finally:
        session_b.rollback()
        session_a.rollback()
        session_b.close()
        session_a.close()



def test_postgres_outbox_claim_uses_skip_locked(postgres_session_factory) -> None:
    seed_session = postgres_session_factory()
    item = NotificationOutbox(
        outbox_id=uuid4().hex,
        cycle_id=None,
        event_type="cycle.completed",
        payload={"cycle_id": "pg-lock-outbox"},
        delivery_state=OutboxDeliveryState.PENDING,
    )
    seed_session.add(item)
    seed_session.commit()
    seed_session.close()

    session_a = postgres_session_factory()
    session_b = postgres_session_factory()
    try:
        claimed_a = OutboxRepository(session_a).claim_pending(limit=1)
        assert [entry.outbox_id for entry in claimed_a] == [item.outbox_id]

        session_b.execute(text("SET LOCAL lock_timeout = '250ms'"))
        claimed_b = OutboxRepository(session_b).claim_pending(limit=1)
        assert claimed_b == []

        session_a.commit()
        refreshed = session_b.execute(
            select(NotificationOutbox).where(NotificationOutbox.outbox_id == item.outbox_id)
        ).scalar_one()
        assert refreshed.delivery_state == OutboxDeliveryState.CLAIMED
    finally:
        session_b.rollback()
        session_a.rollback()
        session_b.close()
        session_a.close()



def test_postgres_cycle_row_lock_blocks_second_for_update(postgres_session_factory) -> None:
    cycle_id = uuid4().hex
    seed_session = postgres_session_factory()
    seed_cycle = Cycle(
        cycle_id=cycle_id,
        tenant_id=None,
        project_id="pg-lock-proj",
        owner_user_id="pg-owner",
        current_state=CycleState.HUMAN_APPROVAL_PENDING,
        user_status="approval_required",
        idempotency_key=f"lock-{uuid4().hex}",
        request_fingerprint=uuid4().hex,
    )
    seed_session.add(seed_cycle)
    seed_session.commit()
    seed_session.close()

    session_a = postgres_session_factory()
    session_b = postgres_session_factory()
    try:
        locked = CycleRepository(session_a).get_by_id_for_update(cycle_id)
        assert locked is not None

        session_b.execute(text("SET LOCAL lock_timeout = '250ms'"))
        with pytest.raises((OperationalError, DBAPIError)):
            CycleRepository(session_b).get_by_id_for_update(cycle_id)
    finally:
        session_b.rollback()
        session_a.rollback()
        session_b.close()
        session_a.close()


def test_postgres_approval_row_lock_blocks_second_for_update(postgres_session_factory) -> None:
    cycle_id = uuid4().hex
    approval_id = uuid4().hex
    seed_session = postgres_session_factory()
    seed_cycle = Cycle(
        cycle_id=cycle_id,
        tenant_id=None,
        project_id="pg-lock-proj-approval",
        owner_user_id="pg-owner",
        current_state=CycleState.HUMAN_APPROVAL_PENDING,
        user_status="approval_required",
        idempotency_key=f"lock-{uuid4().hex}",
        request_fingerprint=uuid4().hex,
    )
    seed_approval = Approval(
        approval_id=approval_id,
        cycle_id=cycle_id,
        approval_state="pending",
        required_role="approver",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    seed_session.add_all([seed_cycle, seed_approval])
    seed_session.commit()
    seed_session.close()

    session_a = postgres_session_factory()
    session_b = postgres_session_factory()
    try:
        locked = ApprovalRepository(session_a).get_by_id_for_update(approval_id)
        assert locked is not None

        session_b.execute(text("SET LOCAL lock_timeout = '250ms'"))
        with pytest.raises((OperationalError, DBAPIError)):
            ApprovalRepository(session_b).get_by_id_for_update(approval_id)
    finally:
        session_b.rollback()
        session_a.rollback()
        session_b.close()
        session_a.close()
