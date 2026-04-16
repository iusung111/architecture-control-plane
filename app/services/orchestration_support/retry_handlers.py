from __future__ import annotations

from app.domain.enums import CycleState
from app.workers.job_runner import JobExecutionError


class RetryHandlersMixin:
    def handle_retry_cycle(self, job) -> None:
        cycle = self._require_cycle(job.cycle_id)
        if cycle.current_state != CycleState.RETRY_SCHEDULED:
            raise JobExecutionError(f"cycle cannot retry from state={cycle.current_state}", retryable=False)
        snapshot = self._get_latest_request_snapshot(cycle.cycle_id)
        self._enqueue_verification_job(cycle, source_job=job, snapshot=snapshot, trigger="retry")
        self._audit.add(
            event_type="cycle.retry_enqueued",
            cycle_id=cycle.cycle_id,
            actor_id=job.payload.get("requested_by"),
            event_payload={"source_job_id": job.job_id},
        )

    def handle_replan_cycle(self, job) -> None:
        cycle = self._require_cycle(job.cycle_id)
        if cycle.current_state != CycleState.REPLAN_REQUESTED:
            raise JobExecutionError(f"cycle cannot replan from state={cycle.current_state}", retryable=False)
        latest_snapshot = self._get_latest_request_snapshot(cycle.cycle_id)
        override_input = {str(key): value for key, value in (job.payload.get("override_input") or {}).items()}
        merged_snapshot = self._merge_override_input(latest_snapshot, override_input)
        snapshot_receipt = self._store_request_snapshot(cycle.cycle_id, merged_snapshot, summary="replan request snapshot")
        self._enqueue_verification_job(
            cycle,
            source_job=job,
            snapshot=merged_snapshot,
            trigger="replan",
            input_snapshot_ref=snapshot_receipt.receipt_id,
        )
        self._audit.add(
            event_type="cycle.replan_enqueued",
            cycle_id=cycle.cycle_id,
            actor_id=job.payload.get("requested_by"),
            event_payload={"source_job_id": job.job_id, "override_input": override_input},
        )
