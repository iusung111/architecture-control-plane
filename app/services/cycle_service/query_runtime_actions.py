from __future__ import annotations

from .runtime_helpers import (
    _build_runtime_action_view,
    _decorate_runtime_action_with_receipts,
    _list_runtime_action_receipt_events,
    _merge_runtime_action_updates,
    _payload_visible_for_tenant,
    _runtime_action_from_audit,
    _runtime_action_receipt_from_audit,
    _runtime_action_timeline_event_from_audit,
)
from .runtime_registration import _get_latest_runtime_registration_event
from .timeline import _coerce_utc
from app.core.auth import AuthContext
from app.db.models import AuditEvent
from typing import Any


def _group_runtime_action_updates(
    *,
    update_events: list[AuditEvent],
    runtime_id: str,
    auth: AuthContext,
    base_ids: set[str],
) -> dict[str, list[AuditEvent]]:
    grouped_updates: dict[str, list[AuditEvent]] = {key: [] for key in base_ids}

    for event in update_events:
        payload = event.event_payload if isinstance(event.event_payload, dict) else {}

        if str(payload.get("runtime_id") or "") != runtime_id:
            continue

        if not _payload_visible_for_tenant(payload, auth):
            continue

        action_id = str(payload.get("action_id") or "")
        if action_id in grouped_updates:
            grouped_updates[action_id].append(event)

    return grouped_updates


class CycleQueryRuntimeActionMixin:
    def get_runtime_action_live_snapshot(
        self, *, auth: AuthContext, runtime_id: str, action_id: str, timeline_limit: int = 100
    ) -> dict[str, Any]:
        action_view = _build_runtime_action_view(
            self._audit_repo,
            auth=auth,
            runtime_id=runtime_id,
            action_id=action_id,
        )
        if action_view is None:
            raise ValueError("action not found")

        timeline = self.get_runtime_action_timeline(
            auth=auth,
            runtime_id=runtime_id,
            action_id=action_id,
            limit=timeline_limit,
        )

        return {
            "runtime_id": runtime_id,
            "action_id": action_id,
            "action": action_view,
            "timeline": timeline.get("items", []),
            "has_more": timeline.get("has_more", False),
        }

    def list_runtime_actions(
        self, *, auth: AuthContext, runtime_id: str, limit: int = 50
    ) -> dict[str, Any]:
        registration = _get_latest_runtime_registration_event(
            self._audit_repo,
            auth=auth,
            runtime_id=runtime_id,
        )
        if registration is None:
            raise ValueError("runtime not found")

        registration_payload = (
            registration.event_payload if isinstance(registration.event_payload, dict) else {}
        )
        max_limit = min(max(limit, 1), 200)

        base_events = self._audit_repo.list_by_event_type(
            event_type="runtime.action.enqueued",
            actor_id=auth.user_id,
            limit=max_limit * 6,
        )

        update_events: list[AuditEvent] = []
        for event_type in ("runtime.action.acknowledged", "runtime.action.state_changed"):
            update_events.extend(
                self._audit_repo.list_by_event_type(
                    event_type=event_type,
                    actor_id=auth.user_id,
                    limit=max_limit * 8,
                )
            )

        bases: dict[str, dict[str, Any]] = {}
        for event in base_events:
            payload = event.event_payload if isinstance(event.event_payload, dict) else {}

            if str(payload.get("runtime_id") or "") != runtime_id:
                continue

            if not _payload_visible_for_tenant(payload, auth):
                continue

            row = _runtime_action_from_audit(event)
            row.setdefault("last_updated_at", row.get("occurred_at"))
            bases[row["action_id"]] = row

        grouped_updates = _group_runtime_action_updates(
            update_events=update_events,
            runtime_id=runtime_id,
            auth=auth,
            base_ids=set(bases),
        )

        receipt_events = _list_runtime_action_receipt_events(
            self._audit_repo,
            auth=auth,
            runtime_id=runtime_id,
            limit=max_limit * 12,
        )

        receipts_by_action: dict[str, list[AuditEvent]] = {}
        for event in receipt_events:
            payload = event.event_payload if isinstance(event.event_payload, dict) else {}
            receipts_by_action.setdefault(str(payload.get("action_id") or ""), []).append(event)

        merged = [
            _decorate_runtime_action_with_receipts(
                _merge_runtime_action_updates(base, grouped_updates.get(action_id, [])),
                receipts_by_action.get(action_id, []),
            )
            for action_id, base in bases.items()
        ]
        merged.sort(
            key=lambda item: (
                _coerce_utc(item.get("last_updated_at") or item["occurred_at"]),
                item["action_id"],
            ),
            reverse=True,
        )

        limited = merged[:max_limit]
        return {
            "runtime_id": runtime_id,
            "project_id": registration_payload.get("project_id"),
            "items": limited,
            "has_more": len(merged) > len(limited),
        }

    def list_runtime_action_receipts(
        self, *, auth: AuthContext, runtime_id: str, action_id: str, limit: int = 50
    ) -> dict[str, Any]:
        action_view = _build_runtime_action_view(
            self._audit_repo,
            auth=auth,
            runtime_id=runtime_id,
            action_id=action_id,
        )
        if action_view is None:
            raise ValueError("action not found")

        max_limit = min(max(limit, 1), 200)
        receipt_events = _list_runtime_action_receipt_events(
            self._audit_repo,
            auth=auth,
            runtime_id=runtime_id,
            action_id=action_id,
            limit=max_limit * 4,
        )

        rows = [_runtime_action_receipt_from_audit(event) for event in receipt_events]
        rows.sort(
            key=lambda row: (_coerce_utc(row["occurred_at"]), row["receipt_id"]),
            reverse=True,
        )

        limited = rows[:max_limit]
        return {
            "runtime_id": runtime_id,
            "action_id": action_id,
            "items": limited,
            "has_more": len(rows) > len(limited),
        }

    def get_runtime_action_timeline(
        self, *, auth: AuthContext, runtime_id: str, action_id: str, limit: int = 100
    ) -> dict[str, Any]:
        action_view = _build_runtime_action_view(
            self._audit_repo,
            auth=auth,
            runtime_id=runtime_id,
            action_id=action_id,
        )
        if action_view is None:
            raise ValueError("action not found")

        max_limit = min(max(limit, 1), 300)
        events: list[AuditEvent] = []

        for event_type in (
            "runtime.action.enqueued",
            "runtime.action.acknowledged",
            "runtime.action.state_changed",
            "runtime.action.receipt.recorded",
        ):
            for event in self._audit_repo.list_by_event_type(
                event_type=event_type,
                actor_id=auth.user_id,
                limit=max_limit * 8,
            ):
                payload = event.event_payload if isinstance(event.event_payload, dict) else {}

                if str(payload.get("runtime_id") or "") != runtime_id:
                    continue

                if str(payload.get("action_id") or event.audit_event_id) != action_id:
                    continue

                if not _payload_visible_for_tenant(payload, auth):
                    continue

                events.append(event)

        rows = [_runtime_action_timeline_event_from_audit(event) for event in events]
        rows.sort(
            key=lambda row: (_coerce_utc(row["occurred_at"]), row["event_id"]),
            reverse=True,
        )

        limited = rows[:max_limit]
        return {
            "runtime_id": runtime_id,
            "action_id": action_id,
            "items": limited,
            "has_more": len(rows) > len(limited),
        }
