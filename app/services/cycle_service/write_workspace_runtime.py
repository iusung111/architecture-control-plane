from __future__ import annotations

from .runtime_registration import _runtime_registration_from_audit
from app.core.auth import AuthContext
from datetime import datetime, timezone
from typing import Any


class CycleWriteWorkspaceRuntimeMixin:
    def register_runtime(self, *, payload: dict[str, Any], auth: AuthContext) -> dict[str, Any]:
        heartbeat_at = datetime.now(timezone.utc).isoformat()

        with self._uow:
            event = self._audit_repo.add(
                event_type="runtime.registration.heartbeat",
                actor_id=auth.user_id,
                event_payload={
                    "runtime_id": payload.get("runtime_id"),
                    "workspace_id": payload.get("workspace_id"),
                    "project_id": payload.get("project_id"),
                    "tenant_id": auth.tenant_id,
                    "label": payload.get("label"),
                    "status": payload.get("status"),
                    "mode": payload.get("mode"),
                    "version": payload.get("version"),
                    "capabilities": payload.get("capabilities") or [],
                    "metadata": payload.get("metadata") or {},
                    "heartbeat_at": heartbeat_at,
                },
            )
            self._uow.commit()

        return _runtime_registration_from_audit(event)
