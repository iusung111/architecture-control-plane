from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Approval, Cycle
from app.domain.enums import ApprovalState


class ApprovalRepository:
    def __init__(self, db: Session):
        self._db = db

    def get_by_id(self, approval_id: str) -> Approval | None:
        return self._db.get(Approval, approval_id)

    def get_by_id_for_update(self, approval_id: str) -> Approval | None:
        stmt = select(Approval).where(Approval.approval_id == approval_id).with_for_update()
        return self._db.execute(stmt).scalar_one_or_none()

    def apply_decision(
        self,
        approval: Approval,
        decision: str,
        actor_id: str,
        comment: str | None,
        reason_code: str | None,
    ) -> None:
        approval.approval_state = ApprovalState.APPROVED if decision == "approved" else ApprovalState.REJECTED
        approval.actor_id = actor_id
        approval.comment = comment
        approval.reason_code = reason_code
        approval.acted_at = datetime.now(timezone.utc)
        approval.version += 1


    def list_pending_for_actor(
        self,
        *,
        actor_id: str,
        actor_role: str,
        actor_tenant_id: str | None,
        project_id: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        stmt = (
            select(Approval, Cycle)
            .join(Cycle, Cycle.cycle_id == Approval.cycle_id)
            .where(Approval.approval_state == ApprovalState.PENDING)
            .where(Approval.required_role == actor_role)
            .where(Cycle.owner_user_id == actor_id)
            .order_by(Approval.expires_at.asc(), Approval.created_at.asc())
            .limit(limit)
        )
        if actor_tenant_id is not None:
            stmt = stmt.where(Cycle.tenant_id == actor_tenant_id)
        if project_id:
            stmt = stmt.where(Cycle.project_id == project_id)
        rows = self._db.execute(stmt).all()
        return [
            {
                "approval_id": approval.approval_id,
                "cycle_id": approval.cycle_id,
                "project_id": cycle.project_id,
                "required_role": approval.required_role,
                "approval_state": approval.approval_state,
                "cycle_state": cycle.current_state,
                "user_status": cycle.user_status,
                "expires_at": approval.expires_at,
                "created_at": approval.created_at,
            }
            for approval, cycle in rows
        ]
