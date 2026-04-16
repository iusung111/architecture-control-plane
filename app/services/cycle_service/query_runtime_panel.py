from __future__ import annotations

from .runtime_registration import _runtime_registration_from_audit
from .timeline import _coerce_utc, _timeline_event_from_job
from app.core.auth import AuthContext
from app.db.models import AuditEvent
from app.domain.enums import JobState, OutboxDeliveryState
from datetime import datetime, timezone
from typing import Any


def _build_runtime_queue_metrics(jobs: list[Any], outbox: dict[Any, Any]) -> list[dict[str, Any]]:
    return [
        {
            "key": "jobs_pending",
            "label": "Pending jobs",
            "value": sum(1 for job in jobs if job.job_state == JobState.PENDING),
            "detail": "Queued and waiting for workers",
        },
        {
            "key": "jobs_running",
            "label": "Running jobs",
            "value": sum(
                1 for job in jobs if job.job_state in {JobState.CLAIMED, JobState.RUNNING}
            ),
            "detail": "Claimed or actively executing",
        },
        {
            "key": "jobs_failed",
            "label": "Failed jobs",
            "value": sum(
                1 for job in jobs if job.job_state in {JobState.FAILED, JobState.DEAD_LETTERED}
            ),
            "detail": "Needs retry or operator attention",
        },
        {
            "key": "notifications_pending",
            "label": "Pending notifications",
            "value": int(
                outbox.get(OutboxDeliveryState.PENDING, 0)
                + outbox.get(OutboxDeliveryState.FAILED, 0)
            ),
            "detail": "Outbox deliveries not yet completed",
        },
    ]


def _runtime_panel_signals(
    *, queue_metrics: list[dict[str, Any]], outbox: dict[Any, Any]
) -> list[str]:
    signals: list[str] = []

    if queue_metrics[0]["value"] > 5:
        signals.append("Queue is building up; verify worker capacity and Redis health.")

    if queue_metrics[2]["value"] > 0:
        signals.append(
            "At least one job failed or dead-lettered; review retry and audit history."
        )

    pending_notifications = int(
        outbox.get(OutboxDeliveryState.PENDING, 0) + outbox.get(OutboxDeliveryState.FAILED, 0)
    )
    if pending_notifications:
        signals.append(f"{pending_notifications} notifications are still pending delivery.")

    return signals


class CycleQueryRuntimePanelMixin:
    def get_runtime_panel(self, *, auth: AuthContext, project_id: str | None) -> dict[str, Any]:
        jobs = self._cycle_repo.list_jobs_for_owner(
            owner_user_id=auth.user_id,
            tenant_id=auth.tenant_id,
            project_id=project_id,
            limit=80,
        )
        outbox = self._cycle_repo.count_outbox_by_state_for_owner(
            owner_user_id=auth.user_id,
            tenant_id=auth.tenant_id,
            project_id=project_id,
        )

        queue_metrics = _build_runtime_queue_metrics(jobs, outbox)
        recent_jobs = [_timeline_event_from_job(job) for job in jobs[:10]]
        signals = _runtime_panel_signals(queue_metrics=queue_metrics, outbox=outbox)

        return {
            "generated_at": datetime.now(timezone.utc),
            "selected_project_id": project_id,
            "queue_metrics": queue_metrics,
            "recent_jobs": [
                {
                    "event_id": item.event_id,
                    "source": item.source,
                    "event_type": item.event_type,
                    "title": item.title,
                    "detail": item.detail,
                    "actor_id": item.actor_id,
                    "status": item.status,
                    "occurred_at": item.occurred_at,
                    "metadata": item.metadata,
                }
                for item in recent_jobs
            ],
            "outbox_metrics": {str(key): int(value) for key, value in outbox.items()},
            "signals": signals,
        }

    def list_runtime_registrations(
        self, *, auth: AuthContext, project_id: str | None, limit: int = 50
    ) -> dict[str, Any]:
        events = self._audit_repo.list_by_event_type(
            event_type="runtime.registration.heartbeat",
            actor_id=auth.user_id,
            limit=min(max(limit, 1), 200) * 4,
        )

        latest_by_runtime: dict[str, AuditEvent] = {}
        for event in events:
            payload = event.event_payload if isinstance(event.event_payload, dict) else {}
            runtime_id = str(payload.get("runtime_id") or "")

            if not runtime_id:
                continue

            if auth.tenant_id is not None and payload.get("tenant_id") not in {
                auth.tenant_id,
                None,
            }:
                continue

            if project_id and payload.get("project_id") != project_id:
                continue

            current = latest_by_runtime.get(runtime_id)
            if current is None:
                latest_by_runtime[runtime_id] = event
                continue

            current_seen = _runtime_registration_from_audit(current)["occurred_at"]
            event_seen = _runtime_registration_from_audit(event)["occurred_at"]
            if _coerce_utc(event_seen) >= _coerce_utc(current_seen):
                latest_by_runtime[runtime_id] = event

        ordered = sorted(
            latest_by_runtime.values(),
            key=lambda item: (
                _coerce_utc(_runtime_registration_from_audit(item)["occurred_at"]),
                item.audit_event_id,
            ),
            reverse=True,
        )

        return {
            "selected_project_id": project_id,
            "items": [
                _runtime_registration_from_audit(item)
                for item in ordered[: min(max(limit, 1), 200)]
            ],
        }
