from datetime import datetime, timezone

from app.domain.enums import ApprovalState, CycleState, JobType, UserStatus
from app.repositories.approvals import ApprovalRepository
from app.repositories.audit import AuditEventRepository
from app.repositories.cycles import CycleRepository
from app.repositories.jobs import JobRepository
from app.repositories.outbox import OutboxRepository
from app.services.unit_of_work import SqlAlchemyUnitOfWork


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class ApprovalNotFoundError(ValueError):
    pass


class ApprovalExpiredError(ValueError):
    pass


class ApprovalConflictError(ValueError):
    pass


class ApprovalService:
    @staticmethod
    def _ensure_access(*, owner_user_id: str, cycle_tenant_id: str | None, actor_id: str, actor_tenant_id: str | None) -> None:
        if owner_user_id != actor_id:
            raise PermissionError("forbidden")
        if actor_tenant_id is not None and cycle_tenant_id != actor_tenant_id:
            raise PermissionError("forbidden")

    def __init__(
        self,
        approval_repo: ApprovalRepository,
        cycle_repo: CycleRepository,
        job_repo: JobRepository,
        outbox_repo: OutboxRepository,
        audit_repo: AuditEventRepository,
        uow: SqlAlchemyUnitOfWork,
    ):
        self._approval_repo = approval_repo
        self._cycle_repo = cycle_repo
        self._job_repo = job_repo
        self._outbox_repo = outbox_repo
        self._audit_repo = audit_repo
        self._uow = uow

    def _record_audit_event(
        self,
        *,
        event_type: str,
        actor_id: str | None,
        cycle_id: str | None = None,
        approval_id: str | None = None,
        payload: dict | None = None,
    ) -> None:
        self._audit_repo.add(
            event_type=event_type,
            cycle_id=cycle_id,
            approval_id=approval_id,
            actor_id=actor_id,
            event_payload=payload or {},
        )

    def confirm(
        self,
        approval_id: str,
        decision: str,
        actor_id: str,
        actor_role: str,
        actor_tenant_id: str | None,
        comment: str | None,
        reason_code: str | None,
        idempotency_key: str,
    ) -> dict:
        with self._uow:
            approval = self._approval_repo.get_by_id_for_update(approval_id)
            if not approval:
                raise ApprovalNotFoundError("approval not found")
            if approval.required_role != actor_role:
                raise ApprovalConflictError("actor role does not satisfy approval requirement")

            cycle = self._cycle_repo.get_by_id_for_update(approval.cycle_id)
            if not cycle:
                raise ApprovalConflictError("linked cycle not found")

            self._ensure_access(
                owner_user_id=cycle.owner_user_id,
                cycle_tenant_id=cycle.tenant_id,
                actor_id=actor_id,
                actor_tenant_id=actor_tenant_id,
            )

            if approval.approval_state != ApprovalState.PENDING:
                if approval.approval_state == ApprovalState.APPROVED and decision == "approved":
                    return {
                        "approval_id": approval.approval_id,
                        "decision": decision,
                        "approval_state": approval.approval_state,
                        "cycle_id": approval.cycle_id,
                        "resume_enqueued": True,
                        "acted_at": approval.acted_at,
                    }
                if approval.approval_state == ApprovalState.REJECTED and decision == "rejected":
                    return {
                        "approval_id": approval.approval_id,
                        "decision": decision,
                        "approval_state": approval.approval_state,
                        "cycle_id": approval.cycle_id,
                        "resume_enqueued": False,
                        "acted_at": approval.acted_at,
                    }
                raise ApprovalConflictError(f"approval already decided: {approval.approval_state}")

            if _as_utc(approval.expires_at) < datetime.now(timezone.utc):
                approval.approval_state = ApprovalState.EXPIRED
                approval.acted_at = datetime.now(timezone.utc)
                if cycle.active_approval_id == approval.approval_id:
                    self._cycle_repo.set_active_approval(cycle, None)
                self._record_audit_event(
                    event_type="approval.expired",
                    actor_id=actor_id,
                    cycle_id=approval.cycle_id,
                    approval_id=approval.approval_id,
                    payload={
                        "attempted_decision": decision,
                        "idempotency_key": idempotency_key,
                        "expired_at": approval.expires_at.isoformat(),
                    },
                )
                self._uow.commit()
                raise ApprovalExpiredError("approval expired")

            previous_cycle_state = cycle.current_state
            self._approval_repo.apply_decision(approval, decision, actor_id, comment, reason_code)
            if cycle.active_approval_id == approval.approval_id:
                self._cycle_repo.set_active_approval(cycle, None)
            resume_enqueued = False
            if decision == "approved":
                self._job_repo.enqueue(
                    cycle_id=approval.cycle_id,
                    job_type=JobType.RESUME_AFTER_APPROVAL,
                    payload={
                        "approval_id": approval_id,
                        "cycle_id": approval.cycle_id,
                        "requested_by": actor_id,
                    },
                    dedup_key=f"resume_after_approval:{approval_id}:{idempotency_key}",
                )
                self._outbox_repo.add(
                    approval.cycle_id,
                    "approval.approved",
                    {"approval_id": approval_id, "cycle_id": approval.cycle_id},
                )
                self._record_audit_event(
                    event_type="approval.approved",
                    actor_id=actor_id,
                    cycle_id=approval.cycle_id,
                    approval_id=approval_id,
                    payload={
                        "comment": comment,
                        "reason_code": reason_code,
                        "resume_enqueued": True,
                        "idempotency_key": idempotency_key,
                    },
                )
                resume_enqueued = True
            else:
                self._cycle_repo.update_state(
                    cycle,
                    next_state=CycleState.TERMINAL_FAIL,
                    user_status=UserStatus.FAILED,
                )
                self._outbox_repo.add(
                    approval.cycle_id,
                    "approval.rejected",
                    {"approval_id": approval_id, "cycle_id": approval.cycle_id},
                )
                self._record_audit_event(
                    event_type="approval.rejected",
                    actor_id=actor_id,
                    cycle_id=approval.cycle_id,
                    approval_id=approval_id,
                    payload={
                        "comment": comment,
                        "reason_code": reason_code,
                        "idempotency_key": idempotency_key,
                    },
                )
                self._record_audit_event(
                    event_type="cycle.terminalized",
                    actor_id=actor_id,
                    cycle_id=approval.cycle_id,
                    approval_id=approval_id,
                    payload={
                        "from_state": previous_cycle_state,
                        "to_state": cycle.current_state,
                        "terminalized_at": cycle.terminalized_at.isoformat() if cycle.terminalized_at else None,
                    },
                )
            self._uow.commit()

            return {
                "approval_id": approval.approval_id,
                "decision": decision,
                "approval_state": approval.approval_state,
                "cycle_id": approval.cycle_id,
                "resume_enqueued": resume_enqueued,
                "acted_at": approval.acted_at,
            }


    def list_pending(
        self,
        *,
        actor_id: str,
        actor_role: str,
        actor_tenant_id: str | None,
        project_id: str | None = None,
        limit: int = 20,
    ) -> dict:
        items = self._approval_repo.list_pending_for_actor(
            actor_id=actor_id,
            actor_role=actor_role,
            actor_tenant_id=actor_tenant_id,
            project_id=project_id,
            limit=limit,
        )
        return {"items": items}
