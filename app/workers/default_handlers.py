from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy.orm import Session

from app.domain.enums import JobType
from app.services.management_config import ManagementConfigService
from app.services.notifications import NotificationDeliveryError, NotificationDispatcher
from app.services.orchestration import CycleExecutionOrchestrator
from app.workers.job_runner import JobHandler
from app.workers.outbox_consumer import OutboxDeliveryError, OutboxHandler



def build_default_job_handlers(db: Session) -> Mapping[str, JobHandler]:
    orchestrator = CycleExecutionOrchestrator(db)
    management = ManagementConfigService(db)
    return {
        JobType.RETRY_CYCLE: orchestrator.handle_retry_cycle,
        JobType.REPLAN_CYCLE: orchestrator.handle_replan_cycle,
        JobType.RESUME_AFTER_APPROVAL: orchestrator.handle_resume_after_approval,
        JobType.RUN_VERIFICATION: orchestrator.handle_run_verification,
        JobType.BACKUP_RESTORE_DRILL: management.execute_backup_drill_job,
    }



def build_default_outbox_handlers(dispatcher: NotificationDispatcher | None = None) -> Mapping[str, OutboxHandler]:
    dispatcher = dispatcher or NotificationDispatcher()
    supported_events = {
        "cycle.accepted",
        "cycle.execution_enqueued",
        "cycle.completed",
        "cycle.retry_scheduled",
        "cycle.replan_requested",
        "cycle.verification_failed",
        "approval.requested",
        "approval.approved",
        "approval.rejected",
    }

    def _handler(item) -> None:
        try:
            dispatcher.dispatch(item.event_type, item.payload, outbox_id=item.outbox_id, cycle_id=item.cycle_id)
        except NotificationDeliveryError as exc:
            raise OutboxDeliveryError(str(exc), retryable=exc.retryable) from exc

    return {event_type: _handler for event_type in supported_events}
