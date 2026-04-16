from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.db.base import Base
from app.domain.enums import ApprovalState, CycleState, JobState, OutboxDeliveryState, UserStatus, VerificationStatus
from app.domain.tenancy import GLOBAL_TENANT_SCOPE, normalize_tenant_scope


def _enum_values(enum_cls) -> str:
    return ", ".join(repr(item.value) for item in enum_cls)


class Cycle(Base):
    __tablename__ = "cycles"
    __table_args__ = (
        UniqueConstraint("tenant_scope", "owner_user_id", "project_id", "idempotency_key", name="uq_cycles_idempotency"),
        CheckConstraint(f"current_state IN ({_enum_values(CycleState)})", name="ck_cycles_current_state"),
        CheckConstraint(f"user_status IN ({_enum_values(UserStatus)})", name="ck_cycles_user_status"),
    )

    cycle_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tenant_scope: Mapped[str] = mapped_column(String(64), nullable=False, default=GLOBAL_TENANT_SCOPE, server_default=GLOBAL_TENANT_SCOPE, index=True)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    current_state: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_status: Mapped[str] = mapped_column(String(64), nullable=False)
    latest_iteration_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active_approval_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    terminalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    approvals: Mapped[list["Approval"]] = relationship(back_populates="cycle")
    jobs: Mapped[list["Job"]] = relationship(back_populates="cycle")
    outbox_items: Mapped[list["NotificationOutbox"]] = relationship(back_populates="cycle")

    @validates("tenant_id")
    def _sync_tenant_scope(self, _key: str, tenant_id: str | None) -> str | None:
        self.tenant_scope = normalize_tenant_scope(tenant_id)
        return tenant_id


class CycleIteration(Base):
    __tablename__ = "cycle_iterations"
    __table_args__ = (
        UniqueConstraint("cycle_id", "iteration_no", name="uq_cycle_iterations_cycle_no"),
    )

    iteration_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    cycle_id: Mapped[str] = mapped_column(ForeignKey("cycles.cycle_id", ondelete="CASCADE"), nullable=False)
    iteration_no: Mapped[int] = mapped_column(Integer, nullable=False)
    trigger_reason: Mapped[str] = mapped_column(String(64), nullable=False)
    source_job_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_snapshot_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)
    output_snapshot_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class VerificationResult(Base):
    __tablename__ = "verification_results"
    __table_args__ = (
        CheckConstraint(f"verification_status IN ({_enum_values(VerificationStatus)})", name="ck_verification_results_status"),
    )

    verification_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    cycle_id: Mapped[str] = mapped_column(ForeignKey("cycles.cycle_id", ondelete="CASCADE"), nullable=False, index=True)
    iteration_id: Mapped[str | None] = mapped_column(ForeignKey("cycle_iterations.iteration_id", ondelete="SET NULL"), nullable=True)
    verification_status: Mapped[str] = mapped_column(String(64), nullable=False)
    failed_rules: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Approval(Base):
    __tablename__ = "approvals"
    __table_args__ = (
        CheckConstraint(f"approval_state IN ({_enum_values(ApprovalState)})", name="ck_approvals_approval_state"),
    )

    approval_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    cycle_id: Mapped[str] = mapped_column(ForeignKey("cycles.cycle_id", ondelete="CASCADE"), nullable=False, index=True)
    approval_state: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    required_role: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    acted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    cycle: Mapped[Cycle] = relationship(back_populates="approvals")


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(f"job_state IN ({_enum_values(JobState)})", name="ck_jobs_job_state"),
    )

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    cycle_id: Mapped[str | None] = mapped_column(ForeignKey("cycles.cycle_id", ondelete="CASCADE"), nullable=True, index=True)
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    job_state: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    dedup_key: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    cycle: Mapped[Cycle | None] = relationship(back_populates="jobs")


