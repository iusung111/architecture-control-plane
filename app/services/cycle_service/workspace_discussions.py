from __future__ import annotations

from .timeline import _coerce_utc
from app.core.auth import AuthContext
from app.db.models import AuditEvent
from app.repositories.audit import AuditEventRepository
from datetime import datetime
from typing import Any


def _comment_from_audit(event: AuditEvent) -> dict[str, Any]:
    payload = event.event_payload if isinstance(event.event_payload, dict) else {}
    return {
        "comment_id": event.audit_event_id,
        "cycle_id": event.cycle_id,
        "body": str(payload.get("body") or ""),
        "mentions": [str(item) for item in payload.get("mentions", []) if str(item)],
        "actor_id": event.actor_id,
        "actor_role": payload.get("actor_role"),
        "occurred_at": event.occurred_at,
    }


def _workspace_discussion_from_audit(event: AuditEvent) -> dict[str, Any]:
    payload = event.event_payload if isinstance(event.event_payload, dict) else {}
    return {
        "discussion_id": event.audit_event_id,
        "project_id": payload.get("project_id"),
        "body": str(payload.get("body") or ""),
        "mentions": [str(item) for item in payload.get("mentions", []) if str(item)],
        "actor_id": event.actor_id,
        "actor_role": payload.get("actor_role"),
        "occurred_at": event.occurred_at,
        "is_resolved": False,
        "is_pinned": False,
        "resolved_at": None,
        "resolved_by": None,
        "pinned_at": None,
        "pinned_by": None,
        "last_updated_at": event.occurred_at,
    }


def _workspace_discussion_reply_from_audit(event: AuditEvent) -> dict[str, Any]:
    payload = event.event_payload if isinstance(event.event_payload, dict) else {}
    return {
        "reply_id": event.audit_event_id,
        "discussion_id": str(payload.get("discussion_id") or ""),
        "project_id": payload.get("project_id"),
        "body": str(payload.get("body") or ""),
        "mentions": [str(item) for item in payload.get("mentions", []) if str(item)],
        "actor_id": event.actor_id,
        "actor_role": payload.get("actor_role"),
        "occurred_at": event.occurred_at,
    }


def _discussion_search_terms(query: str | None) -> list[str]:
    normalized = (query or "").strip().lower()
    if not normalized:
        return []
    terms: list[str] = []
    seen: set[str] = set()
    for term in normalized.split():
        cleaned = term.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            terms.append(cleaned)
    return terms


def _workspace_discussion_search_rank(
    payload: dict[str, Any], query: str | None, *, actor_id: str | None = None
) -> tuple[float, list[str]]:
    terms = _discussion_search_terms(query)
    if not terms:
        return 0.0, []
    body = str(payload.get("body") or "").lower()
    mentions = [str(item).lower() for item in payload.get("mentions", []) if str(item)]
    actor = str(actor_id or payload.get("actor_id") or "").lower()
    actor_role = str(payload.get("actor_role") or "").lower()
    project_id = str(payload.get("project_id") or "").lower()
    matched: list[str] = []
    score = 0.0
    for term in terms:
        term_score = 0.0
        body_hits = body.count(term)
        if body_hits:
            term_score += 5.0 + min(body_hits - 1, 4) * 1.2
        if any(term in mention for mention in mentions):
            term_score += 3.25
        if term and term in actor:
            term_score += 2.0
        if term and term in actor_role:
            term_score += 1.5
        if term and term in project_id:
            term_score += 1.75
        if term_score > 0:
            matched.append(term)
            score += term_score
    return round(score, 2), matched


def _parse_iso_datetime(value: Any, fallback: datetime | None = None) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return fallback
    return fallback


