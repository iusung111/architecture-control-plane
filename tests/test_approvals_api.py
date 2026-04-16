from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db.models import Approval, AuditEvent, Cycle
from app.domain.enums import ApprovalState, CycleState, UserStatus


def _seed_cycle(db_session, cycle_id: str, current_state: str = CycleState.HUMAN_APPROVAL_PENDING) -> Cycle:
    cycle = Cycle(
        cycle_id=cycle_id,
        tenant_id="tenant-1",
        tenant_scope="tenant-1",
        project_id="project-1",
        owner_user_id="user-1",
        current_state=current_state,
        user_status=UserStatus.APPROVAL_REQUIRED,
        idempotency_key=f"idem-{cycle_id}",
        request_fingerprint=f"fp-{cycle_id}",
    )
    db_session.add(cycle)
    db_session.flush()
    return cycle


def _seed_approval(db_session, approval_id: str, cycle_id: str, expires_at: datetime, state: str = ApprovalState.PENDING) -> Approval:
    approval = Approval(
        approval_id=approval_id,
        cycle_id=cycle_id,
        approval_state=state,
        required_role="operator",
        expires_at=expires_at,
    )
    db_session.add(approval)
    cycle = db_session.get(Cycle, cycle_id)
    if cycle is not None and state == ApprovalState.PENDING:
        cycle.active_approval_id = approval_id
    db_session.commit()
    return approval


