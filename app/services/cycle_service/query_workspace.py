from __future__ import annotations

from .timeline import _coerce_utc
from .workspace_discussions import _comment_from_audit
from app.core.auth import AuthContext
from app.domain.enums import CycleState, JobState, JobType
from datetime import datetime, timezone
from typing import Any


def _agent_status_for(count: int, *, failed: int = 0) -> str:
    if failed:
        return "degraded"

    if count:
        return "active"

    return "idle"


class CycleQueryWorkspaceMixin:
    def get_workspace_overview(
        self, *, auth: AuthContext, project_id: str | None
    ) -> dict[str, Any]:
        cycles = self._cycle_repo.list_for_owner(
            owner_user_id=auth.user_id,
            tenant_id=auth.tenant_id,
            project_id=project_id,
            state=None,
            user_status=None,
            created_after=None,
            created_before=None,
            updated_after=None,
            updated_before=None,
            cursor_updated_at=None,
            cursor_cycle_id=None,
            limit=500,
        )

        projects: dict[str, dict[str, Any]] = {}
        totals = {
            "cycles": len(cycles),
            "active": 0,
            "pending_reviews": 0,
            "completed": 0,
            "failed": 0,
        }

        for cycle in cycles:
            bucket = projects.setdefault(
                cycle.project_id,
                {
                    "project_id": cycle.project_id,
                    "total_cycles": 0,
                    "active_cycles": 0,
                    "pending_reviews": 0,
                    "completed_cycles": 0,
                    "failed_cycles": 0,
                    "updated_at": cycle.updated_at,
                },
            )

            bucket["total_cycles"] += 1

            if cycle.current_state not in {CycleState.TERMINALIZED, CycleState.TERMINAL_FAIL}:
                bucket["active_cycles"] += 1
                totals["active"] += 1

            if cycle.current_state == CycleState.HUMAN_APPROVAL_PENDING:
                bucket["pending_reviews"] += 1
                totals["pending_reviews"] += 1

            if cycle.current_state == CycleState.TERMINALIZED:
                bucket["completed_cycles"] += 1
                totals["completed"] += 1

            if cycle.current_state == CycleState.TERMINAL_FAIL:
                bucket["failed_cycles"] += 1
                totals["failed"] += 1

            if bucket["updated_at"] is None or (
                cycle.updated_at and cycle.updated_at > bucket["updated_at"]
            ):
                bucket["updated_at"] = cycle.updated_at

        project_list = sorted(
            projects.values(),
            key=lambda item: (
                _coerce_utc(item["updated_at"])
                if item["updated_at"]
                else datetime.min.replace(tzinfo=timezone.utc),
                item["project_id"],
            ),
            reverse=True,
        )

        recent_comments = self._cycle_repo.list_recent_comments_for_owner(
            owner_user_id=auth.user_id,
            tenant_id=auth.tenant_id,
            project_id=project_id,
            limit=10,
        )

        return {
            "tenant_id": auth.tenant_id,
            "selected_project_id": project_id,
            "totals": totals,
            "projects": project_list[:12],
            "recent_comments": [_comment_from_audit(item) for item in recent_comments],
            "generated_at": datetime.now(timezone.utc),
        }

    def get_agent_profiles(self, *, auth: AuthContext, project_id: str | None) -> dict[str, Any]:
        cycles = self._cycle_repo.list_for_owner(
            owner_user_id=auth.user_id,
            tenant_id=auth.tenant_id,
            project_id=project_id,
            state=None,
            user_status=None,
            created_after=None,
            created_before=None,
            updated_after=None,
            updated_before=None,
            cursor_updated_at=None,
            cursor_cycle_id=None,
            limit=500,
        )
        jobs = self._cycle_repo.list_jobs_for_owner(
            owner_user_id=auth.user_id,
            tenant_id=auth.tenant_id,
            project_id=project_id,
            limit=200,
        )

        pending_reviews = len(
            [cycle for cycle in cycles if cycle.current_state == CycleState.HUMAN_APPROVAL_PENDING]
        )
        active_cycles = [
            cycle
            for cycle in cycles
            if cycle.current_state not in {CycleState.TERMINALIZED, CycleState.TERMINAL_FAIL}
        ]
        completed_cycles = [
            cycle for cycle in cycles if cycle.current_state == CycleState.TERMINALIZED
        ]
        failed_cycles = [
            cycle for cycle in cycles if cycle.current_state == CycleState.TERMINAL_FAIL
        ]

        verification_jobs = [job for job in jobs if job.job_type == JobType.RUN_VERIFICATION]
        retry_jobs = [
            job for job in jobs if job.job_type in {JobType.RETRY_CYCLE, JobType.REPLAN_CYCLE}
        ]

        planner_queue_cycles = [
            cycle
            for cycle in cycles
            if cycle.current_state
            in {
                CycleState.INTENT_ACCEPTED,
                CycleState.PLAN_GENERATED,
                CycleState.RETRY_SCHEDULED,
                CycleState.REPLAN_REQUESTED,
            }
        ]
        active_verification_jobs = [
            job
            for job in verification_jobs
            if job.job_state in {JobState.PENDING, JobState.CLAIMED, JobState.RUNNING}
        ]
        active_retry_jobs = [
            job
            for job in retry_jobs
            if job.job_state in {JobState.PENDING, JobState.CLAIMED, JobState.RUNNING}
        ]

        items = [
            {
                "agent_id": "planner-coordinator",
                "name": "Planner Coordinator",
                "persona": "Keeps accepted work flowing into execution and monitors queued load.",
                "status": _agent_status_for(len(active_cycles)),
                "focus": project_id or (active_cycles[0].project_id if active_cycles else None),
                "current_load": len(planner_queue_cycles),
                "capacity_hint": "Scale when queued cycles remain above active workers for sustained periods.",
                "specialties": ["triage", "queue shaping", "project routing"],
                "metrics": {
                    "queued_cycles": len(planner_queue_cycles),
                    "active_cycles": len(active_cycles),
                },
            },
            {
                "agent_id": "verification-specialist",
                "name": "Verification Specialist",
                "persona": "Owns verification passes, failed rules, and evidence capture before completion.",
                "status": _agent_status_for(
                    len(verification_jobs),
                    failed=len(failed_cycles),
                ),
                "focus": project_id,
                "current_load": len(active_verification_jobs),
                "capacity_hint": "Watch for rising verification backlog when work models finish faster than reviewers.",
                "specialties": ["verification", "evidence", "policy checks"],
                "metrics": {
                    "verification_jobs": len(verification_jobs),
                    "failed_cycles": len(failed_cycles),
                },
            },
            {
                "agent_id": "review-captain",
                "name": "Review Captain",
                "persona": "Tracks approvals, escalations, and human checkpoints before release.",
                "status": _agent_status_for(pending_reviews),
                "focus": project_id,
                "current_load": pending_reviews,
                "capacity_hint": "Keep reviewer SLAs tight when approvals are accumulating.",
                "specialties": ["approval handoff", "stakeholder review", "decision logging"],
                "metrics": {
                    "pending_reviews": pending_reviews,
                    "completed_cycles": len(completed_cycles),
                },
            },
            {
                "agent_id": "recovery-operator",
                "name": "Recovery Operator",
                "persona": "Handles retries, replans, and failure recovery when execution needs intervention.",
                "status": _agent_status_for(len(retry_jobs), failed=len(failed_cycles)),
                "focus": project_id,
                "current_load": len(active_retry_jobs),
                "capacity_hint": "Increase scrutiny when failures and retries climb together.",
                "specialties": ["recovery", "replan", "operator handoff"],
                "metrics": {
                    "retry_related_jobs": len(retry_jobs),
                    "failed_cycles": len(failed_cycles),
                },
            },
        ]

        return {"generated_at": datetime.now(timezone.utc), "items": items}
