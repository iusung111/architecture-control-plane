from __future__ import annotations

from .assignment_helpers import _assignment_suggestion_feedback_from_audit
from .runtime_helpers import _cycle_assignment_from_audit
from app.core.auth import AuthContext
from typing import Any


_ALLOWED_FEEDBACK_VALUES = {"accepted", "dismissed", "applied"}


class CycleWriteRuntimeAssignmentMixin:
    def assign_cycle_agent(
        self,
        cycle_id: str,
        *,
        agent_id: str,
        assignment_role: str,
        note: str | None,
        auth: AuthContext,
    ) -> dict[str, Any]:
        with self._uow:
            cycle = self._cycle_repo.get_by_id(cycle_id)
            if cycle is None:
                raise ValueError("cycle not found")

            self._ensure_access(cycle, auth)
            event = self._audit_repo.add(
                event_type="cycle.assignment.updated",
                cycle_id=cycle_id,
                actor_id=auth.user_id,
                event_payload={
                    "agent_id": agent_id.strip(),
                    "assignment_role": assignment_role.strip(),
                    "note": note.strip() if note else None,
                    "actor_role": auth.role,
                    "project_id": cycle.project_id,
                    "tenant_id": cycle.tenant_id,
                },
            )
            self._uow.commit()

        return _cycle_assignment_from_audit(event)

    def record_assignment_suggestion_feedback(
        self,
        cycle_id: str,
        *,
        agent_id: str,
        feedback: str,
        note: str | None,
        auth: AuthContext,
    ) -> dict[str, Any]:
        normalized_feedback = feedback.strip().lower()
        if normalized_feedback not in _ALLOWED_FEEDBACK_VALUES:
            raise ValueError("invalid assignment suggestion feedback")

        with self._uow:
            cycle = self._cycle_repo.get_by_id(cycle_id)
            if cycle is None:
                raise ValueError("cycle not found")

            self._ensure_access(cycle, auth)
            event = self._audit_repo.add(
                event_type="cycle.assignment.suggestion.feedback",
                cycle_id=cycle_id,
                actor_id=auth.user_id,
                event_payload={
                    "agent_id": agent_id.strip(),
                    "feedback": normalized_feedback,
                    "note": note.strip() if note else None,
                    "actor_role": auth.role,
                    "project_id": cycle.project_id,
                    "tenant_id": cycle.tenant_id,
                },
            )
            self._uow.commit()

        return _assignment_suggestion_feedback_from_audit(event)