def test_confirm_approval_approved_enqueues_resume_job(client, db_session):
    _seed_cycle(db_session, "cycle-approval-ok")
    _seed_approval(
        db_session,
        approval_id="approval-ok",
        cycle_id="cycle-approval-ok",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    response = client.post(
        "/v1/approvals/approval-ok/confirm",
        headers={"X-User-Id": "user-1", "X-User-Role": "operator", "Idempotency-Key": "approval-key-1"},
        json={"decision": "approved", "comment": "looks good"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["approval_id"] == "approval-ok"
    assert body["data"]["approval_state"] == "approved"
    assert body["data"]["resume_enqueued"] is True
    cycle = db_session.get(Cycle, "cycle-approval-ok")
    assert cycle is not None
    assert cycle.active_approval_id is None

    audit_event = db_session.execute(
        select(AuditEvent).where(AuditEvent.approval_id == "approval-ok", AuditEvent.event_type == "approval.approved")
    ).scalar_one()
    assert audit_event.actor_id == "user-1"
    assert audit_event.event_payload["resume_enqueued"] is True


def test_confirm_approval_rejected_terminalizes_cycle(client, db_session):
    _seed_cycle(db_session, "cycle-approval-reject")
    _seed_approval(
        db_session,
        approval_id="approval-reject",
        cycle_id="cycle-approval-reject",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    response = client.post(
        "/v1/approvals/approval-reject/confirm",
        headers={"X-User-Id": "user-1", "X-User-Role": "operator", "Idempotency-Key": "approval-key-2"},
        json={"decision": "rejected", "reason_code": "unsafe"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["approval_state"] == "rejected"
    cycle = db_session.get(Cycle, "cycle-approval-reject")
    assert cycle is not None
    assert cycle.current_state == CycleState.TERMINAL_FAIL
    assert cycle.active_approval_id is None
    assert cycle.terminalized_at is not None

    audit_events = db_session.execute(
        select(AuditEvent).where(AuditEvent.cycle_id == "cycle-approval-reject").order_by(AuditEvent.occurred_at.asc())
    ).scalars().all()
    event_types = [item.event_type for item in audit_events]
    assert "approval.rejected" in event_types
    assert "cycle.terminalized" in event_types

    terminalized_event = next(item for item in audit_events if item.event_type == "cycle.terminalized")
    assert terminalized_event.event_payload["from_state"] == CycleState.HUMAN_APPROVAL_PENDING
    assert terminalized_event.event_payload["to_state"] == CycleState.TERMINAL_FAIL


def test_confirm_approval_expired_returns_conflict(client, db_session):
    _seed_cycle(db_session, "cycle-approval-expired")
    _seed_approval(
        db_session,
        approval_id="approval-expired",
        cycle_id="cycle-approval-expired",
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )

    response = client.post(
        "/v1/approvals/approval-expired/confirm",
        headers={"X-User-Id": "user-1", "X-User-Role": "operator", "Idempotency-Key": "approval-key-3"},
        json={"decision": "approved"},
    )

    assert response.status_code == 409
    body = response.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "conflict"
    assert "expired" in body["error"]["message"]

    cycle = db_session.get(Cycle, "cycle-approval-expired")
    approval = db_session.get(Approval, "approval-expired")
    assert cycle is not None
    assert approval is not None
    assert cycle.active_approval_id is None
    assert approval.approval_state == ApprovalState.EXPIRED

    audit_event = db_session.execute(
        select(AuditEvent).where(AuditEvent.approval_id == "approval-expired", AuditEvent.event_type == "approval.expired")
    ).scalar_one()
    assert audit_event.actor_id == "user-1"
    assert audit_event.event_payload["attempted_decision"] == "approved"


def test_confirm_approval_forbidden_for_different_owner(client, db_session):
    _seed_cycle(db_session, "cycle-approval-forbidden-owner")
    _seed_approval(
        db_session,
        approval_id="approval-forbidden-owner",
        cycle_id="cycle-approval-forbidden-owner",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    response = client.post(
        "/v1/approvals/approval-forbidden-owner/confirm",
        headers={"X-User-Id": "user-2", "X-User-Role": "operator", "Idempotency-Key": "approval-key-4"},
        json={"decision": "approved"},
    )

    assert response.status_code == 403
    body = response.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "forbidden"
    assert "forbidden" in body["error"]["message"]


def test_confirm_approval_forbidden_for_different_tenant(client, db_session):
    _seed_cycle(db_session, "cycle-approval-forbidden-tenant")
    _seed_approval(
        db_session,
        approval_id="approval-forbidden-tenant",
        cycle_id="cycle-approval-forbidden-tenant",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    response = client.post(
        "/v1/approvals/approval-forbidden-tenant/confirm",
        headers={"X-User-Id": "user-1", "X-User-Role": "operator", "X-Tenant-Id": "tenant-2", "Idempotency-Key": "approval-key-5"},
        json={"decision": "approved"},
    )

    assert response.status_code == 403
    body = response.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "forbidden"
    assert "forbidden" in body["error"]["message"]



def test_cycle_summary_shows_approval_required_when_active_approval_present(client, db_session):
    _seed_cycle(db_session, "cycle-summary-approval")
    _seed_approval(
        db_session,
        approval_id="approval-summary",
        cycle_id="cycle-summary-approval",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    response = client.get(
        "/v1/cycles/cycle-summary-approval",
        headers={"X-User-Id": "user-1", "X-Tenant-Id": "tenant-1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["approval_required"] is True


def test_confirm_approval_uses_row_lock_reads(monkeypatch, db_session):
    from app.repositories.approvals import ApprovalRepository
    from app.repositories.audit import AuditEventRepository
    from app.repositories.cycles import CycleRepository
    from app.repositories.jobs import JobRepository
    from app.repositories.outbox import OutboxRepository
    from app.services.approvals import ApprovalService
    from app.services.unit_of_work import SqlAlchemyUnitOfWork

    _seed_cycle(db_session, "cycle-lock-check")
    _seed_approval(
        db_session,
        approval_id="approval-lock-check",
        cycle_id="cycle-lock-check",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    called = {"approval": False, "cycle": False}
    approval_repo = ApprovalRepository(db_session)
    cycle_repo = CycleRepository(db_session)

    orig_approval = approval_repo.get_by_id_for_update
    orig_cycle = cycle_repo.get_by_id_for_update

    def wrapped_approval(approval_id: str):
        called["approval"] = True
        return orig_approval(approval_id)

    def wrapped_cycle(cycle_id: str):
        called["cycle"] = True
        return orig_cycle(cycle_id)

    monkeypatch.setattr(approval_repo, "get_by_id_for_update", wrapped_approval)
    monkeypatch.setattr(cycle_repo, "get_by_id_for_update", wrapped_cycle)

    service = ApprovalService(
        approval_repo=approval_repo,
        cycle_repo=cycle_repo,
        job_repo=JobRepository(db_session),
        outbox_repo=OutboxRepository(db_session),
        audit_repo=AuditEventRepository(db_session),
        uow=SqlAlchemyUnitOfWork(db_session),
    )

    result = service.confirm(
        approval_id="approval-lock-check",
        decision="approved",
        actor_id="user-1",
        actor_role="operator",
        actor_tenant_id="tenant-1",
        comment=None,
        reason_code=None,
        idempotency_key="approval-key-lock",
    )

    assert result["approval_state"] == "approved"
    assert called["approval"] is True
    assert called["cycle"] is True


def test_list_pending_approvals_scopes_to_current_actor(client, db_session):
    _seed_cycle(db_session, "cycle-pending-visible")
    _seed_approval(
        db_session,
        approval_id="approval-visible",
        cycle_id="cycle-pending-visible",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    other_cycle = Cycle(
        cycle_id="cycle-pending-hidden",
        tenant_id="tenant-1",
        tenant_scope="tenant-1",
        project_id="project-1",
        owner_user_id="user-2",
        current_state=CycleState.HUMAN_APPROVAL_PENDING,
        user_status=UserStatus.APPROVAL_REQUIRED,
        idempotency_key="idem-cycle-pending-hidden",
        request_fingerprint="fp-cycle-pending-hidden",
        active_approval_id="approval-hidden",
    )
    db_session.add(other_cycle)
    db_session.add(Approval(
        approval_id="approval-hidden",
        cycle_id="cycle-pending-hidden",
        approval_state=ApprovalState.PENDING,
        required_role="operator",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
    ))
    db_session.commit()

    response = client.get(
        "/v1/approvals/pending",
        headers={"X-User-Id": "user-1", "X-User-Role": "operator", "X-Tenant-Id": "tenant-1"},
    )

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["approval_id"] == "approval-visible"
    assert items[0]["cycle_id"] == "cycle-pending-visible"


def test_list_pending_approvals_filters_by_project_and_role(client, db_session):
    _seed_cycle(db_session, "cycle-project-a")
    _seed_approval(
        db_session,
        approval_id="approval-project-a",
        cycle_id="cycle-project-a",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    cycle_b = Cycle(
        cycle_id="cycle-project-b",
        tenant_id="tenant-1",
        tenant_scope="tenant-1",
        project_id="project-b",
        owner_user_id="user-1",
        current_state=CycleState.HUMAN_APPROVAL_PENDING,
        user_status=UserStatus.APPROVAL_REQUIRED,
        idempotency_key="idem-cycle-project-b",
        request_fingerprint="fp-cycle-project-b",
        active_approval_id="approval-project-b",
    )
    db_session.add(cycle_b)
    db_session.add(Approval(
        approval_id="approval-project-b",
        cycle_id="cycle-project-b",
        approval_state=ApprovalState.PENDING,
        required_role="reviewer",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
    ))
    db_session.commit()

    response = client.get(
        "/v1/approvals/pending?project_id=project-1",
        headers={"X-User-Id": "user-1", "X-User-Role": "operator", "X-Tenant-Id": "tenant-1"},
    )

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert [item["approval_id"] for item in items] == ["approval-project-a"]
