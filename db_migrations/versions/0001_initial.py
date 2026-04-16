"""initial control plane schema

Revision ID: 0001_initial
Revises: None
Create Date: 2026-04-13 00:00:00
"""

from alembic import op
import sqlalchemy as sa

APPROVAL_STATE_VALUES = ("pending", "approved", "rejected", "expired", "cancelled")
CYCLE_STATE_VALUES = (
    "intent_accepted",
    "plan_generated",
    "execution_attempted",
    "result_captured",
    "verification_failed",
    "verification_passed",
    "human_approval_pending",
    "retry_scheduled",
    "replan_requested",
    "terminalized",
    "terminal_fail",
)
JOB_STATE_VALUES = ("pending", "claimed", "running", "succeeded", "failed", "dead_lettered", "cancelled")
OUTBOX_DELIVERY_STATE_VALUES = ("pending", "claimed", "failed", "delivered", "dead_lettered")
GLOBAL_TENANT_SCOPE = "__global__"
USER_STATUS_VALUES = ("accepted", "in_progress", "verifying", "approval_required", "action_required", "completed", "failed")
VERIFICATION_STATUS_VALUES = ("passed", "failed")


def _enum_values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cycles",
        sa.Column("cycle_id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=True),
        sa.Column("tenant_scope", sa.String(length=64), nullable=False, server_default=GLOBAL_TENANT_SCOPE),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", sa.String(length=64), nullable=False),
        sa.Column("current_state", sa.String(length=64), nullable=False),
        sa.Column("user_status", sa.String(length=64), nullable=False),
        sa.Column("latest_iteration_no", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active_approval_id", sa.String(length=64), nullable=True),
        sa.Column("result_ref", sa.String(length=256), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("terminalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("tenant_scope", "owner_user_id", "project_id", "idempotency_key", name="uq_cycles_idempotency"),
        sa.CheckConstraint(f"current_state IN ({_enum_values(CYCLE_STATE_VALUES)})", name="ck_cycles_current_state"),
        sa.CheckConstraint(f"user_status IN ({_enum_values(USER_STATUS_VALUES)})", name="ck_cycles_user_status"),
    )
    op.create_index("ix_cycles_tenant_scope", "cycles", ["tenant_scope"])
    op.create_index("idx_cycles_project_state", "cycles", ["project_id", "current_state"])
    op.create_index("idx_cycles_owner_created_at", "cycles", ["owner_user_id", "created_at"])

    op.create_table(
        "cycle_iterations",
        sa.Column("iteration_id", sa.String(length=64), primary_key=True),
        sa.Column("cycle_id", sa.String(length=64), sa.ForeignKey("cycles.cycle_id", ondelete="CASCADE"), nullable=False),
        sa.Column("iteration_no", sa.Integer(), nullable=False),
        sa.Column("trigger_reason", sa.String(length=64), nullable=False),
        sa.Column("source_job_id", sa.String(length=64), nullable=True),
        sa.Column("input_snapshot_ref", sa.String(length=256), nullable=True),
        sa.Column("output_snapshot_ref", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("cycle_id", "iteration_no", name="uq_cycle_iterations_cycle_no"),
    )
    op.create_table(
        "verification_results",
        sa.Column("verification_id", sa.String(length=64), primary_key=True),
        sa.Column("cycle_id", sa.String(length=64), sa.ForeignKey("cycles.cycle_id", ondelete="CASCADE"), nullable=False),
        sa.Column("iteration_id", sa.String(length=64), sa.ForeignKey("cycle_iterations.iteration_id", ondelete="SET NULL"), nullable=True),
        sa.Column("verification_status", sa.String(length=64), nullable=False),
        sa.Column("failed_rules", sa.JSON(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint(f"verification_status IN ({_enum_values(VERIFICATION_STATUS_VALUES)})", name="ck_verification_results_status"),
    )
    op.create_index("idx_verification_results_cycle_created_at", "verification_results", ["cycle_id", "created_at"])
    op.create_table(
        "approvals",
        sa.Column("approval_id", sa.String(length=64), primary_key=True),
        sa.Column("cycle_id", sa.String(length=64), sa.ForeignKey("cycles.cycle_id", ondelete="CASCADE"), nullable=False),
        sa.Column("approval_state", sa.String(length=32), nullable=False),
        sa.Column("required_role", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=64), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("reason_code", sa.String(length=64), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(f"approval_state IN ({_enum_values(APPROVAL_STATE_VALUES)})", name="ck_approvals_approval_state"),
    )
    op.create_index("idx_approvals_cycle_state", "approvals", ["cycle_id", "approval_state"])
    op.create_index("idx_approvals_expires_at", "approvals", ["expires_at"])
    op.create_table(
        "jobs",
        sa.Column("job_id", sa.String(length=64), primary_key=True),
        sa.Column("cycle_id", sa.String(length=64), sa.ForeignKey("cycles.cycle_id", ondelete="CASCADE"), nullable=True),
        sa.Column("job_type", sa.String(length=64), nullable=False),
        sa.Column("job_state", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("dedup_key", sa.String(length=256), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("run_after", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("worker_id", sa.String(length=64), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("dedup_key", name="uq_jobs_dedup_key"),
        sa.CheckConstraint(f"job_state IN ({_enum_values(JOB_STATE_VALUES)})", name="ck_jobs_job_state"),
    )
    op.create_index("idx_jobs_claim", "jobs", ["job_state", "run_after", "priority"])
    op.create_index("idx_jobs_cycle", "jobs", ["cycle_id", "created_at"])
    op.create_table(
        "artifacts",
        sa.Column("artifact_id", sa.String(length=64), primary_key=True),
        sa.Column("cycle_id", sa.String(length=64), sa.ForeignKey("cycles.cycle_id", ondelete="CASCADE"), nullable=False),
        sa.Column("iteration_id", sa.String(length=64), sa.ForeignKey("cycle_iterations.iteration_id", ondelete="SET NULL"), nullable=True),
        sa.Column("artifact_type", sa.String(length=64), nullable=False),
        sa.Column("uri", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("idx_artifacts_cycle", "artifacts", ["cycle_id", "created_at"])
    op.create_table(
        "receipts",
        sa.Column("receipt_id", sa.String(length=64), primary_key=True),
        sa.Column("cycle_id", sa.String(length=64), sa.ForeignKey("cycles.cycle_id", ondelete="CASCADE"), nullable=False),
        sa.Column("iteration_id", sa.String(length=64), sa.ForeignKey("cycle_iterations.iteration_id", ondelete="SET NULL"), nullable=True),
        sa.Column("receipt_type", sa.String(length=64), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("idx_receipts_cycle", "receipts", ["cycle_id", "created_at"])
    op.create_table(
        "notifications_outbox",
        sa.Column("outbox_id", sa.String(length=64), primary_key=True),
        sa.Column("cycle_id", sa.String(length=64), sa.ForeignKey("cycles.cycle_id", ondelete="CASCADE"), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("delivery_state", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dead_lettered_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(f"delivery_state IN ({_enum_values(OUTBOX_DELIVERY_STATE_VALUES)})", name="ck_notifications_outbox_delivery_state"),
    )
    op.create_index("idx_notifications_outbox_delivery", "notifications_outbox", ["delivery_state", "next_attempt_at"])

    op.create_table(
        "management_config_documents",
        sa.Column("namespace", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("namespace"),
    )

    op.create_table(
        "audit_events",
        sa.Column("audit_event_id", sa.String(length=64), primary_key=True),
        sa.Column("cycle_id", sa.String(length=64), sa.ForeignKey("cycles.cycle_id", ondelete="CASCADE"), nullable=True),
        sa.Column("approval_id", sa.String(length=64), sa.ForeignKey("approvals.approval_id", ondelete="SET NULL"), nullable=True),
        sa.Column("actor_id", sa.String(length=64), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("event_payload", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("idx_audit_events_cycle", "audit_events", ["cycle_id", "occurred_at"])
    op.create_index("idx_audit_events_approval", "audit_events", ["approval_id", "occurred_at"])

    op.create_table(
        "llm_provider_policies",
        sa.Column("provider_name", sa.String(length=64), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("allow_work", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("allow_review", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("usage_mode", sa.String(length=32), nullable=False, server_default="free_only"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("daily_request_limit_override", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("usage_mode IN ('free_only','paid')", name="ck_llm_provider_policies_usage_mode"),
    )
    op.create_table(
        "llm_scope_overrides",
        sa.Column("override_id", sa.String(length=64), primary_key=True),
        sa.Column("scope_type", sa.String(length=32), nullable=False),
        sa.Column("scope_id", sa.String(length=128), nullable=False),
        sa.Column("provider_name", sa.String(length=64), nullable=False),
        sa.Column("enabled_override", sa.Boolean(), nullable=True),
        sa.Column("allow_work_override", sa.Boolean(), nullable=True),
        sa.Column("allow_review_override", sa.Boolean(), nullable=True),
        sa.Column("usage_mode_override", sa.String(length=32), nullable=True),
        sa.Column("priority_offset", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("daily_request_limit_override", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("scope_type IN ('tenant','project')", name="ck_llm_scope_overrides_scope_type"),
        sa.CheckConstraint("usage_mode_override IS NULL OR usage_mode_override IN ('free_only','paid')", name="ck_llm_scope_overrides_usage_mode"),
        sa.UniqueConstraint("scope_type", "scope_id", "provider_name", name="uq_llm_scope_overrides_scope_provider"),
    )
    op.create_index("ix_llm_scope_overrides_scope_type", "llm_scope_overrides", ["scope_type"])
    op.create_index("ix_llm_scope_overrides_scope_id", "llm_scope_overrides", ["scope_id"])
    op.create_index("ix_llm_scope_overrides_provider_name", "llm_scope_overrides", ["provider_name"])
    op.create_table(
        "llm_provider_quota_snapshots",
        sa.Column("provider_name", sa.String(length=64), primary_key=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("requests_limit", sa.Integer(), nullable=True),
        sa.Column("requests_remaining", sa.Integer(), nullable=True),
        sa.Column("requests_reset_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tokens_limit", sa.Integer(), nullable=True),
        sa.Column("tokens_remaining", sa.Integer(), nullable=True),
        sa.Column("tokens_reset_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("daily_request_limit", sa.Integer(), nullable=True),
        sa.Column("daily_requests_used", sa.Integer(), nullable=True),
        sa.Column("daily_requests_remaining", sa.Integer(), nullable=True),
        sa.Column("spend_limit_usd", sa.Float(), nullable=True),
        sa.Column("spend_used_usd", sa.Float(), nullable=True),
        sa.Column("spend_remaining_usd", sa.Float(), nullable=True),
        sa.Column("usage_tokens_input", sa.Integer(), nullable=True),
        sa.Column("usage_tokens_output", sa.Integer(), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_table(
        "llm_daily_usage",
        sa.Column("usage_id", sa.String(length=64), primary_key=True),
        sa.Column("provider_name", sa.String(length=64), nullable=False),
        sa.Column("usage_date", sa.String(length=10), nullable=False),
        sa.Column("work_requests", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("review_requests", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_requests", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("provider_name", "usage_date", name="uq_llm_daily_usage_provider_date"),
    )
    op.create_index("ix_llm_daily_usage_provider_name", "llm_daily_usage", ["provider_name"])
    op.create_index("ix_llm_daily_usage_usage_date", "llm_daily_usage", ["usage_date"])
    op.create_table(
        "llm_routing_decisions",
        sa.Column("routing_decision_id", sa.String(length=64), primary_key=True),
        sa.Column("cycle_id", sa.String(length=64), sa.ForeignKey("cycles.cycle_id", ondelete="CASCADE"), nullable=True),
        sa.Column("assignment_group_id", sa.String(length=64), nullable=False),
        sa.Column("prompt_type", sa.String(length=64), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("complexity", sa.String(length=32), nullable=False),
        sa.Column("selected_provider", sa.String(length=64), nullable=False),
        sa.Column("selected_model", sa.String(length=128), nullable=False),
        sa.Column("selected_usage_mode", sa.String(length=32), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("source_session_id", sa.String(length=64), nullable=True),
        sa.Column("requires_fresh_session", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("remaining_requests", sa.Integer(), nullable=True),
        sa.Column("paired_provider", sa.String(length=64), nullable=True),
        sa.Column("rationale", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_llm_routing_decisions_assignment_group_id", "llm_routing_decisions", ["assignment_group_id"])
    op.create_index("ix_llm_routing_decisions_cycle_id", "llm_routing_decisions", ["cycle_id"])
    op.create_index("ix_llm_routing_decisions_session_id", "llm_routing_decisions", ["session_id"])
    op.create_index("ix_llm_routing_decisions_stage", "llm_routing_decisions", ["stage"])
    op.create_index("ix_llm_routing_decisions_selected_provider", "llm_routing_decisions", ["selected_provider"])


def downgrade() -> None:
    op.drop_index("ix_llm_routing_decisions_selected_provider", table_name="llm_routing_decisions")
    op.drop_index("ix_llm_routing_decisions_stage", table_name="llm_routing_decisions")
    op.drop_index("ix_llm_routing_decisions_session_id", table_name="llm_routing_decisions")
    op.drop_index("ix_llm_routing_decisions_cycle_id", table_name="llm_routing_decisions")
    op.drop_index("ix_llm_routing_decisions_assignment_group_id", table_name="llm_routing_decisions")
    op.drop_table("llm_routing_decisions")
    op.drop_index("ix_llm_daily_usage_usage_date", table_name="llm_daily_usage")
    op.drop_index("ix_llm_daily_usage_provider_name", table_name="llm_daily_usage")
    op.drop_table("llm_daily_usage")
    op.drop_table("llm_provider_quota_snapshots")
    op.drop_index("ix_llm_scope_overrides_provider_name", table_name="llm_scope_overrides")
    op.drop_index("ix_llm_scope_overrides_scope_id", table_name="llm_scope_overrides")
    op.drop_index("ix_llm_scope_overrides_scope_type", table_name="llm_scope_overrides")
    op.drop_table("llm_scope_overrides")
    op.drop_table("llm_provider_policies")
    op.drop_index("idx_audit_events_approval", table_name="audit_events")
    op.drop_index("idx_audit_events_cycle", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("management_config_documents")
    op.drop_index("idx_notifications_outbox_delivery", table_name="notifications_outbox")
    op.drop_table("notifications_outbox")
    op.drop_index("idx_receipts_cycle", table_name="receipts")
    op.drop_table("receipts")
    op.drop_index("idx_artifacts_cycle", table_name="artifacts")
    op.drop_table("artifacts")
    op.drop_index("idx_jobs_cycle", table_name="jobs")
    op.drop_index("idx_jobs_claim", table_name="jobs")
    op.drop_table("jobs")
    op.drop_index("idx_approvals_expires_at", table_name="approvals")
    op.drop_index("idx_approvals_cycle_state", table_name="approvals")
    op.drop_table("approvals")
    op.drop_index("idx_verification_results_cycle_created_at", table_name="verification_results")
    op.drop_table("verification_results")
    op.drop_table("cycle_iterations")
    op.drop_index("idx_cycles_owner_created_at", table_name="cycles")
    op.drop_index("idx_cycles_project_state", table_name="cycles")
    op.drop_index("ix_cycles_tenant_scope", table_name="cycles")
    op.drop_table("cycles")
