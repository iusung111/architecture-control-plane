from __future__ import annotations

from .runtime_helpers import _payload_visible_for_tenant
from .timeline import _coerce_utc
from app.core.auth import AuthContext
from app.db.models import AuditEvent
from app.repositories.audit import AuditEventRepository
from datetime import datetime, timezone
from math import exp
from typing import Any


def _feedback_decay_factor(
    occurred_at: datetime | None, *, now: datetime | None = None, half_life_days: float = 14.0
) -> float:
    if occurred_at is None:
        return 0.0
    reference = _coerce_utc(now or datetime.now(timezone.utc))
    age_seconds = max((reference - _coerce_utc(occurred_at)).total_seconds(), 0.0)
    if half_life_days <= 0:
        return 1.0
    decay_constant = 0.6931471805599453 / (half_life_days * 86400.0)
    return round(exp(-decay_constant * age_seconds), 4)


def _remote_assignment_outcomes(
    audit_repo: AuditEventRepository, *, project_id: str, auth: AuthContext, limit: int = 800
) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for event in reversed(
        audit_repo.list_recent(event_type_prefix="remote.workspace.execution.", limit=limit)
    ):
        payload = event.event_payload if isinstance(event.event_payload, dict) else {}
        if payload.get("project_id") != project_id:
            continue
        if not _payload_visible_for_tenant(payload, auth):
            continue
        execution_id = str(payload.get("execution_id") or "")
        if not execution_id:
            continue
        current = merged.get(execution_id, {})
        current.update(payload)
        current["last_updated_at"] = payload.get("last_updated_at") or event.occurred_at.isoformat()
        merged[execution_id] = current
    by_agent: dict[str, dict[str, Any]] = {}
    for row in merged.values():
        agent_id = str(
            row.get("assigned_agent_id") or row.get("metadata", {}).get("assigned_agent_id")
            if isinstance(row.get("metadata"), dict)
            else ""
        )
        if not agent_id:
            continue
        status = str(row.get("status") or "")
        stats = by_agent.setdefault(
            agent_id,
            {
                "remote_success_count": 0,
                "remote_failure_count": 0,
                "remote_total_count": 0,
                "last_remote_status": None,
                "last_remote_at": None,
            },
        )
        if status in {"succeeded", "failed", "timed_out", "dispatch_failed", "cancelled"}:
            stats["remote_total_count"] += 1
            if status == "succeeded":
                stats["remote_success_count"] += 1
            else:
                stats["remote_failure_count"] += 1
            occurred_at = row.get("completed_at") or row.get("last_updated_at")
            if stats["last_remote_at"] is None or _coerce_utc(occurred_at) >= _coerce_utc(
                stats["last_remote_at"]
            ):
                stats["last_remote_at"] = occurred_at
                stats["last_remote_status"] = status
    for stats in by_agent.values():
        total = int(stats["remote_total_count"] or 0)
        stats["remote_success_rate"] = (
            round((stats["remote_success_count"] / total), 2) if total else None
        )
    return by_agent


def _assignment_suggestion_feedback_from_audit(event: AuditEvent) -> dict[str, Any]:
    payload = event.event_payload if isinstance(event.event_payload, dict) else {}
    return {
        "feedback_id": event.audit_event_id,
        "cycle_id": event.cycle_id,
        "agent_id": str(payload.get("agent_id") or ""),
        "feedback": str(payload.get("feedback") or ""),
        "note": payload.get("note"),
        "actor_id": event.actor_id,
        "actor_role": payload.get("actor_role"),
        "occurred_at": event.occurred_at,
    }


def _runtime_action_receipt_from_audit(event: AuditEvent) -> dict[str, Any]:
    payload = event.event_payload if isinstance(event.event_payload, dict) else {}
    return {
        "receipt_id": event.audit_event_id,
        "action_id": str(payload.get("action_id") or ""),
        "runtime_id": str(payload.get("runtime_id") or ""),
        "project_id": payload.get("project_id"),
        "workspace_id": payload.get("workspace_id"),
        "summary": str(payload.get("summary") or ""),
        "status": payload.get("status"),
        "actor_id": event.actor_id,
        "actor_role": payload.get("actor_role"),
        "occurred_at": event.occurred_at,
        "metadata": payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
    }


def _cycle_assignment_from_audit(event: AuditEvent) -> dict[str, Any]:
    payload = event.event_payload if isinstance(event.event_payload, dict) else {}
    return {
        "assignment_id": event.audit_event_id,
        "cycle_id": event.cycle_id,
        "agent_id": str(payload.get("agent_id") or ""),
        "assignment_role": str(payload.get("assignment_role") or "primary"),
        "note": payload.get("note"),
        "actor_id": event.actor_id,
        "actor_role": payload.get("actor_role"),
        "occurred_at": event.occurred_at,
    }
