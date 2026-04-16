from __future__ import annotations

from .assignment_helpers import (
    _assignment_suggestion_feedback_from_audit,
    _feedback_decay_factor,
    _remote_assignment_outcomes,
)
from .runtime_helpers import _payload_visible_for_tenant
from .timeline import _coerce_utc
from app.core.auth import AuthContext
from typing import Any


_PREFERRED_ASSIGNMENTS = {
    "queued": [
        (
            "planner-coordinator",
            "primary",
            "Own the queue and push accepted work into execution.",
        ),
        (
            "verification-specialist",
            "observer",
            "Prepare verification context before execution starts.",
        ),
    ],
    "in_progress": [
        (
            "planner-coordinator",
            "primary",
            "Keep active execution unblocked and coordinated.",
        ),
        (
            "verification-specialist",
            "validator",
            "Track verification evidence as work completes.",
        ),
    ],
    "review": [
        (
            "review-captain",
            "reviewer",
            "Human checkpoint is pending and needs explicit review ownership.",
        ),
        (
            "verification-specialist",
            "validator",
            "Support review with evidence and policy context.",
        ),
    ],
    "blocked": [
        (
            "recovery-operator",
            "recovery",
            "Failure or blockage needs remediation ownership.",
        ),
        (
            "verification-specialist",
            "validator",
            "Investigate failing checks and missing evidence.",
        ),
    ],
    "done": [
        (
            "review-captain",
            "reviewer",
            "Completed work can be wrapped with final review and sign-off.",
        )
    ],
    "failed": [
        (
            "recovery-operator",
            "recovery",
            "Terminal failure needs retry or replan leadership.",
        ),
        (
            "planner-coordinator",
            "observer",
            "Track recovery queue and reprioritize follow-up work.",
        ),
    ],
}
_DEFAULT_ASSIGNMENT = [
    ("planner-coordinator", "primary", "General coordination is the safest default.")
]


def _preferred_assignments_for(board_key: str) -> list[tuple[str, str, str]]:
    return _PREFERRED_ASSIGNMENTS.get(board_key, _DEFAULT_ASSIGNMENT)


class CycleQueryAssignmentMixin:
    def get_cycle_assignment_suggestions(
        self, cycle_id: str, auth: AuthContext
    ) -> dict[str, Any] | None:
        cycle = self._cycle_repo.get_by_id(cycle_id)
        if cycle is None:
            return None

        self._ensure_access(cycle, auth)
        board_key = self._board_column_key(cycle)

        profiles = self.get_agent_profiles(auth=auth, project_id=cycle.project_id).get("items", [])
        preferred = _preferred_assignments_for(board_key)

        feedback_events = self._audit_repo.list_by_event_type(
            event_type="cycle.assignment.suggestion.feedback",
            actor_id=auth.user_id,
            limit=600,
        )

        feedback_by_agent: dict[str, dict[str, Any]] = {}
        feedback_counts: dict[str, dict[str, int]] = {}
        weighted_counts: dict[str, dict[str, float]] = {}

        for event in feedback_events:
            payload = event.event_payload if isinstance(event.event_payload, dict) else {}

            if not _payload_visible_for_tenant(payload, auth):
                continue

            if payload.get("project_id") != cycle.project_id:
                continue

            row = _assignment_suggestion_feedback_from_audit(event)
            agent_key = row.get("agent_id") or ""

            counts = feedback_counts.setdefault(
                agent_key,
                {"accepted": 0, "dismissed": 0, "applied": 0},
            )
            weighted = weighted_counts.setdefault(
                agent_key,
                {"accepted": 0.0, "dismissed": 0.0, "applied": 0.0},
            )

            feedback_value = row.get("feedback") or ""
            decay = _feedback_decay_factor(row.get("occurred_at"))
            if feedback_value in counts:
                counts[feedback_value] += 1
                weighted[feedback_value] += decay

            existing = feedback_by_agent.get(agent_key)
            if existing is None or _coerce_utc(row["occurred_at"]) >= _coerce_utc(
                existing["occurred_at"]
            ):
                feedback_by_agent[agent_key] = row

        by_agent = {str(item.get("agent_id") or ""): item for item in profiles}
        remote_outcomes = _remote_assignment_outcomes(
            self._audit_repo,
            project_id=cycle.project_id,
            auth=auth,
        )

        suggestions = []
        for rank, (agent_id, role, rationale) in enumerate(preferred, start=1):
            profile = by_agent.get(agent_id)
            if not profile:
                continue

            load = int(profile.get("current_load") or 0)
            queue_pressure = "high" if load >= 5 else "medium" if load >= 2 else "low"

            feedback = feedback_by_agent.get(agent_id, {})
            counts = feedback_counts.get(
                agent_id,
                {"accepted": 0, "dismissed": 0, "applied": 0},
            )
            weighted = weighted_counts.get(
                agent_id,
                {"accepted": 0.0, "dismissed": 0.0, "applied": 0.0},
            )

            last_feedback_at = feedback.get("occurred_at")
            recency_weight = _feedback_decay_factor(last_feedback_at) if last_feedback_at else 0.0
            learned_weight = round(
                weighted["accepted"] * 0.75
                + weighted["applied"] * 1.35
                - weighted["dismissed"] * 0.9,
                2,
            )

            remote = remote_outcomes.get(
                agent_id,
                {
                    "remote_success_count": 0,
                    "remote_failure_count": 0,
                    "remote_total_count": 0,
                    "remote_success_rate": None,
                    "last_remote_status": None,
                    "last_remote_at": None,
                },
            )
            remote_score = (
                ((remote.get("remote_success_rate") or 0.5) - 0.5) * 16
                if remote.get("remote_success_rate") is not None
                else 0.0
            )
            score = max(
                5,
                int(
                    100
                    - (rank - 1) * 14
                    - load * 6
                    + learned_weight * 6
                    + recency_weight * 3
                    + remote_score
                ),
            )

            suggestions.append(
                {
                    "agent_id": agent_id,
                    "name": profile.get("name") or agent_id,
                    "recommended_role": role,
                    "rationale": rationale,
                    "current_load": load,
                    "queue_pressure": queue_pressure,
                    "status": profile.get("status") or "idle",
                    "capacity_hint": profile.get("capacity_hint"),
                    "specialties": profile.get("specialties") or [],
                    "score": score,
                    "autofill_note": f"Suggested for {board_key.replace('_', ' ')} work on {cycle.project_id}.",
                    "last_feedback": feedback.get("feedback"),
                    "feedback_note": feedback.get("note"),
                    "feedback_actor_id": feedback.get("actor_id"),
                    "feedback_occurred_at": feedback.get("occurred_at"),
                    "learned_weight": learned_weight,
                    "weighted_feedback_score": learned_weight,
                    "recency_weight": recency_weight,
                    "last_feedback_at": last_feedback_at,
                    "accepted_count": counts["accepted"],
                    "dismissed_count": counts["dismissed"],
                    "applied_count": counts["applied"],
                    "remote_success_count": remote.get("remote_success_count", 0),
                    "remote_failure_count": remote.get("remote_failure_count", 0),
                    "remote_total_count": remote.get("remote_total_count", 0),
                    "remote_success_rate": remote.get("remote_success_rate"),
                    "last_remote_status": remote.get("last_remote_status"),
                    "last_remote_at": remote.get("last_remote_at"),
                }
            )

        return {"cycle_id": cycle_id, "board_column": board_key, "items": suggestions}
