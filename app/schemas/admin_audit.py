from __future__ import annotations

from pydantic import BaseModel

from app.schemas.common import OkEnvelope


class AuditEventResponse(BaseModel):
    audit_event_id: str
    cycle_id: str | None = None
    approval_id: str | None = None
    actor_id: str | None = None
    event_type: str
    event_payload: dict
    occurred_at: str


class AuditEventListResponse(BaseModel):
    events: list[AuditEventResponse]


AuditEventListEnvelope = OkEnvelope[AuditEventListResponse]
