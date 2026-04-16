from enum import StrEnum


class CycleState(StrEnum):
    INTENT_ACCEPTED = "intent_accepted"
    PLAN_GENERATED = "plan_generated"
    EXECUTION_ATTEMPTED = "execution_attempted"
    RESULT_CAPTURED = "result_captured"
    VERIFICATION_FAILED = "verification_failed"
    VERIFICATION_PASSED = "verification_passed"
    HUMAN_APPROVAL_PENDING = "human_approval_pending"
    RETRY_SCHEDULED = "retry_scheduled"
    REPLAN_REQUESTED = "replan_requested"
    TERMINALIZED = "terminalized"
    TERMINAL_FAIL = "terminal_fail"


class UserStatus(StrEnum):
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"
    VERIFYING = "verifying"
    APPROVAL_REQUIRED = "approval_required"
    ACTION_REQUIRED = "action_required"
    COMPLETED = "completed"
    FAILED = "failed"


class ApprovalState(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class JobType(StrEnum):
    RETRY_CYCLE = "retry_cycle"
    REPLAN_CYCLE = "replan_cycle"
    RESUME_AFTER_APPROVAL = "resume_after_approval"
    RUN_VERIFICATION = "run_verification"
    DELIVER_NOTIFICATION = "deliver_notification"
    BACKUP_RESTORE_DRILL = "backup_restore_drill"


class JobState(StrEnum):
    PENDING = "pending"
    CLAIMED = "claimed"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DEAD_LETTERED = "dead_lettered"
    CANCELLED = "cancelled"


class VerificationStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"


class OutboxDeliveryState(StrEnum):
    PENDING = "pending"
    CLAIMED = "claimed"
    FAILED = "failed"
    DELIVERED = "delivered"
    DEAD_LETTERED = "dead_lettered"
