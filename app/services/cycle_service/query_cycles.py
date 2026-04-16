from __future__ import annotations

from .workspace_discussions import _comment_from_audit
from app.core.auth import AuthContext
from app.db.models import Cycle
from app.domain.enums import CycleState, JobState
from app.domain.guards import StateConflictError, ensure_result_available
from datetime import datetime, timezone
from typing import Any


class CycleQueryCycleMixin:
    def get_cycle_summary(self, cycle_id: str, auth: AuthContext) -> dict | None:
        cycle = self._cycle_repo.get_by_id(cycle_id)
        if not cycle:
            return None
        self._ensure_access(cycle, auth)
        payload = self._cycle_summary_payload(cycle)
        return {
            "cycle_id": payload["cycle_id"],
            "state": payload["state"],
            "user_status": payload["user_status"],
            "next_action": payload["next_action"],
            "approval_required": payload["approval_required"],
            "retry_allowed": payload["retry_allowed"],
            "replan_allowed": payload["replan_allowed"],
            "updated_at": payload["updated_at"],
        }

    def get_cycle_result(self, cycle_id: str, auth: AuthContext) -> dict | None:
        bundle = self._cycle_repo.get_result_bundle(cycle_id)
        if not bundle:
            return None
        cycle = bundle["cycle"]
        self._ensure_access(cycle, auth)
        ensure_result_available(cycle.current_state)
        verification = bundle["verification"]
        approval = bundle["approval"]
        artifacts = bundle["artifacts"]
        receipt = bundle["receipt"]
        return {
            "cycle_id": cycle.cycle_id,
            "final_state": cycle.current_state,
            "summary": receipt.summary if receipt and receipt.summary else "Cycle completed",
            "output_artifacts": [
                {
                    "artifact_id": item.artifact_id,
                    "artifact_type": item.artifact_type,
                    "uri": item.uri,
                    "content_type": item.content_type,
                }
                for item in artifacts
            ],
            "verification": {
                "status": verification.verification_status if verification else None,
                "failed_rules": verification.failed_rules if verification else [],
            },
            "approval": {
                "required": approval is not None,
                "approval_id": approval.approval_id if approval else None,
                "state": approval.approval_state if approval else None,
            },
            "evidence_summary": receipt.payload if receipt else {},
            "generated_at": cycle.updated_at,
        }

    def list_cycles(
        self,
        *,
        auth: AuthContext,
        project_id: str | None,
        state: str | None,
        user_status: str | None,
        created_after: datetime | None,
        created_before: datetime | None,
        updated_after: datetime | None,
        updated_before: datetime | None,
        cursor: str | None,
        limit: int,
    ) -> dict[str, Any]:
        cursor_updated_at, cursor_cycle_id = self._decode_list_cursor(cursor)
        fetch_limit = min(max(limit, 1), 100) + 1
        cycles = self._cycle_repo.list_for_owner(
            owner_user_id=auth.user_id,
            tenant_id=auth.tenant_id,
            project_id=project_id,
            state=state,
            user_status=user_status,
            created_after=created_after,
            created_before=created_before,
            updated_after=updated_after,
            updated_before=updated_before,
            cursor_updated_at=cursor_updated_at,
            cursor_cycle_id=cursor_cycle_id,
            limit=fetch_limit,
        )
        has_more = len(cycles) > fetch_limit - 1
        page = cycles[: fetch_limit - 1]
        next_cursor = None
        if has_more and page:
            last = page[-1]
            next_cursor = self._encode_list_cursor(last.updated_at, last.cycle_id)
        return {
            "items": [self._cycle_summary_payload(cycle) for cycle in page],
            "next_cursor": next_cursor,
            "has_more": has_more,
        }

    @staticmethod
    def _board_column_metadata() -> list[tuple[str, str, str]]:
        return [
            ("queued", "Queued", "Accepted or rescheduled work waiting to run"),
            ("in_progress", "In Progress", "Execution is active or verification is underway"),
            ("review", "Needs Review", "Human approval is required before completion"),
            ("blocked", "Blocked", "Verification failed or user action is required"),
            ("done", "Done", "Completed successfully"),
            ("failed", "Failed", "Terminal failures requiring operator attention"),
        ]

    @staticmethod
    def _board_column_key(cycle: Cycle) -> str:
        state = cycle.current_state
        if state in {
            CycleState.INTENT_ACCEPTED,
            CycleState.PLAN_GENERATED,
            CycleState.RETRY_SCHEDULED,
            CycleState.REPLAN_REQUESTED,
        }:
            return "queued"
        if state in {
            CycleState.EXECUTION_ATTEMPTED,
            CycleState.RESULT_CAPTURED,
            CycleState.VERIFICATION_PASSED,
        }:
            return "in_progress"
        if state == CycleState.HUMAN_APPROVAL_PENDING:
            return "review"
        if state == CycleState.VERIFICATION_FAILED:
            return "blocked"
        if state == CycleState.TERMINALIZED:
            return "done"
        if state == CycleState.TERMINAL_FAIL:
            return "failed"
        return "queued"

    def get_board_snapshot(
        self, *, auth: AuthContext, project_id: str | None, limit_per_column: int = 12
    ) -> dict[str, Any]:
        bounded_limit = min(max(limit_per_column, 1), 50)
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
        grouped: dict[str, list[Cycle]] = {key: [] for key, _, _ in self._board_column_metadata()}
        for cycle in cycles:
            grouped[self._board_column_key(cycle)].append(cycle)
        columns = []
        for key, title, description in self._board_column_metadata():
            items = grouped[key]
            columns.append(
                {
                    "key": key,
                    "title": title,
                    "description": description,
                    "count": len(items),
                    "items": [
                        self._cycle_summary_payload(cycle) for cycle in items[:bounded_limit]
                    ],
                }
            )
        return {
            "project_id": project_id,
            "generated_at": datetime.now(timezone.utc),
            "total_count": len(cycles),
            "columns": columns,
        }

    def list_cycle_comments(
        self, cycle_id: str, auth: AuthContext, *, limit: int = 50
    ) -> dict[str, Any] | None:
        cycle = self._cycle_repo.get_by_id(cycle_id)
        if cycle is None:
            return None
        self._ensure_access(cycle, auth)
        comments = self._cycle_repo.list_comments_for_cycle(cycle_id, limit=limit)
        limited = comments[: min(max(limit, 1), 200)]
        return {
            "cycle_id": cycle_id,
            "items": [_comment_from_audit(item) for item in limited],
            "has_more": len(comments) > len(limited),
        }

    def get_cycle_card(self, cycle_id: str, auth: AuthContext) -> dict[str, Any] | None:
        cycle = self._cycle_repo.get_by_id(cycle_id)
        if cycle is None:
            return None
        self._ensure_access(cycle, auth)
        summary = self.get_cycle_summary(cycle_id, auth)
        assert summary is not None
        result = None
        if cycle.current_state in {CycleState.TERMINALIZED, CycleState.TERMINAL_FAIL}:
            try:
                result = self.get_cycle_result(cycle_id, auth)
            except StateConflictError:
                result = None
        timeline = self.get_cycle_timeline(cycle_id, auth, limit=8)
        comments = self.list_cycle_comments(cycle_id, auth, limit=6)
        approvals = self._cycle_repo.get_timeline_bundle(cycle_id, limit=8)["approvals"]
        jobs = self._cycle_repo.list_jobs_for_owner(
            owner_user_id=auth.user_id,
            tenant_id=auth.tenant_id,
            project_id=cycle.project_id,
            limit=200,
        )
        cycle_jobs = [job for job in jobs if job.cycle_id == cycle_id]
        active_approval = approvals[0] if approvals else None
        assignments = self.list_cycle_assignments(cycle_id, auth, limit=10) or {"items": []}
        current_assignment = assignments["items"][0] if assignments["items"] else None
        suggestion_bundle = self.get_cycle_assignment_suggestions(cycle_id, auth) or {"items": []}
        suggested_agents = [item["agent_id"] for item in suggestion_bundle.get("items", [])]
        return {
            "cycle": self._cycle_summary_payload(cycle),
            "summary": summary,
            "result": result,
            "timeline_preview": (timeline or {}).get("events", []),
            "comments_preview": (comments or {}).get("items", []),
            "comment_count": len(self._cycle_repo.list_comments_for_cycle(cycle_id, limit=500)),
            "active_job_count": len(
                [
                    job
                    for job in cycle_jobs
                    if job.job_state in {JobState.PENDING, JobState.CLAIMED, JobState.RUNNING}
                ]
            ),
            "active_approval": {
                "required": active_approval is not None,
                "approval_id": active_approval.approval_id if active_approval else None,
                "state": active_approval.approval_state if active_approval else None,
            }
            if active_approval
            else None,
            "current_assignment": current_assignment,
            "suggested_agents": suggested_agents,
            "assignment_suggestions": suggestion_bundle.get("items", []),
        }
