from __future__ import annotations

from .runtime_helpers import _payload_visible_for_tenant
from .timeline import _coerce_utc
from app.core.auth import AuthContext
from app.db.models import AuditEvent
from app.repositories.audit import AuditEventRepository
from typing import Any


def _workspace_discussion_saved_filter_from_audit(event: AuditEvent) -> dict[str, Any]:
    payload = event.event_payload if isinstance(event.event_payload, dict) else {}
    occurred_at = event.occurred_at
    return {
        "filter_id": event.audit_event_id,
        "name": str(payload.get("name") or ""),
        "project_id": payload.get("project_id"),
        "mention": payload.get("mention"),
        "query": payload.get("query"),
        "actor_id": event.actor_id,
        "occurred_at": occurred_at,
        "updated_at": occurred_at,
        "last_used_at": None,
        "is_favorite": False,
        "is_deleted": False,
    }


def _workspace_discussion_saved_filter_state_from_audit(event: AuditEvent) -> dict[str, Any]:
    payload = event.event_payload if isinstance(event.event_payload, dict) else {}
    return {
        "filter_id": str(payload.get("filter_id") or ""),
        "name": str(payload.get("name") or "").strip() or None,
        "project_id": payload.get("project_id"),
        "mention": payload.get("mention"),
        "query": payload.get("query"),
        "is_favorite": payload.get("is_favorite") if "is_favorite" in payload else None,
        "is_deleted": payload.get("is_deleted") if "is_deleted" in payload else None,
        "last_used_at": event.occurred_at
        if event.event_type == "workspace.comment.filter.used"
        else None,
        "actor_id": event.actor_id,
        "occurred_at": event.occurred_at,
        "event_type": event.event_type,
    }


def _merge_workspace_discussion_saved_filter_updates(
    base: dict[str, Any], updates: list[AuditEvent]
) -> dict[str, Any]:
    merged = dict(base)
    ordered = sorted(
        (
            _workspace_discussion_saved_filter_state_from_audit(event)
            for event in updates
            if str((event.event_payload or {}).get("filter_id") or "") == base.get("filter_id")
        ),
        key=lambda row: (
            _coerce_utc(row.get("occurred_at") or merged.get("occurred_at")),
            row.get("event_type") or "",
        ),
    )
    for row in ordered:
        if row.get("name"):
            merged["name"] = row["name"]
        if "project_id" in row:
            merged["project_id"] = row.get("project_id")
        if "mention" in row:
            merged["mention"] = row.get("mention")
        if "query" in row:
            merged["query"] = row.get("query")
        if row.get("is_favorite") is not None:
            merged["is_favorite"] = bool(row["is_favorite"])
        if row.get("is_deleted") is not None:
            merged["is_deleted"] = bool(row["is_deleted"])
        if row.get("last_used_at") is not None:
            merged["last_used_at"] = row["last_used_at"]
        occurred_at = row.get("occurred_at")
        if occurred_at is not None:
            merged["updated_at"] = occurred_at
    return merged


def _ensure_workspace_discussion_saved_filter_event(
    audit_repo: AuditEventRepository, *, filter_id: str, auth: AuthContext
) -> AuditEvent:
    event = audit_repo.get_by_id(filter_id)
    if event is None or event.event_type != "workspace.comment.filter.saved":
        raise ValueError("saved filter not found")
    if event.actor_id != auth.user_id:
        raise PermissionError("forbidden")
    payload = event.event_payload if isinstance(event.event_payload, dict) else {}
    if not _payload_visible_for_tenant(payload, auth):
        raise PermissionError("forbidden")
    return event


def _build_workspace_discussion_saved_filter_view(
    audit_repo: AuditEventRepository, *, auth: AuthContext, filter_id: str
) -> dict[str, Any] | None:
    try:
        base_event = _ensure_workspace_discussion_saved_filter_event(
            audit_repo, filter_id=filter_id, auth=auth
        )
    except (ValueError, PermissionError):
        return None
    base = _workspace_discussion_saved_filter_from_audit(base_event)
    updates = []
    for event in audit_repo.list_recent(event_type_prefix="workspace.comment.filter.", limit=400):
        if event.event_type == "workspace.comment.filter.saved":
            continue
        if event.actor_id != auth.user_id:
            continue
        payload = event.event_payload if isinstance(event.event_payload, dict) else {}
        if str(payload.get("filter_id") or "") != filter_id:
            continue
        if not _payload_visible_for_tenant(payload, auth):
            continue
        updates.append(event)
    return _merge_workspace_discussion_saved_filter_updates(base, updates)
