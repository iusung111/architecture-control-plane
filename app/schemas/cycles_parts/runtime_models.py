from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import AcceptedEnvelope, OkEnvelope

from .cycle_models import ArtifactRef, CycleCommentResponse, CycleListItemResponse, CycleSummaryResponse, CycleTimelineEventResponse
from .discussion_models import AssignmentSuggestionResponse, CycleAssignmentResponse

class AssignmentSuggestionFeedbackRequest(BaseModel):
    agent_id: str = Field(min_length=1, max_length=128)
    feedback: str = Field(min_length=1, max_length=32)
    note: str | None = Field(default=None, max_length=500)


class AssignmentSuggestionFeedbackResponse(BaseModel):
    feedback_id: str
    cycle_id: str
    agent_id: str
    feedback: str
    note: str | None = None
    actor_id: str | None = None
    actor_role: str | None = None
    occurred_at: datetime


AssignmentSuggestionFeedbackEnvelope = OkEnvelope[AssignmentSuggestionFeedbackResponse]


class CycleCardResponse(BaseModel):
    cycle: CycleListItemResponse
    summary: CycleSummaryResponse
    result: CycleResultResponse | None = None
    timeline_preview: list[CycleTimelineEventResponse] = Field(default_factory=list)
    comments_preview: list[CycleCommentResponse] = Field(default_factory=list)
    comment_count: int = 0
    active_job_count: int = 0
    active_approval: ApprovalSummary | None = None
    current_assignment: CycleAssignmentResponse | None = None
    suggested_agents: list[str] = Field(default_factory=list)
    assignment_suggestions: list[AssignmentSuggestionResponse] = Field(default_factory=list)


CycleCardEnvelope = OkEnvelope[CycleCardResponse]


class RuntimeRegistrationRequest(BaseModel):
    runtime_id: str = Field(min_length=1, max_length=128)
    workspace_id: str | None = Field(default=None, max_length=128)
    project_id: str | None = Field(default=None, max_length=64)
    label: str = Field(min_length=1, max_length=128)
    status: str = Field(min_length=1, max_length=32)
    mode: str = Field(default="daemon", min_length=1, max_length=32)
    version: str | None = Field(default=None, max_length=64)
    capabilities: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeRegistrationResponse(BaseModel):
    runtime_id: str
    workspace_id: str | None = None
    project_id: str | None = None
    label: str
    status: str
    mode: str
    version: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    actor_id: str | None = None
    occurred_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeRegistrationListResponse(BaseModel):
    selected_project_id: str | None = None
    items: list[RuntimeRegistrationResponse] = Field(default_factory=list)


RuntimeRegistrationListEnvelope = OkEnvelope[RuntimeRegistrationListResponse]
RuntimeRegistrationEnvelope = OkEnvelope[RuntimeRegistrationResponse]


class RuntimeActionRequest(BaseModel):
    action: str = Field(min_length=1, max_length=64)
    arguments: dict[str, Any] = Field(default_factory=dict)


class RuntimeActionResponse(BaseModel):
    action_id: str
    runtime_id: str
    project_id: str | None = None
    workspace_id: str | None = None
    action: str
    status: str
    actor_id: str | None = None
    actor_role: str | None = None
    occurred_at: datetime
    arguments: dict[str, Any] = Field(default_factory=dict)
    note: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    acknowledged_at: datetime | None = None
    acknowledged_by: str | None = None
    last_updated_at: datetime | None = None
    latest_receipt_summary: str | None = None
    latest_receipt_status: str | None = None
    receipt_count: int = 0


class RuntimeActionListResponse(BaseModel):
    runtime_id: str
    project_id: str | None = None
    items: list[RuntimeActionResponse] = Field(default_factory=list)
    has_more: bool = False


RuntimeActionListEnvelope = OkEnvelope[RuntimeActionListResponse]
RuntimeActionEnvelope = OkEnvelope[RuntimeActionResponse]


class RuntimeActionReceiptRequest(BaseModel):
    summary: str = Field(min_length=1, max_length=500)
    status: str | None = Field(default=None, max_length=32)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeActionReceiptResponse(BaseModel):
    receipt_id: str
    action_id: str
    runtime_id: str
    project_id: str | None = None
    workspace_id: str | None = None
    summary: str
    status: str | None = None
    actor_id: str | None = None
    actor_role: str | None = None
    occurred_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeActionReceiptListResponse(BaseModel):
    runtime_id: str
    action_id: str
    items: list[RuntimeActionReceiptResponse] = Field(default_factory=list)
    has_more: bool = False


RuntimeActionReceiptListEnvelope = OkEnvelope[RuntimeActionReceiptListResponse]
RuntimeActionReceiptEnvelope = OkEnvelope[RuntimeActionReceiptResponse]


class RuntimeActionTimelineEventResponse(BaseModel):
    event_id: str
    action_id: str
    runtime_id: str
    event_type: str
    title: str
    status: str | None = None
    detail: str | None = None
    actor_id: str | None = None
    occurred_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeActionTimelineResponse(BaseModel):
    runtime_id: str
    action_id: str
    items: list[RuntimeActionTimelineEventResponse] = Field(default_factory=list)
    has_more: bool = False


RuntimeActionTimelineEnvelope = OkEnvelope[RuntimeActionTimelineResponse]


class RuntimeActionAcknowledgeRequest(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class RuntimeActionStateRequest(BaseModel):
    status: str = Field(min_length=1, max_length=32)
    note: str | None = Field(default=None, max_length=500)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetryCycleRequest(BaseModel):
    reason: str
    force: bool = False


class ReplanCycleRequest(BaseModel):
    reason: str
    override_input: dict[str, str] | None = None


class ActionAcceptedResponse(BaseModel):
    cycle_id: str
    action: str
    accepted: bool
    job_id: str
    state: str


ActionAcceptedEnvelope = AcceptedEnvelope[ActionAcceptedResponse]


class VerificationSummary(BaseModel):
    status: str | None = None
    failed_rules: list[str] = Field(default_factory=list)


class ApprovalSummary(BaseModel):
    required: bool = False
    approval_id: str | None = None
    state: str | None = None


class CycleResultResponse(BaseModel):
    cycle_id: str
    final_state: str
    summary: str
    output_artifacts: list[ArtifactRef] = Field(default_factory=list)
    verification: VerificationSummary = Field(default_factory=VerificationSummary)
    approval: ApprovalSummary = Field(default_factory=ApprovalSummary)
    evidence_summary: dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime


CycleResultEnvelope = OkEnvelope[CycleResultResponse]
