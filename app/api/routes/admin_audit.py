from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_audit_event_repository, get_request_id, require_management_operator
from app.repositories.audit import AuditEventRepository
from app.schemas.admin_audit import AuditEventListEnvelope, AuditEventListResponse, AuditEventResponse
from app.schemas.common import ErrorEnvelope, envelope_ok

router = APIRouter(prefix="/admin/audit", tags=["admin-audit"], dependencies=[Depends(require_management_operator)])


@router.get(
    "/events",
    response_model=AuditEventListEnvelope,
    responses={403: {"model": ErrorEnvelope}},
)
def list_audit_events(
    request_id: str = Depends(get_request_id),
    audit_repo: AuditEventRepository = Depends(get_audit_event_repository),
    event_type_prefix: str | None = "management.",
    limit: int = 100,
):
    events = [
        AuditEventResponse(
            audit_event_id=item.audit_event_id,
            cycle_id=item.cycle_id,
            approval_id=item.approval_id,
            actor_id=item.actor_id,
            event_type=item.event_type,
            event_payload=item.event_payload,
            occurred_at=item.occurred_at.isoformat() if item.occurred_at else "",
        )
        for item in audit_repo.list_recent(event_type_prefix=event_type_prefix, limit=min(max(limit, 1), 200))
    ]
    return envelope_ok(data=AuditEventListResponse(events=events), request_id=request_id)
