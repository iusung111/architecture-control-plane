from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Artifact, Cycle, CycleIteration, Receipt
from app.domain.enums import JobType
from app.repositories.approvals import ApprovalRepository
from app.repositories.audit import AuditEventRepository
from app.repositories.cycles import CycleRepository
from app.repositories.jobs import JobRepository
from app.repositories.outbox import OutboxRepository
from app.services.llm_management import LLMRoutingService
from app.workers.job_runner import JobExecutionError

from .models import ExecutionSnapshot


class OrchestrationBase:
    def __init__(self, db: Session):
        self._db = db
        self._cycles = CycleRepository(db)
        self._jobs = JobRepository(db)
        self._outbox = OutboxRepository(db)
        self._approvals = ApprovalRepository(db)
        self._audit = AuditEventRepository(db)
        self._settings = get_settings()
        self._llm_routing = LLMRoutingService(db, self._settings)

    def _require_cycle(self, cycle_id: str | None) -> Cycle:
        if not cycle_id:
            raise JobExecutionError("job is missing cycle_id", retryable=False)
        cycle = self._cycles.get_by_id_for_update(cycle_id)
        if not cycle:
            raise JobExecutionError("cycle not found", retryable=False)
        return cycle

    def _enqueue_verification_job(self, cycle: Cycle, *, source_job, snapshot: ExecutionSnapshot, trigger: str, input_snapshot_ref: str | None = None) -> None:
        self._jobs.enqueue(
            cycle_id=cycle.cycle_id,
            job_type=JobType.RUN_VERIFICATION,
            payload={
                **snapshot.model_dump(),
                "trigger": trigger,
                "requested_by": source_job.payload.get("requested_by"),
                "source_job_id": source_job.job_id,
                "input_snapshot_ref": input_snapshot_ref,
            },
            dedup_key=f"run_verification:{source_job.job_id}",
            max_attempts=3,
            priority=80,
        )
        self._outbox.add(cycle.cycle_id, "cycle.execution_enqueued", {"cycle_id": cycle.cycle_id, "source_job_id": source_job.job_id})

    def _get_latest_request_snapshot(self, cycle_id: str) -> ExecutionSnapshot:
        receipt = self._db.execute(
            select(Receipt)
            .where(Receipt.cycle_id == cycle_id, Receipt.receipt_type == "request_snapshot")
            .order_by(Receipt.created_at.desc())
        ).scalars().first()
        if not receipt:
            raise JobExecutionError("cycle request snapshot not found", retryable=False)
        return self._snapshot_from_payload(receipt.payload)

    def _snapshot_from_payload(self, payload: dict[str, Any] | None) -> ExecutionSnapshot:
        payload = payload or {}
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        override_input = payload.get("override_input") if isinstance(payload.get("override_input"), dict) else {}
        input_artifacts = payload.get("input_artifacts") if isinstance(payload.get("input_artifacts"), list) else []
        user_input = payload.get("user_input")
        if not isinstance(user_input, str) or not user_input:
            raise JobExecutionError("execution snapshot is missing user_input", retryable=False)
        return ExecutionSnapshot(
            project_id=str(payload.get("project_id") or ""),
            user_input=user_input,
            tenant_id=payload.get("tenant_id") if isinstance(payload.get("tenant_id"), str) else None,
            input_artifacts=input_artifacts,
            metadata={str(key): value for key, value in metadata.items()},
            override_input={str(key): value for key, value in override_input.items()},
        )

    def _merge_override_input(self, snapshot: ExecutionSnapshot, override_input: dict[str, Any]) -> ExecutionSnapshot:
        metadata = dict(snapshot.metadata)
        normalized_override = {str(key): self._normalize_override_value(value) for key, value in override_input.items()}
        metadata.update({key: value for key, value in normalized_override.items() if key != "user_input"})
        return ExecutionSnapshot(
            project_id=snapshot.project_id,
            user_input=str(normalized_override.get("user_input", snapshot.user_input)),
            tenant_id=snapshot.tenant_id,
            input_artifacts=list(snapshot.input_artifacts),
            metadata=metadata,
            override_input=normalized_override,
        )

    def _store_request_snapshot(self, cycle_id: str, snapshot: ExecutionSnapshot, *, summary: str) -> Receipt:
        return self._create_receipt(cycle_id, None, receipt_type="request_snapshot", summary=summary, payload=snapshot.model_dump())

    def _create_iteration(self, cycle: Cycle, *, trigger_reason: str, source_job_id: str | None) -> CycleIteration:
        cycle.latest_iteration_no += 1
        iteration = CycleIteration(
            iteration_id=uuid4().hex,
            cycle_id=cycle.cycle_id,
            iteration_no=cycle.latest_iteration_no,
            trigger_reason=trigger_reason,
            source_job_id=source_job_id,
            input_snapshot_ref=cycle.result_ref,
        )
        self._db.add(iteration)
        return iteration

    def _create_output_artifact(self, cycle: Cycle, iteration: CycleIteration, *, suffix: str) -> Artifact:
        artifact = Artifact(
            artifact_id=uuid4().hex,
            cycle_id=cycle.cycle_id,
            iteration_id=iteration.iteration_id,
            artifact_type="result_summary",
            uri=f"memory://cycles/{cycle.cycle_id}/artifacts/{suffix}-{iteration.iteration_no}.json",
            content_type="application/json",
            metadata_={"iteration_no": iteration.iteration_no, "suffix": suffix},
        )
        self._db.add(artifact)
        return artifact

    def _create_receipt(self, cycle_id: str, iteration_id: str | None, *, receipt_type: str, summary: str, payload: dict[str, Any]) -> Receipt:
        receipt = Receipt(
            receipt_id=uuid4().hex,
            cycle_id=cycle_id,
            iteration_id=iteration_id,
            receipt_type=receipt_type,
            summary=summary,
            payload=payload,
        )
        self._db.add(receipt)
        return receipt

    @staticmethod
    def _coerce_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y", "on"}
        if isinstance(value, (int, float)):
            return bool(value)
        return False

    @staticmethod
    def _normalize_override_value(value: Any) -> Any:
        if not isinstance(value, str):
            return value
        lowered = value.strip().lower()
        if lowered in {"true", "false"}:
            return lowered == "true"
        try:
            return json.loads(value)
        except Exception:
            return value
