from __future__ import annotations

from .runtime_helpers import _mention_matches, _payload_visible_for_tenant
from .timeline import _coerce_utc
from .workspace_discussions import (
    _discussion_search_terms,
    _ensure_workspace_discussion_event,
    _merge_workspace_discussion_updates,
    _workspace_discussion_from_audit,
    _workspace_discussion_reply_from_audit,
    _workspace_discussion_search_rank,
)
from .workspace_filters import _build_workspace_discussion_saved_filter_view
from app.core.auth import AuthContext
from app.db.models import AuditEvent
from datetime import datetime, timezone
from typing import Any


class CycleQueryWorkspaceDiscussionMixin:
    def list_workspace_discussions(
        self,
        *,
        auth: AuthContext,
        project_id: str | None,
        mention: str | None = None,
        query: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        max_limit = min(max(limit, 1), 200)
        events = self._audit_repo.list_by_event_type(
            event_type="workspace.comment.added",
            actor_id=auth.user_id,
            limit=max_limit * 4,
        )
        reply_events = self._audit_repo.list_by_event_type(
            event_type="workspace.comment.reply.added",
            actor_id=auth.user_id,
            limit=max_limit * 8,
        )
        state_updates: dict[str, list[AuditEvent]] = {}
        for event_type in ("workspace.comment.resolution_changed", "workspace.comment.pin_changed"):
            for event in self._audit_repo.list_by_event_type(
                event_type=event_type, actor_id=auth.user_id, limit=max_limit * 8
            ):
                payload = event.event_payload if isinstance(event.event_payload, dict) else {}
                discussion_id = str(payload.get("discussion_id") or "")
                if discussion_id and _payload_visible_for_tenant(payload, auth):
                    state_updates.setdefault(discussion_id, []).append(event)
        reply_counts: dict[str, int] = {}
        for reply in reply_events:
            payload = reply.event_payload if isinstance(reply.event_payload, dict) else {}
            discussion_id = str(payload.get("discussion_id") or "")
            if discussion_id:
                reply_counts[discussion_id] = reply_counts.get(discussion_id, 0) + 1
        items = []
        for event in events:
            payload = event.event_payload if isinstance(event.event_payload, dict) else {}
            if not _payload_visible_for_tenant(payload, auth):
                continue
            if project_id and payload.get("project_id") != project_id:
                continue
            if not _mention_matches(payload, mention):
                continue
            search_rank, matched_terms = _workspace_discussion_search_rank(
                {**payload, "actor_id": event.actor_id}, query, actor_id=event.actor_id
            )
            if _discussion_search_terms(query) and search_rank <= 0:
                continue
            row = _merge_workspace_discussion_updates(
                _workspace_discussion_from_audit(event), state_updates.get(event.audit_event_id, [])
            )
            row["reply_count"] = int(reply_counts.get(event.audit_event_id, 0))
            row["search_rank"] = search_rank
            row["matched_terms"] = matched_terms
            items.append(row)
        items.sort(
            key=lambda row: (
                bool(row.get("is_pinned")),
                float(row.get("search_rank") or 0.0),
                _coerce_utc(row.get("last_updated_at") or row.get("occurred_at")),
                row.get("discussion_id") or "",
            ),
            reverse=True,
        )
        limited = items[:max_limit]
        return {
            "selected_project_id": project_id,
            "mention_filter": mention.strip() if mention else None,
            "query": query.strip() if query else None,
            "items": limited,
            "has_more": len(items) > len(limited),
        }

    def group_workspace_discussions(
        self,
        *,
        auth: AuthContext,
        project_id: str | None,
        mention: str | None = None,
        query: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        listing = self.list_workspace_discussions(
            auth=auth, project_id=project_id, mention=mention, query=query, limit=max(limit, 1) * 4
        )
        groups: dict[str, dict[str, Any]] = {}
        for item in listing.get("items", []):
            key = str(item.get("project_id") or "workspace")
            group = groups.setdefault(
                key,
                {
                    "group_key": key,
                    "label": item.get("project_id") or "workspace",
                    "project_id": item.get("project_id"),
                    "total_count": 0,
                    "unresolved_count": 0,
                    "resolved_count": 0,
                    "pinned_count": 0,
                    "last_updated_at": item.get("last_updated_at") or item.get("occurred_at"),
                    "items": [],
                },
            )
            group["total_count"] += 1
            group["resolved_count"] += 1 if item.get("is_resolved") else 0
            group["unresolved_count"] += 0 if item.get("is_resolved") else 1
            group["pinned_count"] += 1 if item.get("is_pinned") else 0
            seen = item.get("last_updated_at") or item.get("occurred_at")
            if seen is not None and _coerce_utc(seen) >= _coerce_utc(
                group.get("last_updated_at") or seen
            ):
                group["last_updated_at"] = seen
            if len(group["items"]) < 3:
                group["items"].append(item)
        ordered = sorted(
            groups.values(),
            key=lambda row: (
                _coerce_utc(row.get("last_updated_at") or datetime.now(timezone.utc)),
                row["pinned_count"],
                row["group_key"],
            ),
            reverse=True,
        )
        limited = ordered[: min(max(limit, 1), 50)]
        return {
            "selected_project_id": project_id,
            "mention_filter": mention.strip() if mention else None,
            "query": query.strip() if query else None,
            "items": limited,
            "has_more": len(ordered) > len(limited),
        }

    def list_workspace_discussion_saved_filters(
        self, *, auth: AuthContext, limit: int = 50
    ) -> dict[str, Any]:
        max_limit = min(max(limit, 1), 200)
        base_events = self._audit_repo.list_by_event_type(
            event_type="workspace.comment.filter.saved", actor_id=auth.user_id, limit=max_limit * 8
        )
        rows = []
        for event in base_events:
            payload = event.event_payload if isinstance(event.event_payload, dict) else {}
            if not _payload_visible_for_tenant(payload, auth):
                continue
            built = _build_workspace_discussion_saved_filter_view(
                self._audit_repo, auth=auth, filter_id=event.audit_event_id
            )
            if built is None or built.get("is_deleted"):
                continue
            rows.append(built)
        rows.sort(
            key=lambda row: (
                bool(row.get("is_favorite")),
                _coerce_utc(
                    row.get("last_used_at") or row.get("updated_at") or row.get("occurred_at")
                ),
                row.get("filter_id") or "",
            ),
            reverse=True,
        )
        limited = rows[:max_limit]
        return {"items": limited, "has_more": len(rows) > len(limited)}

    def list_workspace_discussion_replies(
        self, *, auth: AuthContext, discussion_id: str, mention: str | None = None, limit: int = 50
    ) -> dict[str, Any]:
        parent = _ensure_workspace_discussion_event(
            self._audit_repo, discussion_id=discussion_id, auth=auth
        )
        parent_payload = parent.event_payload if isinstance(parent.event_payload, dict) else {}
        max_limit = min(max(limit, 1), 200)
        events = self._audit_repo.list_by_event_type(
            event_type="workspace.comment.reply.added",
            actor_id=auth.user_id,
            limit=max_limit * 4,
        )
        filtered = []
        for event in events:
            payload = event.event_payload if isinstance(event.event_payload, dict) else {}
            if str(payload.get("discussion_id") or "") != discussion_id:
                continue
            if not _payload_visible_for_tenant(payload, auth):
                continue
            if not _mention_matches(payload, mention):
                continue
            filtered.append(event)
        limited = filtered[:max_limit]
        return {
            "discussion_id": discussion_id,
            "project_id": parent_payload.get("project_id"),
            "mention_filter": mention.strip() if mention else None,
            "items": [_workspace_discussion_reply_from_audit(item) for item in limited],
            "has_more": len(filtered) > len(limited),
        }
