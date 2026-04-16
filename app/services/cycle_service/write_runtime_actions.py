from __future__ import annotations

from .runtime_helpers import (
    _build_runtime_action_view,
    _merge_runtime_action_updates,
    _runtime_action_from_audit,
    _runtime_action_receipt_from_audit,
)
from .runtime_registration import _get_latest_runtime_registration_event
from app.core.auth import AuthContext
from datetime import datetime, timezone
from typing import Any


_ALLOWED_RUNTIME_ACTION_STATUSES = {"running", "succeeded", "failed", "cancelled"}


class CycleWriteRuntimeActionMixin:
    def enqueue_runtime_action(
        self, *, runtime_id: str, action: str, arguments: dict[str, Any], auth: AuthContext
    ) -> dict[str, Any]:
        registration = _get_latest_runtime_registration_event(
            self._audit_repo,
            auth=auth,
            runtime_id=runtime_id,
        )
        if registration is None:
            raise ValueError("runtime not found")

        registration_payload = (
            registration.event_payload if isinstance(registration.event_payload, dict) else {}
        )
        now = datetime.now(timezone.utc).isoformat()

        with self._uow:
            event = self._audit_repo.add(
                event_type="runtime.action.enqueued",
                actor_id=auth.user_id,
                event_payload={
                    "runtime_id": runtime_id,
                    "workspace_id": registration_payload.get("workspace_id"),
                    "project_id": registration_payload.get("project_id"),
                    "tenant_id": registration_payload.get("tenant_id", auth.tenant_id),
                    "label": registration_payload.get("label"),
                    "action": action.strip(),
                    "arguments": arguments or {},
                    "status": "queued",
                    "actor_role": auth.role,
                    "last_updated_at": now,
                },
            )
            self._uow.commit()

        return _runtime_action_from_audit(event)

    def acknowledge_runtime_action(
        self, *, runtime_id: str, action_id: str, note: str | None, auth: AuthContext
    ) -> dict[str, Any]:
        registration = _get_latest_runtime_registration_event(
            self._audit_repo,
            auth=auth,
            runtime_id=runtime_id,
        )
        if registration is None:
            raise ValueError("runtime not found")

        base = _build_runtime_action_view(
            self._audit_repo,
            auth=auth,
            runtime_id=runtime_id,
            action_id=action_id,
        )
        if base is None:
            raise ValueError("action not found")

        registration_payload = (
            registration.event_payload if isinstance(registration.event_payload, dict) else {}
        )
        now = datetime.now(timezone.utc)

        with self._uow:
            event = self._audit_repo.add(
                event_type="runtime.action.acknowledged",
                actor_id=auth.user_id,
                event_payload={
                    "action_id": action_id,
                    "runtime_id": runtime_id,
                    "workspace_id": registration_payload.get("workspace_id"),
                    "project_id": registration_payload.get("project_id"),
                    "tenant_id": registration_payload.get("tenant_id", auth.tenant_id),
                    "action": base.get("action"),
                    "arguments": base.get("arguments") or {},
                    "status": "acknowledged",
                    "note": note.strip() if note else None,
                    "actor_role": auth.role,
                    "acknowledged_at": now.isoformat(),
                    "acknowledged_by": auth.user_id,
                    "last_updated_at": now.isoformat(),
                },
            )
            self._uow.commit()

        return _merge_runtime_action_updates(base, [event])

    def transition_runtime_action_state(
        self,
        *,
        runtime_id: str,
        action_id: str,
        status: str,
        note: str | None,
        metadata: dict[str, Any],
        auth: AuthContext,
    ) -> dict[str, Any]:
        normalized_status = status.strip().lower()
        if normalized_status not in _ALLOWED_RUNTIME_ACTION_STATUSES:
            raise ValueError("invalid runtime action status")

        registration = _get_latest_runtime_registration_event(
            self._audit_repo,
            auth=auth,
            runtime_id=runtime_id,
        )
        if registration is None:
            raise ValueError("runtime not found")

        base = _build_runtime_action_view(
            self._audit_repo,
            auth=auth,
            runtime_id=runtime_id,
            action_id=action_id,
        )
        if base is None:
            raise ValueError("action not found")

        registration_payload = (
            registration.event_payload if isinstance(registration.event_payload, dict) else {}
        )
        now = datetime.now(timezone.utc)
        terminal_status = normalized_status in {"succeeded", "failed", "cancelled"}

        with self._uow:
            self._audit_repo.add(
                event_type="runtime.action.state_changed",
                actor_id=auth.user_id,
                event_payload={
                    "action_id": action_id,
                    "runtime_id": runtime_id,
                    "workspace_id": registration_payload.get("workspace_id"),
                    "project_id": registration_payload.get("project_id"),
                    "tenant_id": registration_payload.get("tenant_id", auth.tenant_id),
                    "action": base.get("action"),
                    "arguments": base.get("arguments") or {},
                    "status": normalized_status,
                    "note": note.strip() if note else None,
                    "metadata": metadata or {},
                    "actor_role": auth.role,
                    "acknowledged_at": base.get("acknowledged_at").isoformat()
                    if isinstance(base.get("acknowledged_at"), datetime)
                    else None,
                    "acknowledged_by": base.get("acknowledged_by"),
                    "last_updated_at": now.isoformat(),
                },
            )

            if terminal_status and (note or metadata):
                self._audit_repo.add(
                    event_type="runtime.action.receipt.recorded",
                    actor_id=auth.user_id,
                    event_payload={
                        "action_id": action_id,
                        "runtime_id": runtime_id,
                        "workspace_id": registration_payload.get("workspace_id"),
                        "project_id": registration_payload.get("project_id"),
                        "tenant_id": registration_payload.get("tenant_id", auth.tenant_id),
                        "summary": (note or f"Action {normalized_status}").strip(),
                        "status": normalized_status,
                        "metadata": metadata or {},
                        "actor_role": auth.role,
                    },
                )

            self._uow.commit()

        refreshed = _build_runtime_action_view(
            self._audit_repo,
            auth=auth,
            runtime_id=runtime_id,
            action_id=action_id,
        )
        if refreshed is None:
            raise ValueError("action not found")

        return refreshed

    def add_runtime_action_receipt(
        self,
        *,
        runtime_id: str,
        action_id: str,
        summary: str,
        status: str | None,
        metadata: dict[str, Any],
        auth: AuthContext,
    ) -> dict[str, Any]:
        registration = _get_latest_runtime_registration_event(
            self._audit_repo,
            auth=auth,
            runtime_id=runtime_id,
        )
        if registration is None:
            raise ValueError("runtime not found")

        action_view = _build_runtime_action_view(
            self._audit_repo,
            auth=auth,
            runtime_id=runtime_id,
            action_id=action_id,
        )
        if action_view is None:
            raise ValueError("action not found")

        registration_payload = (
            registration.event_payload if isinstance(registration.event_payload, dict) else {}
        )
        normalized_status = (
            status.strip().lower()
            if isinstance(status, str) and status.strip()
            else str(action_view.get("status") or "") or None
        )

        with self._uow:
            event = self._audit_repo.add(
                event_type="runtime.action.receipt.recorded",
                actor_id=auth.user_id,
                event_payload={
                    "action_id": action_id,
                    "runtime_id": runtime_id,
                    "workspace_id": registration_payload.get("workspace_id"),
                    "project_id": registration_payload.get("project_id"),
                    "tenant_id": registration_payload.get("tenant_id", auth.tenant_id),
                    "summary": summary.strip(),
                    "status": normalized_status,
                    "metadata": metadata or {},
                    "actor_role": auth.role,
                },
            )
            self._uow.commit()

        return _runtime_action_receipt_from_audit(event)
