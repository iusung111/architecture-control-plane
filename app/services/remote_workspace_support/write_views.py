from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException

from app.core.auth import AuthContext

from .helpers import _coerce_utc, ensure_list_of_strings, workspace_has_active_execution
from .payloads import build_resume_payload
from .persistent import persistent_session_from_payload
from .query_service import RemoteWorkspaceQueryService


class RemoteWorkspaceViewWriteMixin:
    def mark_resumed(self, *, workspace_id: str, auth: AuthContext, note: str | None = None) -> dict[str, object]:
        query = RemoteWorkspaceQueryService(self._audit_repo, self._settings)
        snapshot = query.get_snapshot(workspace_id=workspace_id, auth=auth)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="remote workspace not found")

        resume_state = self._resume_state_for_workspace(workspace_id, auth)
        payload = {
            "workspace_id": workspace_id,
            "cycle_id": snapshot.get("cycle_id"),
            "project_id": snapshot.get("project_id"),
            "resume_count": int(resume_state.get("resume_count") or 0) + 1,
            "last_resumed_at": datetime.now(UTC).isoformat(),
            "note": note,
            "tenant_id": auth.tenant_id,
            "actor_id": auth.user_id,
        }
        with self._uow:
            self._audit_repo.add(event_type="remote.workspace.resume.recorded", actor_id=auth.user_id, cycle_id=snapshot.get("cycle_id"), event_payload=payload)
            if self._settings.remote_workspace_persistent_enabled:
                persistent_current = query.get_persistent_session(workspace_id=workspace_id, auth=auth)
                if persistent_current is not None:
                    self._audit_repo.add(
                        event_type="remote.workspace.persistent.session.saved",
                        actor_id=auth.user_id,
                        cycle_id=snapshot.get("cycle_id"),
                        event_payload={
                            "workspace_id": workspace_id,
                            "cycle_id": snapshot.get("cycle_id"),
                            "project_id": snapshot.get("project_id"),
                            "repo_url": snapshot.get("repo_url"),
                            "repo_branch": snapshot.get("repo_branch"),
                            "repo_ref": snapshot.get("repo_ref"),
                            "provider": persistent_current.get("provider") or self._settings.remote_workspace_persistent_provider,
                            "status": "active",
                            "note": note or persistent_current.get("note"),
                            "created_at": _coerce_utc(persistent_current.get("created_at")).isoformat() if persistent_current.get("created_at") else payload["last_resumed_at"],
                            "updated_at": payload["last_resumed_at"],
                            "last_resumed_at": payload["last_resumed_at"],
                            "idle_timeout_minutes": int(persistent_current.get("idle_timeout_minutes") or self._settings.remote_workspace_persistent_idle_timeout_minutes),
                            "ttl_hours": int(persistent_current.get("ttl_hours") or self._settings.remote_workspace_persistent_ttl_hours),
                            "expires_at": _coerce_utc(persistent_current.get("expires_at")).isoformat() if persistent_current.get("expires_at") else (datetime.now(UTC) + timedelta(hours=self._settings.remote_workspace_persistent_ttl_hours)).isoformat(),
                            "hibernate_supported": bool(persistent_current.get("hibernate_supported", True)),
                            "tenant_id": auth.tenant_id,
                            "actor_id": auth.user_id,
                        },
                    )
            self._uow.commit()
        executions = query.list_executions(workspace_id=workspace_id, auth=auth, limit=10).get("items", [])
        return build_resume_payload(snapshot, executions, payload) or {}

    def save_workbench_view(self, *, payload: dict[str, object], auth: AuthContext) -> dict[str, object]:
        import uuid
        view_id = str(payload.get("view_id") or uuid.uuid4().hex[:16])
        event_payload = {
            "view_id": view_id,
            "name": payload.get("name"),
            "project_id": payload.get("project_id"),
            "cycle_id": payload.get("cycle_id"),
            "workspace_id": payload.get("workspace_id"),
            "query": payload.get("query"),
            "discussion_filter_id": payload.get("discussion_filter_id"),
            "layout": payload.get("layout") if isinstance(payload.get("layout"), dict) else {},
            "selected_panels": ensure_list_of_strings(payload.get("selected_panels")),
            "notes": payload.get("notes"),
            "use_count": int(payload.get("use_count") or 0),
            "last_used_at": payload.get("last_used_at"),
            "is_deleted": False,
            "updated_at": datetime.now(UTC).isoformat(),
            "tenant_id": auth.tenant_id,
            "actor_id": auth.user_id,
        }
        with self._uow:
            self._audit_repo.add(event_type="workbench.view.saved", actor_id=auth.user_id, event_payload=event_payload)
            self._uow.commit()
        query = RemoteWorkspaceQueryService(self._audit_repo, self._settings)
        return query.get_workbench_view(view_id=view_id, auth=auth) or event_payload

    def update_workbench_view(self, *, view_id: str, payload: dict[str, object], auth: AuthContext) -> dict[str, object]:
        query = RemoteWorkspaceQueryService(self._audit_repo, self._settings)
        current = query.get_workbench_view(view_id=view_id, auth=auth)
        if current is None:
            raise HTTPException(status_code=404, detail="workbench view not found")
        merged = {**current, **payload, "view_id": view_id, "updated_at": datetime.now(UTC).isoformat(), "tenant_id": auth.tenant_id, "actor_id": auth.user_id, "is_deleted": False}
        merged["layout"] = payload.get("layout") if isinstance(payload.get("layout"), dict) else current.get("layout", {})
        merged["selected_panels"] = ensure_list_of_strings(payload.get("selected_panels")) or current.get("selected_panels", [])
        with self._uow:
            self._audit_repo.add(event_type="workbench.view.saved", actor_id=auth.user_id, event_payload=merged)
            self._uow.commit()
        return query.get_workbench_view(view_id=view_id, auth=auth) or merged

    def delete_workbench_view(self, *, view_id: str, auth: AuthContext) -> dict[str, object]:
        query = RemoteWorkspaceQueryService(self._audit_repo, self._settings)
        current = query.get_workbench_view(view_id=view_id, auth=auth)
        if current is None:
            raise HTTPException(status_code=404, detail="workbench view not found")
        payload = {**current, "is_deleted": True, "updated_at": datetime.now(UTC).isoformat(), "tenant_id": auth.tenant_id, "actor_id": auth.user_id}
        with self._uow:
            self._audit_repo.add(event_type="workbench.view.deleted", actor_id=auth.user_id, event_payload=payload)
            self._uow.commit()
        return payload

    def mark_workbench_view_used(self, *, view_id: str, auth: AuthContext) -> dict[str, object]:
        query = RemoteWorkspaceQueryService(self._audit_repo, self._settings)
        current = query.get_workbench_view(view_id=view_id, auth=auth)
        if current is None:
            raise HTTPException(status_code=404, detail="workbench view not found")
        now = datetime.now(UTC).isoformat()
        payload = {
            **current,
            "use_count": int(current.get("use_count") or 0) + 1,
            "last_used_at": now,
            "updated_at": now,
            "tenant_id": auth.tenant_id,
            "actor_id": auth.user_id,
            "is_deleted": False,
        }
        with self._uow:
            self._audit_repo.add(event_type="workbench.view.used", actor_id=auth.user_id, event_payload=payload)
            self._uow.commit()
        return query.get_workbench_view(view_id=view_id, auth=auth) or payload

    def save_persistent_session(self, *, payload: dict[str, object], auth: AuthContext) -> dict[str, object]:
        if not self._settings.remote_workspace_persistent_enabled:
            raise HTTPException(status_code=409, detail="persistent workspace track is disabled")
        query = RemoteWorkspaceQueryService(self._audit_repo, self._settings)
        active_items = [
            item for item in query.list_persistent_sessions(auth=auth, limit=500).get("items", [])
            if item.get("status") in {"requested", "active", "resumed", "busy"}
        ]
        workspace_id = str(payload.get("workspace_id") or "").strip()
        if not workspace_id:
            raise HTTPException(status_code=422, detail="workspace_id is required")
        existing = query.get_persistent_session(workspace_id=workspace_id, auth=auth)
        if existing is None and len(active_items) >= self._settings.remote_workspace_persistent_max_active_sessions:
            raise HTTPException(status_code=429, detail="persistent workspace session limit exceeded")
        now = datetime.now(UTC)
        event_payload = {
            "workspace_id": workspace_id,
            "cycle_id": payload.get("cycle_id"),
            "project_id": payload.get("project_id"),
            "repo_url": payload.get("repo_url"),
            "repo_branch": payload.get("repo_branch"),
            "repo_ref": payload.get("repo_ref"),
            "provider": payload.get("provider") or self._settings.remote_workspace_persistent_provider,
            "status": "active",
            "note": payload.get("note"),
            "created_at": existing.get("created_at") if existing else now.isoformat(),
            "updated_at": now.isoformat(),
            "last_resumed_at": now.isoformat(),
            "idle_timeout_minutes": self._settings.remote_workspace_persistent_idle_timeout_minutes,
            "ttl_hours": self._settings.remote_workspace_persistent_ttl_hours,
            "expires_at": (now + timedelta(hours=self._settings.remote_workspace_persistent_ttl_hours)).isoformat(),
            "hibernate_supported": True,
            "tenant_id": auth.tenant_id,
            "actor_id": auth.user_id,
        }
        with self._uow:
            self._audit_repo.add(event_type="remote.workspace.persistent.session.saved", actor_id=auth.user_id, cycle_id=payload.get("cycle_id"), event_payload=event_payload)
            self._uow.commit()
        return persistent_session_from_payload(event_payload)

    def hibernate_persistent_session(self, *, workspace_id: str, auth: AuthContext) -> dict[str, object]:
        query = RemoteWorkspaceQueryService(self._audit_repo, self._settings)
        current = query.get_persistent_session(workspace_id=workspace_id, auth=auth)
        if current is None:
            raise HTTPException(status_code=404, detail="persistent workspace session not found")
        if workspace_has_active_execution(self._audit_repo, workspace_id):
            raise HTTPException(status_code=409, detail="cannot hibernate while a remote workspace execution is still active")
        now = datetime.now(UTC)
        event_payload = {
            "workspace_id": current.get("workspace_id"),
            "cycle_id": current.get("cycle_id"),
            "project_id": current.get("project_id"),
            "repo_url": current.get("repo_url"),
            "repo_branch": current.get("repo_branch"),
            "repo_ref": current.get("repo_ref"),
            "provider": current.get("provider") or self._settings.remote_workspace_persistent_provider,
            "status": "hibernated",
            "note": current.get("note"),
            "created_at": _coerce_utc(current.get("created_at")).isoformat() if current.get("created_at") else now.isoformat(),
            "updated_at": now.isoformat(),
            "last_resumed_at": _coerce_utc(current.get("last_resumed_at")).isoformat() if current.get("last_resumed_at") else None,
            "idle_timeout_minutes": int(current.get("idle_timeout_minutes") or self._settings.remote_workspace_persistent_idle_timeout_minutes),
            "ttl_hours": int(current.get("ttl_hours") or self._settings.remote_workspace_persistent_ttl_hours),
            "expires_at": _coerce_utc(current.get("expires_at")).isoformat() if current.get("expires_at") else None,
            "hibernate_supported": True,
            "tenant_id": auth.tenant_id,
            "actor_id": auth.user_id,
        }
        with self._uow:
            self._audit_repo.add(event_type="remote.workspace.persistent.session.saved", actor_id=auth.user_id, cycle_id=current.get("cycle_id"), event_payload=event_payload)
            self._uow.commit()
        return persistent_session_from_payload(event_payload)

    def delete_persistent_session(self, *, workspace_id: str, auth: AuthContext) -> dict[str, object]:
        query = RemoteWorkspaceQueryService(self._audit_repo, self._settings)
        current = query.get_persistent_session(workspace_id=workspace_id, auth=auth)
        if current is None:
            raise HTTPException(status_code=404, detail="persistent workspace session not found")
        if workspace_has_active_execution(self._audit_repo, workspace_id):
            raise HTTPException(status_code=409, detail="cannot delete while a remote workspace execution is still active")
        now = datetime.now(UTC)
        event_payload = {
            "workspace_id": current.get("workspace_id"),
            "cycle_id": current.get("cycle_id"),
            "project_id": current.get("project_id"),
            "repo_url": current.get("repo_url"),
            "repo_branch": current.get("repo_branch"),
            "repo_ref": current.get("repo_ref"),
            "provider": current.get("provider") or self._settings.remote_workspace_persistent_provider,
            "status": "deleted",
            "note": current.get("note"),
            "created_at": _coerce_utc(current.get("created_at")).isoformat() if current.get("created_at") else now.isoformat(),
            "updated_at": now.isoformat(),
            "last_resumed_at": _coerce_utc(current.get("last_resumed_at")).isoformat() if current.get("last_resumed_at") else None,
            "idle_timeout_minutes": int(current.get("idle_timeout_minutes") or self._settings.remote_workspace_persistent_idle_timeout_minutes),
            "ttl_hours": int(current.get("ttl_hours") or self._settings.remote_workspace_persistent_ttl_hours),
            "expires_at": now.isoformat(),
            "hibernate_supported": bool(current.get("hibernate_supported", True)),
            "tenant_id": auth.tenant_id,
            "actor_id": auth.user_id,
        }
        with self._uow:
            self._audit_repo.add(event_type="remote.workspace.persistent.session.deleted", actor_id=auth.user_id, cycle_id=current.get("cycle_id"), event_payload=event_payload)
            self._uow.commit()
        return persistent_session_from_payload(event_payload)
