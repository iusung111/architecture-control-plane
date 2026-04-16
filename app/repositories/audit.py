from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditEvent


class AuditEventRepository:
    def __init__(self, db: Session):
        self._db = db

    def get_by_id(self, audit_event_id: str) -> AuditEvent | None:
        return self._db.get(AuditEvent, audit_event_id)

    def add(
        self,
        *,
        event_type: str,
        cycle_id: str | None = None,
        approval_id: str | None = None,
        actor_id: str | None = None,
        event_payload: dict | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            audit_event_id=uuid4().hex,
            cycle_id=cycle_id,
            approval_id=approval_id,
            actor_id=actor_id,
            event_type=event_type,
            event_payload=event_payload or {},
        )
        self._db.add(event)
        self._db.flush()
        return event

    def list_recent(self, *, event_type_prefix: str | None = None, limit: int = 100) -> list[AuditEvent]:
        stmt = select(AuditEvent).order_by(AuditEvent.occurred_at.desc())
        if event_type_prefix:
            stmt = stmt.where(AuditEvent.event_type.like(f"{event_type_prefix}%"))
        stmt = stmt.limit(limit)
        return list(self._db.scalars(stmt))

    def list_by_event_type(
        self,
        *,
        event_type: str,
        actor_id: str | None = None,
        cycle_id: str | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        stmt = select(AuditEvent).where(AuditEvent.event_type == event_type)
        if actor_id is not None:
            stmt = stmt.where(AuditEvent.actor_id == actor_id)
        if cycle_id is not None:
            stmt = stmt.where(AuditEvent.cycle_id == cycle_id)
        stmt = stmt.order_by(AuditEvent.occurred_at.desc(), AuditEvent.audit_event_id.desc()).limit(limit)
        return list(self._db.scalars(stmt))