def _workspace_discussion_state_from_audit(event: AuditEvent) -> dict[str, Any]:
    payload = event.event_payload if isinstance(event.event_payload, dict) else {}
    return {
        "discussion_id": str(payload.get("discussion_id") or ""),
        "resolved": payload.get("resolved") if "resolved" in payload else None,
        "pinned": payload.get("pinned") if "pinned" in payload else None,
        "note": payload.get("note"),
        "actor_id": event.actor_id,
        "occurred_at": event.occurred_at,
        "event_type": event.event_type,
    }


def _merge_workspace_discussion_updates(
    base: dict[str, Any], updates: list[AuditEvent]
) -> dict[str, Any]:
    merged = dict(base)
    merged.setdefault("is_resolved", False)
    merged.setdefault("is_pinned", False)
    merged.setdefault("last_updated_at", merged.get("occurred_at"))
    ordered_rows = sorted(
        (_workspace_discussion_state_from_audit(event) for event in updates),
        key=lambda row: (
            _coerce_utc(row.get("occurred_at") or merged.get("occurred_at")),
            row.get("event_type") or "",
        ),
    )
    for row in ordered_rows:
        occurred_at = row.get("occurred_at") or merged.get("occurred_at")
        if row.get("resolved") is not None:
            resolved = bool(row["resolved"])
            merged["is_resolved"] = resolved
            merged["resolved_at"] = occurred_at if resolved else None
            merged["resolved_by"] = row.get("actor_id") if resolved else None
        if row.get("pinned") is not None:
            pinned = bool(row["pinned"])
            merged["is_pinned"] = pinned
            merged["pinned_at"] = occurred_at if pinned else None
            merged["pinned_by"] = row.get("actor_id") if pinned else None
        if occurred_at is not None:
            current = merged.get("last_updated_at") or merged.get("occurred_at")
            if current is None or _coerce_utc(occurred_at) >= _coerce_utc(current):
                merged["last_updated_at"] = occurred_at
    return merged


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


def _ensure_workspace_discussion_root_event(
    audit_repo: AuditEventRepository, *, discussion_id: str, auth: AuthContext
) -> AuditEvent:
    event = audit_repo.get_by_id(discussion_id)
    if event is None or event.event_type != "workspace.comment.added":
        raise ValueError("discussion not found")
    payload = event.event_payload if isinstance(event.event_payload, dict) else {}
    if event.actor_id != auth.user_id:
        raise PermissionError("not allowed to access this discussion")
    if not _payload_visible_for_tenant(payload, auth):
        raise PermissionError("not allowed to access this discussion")
    return event


def _build_workspace_discussion_view(
    audit_repo: AuditEventRepository, *, auth: AuthContext, discussion_id: str
) -> dict[str, Any] | None:
    try:
        root = _ensure_workspace_discussion_root_event(
            audit_repo, discussion_id=discussion_id, auth=auth
        )
    except (ValueError, PermissionError):
        return None
    updates: list[AuditEvent] = []
    for event_type in ("workspace.comment.resolution_changed", "workspace.comment.pin_changed"):
        for event in audit_repo.list_by_event_type(
            event_type=event_type, actor_id=auth.user_id, limit=400
        ):
            payload = event.event_payload if isinstance(event.event_payload, dict) else {}
            if str(payload.get("discussion_id") or "") != discussion_id:
                continue
            if not _payload_visible_for_tenant(payload, auth):
                continue
            updates.append(event)
    return _merge_workspace_discussion_updates(_workspace_discussion_from_audit(root), updates)


def _ensure_workspace_discussion_event(
    audit_repo: AuditEventRepository, *, discussion_id: str, auth: AuthContext
) -> AuditEvent:
    event = audit_repo.get_by_id(discussion_id)
    if event is None or event.event_type not in {
        "workspace.comment.added",
        "workspace.comment.reply.added",
    }:
        raise ValueError("discussion not found")
    payload = event.event_payload if isinstance(event.event_payload, dict) else {}
    if event.actor_id != auth.user_id:
        raise PermissionError("not allowed to access this discussion")
    if not _payload_visible_for_tenant(payload, auth):
        raise PermissionError("not allowed to access this discussion")
    return event
