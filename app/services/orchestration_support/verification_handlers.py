from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.db.models import Approval, VerificationResult
from app.domain.enums import ApprovalState, CycleState, UserStatus, VerificationStatus
from app.workers.job_runner import JobExecutionError


class VerificationHandlersMixin:
    def handle_resume_after_approval(self, job) -> None:
        cycle = self._require_cycle(job.cycle_id)
        approval_id = job.payload.get("approval_id")
        approval = self._approvals.get_by_id_for_update(approval_id) if approval_id else None
        if not approval or approval.approval_state != ApprovalState.APPROVED:
            raise JobExecutionError("approved approval is required before resuming cycle", retryable=False)
        if cycle.current_state != CycleState.HUMAN_APPROVAL_PENDING:
            raise JobExecutionError(f"cycle cannot resume from state={cycle.current_state}", retryable=False)

        iteration = self._create_iteration(cycle, trigger_reason="resume_after_approval", source_job_id=job.job_id)
        artifact = self._create_output_artifact(cycle, iteration, suffix="approved")
        receipt = self._create_receipt(
            cycle.cycle_id,
            iteration.iteration_id,
            receipt_type="completion_summary",
            summary="Cycle completed after human approval",
            payload={"approval_id": approval.approval_id, "artifact_id": artifact.artifact_id},
        )
        cycle.result_ref = artifact.uri
        self._cycles.update_state(cycle, CycleState.TERMINALIZED, UserStatus.COMPLETED)
        self._outbox.add(cycle.cycle_id, "cycle.completed", {"cycle_id": cycle.cycle_id, "receipt_id": receipt.receipt_id})
        self._audit.add(
            event_type="cycle.completed",
            cycle_id=cycle.cycle_id,
            actor_id=job.payload.get("requested_by"),
            event_payload={"source_job_id": job.job_id, "completion_mode": "approval_resume"},
        )

    def handle_run_verification(self, job) -> None:
        cycle = self._require_cycle(job.cycle_id)
        if cycle.current_state not in {CycleState.INTENT_ACCEPTED, CycleState.RETRY_SCHEDULED, CycleState.REPLAN_REQUESTED}:
            raise JobExecutionError(f"cycle cannot run verification from state={cycle.current_state}", retryable=False)
        snapshot = self._snapshot_from_payload(job.payload)
        iteration = self._create_iteration(cycle, trigger_reason=job.payload.get("trigger", "verification"), source_job_id=job.job_id)
        self._cycles.update_state(cycle, CycleState.EXECUTION_ATTEMPTED, UserStatus.IN_PROGRESS)
        metadata = snapshot.metadata
        verification_failed = self._coerce_bool(metadata.get("force_verification_failure"))
        requires_human_approval = self._coerce_bool(metadata.get("requires_human_approval"))
        llm_routing = self._llm_routing.assign_for_job(
            cycle_id=cycle.cycle_id,
            prompt_type="verification",
            complexity=str(metadata.get("llm_complexity") or "medium"),
            review_required=self._coerce_bool(metadata.get("llm_review_required")) or self._coerce_bool(metadata.get("requires_llm_review")),
            tenant_id=snapshot.tenant_id,
            project_id=snapshot.project_id,
        )

        artifact = self._create_output_artifact(cycle, iteration, suffix=job.payload.get("trigger", "run"))
        failed_rules: list[str] = []
        summary = "Verification passed"
        verification_status = VerificationStatus.PASSED
        if verification_failed:
            failed_rules = ["force_verification_failure"]
            summary = "Verification failed due to execution policy"
            verification_status = VerificationStatus.FAILED

        verification = VerificationResult(
            verification_id=uuid4().hex,
            cycle_id=cycle.cycle_id,
            iteration_id=iteration.iteration_id,
            verification_status=verification_status,
            failed_rules=failed_rules,
            summary=summary,
            raw_payload={
                "job_id": job.job_id,
                "trigger": job.payload.get("trigger"),
                "metadata": metadata,
                "override_input": snapshot.override_input,
                "llm_routing": llm_routing,
            },
        )
        self._db.add(verification)

        if llm_routing.get("work"):
            self._audit.add(event_type="llm.work_assigned", cycle_id=cycle.cycle_id, actor_id=job.payload.get("requested_by"), event_payload=llm_routing["work"])
        if llm_routing.get("review"):
            self._audit.add(event_type="llm.review_assigned", cycle_id=cycle.cycle_id, actor_id=job.payload.get("requested_by"), event_payload=llm_routing["review"])

        if verification_status == VerificationStatus.FAILED:
            self._create_receipt(cycle.cycle_id, iteration.iteration_id, receipt_type="verification_failure", summary=summary, payload={"failed_rules": failed_rules, "artifact_id": artifact.artifact_id})
            self._cycles.update_state(cycle, CycleState.VERIFICATION_FAILED, UserStatus.ACTION_REQUIRED)
            self._outbox.add(cycle.cycle_id, "cycle.verification_failed", {"cycle_id": cycle.cycle_id, "failed_rules": failed_rules})
            self._audit.add(event_type="cycle.verification_failed", cycle_id=cycle.cycle_id, actor_id=job.payload.get("requested_by"), event_payload={"source_job_id": job.job_id, "failed_rules": failed_rules})
            return

        if requires_human_approval:
            approval = Approval(
                approval_id=uuid4().hex,
                cycle_id=cycle.cycle_id,
                approval_state=ApprovalState.PENDING,
                required_role=str(metadata.get("required_role") or "approver"),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=self._settings.approval_expiry_hours),
            )
            self._db.add(approval)
            self._cycles.set_active_approval(cycle, approval.approval_id)
            self._cycles.update_state(cycle, CycleState.HUMAN_APPROVAL_PENDING, UserStatus.APPROVAL_REQUIRED)
            self._create_receipt(cycle.cycle_id, iteration.iteration_id, receipt_type="approval_gate", summary="Verification passed and cycle is waiting for human approval", payload={"approval_id": approval.approval_id, "required_role": approval.required_role})
            self._outbox.add(cycle.cycle_id, "approval.requested", {"cycle_id": cycle.cycle_id, "approval_id": approval.approval_id, "required_role": approval.required_role})
            self._audit.add(event_type="approval.requested", cycle_id=cycle.cycle_id, approval_id=approval.approval_id, actor_id=job.payload.get("requested_by"), event_payload={"source_job_id": job.job_id, "required_role": approval.required_role})
            return

        receipt = self._create_receipt(cycle.cycle_id, iteration.iteration_id, receipt_type="completion_summary", summary="Cycle completed without manual approval", payload={"artifact_id": artifact.artifact_id, "verification_status": verification.verification_status})
        cycle.result_ref = artifact.uri
        self._cycles.update_state(cycle, CycleState.TERMINALIZED, UserStatus.COMPLETED)
        self._outbox.add(cycle.cycle_id, "cycle.completed", {"cycle_id": cycle.cycle_id, "receipt_id": receipt.receipt_id})
        self._audit.add(event_type="cycle.completed", cycle_id=cycle.cycle_id, actor_id=job.payload.get("requested_by"), event_payload={"source_job_id": job.job_id, "completion_mode": "automatic"})
