from __future__ import annotations

from datetime import datetime, timezone
from subprocess import TimeoutExpired

from app.db.models import Job
from app.domain.enums import JobState, JobType
from app.repositories.audit import AuditEventRepository
from app.repositories.jobs import JobRepository
from app.workers.job_runner import JobCancelledError, JobExecutionError


class DrillServiceMixin:
    def enqueue_backup_drill(
        self,
        *,
        request_id: str,
        idempotency_key: str,
        actor_id: str,
        management_role: str,
        management_key_source: str,
        management_key_fingerprint: str,
        target_name: str | None = None,
        label: str | None = None,
        restore_from_object_store: bool | None = None,
    ) -> dict[str, object]:
        plan = self.build_backup_drill_execution_plan(
            target_name=target_name,
            label=label,
            restore_from_object_store=restore_from_object_store,
        )
        jobs = JobRepository(self._db)
        dedup_key = f"backup_restore_drill:{idempotency_key}"
        existing = jobs.get_by_dedup_key(dedup_key)
        if existing is not None and existing.job_type == JobType.BACKUP_RESTORE_DRILL:
            payload = dict(existing.payload or {}) if isinstance(existing.payload, dict) else {}
            return {
                "job_id": existing.job_id,
                "action": "backup_restore_drill",
                "accepted": True,
                "deduplicated": True,
                "target_name": str(payload.get("target_name") or plan.target_name),
                "state": existing.job_state,
                "stage": str(payload.get("stage") or "queued"),
                "status_url": f"/v1/admin/ops/backups/drill/jobs/{existing.job_id}",
            }

        job = jobs.enqueue(
            cycle_id=None,
            job_type=JobType.BACKUP_RESTORE_DRILL,
            payload={
                "operation": "backup_restore_drill",
                "request_id": request_id,
                "idempotency_key": idempotency_key,
                "target_name": plan.target_name,
                "label": plan.label,
                "restore_from_object_store": plan.restore_from_object_store,
                "queued_at": datetime.now(timezone.utc).isoformat(),
                "status": "queued",
                "stage": "queued",
                "cancellation_requested": False,
                "requested_by": {
                    "actor_id": actor_id,
                    "management_role": management_role,
                    "management_key_source": management_key_source,
                    "management_key_fingerprint": management_key_fingerprint,
                },
            },
            dedup_key=dedup_key,
            max_attempts=1,
            priority=50,
        )
        self._db.flush()
        return {
            "job_id": job.job_id,
            "action": "backup_restore_drill",
            "accepted": True,
            "deduplicated": False,
            "target_name": plan.target_name,
            "state": job.job_state,
            "stage": "queued",
            "status_url": f"/v1/admin/ops/backups/drill/jobs/{job.job_id}",
        }

    def get_backup_drill_job_status(self, job_id: str) -> dict[str, object] | None:
        job = self._db.get(Job, job_id)
        if job is None or job.job_type != JobType.BACKUP_RESTORE_DRILL:
            return None

        payload = dict(job.payload or {}) if isinstance(job.payload, dict) else {}
        report = payload.get("result")
        accepted_at = job.created_at.isoformat() if job.created_at else payload.get("queued_at")
        updated_at = job.updated_at.isoformat() if job.updated_at else accepted_at
        return {
            "job_id": job.job_id,
            "target_name": str(payload.get("target_name") or "default"),
            "state": job.job_state,
            "stage": str(payload.get("stage") or "queued"),
            "accepted_at": accepted_at,
            "updated_at": updated_at,
            "attempt_count": job.attempt_count,
            "max_attempts": job.max_attempts,
            "cancellation_requested": bool(payload.get("cancellation_requested", False)),
            "report": report,
            "last_error": job.last_error,
        }

    def execute_backup_drill_job(self, job: Job) -> None:
        payload = dict(job.payload or {}) if isinstance(job.payload, dict) else {}
        target_name = payload.get("target_name")
        label = payload.get("label")
        restore_from_object_store = payload.get("restore_from_object_store")
        plan = self.build_backup_drill_execution_plan(
            target_name=target_name if isinstance(target_name, str) else None,
            label=label if isinstance(label, str) else None,
            restore_from_object_store=restore_from_object_store if isinstance(restore_from_object_store, bool) else None,
        )
        payload["started_at"] = datetime.now(timezone.utc).isoformat()
        payload["status"] = "running"
        payload["stage"] = "starting"
        job.payload = payload
        self._db.flush()

        def progress(stage: str) -> None:
            self._db.refresh(job)
            current_payload = dict(job.payload or {}) if isinstance(job.payload, dict) else {}
            if bool(current_payload.get("cancellation_requested")) or job.job_state == JobState.CANCELLED:
                current_payload["status"] = "cancelled"
                current_payload["stage"] = "cancelled"
                current_payload["completed_at"] = datetime.now(timezone.utc).isoformat()
                current_payload["last_error"] = "backup drill cancelled by operator"
                job.payload = current_payload
                self._db.flush()
                self._record_backup_drill_worker_audit(
                    current_payload,
                    event_type="management.backup_drill.cancelled",
                    event_payload={"target_name": plan.target_name, "job_id": job.job_id},
                )
                raise JobCancelledError("backup drill cancelled by operator")

            current_payload["status"] = "running"
            current_payload["stage"] = stage
            job.payload = current_payload
            self._db.flush()

        try:
            from app.services import management_config as management_config_module

            report = management_config_module.run_backup_restore_drill(
                plan.source_url,
                plan.target_url,
                output_dir=plan.output_dir,
                label=plan.label,
                docker_compose_service=plan.compose_service,
                encryption_passphrase=plan.encryption_passphrase,
                prune_keep_last=plan.prune_keep_last,
                prune_max_age_days=plan.prune_max_age_days,
                object_store=plan.object_store,
                restore_from_object_store=plan.restore_from_object_store,
                command_timeout_seconds=plan.command_timeout_seconds,
                progress_callback=progress,
            )
        except JobCancelledError:
            raise
        except TimeoutExpired as exc:
            payload = dict(job.payload or {}) if isinstance(job.payload, dict) else {}
            payload["status"] = "failed"
            payload["stage"] = "failed"
            payload["completed_at"] = datetime.now(timezone.utc).isoformat()
            payload["last_error"] = f"backup drill timed out after {exc.timeout} seconds"
            job.payload = payload
            self._record_backup_drill_worker_audit(
                payload,
                event_type="management.backup_drill.failed",
                event_payload={"target_name": plan.target_name, "error": payload["last_error"]},
            )
            raise JobExecutionError(str(payload["last_error"]), retryable=False) from exc
        except ValueError as exc:
            payload = dict(job.payload or {}) if isinstance(job.payload, dict) else {}
            payload["status"] = "failed"
            payload["stage"] = "failed"
            payload["completed_at"] = datetime.now(timezone.utc).isoformat()
            payload["last_error"] = str(exc)
            job.payload = payload
            self._record_backup_drill_worker_audit(
                payload,
                event_type="management.backup_drill.failed",
                event_payload={"target_name": plan.target_name, "error": str(exc)},
            )
            raise JobExecutionError(str(exc), retryable=False) from exc

        report["target_name"] = plan.target_name
        payload = dict(job.payload or {}) if isinstance(job.payload, dict) else {}
        payload["status"] = "succeeded"
        payload["stage"] = "completed"
        payload["completed_at"] = datetime.now(timezone.utc).isoformat()
        payload["result"] = report
        job.payload = payload
        self._record_backup_drill_worker_audit(
            payload,
            event_type="management.backup_drill.completed",
            event_payload={
                "target_name": plan.target_name,
                "source_database_url": report["source_database_url"],
                "target_database_url": report["target_database_url"],
                "status": report["status"],
                "report_file": report["report_file"],
            },
        )

    def cancel_backup_drill(self, job_id: str, *, requested_by: str | None = None) -> dict[str, object] | None:
        del requested_by
        job = self._db.get(Job, job_id)
        if job is None or job.job_type != JobType.BACKUP_RESTORE_DRILL:
            return None

        payload = dict(job.payload or {}) if isinstance(job.payload, dict) else {}
        if job.job_state in {JobState.SUCCEEDED, JobState.DEAD_LETTERED, JobState.CANCELLED}:
            return self.get_backup_drill_job_status(job_id)

        payload["cancellation_requested"] = True
        payload["cancellation_requested_at"] = datetime.now(timezone.utc).isoformat()
        payload.setdefault("last_error", "backup drill cancelled by operator")
        if job.job_state in {JobState.PENDING, JobState.CLAIMED, JobState.FAILED}:
            payload["status"] = "cancelled"
            payload["stage"] = "cancelled"
            payload["completed_at"] = datetime.now(timezone.utc).isoformat()
            job.payload = payload
            JobRepository(self._db).mark_cancelled(job, error="backup drill cancelled by operator")
        else:
            payload["stage"] = "cancellation_requested"
            job.payload = payload
        self._db.flush()
        return self.get_backup_drill_job_status(job_id)

    def _record_backup_drill_worker_audit(
        self,
        payload: dict[str, object],
        *,
        event_type: str,
        event_payload: dict[str, object],
    ) -> None:
        requested_by = payload.get("requested_by") if isinstance(payload.get("requested_by"), dict) else {}
        AuditEventRepository(self._db).add(
            actor_id=requested_by.get("actor_id") if isinstance(requested_by.get("actor_id"), str) else None,
            event_type=event_type,
            event_payload={
                "request_id": payload.get("request_id"),
                "management_role": requested_by.get("management_role"),
                "management_key_source": requested_by.get("management_key_source"),
                "management_key_fingerprint": requested_by.get("management_key_fingerprint"),
                **event_payload,
            },
        )
