from __future__ import annotations

from typing import Any

from app.core.auth import AuthContext
from app.core.config import Settings
from app.repositories.audit import AuditEventRepository

from .helpers import _coerce_utc, ensure_list_of_strings, event_order_timestamp, merge_artifact_history, payload_visible_for_tenant
from .payloads import build_resume_payload, execution_from_payload, snapshot_from_payload
from .persistent import persistent_session_from_payload
from .registry import RemoteWorkspaceExecutorRegistry


class RemoteWorkspaceQueryService:
    def __init__(self, audit_repo: AuditEventRepository, settings: Settings):
        self._audit_repo = audit_repo
        self._registry = RemoteWorkspaceExecutorRegistry(settings, audit_repo)

    def list_executors(self) -> dict[str, Any]:
        items = self._registry.list()
        default = next((item["key"] for item in items if item["enabled"]), "planning")
        return {"default_executor_key": default, "items": items}

    def _rows(self, *, auth: AuthContext, limit: int = 800) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for event in self._audit_repo.list_recent(event_type_prefix="remote.workspace.", limit=limit):
            payload = event.event_payload if isinstance(event.event_payload, dict) else {}
            actor_ok = event.actor_id in {auth.user_id, "remote-workspace-callback", None} or payload.get("actor_id") == auth.user_id
            if not actor_ok or not payload_visible_for_tenant(payload, auth):
                continue
            rows.append({"event_type": event.event_type, "occurred_at": event.occurred_at, "payload": payload})
        return rows

    def list_snapshots(self, *, auth: AuthContext, project_id: str | None = None, limit: int = 50) -> dict[str, Any]:
        states: dict[str, dict[str, Any]] = {}
        ordered_rows = sorted(self._rows(auth=auth, limit=max(limit, 1) * 20), key=lambda row: event_order_timestamp(row["payload"], row["occurred_at"]))
        for row in ordered_rows:
            payload = row["payload"]
            workspace_id = str(payload.get("workspace_id") or "")
            if not workspace_id:
                continue
            if row["event_type"] == "remote.workspace.snapshot.saved":
                states[workspace_id] = snapshot_from_payload({**payload, "occurred_at": row["occurred_at"]})
                continue
            if not row["event_type"].startswith("remote.workspace.execution"):
                continue

            current = states.setdefault(workspace_id, {"workspace_id": workspace_id, "updated_at": row["occurred_at"], "artifacts": [], "metadata": {}})
            current["last_execution_status"] = payload.get("status") or current.get("last_execution_status")
            current["last_execution_kind"] = payload.get("execution_kind") or current.get("last_execution_kind")
            current["last_execution_requested_at"] = _coerce_utc(payload.get("requested_at") or payload.get("completed_at") or row["occurred_at"])
            current["executor_key"] = payload.get("executor_key") or current.get("executor_key")
            current["updated_at"] = _coerce_utc(payload.get("last_updated_at") or payload.get("completed_at") or row["occurred_at"])
            current["artifacts"] = payload.get("artifacts") or current.get("artifacts", [])
            current["artifact_history"] = merge_artifact_history(current.get("artifact_history"), payload.get("artifacts"))
            current["last_result_summary"] = payload.get("result_summary") or current.get("last_result_summary")
            if payload.get("status") in {"failed", "timed_out", "dispatch_failed"}:
                current["last_failed_command"] = payload.get("command")
            current["last_execution_id"] = payload.get("execution_id") or current.get("last_execution_id")
            current["cycle_id"] = payload.get("cycle_id") or current.get("cycle_id")
            current["project_id"] = payload.get("project_id") or current.get("project_id")

        items = list(states.values())
        if project_id:
            items = [item for item in items if item.get("project_id") == project_id]
        items.sort(key=lambda item: (_coerce_utc(item.get("updated_at")), item.get("workspace_id") or ""), reverse=True)
        limited = items[: min(max(limit, 1), 200)]
        return {"items": limited, "has_more": len(items) > len(limited)}

    def get_snapshot(self, *, workspace_id: str, auth: AuthContext) -> dict[str, Any] | None:
        for item in self.list_snapshots(auth=auth, limit=200).get("items", []):
            if item.get("workspace_id") == workspace_id:
                return item
        return None

    def list_executions(self, *, workspace_id: str, auth: AuthContext, limit: int = 50) -> dict[str, Any]:
        states: dict[str, dict[str, Any]] = {}
        ordered_rows = sorted(self._rows(auth=auth, limit=max(limit, 1) * 20), key=lambda row: event_order_timestamp(row["payload"], row["occurred_at"]))
        for row in ordered_rows:
            payload = row["payload"]
            if str(payload.get("workspace_id") or "") != workspace_id:
                continue
            execution_id = str(payload.get("execution_id") or "")
            if not execution_id:
                continue
            current = states.get(execution_id, {})
            current.update(payload)
            current["execution_id"] = execution_id
            current["workspace_id"] = workspace_id
            current["last_updated_at"] = payload.get("last_updated_at") or row["occurred_at"].isoformat()
            states[execution_id] = current

        items = [execution_from_payload(item) for item in states.values()]
        items.sort(key=lambda item: (_coerce_utc(item.get("last_updated_at")), item.get("execution_id") or ""), reverse=True)
        limited = items[: min(max(limit, 1), 200)]
        return {"workspace_id": workspace_id, "items": limited, "has_more": len(items) > len(limited)}

    def get_execution(self, *, execution_id: str, auth: AuthContext) -> dict[str, Any] | None:
        merged: dict[str, Any] = {}
        found = False
        for row in sorted(self._rows(auth=auth, limit=1000), key=lambda row: event_order_timestamp(row["payload"], row["occurred_at"])):
            payload = row["payload"]
            if str(payload.get("execution_id") or "") != execution_id:
                continue
            merged.update(payload)
            merged["execution_id"] = execution_id
            merged["last_updated_at"] = payload.get("last_updated_at") or row["occurred_at"].isoformat()
            found = True
        return execution_from_payload(merged) if found else None

    def get_resume(self, *, workspace_id: str, auth: AuthContext) -> dict[str, Any] | None:
        snapshot = self.get_snapshot(workspace_id=workspace_id, auth=auth)
        if snapshot is None:
            return None
        executions = self.list_executions(workspace_id=workspace_id, auth=auth, limit=10).get("items", [])
        resume_state = {"resume_count": snapshot.get("resume_count") or 0, "last_resumed_at": snapshot.get("last_resumed_at")}
        for event in self._audit_repo.list_recent(event_type_prefix="remote.workspace.resume.", limit=400):
            payload = event.event_payload if isinstance(event.event_payload, dict) else {}
            if str(payload.get("workspace_id") or "") != workspace_id:
                continue
            actor_ok = event.actor_id in {auth.user_id, None} or payload.get("actor_id") == auth.user_id
            if not actor_ok or not payload_visible_for_tenant(payload, auth):
                continue
            resume_state["resume_count"] = int(payload.get("resume_count") or resume_state.get("resume_count") or 0)
            resume_state["last_resumed_at"] = payload.get("last_resumed_at") or event.occurred_at.isoformat()
        return build_resume_payload(snapshot, executions, resume_state)

    def list_workbench_views(self, *, auth: AuthContext, limit: int = 50) -> dict[str, Any]:
        states: dict[str, dict[str, Any]] = {}
        events = self._audit_repo.list_recent(event_type_prefix="workbench.view.", limit=max(limit, 1) * 20)
        ordered = sorted(events, key=lambda event: event_order_timestamp(event.event_payload if isinstance(event.event_payload, dict) else {}, event.occurred_at))
        for event in ordered:
            payload = event.event_payload if isinstance(event.event_payload, dict) else {}
            view_id = str(payload.get("view_id") or "")
            if not view_id:
                continue
            actor_ok = event.actor_id in {auth.user_id, None} or payload.get("actor_id") == auth.user_id
            if not actor_ok or not payload_visible_for_tenant(payload, auth):
                continue
            current = states.get(view_id, {})
            current.update(payload)
            current["view_id"] = view_id
            current["layout"] = payload.get("layout") if isinstance(payload.get("layout"), dict) else current.get("layout", {})
            current["selected_panels"] = ensure_list_of_strings(payload.get("selected_panels")) or current.get("selected_panels", [])
            current["updated_at"] = payload.get("updated_at") or event.occurred_at.isoformat()
            states[view_id] = current

        items = [item for item in states.values() if not item.get("is_deleted")]
        items.sort(key=lambda item: (_coerce_utc(item.get("last_used_at") or item.get("updated_at")), int(item.get("use_count") or 0), item.get("name") or ""), reverse=True)
        limited = items[: min(max(limit, 1), 200)]
        return {"items": limited, "has_more": len(items) > len(limited)}

    def get_workbench_view(self, *, view_id: str, auth: AuthContext) -> dict[str, Any] | None:
        for item in self.list_workbench_views(auth=auth, limit=200).get("items", []):
            if item.get("view_id") == view_id:
                return item
        return None

    def list_persistent_sessions(self, *, auth: AuthContext, project_id: str | None = None, limit: int = 50) -> dict[str, Any]:
        states: dict[str, dict[str, Any]] = {}
        events = self._audit_repo.list_recent(event_type_prefix="remote.workspace.persistent.", limit=max(limit, 1) * 20)
        ordered = sorted(events, key=lambda event: event_order_timestamp(event.event_payload if isinstance(event.event_payload, dict) else {}, event.occurred_at))
        for event in ordered:
            payload = event.event_payload if isinstance(event.event_payload, dict) else {}
            workspace_id = str(payload.get("workspace_id") or "")
            if not workspace_id:
                continue
            actor_ok = event.actor_id in {auth.user_id, None} or payload.get("actor_id") == auth.user_id
            if not actor_ok or not payload_visible_for_tenant(payload, auth):
                continue
            current = states.get(workspace_id, {})
            current.update(payload)
            current["workspace_id"] = workspace_id
            current["updated_at"] = payload.get("updated_at") or event.occurred_at.isoformat()
            states[workspace_id] = current

        items = [persistent_session_from_payload(item) for item in states.values() if item.get("status") != "deleted"]
        if project_id:
            items = [item for item in items if item.get("project_id") == project_id]
        items.sort(key=lambda item: (_coerce_utc(item.get("updated_at")), item.get("workspace_id") or ""), reverse=True)
        limited = items[: min(max(limit, 1), 200)]
        return {"items": limited, "has_more": len(items) > len(limited)}

    def get_persistent_session(self, *, workspace_id: str, auth: AuthContext) -> dict[str, Any] | None:
        for item in self.list_persistent_sessions(auth=auth, limit=200).get("items", []):
            if item.get("workspace_id") == workspace_id:
                return item
        return None
