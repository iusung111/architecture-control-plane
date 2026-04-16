from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.auth import AuthContext
from app.core.config import Settings
from app.repositories.audit import AuditEventRepository
from app.services.unit_of_work import SqlAlchemyUnitOfWork

from .types import EXECUTION_ACTIVE_STATES


def _coerce_utc(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, str) and value:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    return datetime.now(UTC)


def event_order_timestamp(payload: dict[str, Any], occurred_at: datetime | str | None = None) -> datetime:
    return _coerce_utc(
        payload.get("last_updated_at")
        or payload.get("completed_at")
        or payload.get("requested_at")
        or payload.get("updated_at")
        or payload.get("last_resumed_at")
        or payload.get("created_at")
        or occurred_at
    )


def payload_visible_for_tenant(payload: dict[str, Any], auth: AuthContext) -> bool:
    tenant_id = payload.get("tenant_id")
    return auth.tenant_id is None or tenant_id == auth.tenant_id


def ensure_list_of_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def merge_patch_stack(patch: str | None, existing: Any, incoming: Any = None) -> list[str]:
    items: list[str] = []
    for candidate in (existing, incoming):
        for value in ensure_list_of_strings(candidate):
            if value not in items:
                items.append(value)
    if patch and patch not in items:
        items.insert(0, patch)
    return items[:10]


def latest_cycle_assignment(audit_repo: AuditEventRepository, cycle_id: str | None) -> dict[str, Any] | None:
    if not cycle_id:
        return None
    events = audit_repo.list_by_event_type(event_type="cycle.assignment.updated", cycle_id=cycle_id, limit=10)
    if not events:
        return None

    event = events[0]
    payload = event.event_payload if isinstance(event.event_payload, dict) else {}
    agent_id = str(payload.get("agent_id") or "")
    if not agent_id:
        return None

    return {
        "agent_id": agent_id,
        "assignment_role": str(payload.get("assignment_role") or "primary"),
        "occurred_at": event.occurred_at.isoformat(),
    }


def merge_artifact_history(current: Any, incoming: Any) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for source in (current, incoming):
        if not isinstance(source, list):
            continue
        for item in source:
            if not isinstance(item, dict):
                continue
            key = (str(item.get("artifact_id") or ""), str(item.get("uri") or ""))
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
    return merged[:20]


def workspace_has_active_execution(audit_repo: AuditEventRepository, workspace_id: str) -> bool:
    latest: dict[str, str] = {}
    events = audit_repo.list_recent(event_type_prefix="remote.workspace.execution.", limit=2000)
    ordered = sorted(
        events,
        key=lambda item: event_order_timestamp(item.event_payload if isinstance(item.event_payload, dict) else {}, item.occurred_at),
    )
    for event in ordered:
        payload = event.event_payload if isinstance(event.event_payload, dict) else {}
        if str(payload.get("workspace_id") or "") != workspace_id:
            continue
        execution_id = str(payload.get("execution_id") or "")
        if not execution_id:
            continue
        latest[execution_id] = str(payload.get("status") or latest.get(execution_id) or "")
    return any(status in EXECUTION_ACTIVE_STATES for status in latest.values())


def append_persistent_session_event(
    *,
    audit_repo: AuditEventRepository,
    uow: SqlAlchemyUnitOfWork,
    settings: Settings,
    workspace_id: str,
    actor_id: str | None,
    tenant_id: str | None,
    status: str,
    note: str | None = None,
) -> dict[str, Any] | None:
    from .persistent import persistent_session_from_payload

    current: dict[str, Any] | None = None
    events = audit_repo.list_recent(event_type_prefix="remote.workspace.persistent.", limit=600)
    ordered = sorted(
        events,
        key=lambda item: event_order_timestamp(item.event_payload if isinstance(item.event_payload, dict) else {}, item.occurred_at),
    )
    for event in ordered:
        payload = event.event_payload if isinstance(event.event_payload, dict) else {}
        if str(payload.get("workspace_id") or "") != workspace_id:
            continue
        current = payload
    if current is None:
        return None

    now = datetime.now(UTC)
    ttl_hours = int(current.get("ttl_hours") or settings.remote_workspace_persistent_ttl_hours)
    event_payload = {
        **current,
        "workspace_id": workspace_id,
        "status": status,
        "note": note if note is not None else current.get("note"),
        "updated_at": now.isoformat(),
        "last_resumed_at": now.isoformat() if status in {"active", "resumed", "busy"} else current.get("last_resumed_at"),
        "expires_at": (now + timedelta(hours=ttl_hours)).isoformat(),
        "tenant_id": tenant_id if tenant_id is not None else current.get("tenant_id"),
        "actor_id": current.get("actor_id") if actor_id == "remote-workspace-callback" else (actor_id if actor_id is not None else current.get("actor_id")),
    }
    with uow:
        audit_repo.add(
            event_type="remote.workspace.persistent.session.saved",
            actor_id=actor_id,
            cycle_id=current.get("cycle_id"),
            event_payload=event_payload,
        )
        uow.commit()
    return persistent_session_from_payload(event_payload)
