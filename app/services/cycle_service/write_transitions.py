from __future__ import annotations

from app.core.auth import AuthContext
from app.db.models import Cycle
from app.domain.enums import CycleState, JobType, UserStatus
from app.domain.guards import ensure_replan_allowed, ensure_retry_allowed
from sqlalchemy.exc import IntegrityError


class CycleWriteTransitionMixin:
    def retry_cycle(
        self, cycle_id: str, reason: str, idempotency_key: str, auth: AuthContext
    ) -> dict:
        locked_cycle: Cycle | None = None
        dedup_key: str | None = None
        try:
            with self._uow:
                locked_cycle = self._cycle_repo.get_by_id_for_update(cycle_id)
                if not locked_cycle:
                    raise ValueError("cycle not found")
                self._ensure_access(locked_cycle, auth)
                dedup_key = (
                    f"retry_cycle:{cycle_id}:{locked_cycle.latest_iteration_no}:{idempotency_key}"
                )
                existing_job = self._job_repo.get_by_dedup_key(dedup_key)
                if existing_job is not None:
                    return {
                        "cycle_id": cycle_id,
                        "action": "retry",
                        "accepted": True,
                        "job_id": existing_job.job_id,
                        "state": locked_cycle.current_state,
                    }
                ensure_retry_allowed(locked_cycle.current_state)
                job = self._job_repo.enqueue(
                    cycle_id=cycle_id,
                    job_type=JobType.RETRY_CYCLE,
                    payload={"cycle_id": cycle_id, "reason": reason, "requested_by": auth.user_id},
                    dedup_key=dedup_key,
                )
                previous_state = locked_cycle.current_state
                self._cycle_repo.update_state(
                    locked_cycle,
                    next_state=CycleState.RETRY_SCHEDULED,
                    user_status=UserStatus.ACTION_REQUIRED,
                )
                self._outbox_repo.add(
                    cycle_id, "cycle.retry_scheduled", {"cycle_id": cycle_id, "job_id": job.job_id}
                )
                self._record_audit_event(
                    event_type="cycle.retry_requested",
                    actor_id=auth.user_id,
                    cycle_id=cycle_id,
                    payload={
                        "job_id": job.job_id,
                        "reason": reason,
                        "from_state": previous_state,
                        "to_state": locked_cycle.current_state,
                        "idempotency_key": idempotency_key,
                    },
                )
                self._uow.commit()
        except IntegrityError:
            self._uow.rollback()
            assert dedup_key is not None
            existing_job = self._job_repo.get_by_dedup_key(dedup_key)
            existing_cycle = self._cycle_repo.get_by_id(cycle_id)
            if existing_job is None or existing_cycle is None:
                raise
            return {
                "cycle_id": cycle_id,
                "action": "retry",
                "accepted": True,
                "job_id": existing_job.job_id,
                "state": existing_cycle.current_state,
            }

        assert locked_cycle is not None
        return {
            "cycle_id": cycle_id,
            "action": "retry",
            "accepted": True,
            "job_id": job.job_id,
            "state": locked_cycle.current_state,
        }

    def replan_cycle(
        self,
        cycle_id: str,
        reason: str,
        override_input: dict[str, str],
        idempotency_key: str,
        auth: AuthContext,
    ) -> dict:
        locked_cycle: Cycle | None = None
        dedup_key: str | None = None
        try:
            with self._uow:
                locked_cycle = self._cycle_repo.get_by_id_for_update(cycle_id)
                if not locked_cycle:
                    raise ValueError("cycle not found")
                self._ensure_access(locked_cycle, auth)
                dedup_key = (
                    f"replan_cycle:{cycle_id}:{locked_cycle.latest_iteration_no}:{idempotency_key}"
                )
                existing_job = self._job_repo.get_by_dedup_key(dedup_key)
                if existing_job is not None:
                    return {
                        "cycle_id": cycle_id,
                        "action": "replan",
                        "accepted": True,
                        "job_id": existing_job.job_id,
                        "state": locked_cycle.current_state,
                    }
                ensure_replan_allowed(locked_cycle.current_state)
                job = self._job_repo.enqueue(
                    cycle_id=cycle_id,
                    job_type=JobType.REPLAN_CYCLE,
                    payload={
                        "cycle_id": cycle_id,
                        "reason": reason,
                        "override_input": override_input,
                        "requested_by": auth.user_id,
                    },
                    dedup_key=dedup_key,
                )
                previous_state = locked_cycle.current_state
                self._cycle_repo.update_state(
                    locked_cycle,
                    next_state=CycleState.REPLAN_REQUESTED,
                    user_status=UserStatus.ACTION_REQUIRED,
                )
                self._outbox_repo.add(
                    cycle_id, "cycle.replan_requested", {"cycle_id": cycle_id, "job_id": job.job_id}
                )
                self._record_audit_event(
                    event_type="cycle.replan_requested",
                    actor_id=auth.user_id,
                    cycle_id=cycle_id,
                    payload={
                        "job_id": job.job_id,
                        "reason": reason,
                        "override_input": override_input,
                        "from_state": previous_state,
                        "to_state": locked_cycle.current_state,
                        "idempotency_key": idempotency_key,
                    },
                )
                self._uow.commit()
        except IntegrityError:
            self._uow.rollback()
            assert dedup_key is not None
            existing_job = self._job_repo.get_by_dedup_key(dedup_key)
            existing_cycle = self._cycle_repo.get_by_id(cycle_id)
            if existing_job is None or existing_cycle is None:
                raise
            return {
                "cycle_id": cycle_id,
                "action": "replan",
                "accepted": True,
                "job_id": existing_job.job_id,
                "state": existing_cycle.current_state,
            }

        assert locked_cycle is not None
        return {
            "cycle_id": cycle_id,
            "action": "replan",
            "accepted": True,
            "job_id": job.job_id,
            "state": locked_cycle.current_state,
        }
