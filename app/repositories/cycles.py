from datetime import datetime, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.db.models import Approval, Artifact, AuditEvent, Cycle, CycleIteration, Job, NotificationOutbox, Receipt, VerificationResult
from app.domain.enums import CycleState


class CycleRepository:
    def __init__(self, db: Session):
        self._db = db

    def get_by_id(self, cycle_id: str) -> Cycle | None:
        return self._db.get(Cycle, cycle_id)

    def get_by_id_for_update(self, cycle_id: str) -> Cycle | None:
        stmt = select(Cycle).where(Cycle.cycle_id == cycle_id).with_for_update()
        return self._db.execute(stmt).scalar_one_or_none()

    def get_by_idempotency(self, owner_user_id: str, tenant_scope: str, project_id: str, idempotency_key: str) -> Cycle | None:
        stmt = select(Cycle).where(
            Cycle.owner_user_id == owner_user_id,
            Cycle.tenant_scope == tenant_scope,
            Cycle.project_id == project_id,
            Cycle.idempotency_key == idempotency_key,
        )
        return self._db.execute(stmt).scalar_one_or_none()

    def add(self, cycle: Cycle) -> None:
        self._db.add(cycle)

    def list_for_owner(
        self,
        *,
        owner_user_id: str,
        tenant_id: str | None,
        project_id: str | None,
        state: str | None,
        user_status: str | None,
        created_after: datetime | None,
        created_before: datetime | None,
        updated_after: datetime | None,
        updated_before: datetime | None,
        cursor_updated_at: datetime | None,
        cursor_cycle_id: str | None,
        limit: int,
    ) -> list[Cycle]:
        predicates = [Cycle.owner_user_id == owner_user_id]
        if tenant_id is not None:
            predicates.append(Cycle.tenant_id == tenant_id)
        if project_id is not None:
            predicates.append(Cycle.project_id == project_id)
        if state is not None:
            predicates.append(Cycle.current_state == state)
        if user_status is not None:
            predicates.append(Cycle.user_status == user_status)
        if created_after is not None:
            predicates.append(Cycle.created_at >= created_after)
        if created_before is not None:
            predicates.append(Cycle.created_at <= created_before)
        if updated_after is not None:
            predicates.append(Cycle.updated_at >= updated_after)
        if updated_before is not None:
            predicates.append(Cycle.updated_at <= updated_before)
        if cursor_updated_at is not None and cursor_cycle_id is not None:
            predicates.append(
                or_(
                    Cycle.updated_at < cursor_updated_at,
                    and_(Cycle.updated_at == cursor_updated_at, Cycle.cycle_id < cursor_cycle_id),
                )
            )
        stmt = (
            select(Cycle)
            .where(*predicates)
            .order_by(Cycle.updated_at.desc(), Cycle.cycle_id.desc())
            .limit(limit)
        )
        return self._db.execute(stmt).scalars().all()


    def list_comments_for_cycle(self, cycle_id: str, *, limit: int = 50) -> list[AuditEvent]:
        stmt = (
            select(AuditEvent)
            .where(AuditEvent.cycle_id == cycle_id, AuditEvent.event_type == "cycle.comment.added")
            .order_by(AuditEvent.occurred_at.desc(), AuditEvent.audit_event_id.desc())
            .limit(min(max(limit, 1), 200))
        )
        return self._db.execute(stmt).scalars().all()

    def list_recent_comments_for_owner(
        self,
        *,
        owner_user_id: str,
        tenant_id: str | None,
        project_id: str | None,
        limit: int = 20,
    ) -> list[AuditEvent]:
        stmt = (
            select(AuditEvent)
            .join(Cycle, Cycle.cycle_id == AuditEvent.cycle_id)
            .where(Cycle.owner_user_id == owner_user_id, AuditEvent.event_type == "cycle.comment.added")
            .order_by(AuditEvent.occurred_at.desc(), AuditEvent.audit_event_id.desc())
            .limit(min(max(limit, 1), 100))
        )
        if tenant_id is not None:
            stmt = stmt.where(Cycle.tenant_id == tenant_id)
        if project_id is not None:
            stmt = stmt.where(Cycle.project_id == project_id)
        return self._db.execute(stmt).scalars().all()

    def list_jobs_for_owner(
        self,
        *,
        owner_user_id: str,
        tenant_id: str | None,
        project_id: str | None,
        limit: int = 50,
    ) -> list[Job]:
        stmt = (
            select(Job)
            .join(Cycle, Cycle.cycle_id == Job.cycle_id)
            .where(Cycle.owner_user_id == owner_user_id)
            .order_by(Job.updated_at.desc(), Job.created_at.desc())
            .limit(min(max(limit, 1), 200))
        )
        if tenant_id is not None:
            stmt = stmt.where(Cycle.tenant_id == tenant_id)
        if project_id is not None:
            stmt = stmt.where(Cycle.project_id == project_id)
        return self._db.execute(stmt).scalars().all()

    def count_pending_approvals_for_owner(self, *, owner_user_id: str, tenant_id: str | None, project_id: str | None) -> int:
        stmt = select(func.count(Approval.approval_id)).join(Cycle, Cycle.cycle_id == Approval.cycle_id).where(
            Cycle.owner_user_id == owner_user_id,
            Approval.approval_state == "pending",
        )
        if tenant_id is not None:
            stmt = stmt.where(Cycle.tenant_id == tenant_id)
        if project_id is not None:
            stmt = stmt.where(Cycle.project_id == project_id)
        return int(self._db.scalar(stmt) or 0)

    def count_outbox_by_state_for_owner(self, *, owner_user_id: str, tenant_id: str | None, project_id: str | None) -> dict[str, int]:
        stmt = (
            select(NotificationOutbox.delivery_state, func.count(NotificationOutbox.outbox_id))
            .join(Cycle, Cycle.cycle_id == NotificationOutbox.cycle_id)
            .where(Cycle.owner_user_id == owner_user_id)
            .group_by(NotificationOutbox.delivery_state)
        )
        if tenant_id is not None:
            stmt = stmt.where(Cycle.tenant_id == tenant_id)
        if project_id is not None:
            stmt = stmt.where(Cycle.project_id == project_id)
        return {str(state): int(count) for state, count in self._db.execute(stmt).all()}

    def update_state(self, cycle: Cycle, next_state: str, user_status: str) -> None:
        cycle.current_state = next_state
        cycle.user_status = user_status
        if next_state in {CycleState.TERMINALIZED, CycleState.TERMINAL_FAIL} and cycle.terminalized_at is None:
            cycle.terminalized_at = datetime.now(timezone.utc)
        cycle.version += 1

    def set_active_approval(self, cycle: Cycle, approval_id: str | None) -> None:
        cycle.active_approval_id = approval_id
        cycle.version += 1

    def get_result_bundle(self, cycle_id: str) -> dict | None:
        cycle = self.get_by_id(cycle_id)
        if not cycle:
            return None
        artifacts = self._db.execute(select(Artifact).where(Artifact.cycle_id == cycle_id)).scalars().all()
        verification = self._db.execute(
            select(VerificationResult).where(VerificationResult.cycle_id == cycle_id).order_by(VerificationResult.created_at.desc())
        ).scalars().first()
        approval = self._db.execute(
            select(Approval).where(Approval.cycle_id == cycle_id).order_by(Approval.created_at.desc())
        ).scalars().first()
        receipt = self._db.execute(
            select(Receipt)
            .where(Receipt.cycle_id == cycle_id, Receipt.receipt_type.in_(["completion_summary", "verification_failure"]))
            .order_by(Receipt.created_at.desc())
        ).scalars().first()
        if receipt is None:
            receipt = self._db.execute(
                select(Receipt)
                .where(Receipt.cycle_id == cycle_id, Receipt.receipt_type != "request_snapshot")
                .order_by(Receipt.created_at.desc())
            ).scalars().first()
        return {
            "cycle": cycle,
            "artifacts": artifacts,
            "verification": verification,
            "approval": approval,
            "receipt": receipt,
        }

    def get_timeline_bundle(self, cycle_id: str, *, limit: int = 50) -> dict | None:
        cycle = self.get_by_id(cycle_id)
        if not cycle:
            return None
        limited = min(max(limit, 1), 200)
        return {
            "cycle": cycle,
            "audit_events": self._db.execute(
                select(AuditEvent).where(AuditEvent.cycle_id == cycle_id).order_by(AuditEvent.occurred_at.desc()).limit(limited)
            ).scalars().all(),
            "jobs": self._db.execute(
                select(Job).where(Job.cycle_id == cycle_id).order_by(Job.updated_at.desc(), Job.created_at.desc()).limit(limited)
            ).scalars().all(),
            "approvals": self._db.execute(
                select(Approval).where(Approval.cycle_id == cycle_id).order_by(Approval.updated_at.desc(), Approval.created_at.desc()).limit(limited)
            ).scalars().all(),
            "receipts": self._db.execute(
                select(Receipt).where(Receipt.cycle_id == cycle_id).order_by(Receipt.created_at.desc()).limit(limited)
            ).scalars().all(),
            "iterations": self._db.execute(
                select(CycleIteration).where(CycleIteration.cycle_id == cycle_id).order_by(CycleIteration.created_at.desc()).limit(limited)
            ).scalars().all(),
        }
