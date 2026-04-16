from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from app.core.auth import AuthContext

from .helpers import (
    _coerce_utc,
    event_order_timestamp,
    merge_artifact_history,
    merge_patch_stack,
    payload_visible_for_tenant,
)
from .payloads import snapshot_from_payload
from .types import EXECUTION_ACTIVE_STATES


class RemoteWorkspaceWriteStateMixin:
    def _recent_rows(self, *, auth: AuthContext, limit: int = 500) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for event in self._audit_repo.list_recent(event_type_prefix="remote.workspace.", limit=limit):
            payload = event.event_payload if isinstance(event.event_payload, dict) else {}
            if payload.get("actor_id") not in {None, auth.user_id} and event.actor_id != auth.user_id:
                continue
            if not payload_visible_for_tenant(payload, auth):
                continue
            rows.append({"event_type": event.event_type, "occurred_at": event.occurred_at, "payload": payload, "actor_id": event.actor_id})
        return rows

    def _execution_states(self, *, auth: AuthContext) -> dict[str, dict[str, Any]]:
        states: dict[str, dict[str, Any]] = {}
        ordered_rows = sorted(self._recent_rows(auth=auth, limit=800), key=lambda row: event_order_timestamp(row["payload"], row["occurred_at"]))
        for row in ordered_rows:
            payload = row["payload"]
            execution_id = str(payload.get("execution_id") or "")
            if not execution_id:
                continue
            current = states.get(execution_id, {})
            current.update(payload)
            current.setdefault("execution_id", execution_id)
            current.setdefault("workspace_id", payload.get("workspace_id"))
            current.setdefault("requested_at", row["occurred_at"].isoformat())
            current["last_updated_at"] = row["occurred_at"].isoformat()
            states[execution_id] = current
        return states

    def _enforce_limits(self, *, auth: AuthContext, requested_executor: str) -> None:
        today = datetime.now(UTC) - timedelta(days=1)
        states = self._execution_states(auth=auth)
        active = sum(1 for item in states.values() if item.get("status") in EXECUTION_ACTIVE_STATES)
        if active >= self._settings.remote_workspace_max_parallel_requests:
            raise HTTPException(status_code=429, detail="remote workspace parallel request limit exceeded")
        recent_count = sum(1 for item in states.values() if _coerce_utc(item.get("requested_at")) >= today)
        if recent_count >= self._settings.remote_workspace_daily_request_limit:
            raise HTTPException(status_code=429, detail="remote workspace daily request limit exceeded")
        if requested_executor == "github_actions" and not self._settings.remote_workspace_github_enabled:
            raise HTTPException(status_code=422, detail="github actions executor is not enabled")

    def save_snapshot(self, *, payload: dict[str, Any], auth: AuthContext) -> dict[str, Any]:
        workspace_id = str(payload.get("workspace_id") or "").strip()
        if not workspace_id:
            workspace_id = f"cycle:{payload.get('cycle_id')}" if payload.get("cycle_id") else f"workspace:{uuid4().hex[:12]}"
        now = datetime.now(UTC)
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        event_payload = {
            "workspace_id": workspace_id,
            "cycle_id": payload.get("cycle_id"),
            "project_id": payload.get("project_id"),
            "repo_url": payload.get("repo_url"),
            "repo_branch": payload.get("repo_branch"),
            "repo_ref": payload.get("repo_ref"),
            "patch": payload.get("patch"),
            "patch_stack": merge_patch_stack(payload.get("patch"), payload.get("patch_stack"), metadata.get("patch_stack")),
            "execution_profile": payload.get("execution_profile"),
            "executor_key": payload.get("executor_key") or self._settings.remote_workspace_default_executor,
            "last_execution_status": payload.get("last_execution_status"),
            "last_execution_kind": payload.get("last_execution_kind"),
            "last_execution_requested_at": payload.get("last_execution_requested_at"),
            "artifacts": payload.get("artifacts") or [],
            "artifact_history": merge_artifact_history(payload.get("artifact_history"), payload.get("artifacts") or []),
            "metadata": metadata,
            "tenant_id": auth.tenant_id,
            "updated_at": now.isoformat(),
            "resume_count": int(payload.get("resume_count") or 0),
            "last_resumed_at": payload.get("last_resumed_at"),
            "actor_id": auth.user_id,
        }
        with self._uow:
            self._audit_repo.add(event_type="remote.workspace.snapshot.saved", actor_id=auth.user_id, cycle_id=payload.get("cycle_id"), event_payload=event_payload)
            self._uow.commit()
        return snapshot_from_payload(event_payload)

    def _find_execution_state_any(self, execution_id: str) -> dict[str, Any] | None:
        merged: dict[str, Any] = {}
        found = False
        events = self._audit_repo.list_recent(event_type_prefix="remote.workspace.execution.", limit=2000)
        ordered = sorted(events, key=lambda event: event_order_timestamp(event.event_payload if isinstance(event.event_payload, dict) else {}, event.occurred_at))
        for event in ordered:
            payload = event.event_payload if isinstance(event.event_payload, dict) else {}
            if str(payload.get("execution_id") or "") != execution_id:
                continue
            merged.update(payload)
            merged["execution_id"] = execution_id
            merged["last_updated_at"] = payload.get("last_updated_at") or event.occurred_at.isoformat()
            found = True
        return merged if found else None

    def _resume_state_for_workspace(self, workspace_id: str, auth: AuthContext) -> dict[str, Any]:
        state: dict[str, Any] = {"resume_count": 0, "last_resumed_at": None}
        for event in self._audit_repo.list_recent(event_type_prefix="remote.workspace.resume.", limit=400):
            payload = event.event_payload if isinstance(event.event_payload, dict) else {}
            if str(payload.get("workspace_id") or "") != workspace_id:
                continue
            if payload.get("actor_id") not in {None, auth.user_id} and event.actor_id != auth.user_id:
                continue
            if not payload_visible_for_tenant(payload, auth):
                continue
            state["resume_count"] = int(payload.get("resume_count") or state.get("resume_count") or 0)
            state["last_resumed_at"] = payload.get("last_resumed_at") or event.occurred_at.isoformat()
        return state

    def _snapshot_state_any(self, workspace_id: str) -> dict[str, Any] | None:
        found: dict[str, Any] | None = None
        events = self._audit_repo.list_recent(event_type_prefix="remote.workspace.snapshot.saved", limit=1200)
        ordered = sorted(events, key=lambda event: event_order_timestamp(event.event_payload if isinstance(event.event_payload, dict) else {}, event.occurred_at))
        for event in ordered:
            payload = event.event_payload if isinstance(event.event_payload, dict) else {}
            if str(payload.get("workspace_id") or "") != workspace_id:
                continue
            found = snapshot_from_payload({**payload, "occurred_at": event.occurred_at})
        return found
