from __future__ import annotations

from .timeline import (
    CycleTimelineEvent,
    _coerce_utc,
    _timeline_event_from_approval,
    _timeline_event_from_audit,
    _timeline_event_from_iteration,
    _timeline_event_from_job,
    _timeline_event_from_receipt,
)
from app.core.auth import AuthContext
from typing import Any


class CycleQueryTimelineMixin:
    def get_cycle_timeline(
        self, cycle_id: str, auth: AuthContext, *, limit: int = 50
    ) -> dict[str, Any] | None:
        bundle = self._cycle_repo.get_timeline_bundle(cycle_id, limit=limit)
        if not bundle:
            return None
        cycle = bundle["cycle"]
        self._ensure_access(cycle, auth)
        timeline_events: list[CycleTimelineEvent] = []
        timeline_events.extend(_timeline_event_from_audit(item) for item in bundle["audit_events"])
        timeline_events.extend(_timeline_event_from_job(item) for item in bundle["jobs"])
        timeline_events.extend(_timeline_event_from_approval(item) for item in bundle["approvals"])
        timeline_events.extend(
            _timeline_event_from_receipt(item)
            for item in bundle["receipts"]
            if item.receipt_type != "request_snapshot"
        )
        timeline_events.extend(
            _timeline_event_from_iteration(item) for item in bundle["iterations"]
        )
        timeline_events.sort(
            key=lambda item: (_coerce_utc(item.occurred_at), item.event_id), reverse=True
        )
        limited = timeline_events[: min(max(limit, 1), 200)]
        return {
            "cycle_id": cycle_id,
            "events": [
                {
                    "event_id": item.event_id,
                    "source": item.source,
                    "event_type": item.event_type,
                    "title": item.title,
                    "detail": item.detail,
                    "actor_id": item.actor_id,
                    "status": item.status,
                    "occurred_at": item.occurred_at,
                    "metadata": item.metadata,
                }
                for item in limited
            ],
            "has_more": len(timeline_events) > len(limited),
        }
