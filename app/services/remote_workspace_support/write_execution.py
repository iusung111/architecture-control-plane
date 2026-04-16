from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException

from app.core.auth import AuthContext

from .helpers import append_persistent_session_event, latest_cycle_assignment, merge_artifact_history, merge_patch_stack
from .payloads import execution_from_payload
from .query_service import RemoteWorkspaceQueryService
from .types import EXECUTION_ACTIVE_STATES, WorkspaceExecutionRequest


class RemoteWorkspaceExecutionWriteMixin:
    def request_execution(self, *, payload: dict[str, object], auth: AuthContext) -> dict[str, object]:
        request = WorkspaceExecutionRequest(
            workspace_id=str(payload.get("workspace_id") or "").strip(),
            execution_kind=str(payload.get("execution_kind") or "run_checks"),
            command=payload.get("command"),
            patch=payload.get("patch"),
            repo_url=payload.get("repo_url"),
            repo_branch=payload.get("repo_branch"),
            repo_ref=payload.get("repo_ref"),
            cycle_id=payload.get("cycle_id"),
            project_id=payload.get("project_id"),
            execution_profile=payload.get("execution_profile"),
            executor_key=payload.get("executor_key") or self._settings.remote_workspace_default_executor,
            metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
            execution_id=uuid4().hex,
        )
        self._enforce_limits(auth=auth, requested_executor=request.executor_key or "planning")
        executor = self._registry.get(request.executor_key)
        query = RemoteWorkspaceQueryService(self._audit_repo, self._settings)
        if executor.key == "persistent":
            current_session = query.get_persistent_session(workspace_id=request.workspace_id, auth=auth)
            if current_session is None or current_session.get("status") == "hibernated":
                self.save_persistent_session(
                    payload={
                        "workspace_id": request.workspace_id,
                        "cycle_id": request.cycle_id,
                        "project_id": request.project_id,
                        "repo_url": request.repo_url,
                        "repo_branch": request.repo_branch,
                        "repo_ref": request.repo_ref,
                        "note": "auto-activated for persistent execution",
                    },
                    auth=auth,
                )
        requested_at = datetime.now(UTC)
        assignment = latest_cycle_assignment(self._audit_repo, request.cycle_id)
        metadata = dict(request.metadata or {})
        metadata.setdefault("cycle_id", request.cycle_id)
        metadata.setdefault("project_id", request.project_id)
        metadata.setdefault("execution_profile", request.execution_profile)
        if assignment:
            metadata.setdefault("assigned_agent_id", assignment.get("agent_id"))
            metadata.setdefault("assignment_role", assignment.get("assignment_role"))
        request.metadata = metadata

        request_event_payload = {
            "execution_id": request.execution_id,
            "workspace_id": request.workspace_id,
            "execution_kind": request.execution_kind,
            "status": "requested",
            "executor_key": executor.key,
            "command": request.command,
            "repo_url": request.repo_url,
            "repo_branch": request.repo_branch,
            "repo_ref": request.repo_ref,
            "cycle_id": request.cycle_id,
            "project_id": request.project_id,
            "execution_profile": request.execution_profile,
            "assigned_agent_id": metadata.get("assigned_agent_id"),
            "assignment_role": metadata.get("assignment_role"),
            "patch_present": bool(request.patch),
            "metadata": metadata,
            "tenant_id": auth.tenant_id,
            "requested_at": requested_at.isoformat(),
            "source": "control_plane",
            "actor_id": auth.user_id,
        }
        with self._uow:
            self._audit_repo.add(event_type="remote.workspace.execution.requested", actor_id=auth.user_id, cycle_id=request.cycle_id, event_payload=request_event_payload)
            self._uow.commit()
        try:
            if request.execution_kind == "prepare":
                result = executor.prepare_workspace(request)
            elif request.execution_kind == "apply_patch_and_test":
                result = executor.apply_patch(request)
            else:
                result = executor.run_checks(request)
        except HTTPException:
            failure_payload = {
                **request_event_payload,
                "status": "dispatch_failed",
                "last_updated_at": datetime.now(UTC).isoformat(),
                "message": "executor dispatch failed",
            }
            with self._uow:
                self._audit_repo.add(event_type="remote.workspace.execution.updated", actor_id=auth.user_id, cycle_id=request.cycle_id, event_payload=failure_payload)
                self._uow.commit()
            raise

        resume_state = self._resume_state_for_workspace(request.workspace_id, auth)
        updated_payload = {
            **request_event_payload,
            "status": result.status,
            "executor_key": result.executor_key,
            "message": result.message,
            "metadata": result.metadata or metadata,
            "last_updated_at": result.requested_at.isoformat(),
        }
        snapshot_payload = {
            "workspace_id": request.workspace_id,
            "cycle_id": request.cycle_id,
            "project_id": request.project_id,
            "repo_url": request.repo_url,
            "repo_branch": request.repo_branch,
            "repo_ref": request.repo_ref,
            "patch": request.patch,
            "patch_stack": merge_patch_stack(request.patch, payload.get("patch_stack"), metadata.get("patch_stack")),
            "execution_profile": request.execution_profile,
            "executor_key": result.executor_key,
            "last_execution_status": result.status,
            "last_execution_kind": request.execution_kind,
            "last_execution_requested_at": result.requested_at.isoformat(),
            "artifacts": [],
            "artifact_history": [],
            "metadata": metadata,
            "tenant_id": auth.tenant_id,
            "updated_at": result.requested_at.isoformat(),
            "last_execution_id": result.execution_id,
            "last_result_summary": result.message,
            "resume_count": resume_state.get("resume_count", 0),
            "last_resumed_at": resume_state.get("last_resumed_at"),
            "actor_id": auth.user_id,
        }
        with self._uow:
            self._audit_repo.add(event_type="remote.workspace.execution.updated", actor_id=auth.user_id, cycle_id=request.cycle_id, event_payload=updated_payload)
            self._audit_repo.add(event_type="remote.workspace.snapshot.saved", actor_id=auth.user_id, cycle_id=request.cycle_id, event_payload=snapshot_payload)
            self._uow.commit()
        if executor.key == "persistent":
            append_persistent_session_event(
                audit_repo=self._audit_repo,
                uow=self._uow,
                settings=self._settings,
                workspace_id=request.workspace_id,
                actor_id=auth.user_id,
                tenant_id=auth.tenant_id,
                status="busy" if result.status in EXECUTION_ACTIVE_STATES else "active",
                note=f"persistent execution {request.execution_id} {result.status}",
            )
        return execution_from_payload(updated_payload)

    def record_result_callback(self, *, execution_id: str, payload: dict[str, object]) -> dict[str, object]:
        status = str(payload.get("status") or "succeeded")
        existing = self._find_execution_state_any(execution_id) or {}
        metadata = dict(existing.get("metadata") if isinstance(existing.get("metadata"), dict) else {})
        if isinstance(payload.get("metadata"), dict):
            metadata.update(payload.get("metadata") or {})
        event_payload = {
            "execution_id": execution_id,
            "workspace_id": payload.get("workspace_id") or existing.get("workspace_id") or "",
            "execution_kind": payload.get("execution_kind") or existing.get("execution_kind") or "run_checks",
            "status": status,
            "executor_key": payload.get("executor_key") or existing.get("executor_key") or "github_actions",
            "message": payload.get("message"),
            "result_summary": payload.get("result_summary"),
            "artifacts": payload.get("artifacts") or [],
            "external_url": payload.get("external_url"),
            "logs_url": payload.get("logs_url"),
            "started_at": payload.get("started_at") or existing.get("started_at"),
            "completed_at": payload.get("completed_at") or datetime.now(UTC).isoformat(),
            "exit_code": payload.get("exit_code"),
            "timed_out": bool(payload.get("timed_out", False)),
            "metadata": metadata,
            "tenant_id": payload.get("tenant_id") or existing.get("tenant_id"),
            "last_updated_at": datetime.now(UTC).isoformat(),
            "source": "callback",
            "command": payload.get("command") or existing.get("command"),
            "cycle_id": payload.get("cycle_id") or existing.get("cycle_id") or metadata.get("cycle_id"),
            "project_id": payload.get("project_id") or existing.get("project_id") or metadata.get("project_id"),
            "execution_profile": payload.get("execution_profile") or existing.get("execution_profile") or metadata.get("execution_profile"),
            "assigned_agent_id": payload.get("assigned_agent_id") or existing.get("assigned_agent_id") or metadata.get("assigned_agent_id"),
            "assignment_role": payload.get("assignment_role") or existing.get("assignment_role") or metadata.get("assignment_role"),
            "repo_url": payload.get("repo_url") or existing.get("repo_url"),
            "repo_branch": payload.get("repo_branch") or existing.get("repo_branch"),
            "repo_ref": payload.get("repo_ref") or existing.get("repo_ref"),
            "patch": payload.get("patch") or existing.get("patch"),
        }
        snapshot_before = self._snapshot_state_any(event_payload["workspace_id"]) if event_payload["workspace_id"] else None
        with self._uow:
            self._audit_repo.add(event_type="remote.workspace.execution.result.recorded", actor_id="remote-workspace-callback", cycle_id=event_payload.get("cycle_id"), event_payload=event_payload)
            snapshot_payload = {
                "workspace_id": event_payload["workspace_id"],
                "cycle_id": event_payload.get("cycle_id"),
                "project_id": event_payload.get("project_id"),
                "repo_url": event_payload.get("repo_url"),
                "repo_branch": event_payload.get("repo_branch"),
                "repo_ref": event_payload.get("repo_ref"),
                "patch": event_payload.get("patch"),
                "patch_stack": merge_patch_stack(event_payload.get("patch"), snapshot_before.get("patch_stack") if isinstance(snapshot_before, dict) else None, metadata.get("patch_stack")),
                "execution_profile": event_payload.get("execution_profile"),
                "executor_key": event_payload["executor_key"],
                "last_execution_status": status,
                "last_execution_kind": event_payload["execution_kind"],
                "last_execution_requested_at": event_payload["completed_at"],
                "artifacts": event_payload["artifacts"],
                "artifact_history": merge_artifact_history(snapshot_before.get("artifact_history") if isinstance(snapshot_before, dict) else None, event_payload["artifacts"]),
                "metadata": metadata,
                "tenant_id": event_payload.get("tenant_id"),
                "updated_at": event_payload["completed_at"],
                "last_execution_id": execution_id,
                "last_result_summary": event_payload.get("result_summary"),
                "last_failed_command": event_payload.get("command") if status in {"failed", "timed_out", "dispatch_failed"} else None,
                "resume_count": snapshot_before.get("resume_count", 0) if isinstance(snapshot_before, dict) else 0,
                "last_resumed_at": snapshot_before.get("last_resumed_at") if isinstance(snapshot_before, dict) else None,
                "actor_id": "remote-workspace-callback",
            }
            self._audit_repo.add(event_type="remote.workspace.snapshot.saved", actor_id="remote-workspace-callback", cycle_id=event_payload.get("cycle_id"), event_payload=snapshot_payload)
            self._uow.commit()
        if event_payload.get("executor_key") == "persistent" or metadata.get("persistent_workspace"):
            append_persistent_session_event(
                audit_repo=self._audit_repo,
                uow=self._uow,
                settings=self._settings,
                workspace_id=str(event_payload.get("workspace_id") or ""),
                actor_id="remote-workspace-callback",
                tenant_id=event_payload.get("tenant_id"),
                status="active",
                note=f"persistent execution {execution_id} completed with status {status}",
            )
        return execution_from_payload(event_payload)

    def cancel_execution(self, *, execution_id: str, auth: AuthContext) -> dict[str, object]:
        current = self._execution_states(auth=auth).get(execution_id)
        if not current:
            raise HTTPException(status_code=404, detail="remote workspace execution not found")
        executor = self._registry.get(current.get("executor_key"))
        metadata = current.get("metadata") if isinstance(current.get("metadata"), dict) else None
        cancel_sent = executor.cancel_execution(execution_id, metadata)
        status = "cancel_requested" if cancel_sent else "cancelled"
        event_payload = {
            **current,
            "status": status,
            "message": "cancel requested for remote execution" if cancel_sent else "remote execution cancelled before external acknowledgement",
            "last_updated_at": datetime.now(UTC).isoformat(),
            "tenant_id": auth.tenant_id,
            "source": "control_plane",
        }
        with self._uow:
            self._audit_repo.add(event_type="remote.workspace.execution.cancelled", actor_id=auth.user_id, event_payload=event_payload)
            self._uow.commit()
        if current.get("executor_key") == "persistent":
            append_persistent_session_event(
                audit_repo=self._audit_repo,
                uow=self._uow,
                settings=self._settings,
                workspace_id=str(current.get("workspace_id") or ""),
                actor_id=auth.user_id,
                tenant_id=auth.tenant_id,
                status="active",
                note=f"persistent execution {execution_id} cancelled",
            )
        return execution_from_payload(event_payload)
