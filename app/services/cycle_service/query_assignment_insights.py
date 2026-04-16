from __future__ import annotations

from .assignment_helpers import (
    _cycle_assignment_from_audit,
    _feedback_decay_factor,
    _remote_assignment_outcomes,
)
from .runtime_helpers import _payload_visible_for_tenant
from .timeline import _coerce_utc
from app.core.auth import AuthContext
from typing import Any


class CycleQueryAssignmentInsightMixin:
    def get_assignment_learning_weights(
        self, cycle_id: str, auth: AuthContext
    ) -> dict[str, Any] | None:
        cycle = self._cycle_repo.get_by_id(cycle_id)
        if cycle is None:
            return None
        self._ensure_access(cycle, auth)
        profiles = self.get_agent_profiles(auth=auth, project_id=cycle.project_id).get("items", [])
        stats: dict[str, dict[str, Any]] = {}
        for profile in profiles:
            stats[str(profile.get("agent_id") or "")] = {
                "agent_id": str(profile.get("agent_id") or ""),
                "name": profile.get("name") or str(profile.get("agent_id") or ""),
                "accepted_count": 0,
                "dismissed_count": 0,
                "applied_count": 0,
                "recommendation_count": 0,
                "weighted_accepted_count": 0.0,
                "weighted_dismissed_count": 0.0,
                "weighted_applied_count": 0.0,
                "last_feedback_at": None,
            }
        events = self._audit_repo.list_by_event_type(
            event_type="cycle.assignment.suggestion.feedback", actor_id=auth.user_id, limit=600
        )
        for event in events:
            payload = event.event_payload if isinstance(event.event_payload, dict) else {}
            if not _payload_visible_for_tenant(payload, auth):
                continue
            if payload.get("project_id") != cycle.project_id:
                continue
            agent_id = str(payload.get("agent_id") or "")
            if not agent_id:
                continue
            row = stats.setdefault(
                agent_id,
                {
                    "agent_id": agent_id,
                    "name": agent_id,
                    "accepted_count": 0,
                    "dismissed_count": 0,
                    "applied_count": 0,
                    "recommendation_count": 0,
                    "weighted_accepted_count": 0.0,
                    "weighted_dismissed_count": 0.0,
                    "weighted_applied_count": 0.0,
                    "last_feedback_at": None,
                },
            )
            feedback = str(payload.get("feedback") or "").lower()
            decay = _feedback_decay_factor(event.occurred_at)
            if feedback == "accepted":
                row["accepted_count"] += 1
                row["weighted_accepted_count"] += decay
            elif feedback == "dismissed":
                row["dismissed_count"] += 1
                row["weighted_dismissed_count"] += decay
            elif feedback == "applied":
                row["applied_count"] += 1
                row["weighted_applied_count"] += decay
            row["recommendation_count"] += 1
            if row["last_feedback_at"] is None or _coerce_utc(event.occurred_at) >= _coerce_utc(
                row["last_feedback_at"]
            ):
                row["last_feedback_at"] = event.occurred_at
        remote_outcomes = _remote_assignment_outcomes(
            self._audit_repo, project_id=cycle.project_id, auth=auth
        )
        items = []
        for row in stats.values():
            learned_weight = round(
                row["weighted_accepted_count"] * 0.75
                + row["weighted_applied_count"] * 1.35
                - row["weighted_dismissed_count"] * 0.9,
                2,
            )
            recency_weight = (
                _feedback_decay_factor(row.get("last_feedback_at"))
                if row.get("last_feedback_at")
                else 0.0
            )
            remote = remote_outcomes.get(
                row["agent_id"],
                {
                    "remote_success_count": 0,
                    "remote_failure_count": 0,
                    "remote_total_count": 0,
                    "remote_success_rate": None,
                    "last_remote_status": None,
                    "last_remote_at": None,
                },
            )
            items.append(
                {
                    **row,
                    "learned_weight": learned_weight,
                    "recency_weight": recency_weight,
                    "remote_success_count": remote.get("remote_success_count", 0),
                    "remote_failure_count": remote.get("remote_failure_count", 0),
                    "remote_total_count": remote.get("remote_total_count", 0),
                    "remote_success_rate": remote.get("remote_success_rate"),
                    "last_remote_status": remote.get("last_remote_status"),
                    "last_remote_at": remote.get("last_remote_at"),
                    "rationale": f"weighted accepted={row['weighted_accepted_count']:.2f} · applied={row['weighted_applied_count']:.2f} · dismissed={row['weighted_dismissed_count']:.2f} · remote success={remote.get('remote_success_count', 0)}/{remote.get('remote_total_count', 0)}",
                }
            )
        items.sort(
            key=lambda row: (
                row["learned_weight"],
                row["applied_count"],
                row["accepted_count"],
                row["agent_id"],
            ),
            reverse=True,
        )
        return {"cycle_id": cycle_id, "project_id": cycle.project_id, "items": items}

    def list_cycle_assignments(
        self, cycle_id: str, auth: AuthContext, *, limit: int = 50
    ) -> dict[str, Any] | None:
        cycle = self._cycle_repo.get_by_id(cycle_id)
        if cycle is None:
            return None
        self._ensure_access(cycle, auth)
        max_limit = min(max(limit, 1), 200)
        events = self._audit_repo.list_by_event_type(
            event_type="cycle.assignment.updated", cycle_id=cycle_id, limit=max_limit
        )
        limited = events[:max_limit]
        return {
            "cycle_id": cycle_id,
            "items": [_cycle_assignment_from_audit(item) for item in limited],
            "has_more": len(events) > len(limited),
        }
