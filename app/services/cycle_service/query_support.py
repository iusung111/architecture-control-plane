from __future__ import annotations

import base64
import json

from app.core.auth import AuthContext
from app.db.models import Cycle
from app.domain.enums import CycleState
from app.domain.guards import ensure_result_available
from app.repositories.audit import AuditEventRepository
from app.repositories.cycles import CycleRepository
from datetime import datetime, timezone
from typing import Any


class CycleQuerySupportMixin:
    def __init__(self, cycle_repo: CycleRepository):
        self._cycle_repo = cycle_repo
        self._audit_repo = AuditEventRepository(cycle_repo._db)

    @staticmethod
    def _encode_list_cursor(updated_at: datetime, cycle_id: str) -> str:
        payload = {"updated_at": updated_at.isoformat(), "cycle_id": cycle_id}
        return base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":")).encode()
        ).decode()

    @staticmethod
    def _decode_list_cursor(cursor: str | None) -> tuple[datetime | None, str | None]:
        if not cursor:
            return None, None
        try:
            decoded = base64.urlsafe_b64decode(cursor.encode()).decode()
            payload = json.loads(decoded)
            updated_at = datetime.fromisoformat(payload["updated_at"])
            cycle_id = payload["cycle_id"]
        except Exception as exc:  # pragma: no cover - defensive parsing
            raise ValueError("invalid cursor") from exc
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        return updated_at, str(cycle_id)

    @staticmethod
    def _cycle_summary_payload(cycle: Cycle) -> dict[str, Any]:
        return {
            "cycle_id": cycle.cycle_id,
            "project_id": cycle.project_id,
            "tenant_id": cycle.tenant_id,
            "state": cycle.current_state,
            "user_status": cycle.user_status,
            "next_action": None,
            "approval_required": cycle.active_approval_id is not None,
            "retry_allowed": cycle.current_state == CycleState.VERIFICATION_FAILED,
            "replan_allowed": cycle.current_state == CycleState.VERIFICATION_FAILED,
            "latest_iteration_no": cycle.latest_iteration_no,
            "created_at": cycle.created_at,
            "updated_at": cycle.updated_at,
        }

    @staticmethod
    def _ensure_access(cycle: Cycle, auth: AuthContext) -> None:
        if cycle.owner_user_id != auth.user_id:
            raise PermissionError("forbidden")
        if auth.tenant_id is not None and cycle.tenant_id != auth.tenant_id:
            raise PermissionError("forbidden")

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
