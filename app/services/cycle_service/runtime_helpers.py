from __future__ import annotations

from .timeline import _coerce_utc
from app.core.auth import AuthContext
from app.db.models import AuditEvent
from app.repositories.audit import AuditEventRepository
from datetime import datetime
from typing import Any


def _runtime_action_receipt_from_audit(event: AuditEvent) -> dict[str, Any]:
    payload = event.event_payload if isinstance(event.event_payload, dict) else {}
    return {
        "receipt_id": event.audit_event_id,
        "action_id": str(payload.get("action_id") or ""),
        "runtime_id": str(payload.get("runtime_id") or ""),
        "project_id": payload.get("project_id"),
        "workspace_id": payload.get("workspace_id"),
        "summary": str(payload.get("summary") or ""),
        "status": payload.get("status"),
        "actor_id": event.actor_id,
        "actor_role": payload.get("actor_role"),
        "occurred_at": event.occurred_at,
        "metadata": payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
    }


def _cycle_assignment_from_audit(event: AuditEvent) -> dict[str, Any]:
    payload = event.event_payload if isinstance(event.event_payload, dict) else {}
    return {
        "assignment_id": event.audit_event_id,
        "cycle_id": event.cycle_id,
        "agent_id": str(payload.get("agent_id") or ""),
        "assignment_role": str(payload.get("assignment_role") or "primary"),
        "note": payload.get("note"),
        "actor_id": event.actor_id,
        "actor_role": payload.get("actor_role"),
        "occurred_at": event.occurred_at,
    }


def _runtime_action_from_audit(event: AuditEvent) -> dict[str, Any]:
    payload = event.event_payload if isinstance(event.event_payload, dict) else {}
    occurred_at = event.occurred_at
    acknowledged_at = payload.get("acknowledged_at")
    if isinstance(acknowledged_at, str):
        try:
            acknowledged_at = datetime.fromisoformat(acknowledged_at)
        except ValueError:
            acknowledged_at = None
    else:
        acknowledged_at = None
    last_updated_at = payload.get("last_updated_at")
    if isinstance(last_updated_at, str):
        try:
            last_updated_at = datetime.fromisoformat(last_updated_at)
        except ValueError:
            last_updated_at = occurred_at
    else:
        last_updated_at = occurred_at
    return {
        "action_id": str(payload.get("action_id") or event.audit_event_id),
        "runtime_id": str(payload.get("runtime_id") or ""),
        "project_id": payload.get("project_id"),
        "workspace_id": payload.get("workspace_id"),
        "action": str(payload.get("action") or ""),
        "status": str(payload.get("status") or "queued"),
        "actor_id": event.actor_id,
        "actor_role": payload.get("actor_role"),
        "occurred_at": occurred_at,
        "arguments": payload.get("arguments") if isinstance(payload.get("arguments"), dict) else {},
        "note": payload.get("note"),
        "metadata": payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
        "acknowledged_at": acknowledged_at,
        "acknowledged_by": payload.get("acknowledged_by"),
        "last_updated_at": last_updated_at,
    }


def _normalize_mention(value: str | None) -> str:
    return (value or "").strip().lower()


def _mention_matches(payload: dict[str, Any], mention: str | None) -> bool:
    normalized = _normalize_mention(mention)
    if not normalized:
        return True
    mentions = {
        _normalize_mention(str(item)) for item in payload.get("mentions", []) if str(item).strip()
    }
    return normalized in mentions


def _workspace_discussion_matches_query(payload: dict[str, Any], query: str | None) -> bool:
    normalized = (query or "").strip().lower()
    if not normalized:
        return True
    haystacks = [
        str(payload.get("body") or ""),
        str(payload.get("project_id") or ""),
        str(payload.get("actor_id") or ""),
        str(payload.get("actor_role") or ""),
        " ".join(str(item) for item in payload.get("mentions", []) if str(item)),
    ]
    return any(normalized in item.lower() for item in haystacks if item)


def _payload_visible_for_tenant(payload: dict[str, Any], auth: AuthContext) -> bool:
    return auth.tenant_id is None or payload.get("tenant_id") in {auth.tenant_id, None}


def _get_runtime_action_event(
    audit_repo: AuditEventRepository,
    *,
    auth: AuthContext,
    runtime_id: str,
    action_id: str,
    limit: int = 400,
) -> AuditEvent | None:
    events = audit_repo.list_by_event_type(
        event_type="runtime.action.enqueued",
        actor_id=auth.user_id,
        limit=max(limit, 1),
    )
    for event in events:
        payload = event.event_payload if isinstance(event.event_payload, dict) else {}
        if str(payload.get("runtime_id") or "") != runtime_id:
            continue
        if event.audit_event_id != action_id:
            continue
        if not _payload_visible_for_tenant(payload, auth):
            continue
        return event
    return None


