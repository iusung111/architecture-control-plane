from __future__ import annotations

from .timeline import _coerce_utc
from .workspace_discussions import _payload_visible_for_tenant
from app.core.auth import AuthContext
from app.db.models import AuditEvent
from app.repositories.audit import AuditEventRepository
from datetime import datetime
from typing import Any


def _get_latest_runtime_registration_event(
    audit_repo: AuditEventRepository, *, auth: AuthContext, runtime_id: str, limit: int = 200
) -> AuditEvent | None:
    events = audit_repo.list_by_event_type(
        event_type="runtime.registration.heartbeat",
        actor_id=auth.user_id,
        limit=max(limit, 1),
    )
    latest: AuditEvent | None = None
    latest_seen: datetime | None = None
    for event in events:
        payload = event.event_payload if isinstance(event.event_payload, dict) else {}
        if str(payload.get("runtime_id") or "") != runtime_id:
            continue
        if not _payload_visible_for_tenant(payload, auth):
            continue
        seen = _coerce_utc(_runtime_registration_from_audit(event)["occurred_at"])
        if latest is None or latest_seen is None or seen >= latest_seen:
            latest = event
            latest_seen = seen
    return latest


def _runtime_registration_from_audit(event: AuditEvent) -> dict[str, Any]:
    payload = event.event_payload if isinstance(event.event_payload, dict) else {}
    observed_at = event.occurred_at
    heartbeat_at = payload.get("heartbeat_at")
    if isinstance(heartbeat_at, str):
        try:
            observed_at = datetime.fromisoformat(heartbeat_at)
        except ValueError:
            observed_at = event.occurred_at
    return {
        "runtime_id": str(payload.get("runtime_id") or ""),
        "workspace_id": payload.get("workspace_id"),
        "project_id": payload.get("project_id"),
        "label": str(payload.get("label") or payload.get("runtime_id") or "runtime"),
        "status": str(payload.get("status") or "unknown"),
        "mode": str(payload.get("mode") or "daemon"),
        "version": payload.get("version"),
        "capabilities": [str(item) for item in payload.get("capabilities", []) if str(item)],
        "actor_id": event.actor_id,
        "occurred_at": observed_at,
        "metadata": payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
    }
