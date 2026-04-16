from __future__ import annotations

from typing import Any

from .helpers import _coerce_utc, merge_artifact_history
from .types import EXECUTION_ACTIVE_STATES


def artifact_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def snapshot_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    artifacts = artifact_list(payload.get("artifacts"))
    return {
        "workspace_id": str(payload.get("workspace_id") or ""),
        "cycle_id": payload.get("cycle_id"),
        "project_id": payload.get("project_id"),
        "repo_url": payload.get("repo_url"),
        "repo_branch": payload.get("repo_branch"),
        "repo_ref": payload.get("repo_ref"),
        "patch_present": bool(payload.get("patch") or payload.get("patch_stack")),
        "patch_stack": payload.get("patch_stack") or [],
        "execution_profile": payload.get("execution_profile"),
        "executor_key": payload.get("executor_key"),
        "last_execution_status": payload.get("last_execution_status"),
        "last_execution_kind": payload.get("last_execution_kind"),
        "last_execution_requested_at": _coerce_utc(payload.get("last_execution_requested_at") or payload.get("updated_at") or payload.get("occurred_at")),
        "artifacts": artifacts,
        "artifact_history": merge_artifact_history(payload.get("artifact_history"), artifacts),
        "metadata": metadata,
        "updated_at": _coerce_utc(payload.get("updated_at") or payload.get("occurred_at")),
        "resume_count": int(payload.get("resume_count") or 0),
        "last_resumed_at": _coerce_utc(payload.get("last_resumed_at")) if payload.get("last_resumed_at") else None,
        "last_execution_id": payload.get("last_execution_id"),
        "last_result_summary": payload.get("last_result_summary"),
        "last_failed_command": payload.get("last_failed_command"),
    }


def execution_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    artifacts = artifact_list(payload.get("artifacts"))
    return {
        "execution_id": str(payload.get("execution_id") or ""),
        "workspace_id": str(payload.get("workspace_id") or ""),
        "execution_kind": payload.get("execution_kind"),
        "status": payload.get("status"),
        "executor_key": payload.get("executor_key"),
        "requested_at": _coerce_utc(payload.get("requested_at") or payload.get("occurred_at")),
        "message": payload.get("message"),
        "metadata": metadata,
        "command": payload.get("command"),
        "cycle_id": payload.get("cycle_id") or metadata.get("cycle_id"),
        "project_id": payload.get("project_id") or metadata.get("project_id"),
        "execution_profile": payload.get("execution_profile") or metadata.get("execution_profile"),
        "assigned_agent_id": payload.get("assigned_agent_id") or metadata.get("assigned_agent_id"),
        "assignment_role": payload.get("assignment_role") or metadata.get("assignment_role"),
        "started_at": _coerce_utc(payload.get("started_at")) if payload.get("started_at") else None,
        "completed_at": _coerce_utc(payload.get("completed_at")) if payload.get("completed_at") else None,
        "external_url": payload.get("external_url") or metadata.get("external_url"),
        "logs_url": payload.get("logs_url") or metadata.get("logs_url"),
        "artifacts": artifacts,
        "artifact_count": len(artifacts),
        "result_summary": payload.get("result_summary"),
        "exit_code": payload.get("exit_code"),
        "timed_out": bool(payload.get("timed_out", False)),
        "can_cancel": payload.get("status") in EXECUTION_ACTIVE_STATES,
        "last_updated_at": _coerce_utc(payload.get("last_updated_at") or payload.get("requested_at") or payload.get("occurred_at")),
        "source": payload.get("source") or "control_plane",
    }


def build_resume_payload(
    snapshot: dict[str, Any] | None,
    executions: list[dict[str, Any]],
    resume_state: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if snapshot is None:
        return None

    artifacts = merge_artifact_history(snapshot.get("artifact_history"), snapshot.get("artifacts"))
    last_success = next((item for item in executions if item.get("status") == "succeeded"), None)
    last_failure = next(
        (item for item in executions if item.get("status") in {"failed", "timed_out", "dispatch_failed", "cancelled"}),
        None,
    )
    resume_state = resume_state or {}
    return {
        "workspace_id": snapshot.get("workspace_id"),
        "cycle_id": snapshot.get("cycle_id"),
        "project_id": snapshot.get("project_id"),
        "repo_url": snapshot.get("repo_url"),
        "repo_branch": snapshot.get("repo_branch"),
        "repo_ref": snapshot.get("repo_ref"),
        "patch_stack": snapshot.get("patch_stack") or [],
        "patch_present": bool(snapshot.get("patch") or snapshot.get("patch_stack")),
        "last_execution_id": snapshot.get("last_execution_id"),
        "last_successful_execution_id": last_success.get("execution_id") if last_success else None,
        "last_failed_execution_id": last_failure.get("execution_id") if last_failure else None,
        "last_failed_command": snapshot.get("last_failed_command") or (last_failure.get("command") if last_failure else None),
        "last_result_summary": snapshot.get("last_result_summary") or (executions[0].get("result_summary") if executions else None),
        "artifacts": artifacts,
        "recent_executions": executions[:5],
        "resume_count": int(resume_state.get("resume_count") or snapshot.get("resume_count") or 0),
        "last_resumed_at": _coerce_utc(resume_state.get("last_resumed_at") or snapshot.get("last_resumed_at")) if (resume_state.get("last_resumed_at") or snapshot.get("last_resumed_at")) else None,
        "updated_at": snapshot.get("updated_at"),
    }