def _merge_runtime_action_updates(
    base: dict[str, Any], updates: list[AuditEvent]
) -> dict[str, Any]:
    merged = dict(base)
    merged.setdefault("metadata", {})
    merged.setdefault("arguments", {})
    ordered_rows = sorted(
        (_runtime_action_from_audit(event) for event in updates),
        key=lambda row: (
            _coerce_utc(row.get("last_updated_at") or row.get("occurred_at")),
            row["action_id"],
            row.get("status") or "",
        ),
    )
    for row in ordered_rows:
        if row.get("status"):
            merged["status"] = row["status"]
        if row.get("actor_id") is not None:
            merged["actor_id"] = row["actor_id"]
        if row.get("actor_role") is not None:
            merged["actor_role"] = row["actor_role"]
        if row.get("note") is not None:
            merged["note"] = row["note"]
        if row.get("metadata"):
            merged["metadata"] = {**dict(merged.get("metadata") or {}), **dict(row["metadata"])}
        if row.get("acknowledged_at") is not None:
            merged["acknowledged_at"] = row["acknowledged_at"]
            merged["acknowledged_by"] = row.get("acknowledged_by") or row.get("actor_id")
        last_updated_at = row.get("last_updated_at") or row.get("occurred_at")
        if last_updated_at is not None:
            current = merged.get("last_updated_at") or merged.get("occurred_at")
            if current is None or _coerce_utc(last_updated_at) >= _coerce_utc(current):
                merged["last_updated_at"] = last_updated_at
    return merged


def _list_runtime_action_receipt_events(
    audit_repo: AuditEventRepository,
    *,
    auth: AuthContext,
    runtime_id: str,
    action_id: str | None = None,
    limit: int = 400,
) -> list[AuditEvent]:
    events = audit_repo.list_by_event_type(
        event_type="runtime.action.receipt.recorded", actor_id=auth.user_id, limit=max(limit, 1)
    )
    filtered: list[AuditEvent] = []
    for event in events:
        payload = event.event_payload if isinstance(event.event_payload, dict) else {}
        if str(payload.get("runtime_id") or "") != runtime_id:
            continue
        if action_id is not None and str(payload.get("action_id") or "") != action_id:
            continue
        if not _payload_visible_for_tenant(payload, auth):
            continue
        filtered.append(event)
    return filtered


def _decorate_runtime_action_with_receipts(
    action: dict[str, Any], receipt_events: list[AuditEvent]
) -> dict[str, Any]:
    rows = [_runtime_action_receipt_from_audit(event) for event in receipt_events]
    action = dict(action)
    action["receipt_count"] = len(rows)
    if rows:
        latest = max(rows, key=lambda row: (_coerce_utc(row["occurred_at"]), row["receipt_id"]))
        action["latest_receipt_summary"] = latest["summary"]
        action["latest_receipt_status"] = latest.get("status")
    else:
        action.setdefault("latest_receipt_summary", None)
        action.setdefault("latest_receipt_status", None)
    return action


def _runtime_action_timeline_event_from_audit(event: AuditEvent) -> dict[str, Any]:
    payload = event.event_payload if isinstance(event.event_payload, dict) else {}
    status = payload.get("status")
    title_map = {
        "runtime.action.enqueued": "Action enqueued",
        "runtime.action.acknowledged": "Action acknowledged",
        "runtime.action.state_changed": "Action state changed",
        "runtime.action.receipt.recorded": "Action receipt recorded",
    }
    detail = payload.get("note") or payload.get("summary")
    if detail is None and isinstance(payload.get("metadata"), dict) and payload["metadata"]:
        detail = ", ".join(f"{key}={value}" for key, value in list(payload["metadata"].items())[:4])
    return {
        "event_id": event.audit_event_id,
        "action_id": str(payload.get("action_id") or event.audit_event_id),
        "runtime_id": str(payload.get("runtime_id") or ""),
        "event_type": event.event_type,
        "title": title_map.get(event.event_type, event.event_type.replace(".", " ").title()),
        "status": str(status) if status is not None else None,
        "detail": detail,
        "actor_id": event.actor_id,
        "occurred_at": event.occurred_at,
        "metadata": payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
    }


def _build_runtime_action_view(
    audit_repo: AuditEventRepository, *, auth: AuthContext, runtime_id: str, action_id: str
) -> dict[str, Any] | None:
    base_event = _get_runtime_action_event(
        audit_repo, auth=auth, runtime_id=runtime_id, action_id=action_id
    )
    if base_event is None:
        return None
    base = _runtime_action_from_audit(base_event)
    updates: list[AuditEvent] = []
    for event_type in ("runtime.action.acknowledged", "runtime.action.state_changed"):
        for event in audit_repo.list_by_event_type(
            event_type=event_type, actor_id=auth.user_id, limit=400
        ):
            payload = event.event_payload if isinstance(event.event_payload, dict) else {}
            if str(payload.get("runtime_id") or "") != runtime_id:
                continue
            if str(payload.get("action_id") or "") != action_id:
                continue
            if not _payload_visible_for_tenant(payload, auth):
                continue
            updates.append(event)
    merged = _merge_runtime_action_updates(base, updates)
    return _decorate_runtime_action_with_receipts(
        merged,
        _list_runtime_action_receipt_events(
            audit_repo, auth=auth, runtime_id=runtime_id, action_id=action_id
        ),
    )