class Artifact(Base):
    __tablename__ = "artifacts"

    artifact_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    cycle_id: Mapped[str] = mapped_column(ForeignKey("cycles.cycle_id", ondelete="CASCADE"), nullable=False, index=True)
    iteration_id: Mapped[str | None] = mapped_column(ForeignKey("cycle_iterations.iteration_id", ondelete="SET NULL"), nullable=True)
    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    uri: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Receipt(Base):
    __tablename__ = "receipts"

    receipt_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    cycle_id: Mapped[str] = mapped_column(ForeignKey("cycles.cycle_id", ondelete="CASCADE"), nullable=False, index=True)
    iteration_id: Mapped[str | None] = mapped_column(ForeignKey("cycle_iterations.iteration_id", ondelete="SET NULL"), nullable=True)
    receipt_type: Mapped[str] = mapped_column(String(64), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class NotificationOutbox(Base):
    __tablename__ = "notifications_outbox"
    __table_args__ = (
        CheckConstraint(f"delivery_state IN ({_enum_values(OutboxDeliveryState)})", name="ck_notifications_outbox_delivery_state"),
    )

    outbox_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    cycle_id: Mapped[str | None] = mapped_column(ForeignKey("cycles.cycle_id", ondelete="CASCADE"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    delivery_state: Mapped[str] = mapped_column(String(32), nullable=False, default=OutboxDeliveryState.PENDING, index=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dead_lettered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    cycle: Mapped[Cycle | None] = relationship(back_populates="outbox_items")


class LLMProviderPolicy(Base):
    __tablename__ = "llm_provider_policies"
    __table_args__ = (
        CheckConstraint("usage_mode IN ('free_only','paid')", name="ck_llm_provider_policies_usage_mode"),
    )

    provider_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allow_work: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allow_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    usage_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="free_only")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    daily_request_limit_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class LLMScopeOverride(Base):
    __tablename__ = "llm_scope_overrides"
    __table_args__ = (
        UniqueConstraint("scope_type", "scope_id", "provider_name", name="uq_llm_scope_overrides_scope_provider"),
        CheckConstraint("scope_type IN ('tenant','project')", name="ck_llm_scope_overrides_scope_type"),
        CheckConstraint("usage_mode_override IS NULL OR usage_mode_override IN ('free_only','paid')", name="ck_llm_scope_overrides_usage_mode"),
    )

    override_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    scope_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    provider_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    enabled_override: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    allow_work_override: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    allow_review_override: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    usage_mode_override: Mapped[str | None] = mapped_column(String(32), nullable=True)
    priority_offset: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    daily_request_limit_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class LLMProviderQuotaSnapshot(Base):
    __tablename__ = "llm_provider_quota_snapshots"

    provider_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    requests_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requests_remaining: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requests_reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tokens_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_remaining: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    daily_request_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    daily_requests_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    daily_requests_remaining: Mapped[int | None] = mapped_column(Integer, nullable=True)
    spend_limit_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    spend_used_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    spend_remaining_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    usage_tokens_input: Mapped[int | None] = mapped_column(Integer, nullable=True)
    usage_tokens_output: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class LLMDailyUsage(Base):
    __tablename__ = "llm_daily_usage"
    __table_args__ = (
        UniqueConstraint("provider_name", "usage_date", name="uq_llm_daily_usage_provider_date"),
    )

    usage_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    usage_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    work_requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    review_requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class LLMRoutingDecision(Base):
    __tablename__ = "llm_routing_decisions"

    routing_decision_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    cycle_id: Mapped[str | None] = mapped_column(ForeignKey("cycles.cycle_id", ondelete="CASCADE"), nullable=True, index=True)
    assignment_group_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    prompt_type: Mapped[str] = mapped_column(String(64), nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    complexity: Mapped[str] = mapped_column(String(32), nullable=False)
    selected_provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    selected_model: Mapped[str] = mapped_column(String(128), nullable=False)
    selected_usage_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    requires_fresh_session: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    remaining_requests: Mapped[int | None] = mapped_column(Integer, nullable=True)
    paired_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rationale: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ManagementConfigDocument(Base):
    __tablename__ = "management_config_documents"

    namespace: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class AuditEvent(Base):
    __tablename__ = "audit_events"

    audit_event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    cycle_id: Mapped[str | None] = mapped_column(ForeignKey("cycles.cycle_id", ondelete="CASCADE"), nullable=True, index=True)
    approval_id: Mapped[str | None] = mapped_column(ForeignKey("approvals.approval_id", ondelete="SET NULL"), nullable=True, index=True)
    actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
