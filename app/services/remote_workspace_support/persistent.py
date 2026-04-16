from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.core.config import Settings
from app.repositories.audit import AuditEventRepository

from .helpers import _coerce_utc, event_order_timestamp, merge_artifact_history
from .payloads import snapshot_from_payload
from .types import RemoteWorkspaceExecutor, WorkspaceExecutionRequest, WorkspaceExecutionResult


def persistent_session_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "workspace_id": str(payload.get("workspace_id") or ""),
        "cycle_id": payload.get("cycle_id"),
        "project_id": payload.get("project_id"),
        "repo_url": payload.get("repo_url"),
        "repo_branch": payload.get("repo_branch"),
        "repo_ref": payload.get("repo_ref"),
        "provider": str(payload.get("provider") or "manual"),
        "status": str(payload.get("status") or "requested"),
        "note": payload.get("note"),
        "created_at": _coerce_utc(payload.get("created_at") or payload.get("occurred_at")),
        "updated_at": _coerce_utc(payload.get("updated_at") or payload.get("occurred_at")),
        "last_resumed_at": _coerce_utc(payload.get("last_resumed_at")) if payload.get("last_resumed_at") else None,
        "idle_timeout_minutes": int(payload.get("idle_timeout_minutes") or 120),
        "ttl_hours": int(payload.get("ttl_hours") or 8),
        "expires_at": _coerce_utc(payload.get("expires_at")) if payload.get("expires_at") else None,
        "hibernate_supported": bool(payload.get("hibernate_supported", True)),
        "is_persistent": True,
    }


class OptionalPersistentRemoteWorkspaceExecutor(RemoteWorkspaceExecutor):
    key = "persistent"
    name = "Optional persistent workspace"
    mode = "persistent_opt_in"
    description = "Opt-in long-lived remote workspace session for small-team use; disabled by default."
    capabilities = ("prepare", "run_checks", "resume_snapshot", "collect_artifacts", "cancel_execution", "hibernate")

    def __init__(self, settings: Settings, audit_repo: AuditEventRepository | None = None):
        self._settings = settings
        self._audit_repo = audit_repo

    @property
    def enabled(self) -> bool:
        return bool(self._settings.remote_workspace_persistent_enabled)

    def _latest_persistent_session(self, workspace_id: str) -> dict[str, Any] | None:
        if self._audit_repo is None or not workspace_id:
            return None
        latest: dict[str, Any] | None = None
        events = self._audit_repo.list_recent(event_type_prefix="remote.workspace.persistent.session.saved", limit=1200)
        ordered = sorted(
            events,
            key=lambda event: event_order_timestamp(event.event_payload if isinstance(event.event_payload, dict) else {}, event.occurred_at),
        )
        for event in ordered:
            payload = event.event_payload if isinstance(event.event_payload, dict) else {}
            if str(payload.get("workspace_id") or "") != workspace_id:
                continue
            latest = {**payload, "occurred_at": event.occurred_at.isoformat()}
        return latest

    def _latest_snapshot(self, workspace_id: str) -> dict[str, Any] | None:
        if self._audit_repo is None or not workspace_id:
            return None
        latest: dict[str, Any] | None = None
        events = self._audit_repo.list_recent(event_type_prefix="remote.workspace.snapshot.saved", limit=1200)
        ordered = sorted(
            events,
            key=lambda event: event_order_timestamp(event.event_payload if isinstance(event.event_payload, dict) else {}, event.occurred_at),
        )
        for event in ordered:
            payload = event.event_payload if isinstance(event.event_payload, dict) else {}
            if str(payload.get("workspace_id") or "") != workspace_id:
                continue
            latest = snapshot_from_payload({**payload, "occurred_at": event.occurred_at})
        return latest

    def _session_runtime_metadata(self, request: WorkspaceExecutionRequest) -> dict[str, Any]:
        session = self._latest_persistent_session(request.workspace_id) or {}
        snapshot = self._latest_snapshot(request.workspace_id) or {}
        provider = str(session.get("provider") or self._settings.remote_workspace_persistent_provider)
        session_status = str(session.get("status") or ("active" if self.enabled else "disabled"))
        attach_token = f"{provider}:{request.workspace_id}:attach"
        return {
            **(request.metadata or {}),
            "persistent_workspace": {
                "workspace_id": request.workspace_id,
                "provider": provider,
                "session_status": session_status,
                "hibernate_supported": bool(session.get("hibernate_supported", True)),
                "idle_timeout_minutes": int(session.get("idle_timeout_minutes") or self._settings.remote_workspace_persistent_idle_timeout_minutes),
                "ttl_hours": int(session.get("ttl_hours") or self._settings.remote_workspace_persistent_ttl_hours),
                "expires_at": session.get("expires_at"),
                "last_resumed_at": session.get("last_resumed_at"),
                "resume_supported": session_status in {"active", "hibernated", "resumed"},
                "attach_token": attach_token,
                "artifact_count": len(self.collect_artifacts(request.workspace_id)),
                "snapshot_updated_at": snapshot.get("updated_at").isoformat() if snapshot.get("updated_at") else None,
            },
        }

    def _result(self, request: WorkspaceExecutionRequest, *, status: str, message: str) -> WorkspaceExecutionResult:
        return WorkspaceExecutionResult(
            execution_id=request.execution_id or uuid4().hex,
            workspace_id=request.workspace_id,
            execution_kind=request.execution_kind,
            status=status,
            executor_key=self.key,
            requested_at=datetime.now(UTC),
            message=message,
            metadata=self._session_runtime_metadata(request),
        )

    def prepare_workspace(self, request: WorkspaceExecutionRequest) -> WorkspaceExecutionResult:
        return self._result(request, status="prepared", message="persistent workspace session prepared and attachable")

    def run_checks(self, request: WorkspaceExecutionRequest) -> WorkspaceExecutionResult:
        return self._result(request, status="running", message="persistent workspace executing checks in managed session")

    def apply_patch(self, request: WorkspaceExecutionRequest) -> WorkspaceExecutionResult:
        return self._result(request, status="running", message="persistent workspace applying patch in managed session")

    def collect_artifacts(self, workspace_id: str) -> list[dict[str, Any]]:
        snapshot = self._latest_snapshot(workspace_id) or {}
        return merge_artifact_history(snapshot.get("artifact_history"), snapshot.get("artifacts"))

    def resume_snapshot(self, workspace_id: str) -> dict[str, Any] | None:
        session = self._latest_persistent_session(workspace_id)
        snapshot = self._latest_snapshot(workspace_id)
        if session is None and snapshot is None:
            return None

        artifacts = self.collect_artifacts(workspace_id)
        return {
            "workspace_id": workspace_id,
            "provider": str((session or {}).get("provider") or self._settings.remote_workspace_persistent_provider),
            "session_status": str((session or {}).get("status") or "active"),
            "is_persistent": True,
            "hibernate_supported": bool((session or {}).get("hibernate_supported", True)),
            "artifacts": artifacts,
            "artifact_count": len(artifacts),
            "snapshot": snapshot,
            "expires_at": (session or {}).get("expires_at"),
            "last_resumed_at": (session or {}).get("last_resumed_at") or (snapshot.get("last_resumed_at").isoformat() if snapshot and snapshot.get("last_resumed_at") else None),
        }

    def cancel_execution(self, execution_id: str, metadata: dict[str, Any] | None = None) -> bool:
        del execution_id
        persistent_metadata = (metadata or {}).get("persistent_workspace") if isinstance(metadata, dict) else None
        workspace_id = str((persistent_metadata or {}).get("workspace_id") or "")
        if not workspace_id:
            return False
        return False
