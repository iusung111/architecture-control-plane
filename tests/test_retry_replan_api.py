from sqlalchemy import select

from app.db.models import AuditEvent, Cycle
from app.domain.enums import CycleState, UserStatus


def _seed_verification_failed_cycle(db_session, cycle_id: str) -> Cycle:
    cycle = Cycle(
        cycle_id=cycle_id,
        tenant_id="tenant-1",
        tenant_scope="tenant-1",
        project_id="project-1",
        owner_user_id="user-1",
        current_state=CycleState.VERIFICATION_FAILED,
        user_status=UserStatus.ACTION_REQUIRED,
        idempotency_key=f"idem-{cycle_id}",
        request_fingerprint=f"fp-{cycle_id}",
    )
    db_session.add(cycle)
    db_session.commit()
    return cycle


def test_retry_cycle_accepts_when_verification_failed(client, db_session):
    _seed_verification_failed_cycle(db_session, "cycle-retry-ok")

    response = client.post(
        "/v1/cycles/cycle-retry-ok/retry",
        headers={"X-User-Id": "user-1", "Idempotency-Key": "retry-key-1"},
        json={"reason": "rerun verification path"},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["data"]["cycle_id"] == "cycle-retry-ok"
    assert body["data"]["action"] == "retry"
    assert body["data"]["accepted"] is True

    audit_event = db_session.execute(
        select(AuditEvent).where(AuditEvent.cycle_id == "cycle-retry-ok", AuditEvent.event_type == "cycle.retry_requested")
    ).scalar_one()
    assert audit_event.actor_id == "user-1"
    assert audit_event.event_payload["reason"] == "rerun verification path"
    assert audit_event.event_payload["to_state"] == CycleState.RETRY_SCHEDULED


def test_replan_cycle_accepts_when_verification_failed(client, db_session):
    _seed_verification_failed_cycle(db_session, "cycle-replan-ok")

    response = client.post(
        "/v1/cycles/cycle-replan-ok/replan",
        headers={"X-User-Id": "user-1", "Idempotency-Key": "replan-key-1"},
        json={"reason": "adjust candidate plan", "override_input": {"prompt": "use safer mode"}},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["data"]["cycle_id"] == "cycle-replan-ok"
    assert body["data"]["action"] == "replan"

    audit_event = db_session.execute(
        select(AuditEvent).where(AuditEvent.cycle_id == "cycle-replan-ok", AuditEvent.event_type == "cycle.replan_requested")
    ).scalar_one()
    assert audit_event.actor_id == "user-1"
    assert audit_event.event_payload["override_input"] == {"prompt": "use safer mode"}
    assert audit_event.event_payload["to_state"] == CycleState.REPLAN_REQUESTED


def test_retry_cycle_rejects_invalid_state(client, db_session):
    cycle = Cycle(
        cycle_id="cycle-retry-bad-state",
        tenant_id="tenant-1",
        tenant_scope="tenant-1",
        project_id="project-1",
        owner_user_id="user-1",
        current_state=CycleState.INTENT_ACCEPTED,
        user_status=UserStatus.ACCEPTED,
        idempotency_key="idem-cycle-retry-bad-state",
        request_fingerprint="fp-cycle-retry-bad-state",
    )
    db_session.add(cycle)
    db_session.commit()

    response = client.post(
        "/v1/cycles/cycle-retry-bad-state/retry",
        headers={"X-User-Id": "user-1", "Idempotency-Key": "retry-key-2"},
        json={"reason": "force"},
    )

    assert response.status_code == 409
    assert "retry not allowed" in response.json()["error"]["message"]



def test_retry_cycle_forbidden_for_different_owner(client, db_session):
    _seed_verification_failed_cycle(db_session, "cycle-retry-forbidden")

    response = client.post(
        "/v1/cycles/cycle-retry-forbidden/retry",
        headers={"X-User-Id": "user-2", "Idempotency-Key": "retry-key-3"},
        json={"reason": "unauthorized rerun"},
    )

    assert response.status_code == 403
    assert "forbidden" in response.json()["error"]["message"]


def test_replan_cycle_forbidden_for_different_tenant(client, db_session):
    _seed_verification_failed_cycle(db_session, "cycle-replan-forbidden")

    response = client.post(
        "/v1/cycles/cycle-replan-forbidden/replan",
        headers={"X-User-Id": "user-1", "X-Tenant-Id": "tenant-2", "Idempotency-Key": "replan-key-2"},
        json={"reason": "cross-tenant change", "override_input": {"prompt": "noop"}},
    )

    assert response.status_code == 403
    assert "forbidden" in response.json()["error"]["message"]



def test_retry_cycle_is_idempotent_for_same_key(client, db_session):
    _seed_verification_failed_cycle(db_session, "cycle-retry-idempotent")
    headers = {"X-User-Id": "user-1", "Idempotency-Key": "retry-key-idem"}

    first = client.post(
        "/v1/cycles/cycle-retry-idempotent/retry",
        headers=headers,
        json={"reason": "rerun verification path"},
    )
    second = client.post(
        "/v1/cycles/cycle-retry-idempotent/retry",
        headers=headers,
        json={"reason": "rerun verification path"},
    )

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["data"]["job_id"] == second.json()["data"]["job_id"]



def test_replan_cycle_is_idempotent_for_same_key(client, db_session):
    _seed_verification_failed_cycle(db_session, "cycle-replan-idempotent")
    headers = {"X-User-Id": "user-1", "Idempotency-Key": "replan-key-idem"}

    first = client.post(
        "/v1/cycles/cycle-replan-idempotent/replan",
        headers=headers,
        json={"reason": "adjust candidate plan", "override_input": {"prompt": "use safer mode"}},
    )
    second = client.post(
        "/v1/cycles/cycle-replan-idempotent/replan",
        headers=headers,
        json={"reason": "adjust candidate plan", "override_input": {"prompt": "use safer mode"}},
    )

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["data"]["job_id"] == second.json()["data"]["job_id"]
