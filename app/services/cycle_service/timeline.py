from __future__ import annotations

import json

from app.db.models import Approval, AuditEvent, CycleIteration, Job, Receipt
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class CycleTimelineEvent:
    event_id: str
    source: str
    event_type: str
    title: str
    detail: str | None
    actor_id: str | None
    status: str | None
    occurred_at: datetime
    metadata: dict[str, Any]


def _summarize_payload(payload: dict[str, Any], *, limit: int = 160) -> str | None:
    if not payload:
        return None
    parts: list[str] = []
    for key in ("summary", "reason", "required_role", "completion_mode", "failed_rules", "trigger"):
        value = payload.get(key)
        if value in (None, "", [], {}):
            continue
        if isinstance(value, list):
            rendered = ", ".join(str(item) for item in value)
        elif isinstance(value, dict):
            rendered = json.dumps(value, separators=(",", ":"), sort_keys=True)
        else:
            rendered = str(value)
        parts.append(f"{key}={rendered}")
    if not parts:
        parts.append(json.dumps(payload, separators=(",", ":"), sort_keys=True))
    detail = " · ".join(parts)
    return detail if len(detail) <= limit else detail[: limit - 1] + "…"


def _coerce_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _title_for_audit_event(event: AuditEvent) -> str:
    mapping = {
        "cycle.created": "Cycle created",
        "cycle.retry_requested": "Retry requested",
        "cycle.replan_requested": "Replan requested",
        "cycle.retry_enqueued": "Retry enqueued",
        "cycle.replan_enqueued": "Replan enqueued",
        "cycle.verification_failed": "Verification failed",
        "cycle.completed": "Cycle completed",
        "cycle.terminalized": "Cycle failed terminally",
        "approval.requested": "Approval requested",
        "approval.approved": "Approval approved",
        "approval.rejected": "Approval rejected",
        "approval.expired": "Approval expired",
        "llm.work_assigned": "Work model assigned",
        "llm.review_assigned": "Review model assigned",
        "workspace.comment.reply.added": "Workspace reply added",
        "cycle.assignment.updated": "Cycle assignment updated",
        "runtime.action.enqueued": "Runtime action enqueued",
    }
    return mapping.get(
        event.event_type, event.event_type.replace(".", " ").replace("_", " ").title()
    )


def _timeline_event_from_audit(event: AuditEvent) -> CycleTimelineEvent:
    return CycleTimelineEvent(
        event_id=f"audit:{event.audit_event_id}",
        source="audit",
        event_type=event.event_type,
        title=_title_for_audit_event(event),
        detail=_summarize_payload(event.event_payload),
        actor_id=event.actor_id,
        status=event.event_payload.get("state") if isinstance(event.event_payload, dict) else None,
        occurred_at=event.occurred_at,
        metadata=event.event_payload if isinstance(event.event_payload, dict) else {},
    )


def _timeline_event_from_job(job: Job) -> CycleTimelineEvent:
    return CycleTimelineEvent(
        event_id=f"job:{job.job_id}",
        source="job",
        event_type=f"job.{job.job_type}.{job.job_state}",
        title=f"{job.job_type.replace('_', ' ').title()} job {job.job_state}",
        detail=_summarize_payload(job.payload),
        actor_id=job.payload.get("requested_by") if isinstance(job.payload, dict) else None,
        status=job.job_state,
        occurred_at=job.updated_at or job.created_at,
        metadata={
            "job_id": job.job_id,
            "job_type": job.job_type,
            "job_state": job.job_state,
            "attempt_count": job.attempt_count,
            "max_attempts": job.max_attempts,
        },
    )


def _timeline_event_from_approval(approval: Approval) -> CycleTimelineEvent:
    return CycleTimelineEvent(
        event_id=f"approval:{approval.approval_id}:{approval.approval_state}",
        source="approval",
        event_type=f"approval.{approval.approval_state}",
        title=f"Approval {approval.approval_state}",
        detail=approval.comment
        or approval.reason_code
        or f"required_role={approval.required_role}",
        actor_id=approval.actor_id,
        status=approval.approval_state,
        occurred_at=approval.acted_at or approval.updated_at or approval.created_at,
        metadata={
            "approval_id": approval.approval_id,
            "required_role": approval.required_role,
            "expires_at": approval.expires_at,
        },
    )


def _timeline_event_from_receipt(receipt: Receipt) -> CycleTimelineEvent:
    return CycleTimelineEvent(
        event_id=f"receipt:{receipt.receipt_id}",
        source="receipt",
        event_type=f"receipt.{receipt.receipt_type}",
        title=receipt.receipt_type.replace("_", " ").title(),
        detail=receipt.summary or _summarize_payload(receipt.payload),
        actor_id=None,
        status=receipt.receipt_type,
        occurred_at=receipt.created_at,
        metadata=receipt.payload or {},
    )


def _timeline_event_from_iteration(iteration: CycleIteration) -> CycleTimelineEvent:
    return CycleTimelineEvent(
        event_id=f"iteration:{iteration.iteration_id}",
        source="iteration",
        event_type=f"iteration.{iteration.trigger_reason}",
        title=f"Iteration {iteration.iteration_no} created",
        detail=f"trigger={iteration.trigger_reason}",
        actor_id=None,
        status=iteration.trigger_reason,
        occurred_at=iteration.created_at,
        metadata={
            "iteration_id": iteration.iteration_id,
            "iteration_no": iteration.iteration_no,
            "source_job_id": iteration.source_job_id,
        },
    )
