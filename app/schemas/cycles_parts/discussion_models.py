from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import OkEnvelope


class WorkspaceDiscussionRequest(BaseModel):
    project_id: str | None = None
    body: str = Field(min_length=1, max_length=2000)
    mentions: list[str] = Field(default_factory=list)


class WorkspaceDiscussionResponse(BaseModel):
    discussion_id: str
    project_id: str | None = None
    body: str
    mentions: list[str] = Field(default_factory=list)
    actor_id: str | None = None
    actor_role: str | None = None
    occurred_at: datetime
    reply_count: int = 0
    is_resolved: bool = False
    is_pinned: bool = False
    resolved_at: datetime | None = None
    resolved_by: str | None = None
    pinned_at: datetime | None = None
    pinned_by: str | None = None
    last_updated_at: datetime | None = None
    search_rank: float = 0.0
    matched_terms: list[str] = Field(default_factory=list)


class WorkspaceDiscussionReplyRequest(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    mentions: list[str] = Field(default_factory=list)


class WorkspaceDiscussionResolutionRequest(BaseModel):
    resolved: bool = True
    note: str | None = Field(default=None, max_length=500)


class WorkspaceDiscussionPinRequest(BaseModel):
    pinned: bool = True
    note: str | None = Field(default=None, max_length=500)


class WorkspaceDiscussionReplyResponse(BaseModel):
    reply_id: str
    discussion_id: str
    project_id: str | None = None
    body: str
    mentions: list[str] = Field(default_factory=list)
    actor_id: str | None = None
    actor_role: str | None = None
    occurred_at: datetime


class WorkspaceDiscussionReplyListResponse(BaseModel):
    discussion_id: str
    project_id: str | None = None
    mention_filter: str | None = None
    items: list[WorkspaceDiscussionReplyResponse] = Field(default_factory=list)
    has_more: bool = False


class WorkspaceDiscussionListResponse(BaseModel):
    selected_project_id: str | None = None
    mention_filter: str | None = None
    query: str | None = None
    items: list[WorkspaceDiscussionResponse] = Field(default_factory=list)
    has_more: bool = False


class WorkspaceDiscussionGroupResponse(BaseModel):
    group_key: str
    label: str
    project_id: str | None = None
    total_count: int
    unresolved_count: int
    resolved_count: int
    pinned_count: int
    last_updated_at: datetime | None = None
    items: list[WorkspaceDiscussionResponse] = Field(default_factory=list)


class WorkspaceDiscussionGroupListResponse(BaseModel):
    selected_project_id: str | None = None
    mention_filter: str | None = None
    query: str | None = None
    items: list[WorkspaceDiscussionGroupResponse] = Field(default_factory=list)
    has_more: bool = False


class WorkspaceDiscussionSavedFilterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    project_id: str | None = Field(default=None, max_length=64)
    mention: str | None = Field(default=None, max_length=120)
    query: str | None = Field(default=None, max_length=240)


class WorkspaceDiscussionSavedFilterUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    project_id: str | None = Field(default=None, max_length=64)
    mention: str | None = Field(default=None, max_length=120)
    query: str | None = Field(default=None, max_length=240)


class WorkspaceDiscussionSavedFilterFavoriteRequest(BaseModel):
    is_favorite: bool = True


class WorkspaceDiscussionSavedFilterResponse(BaseModel):
    filter_id: str
    name: str
    project_id: str | None = None
    mention: str | None = None
    query: str | None = None
    actor_id: str | None = None
    occurred_at: datetime
    updated_at: datetime | None = None
    last_used_at: datetime | None = None
    is_favorite: bool = False
    is_deleted: bool = False


class WorkspaceDiscussionSavedFilterListResponse(BaseModel):
    items: list[WorkspaceDiscussionSavedFilterResponse] = Field(default_factory=list)
    has_more: bool = False


WorkspaceDiscussionListEnvelope = OkEnvelope[WorkspaceDiscussionListResponse]
WorkspaceDiscussionEnvelope = OkEnvelope[WorkspaceDiscussionResponse]
WorkspaceDiscussionReplyListEnvelope = OkEnvelope[WorkspaceDiscussionReplyListResponse]
WorkspaceDiscussionReplyEnvelope = OkEnvelope[WorkspaceDiscussionReplyResponse]
WorkspaceDiscussionGroupListEnvelope = OkEnvelope[WorkspaceDiscussionGroupListResponse]
WorkspaceDiscussionSavedFilterEnvelope = OkEnvelope[WorkspaceDiscussionSavedFilterResponse]
WorkspaceDiscussionSavedFilterListEnvelope = OkEnvelope[WorkspaceDiscussionSavedFilterListResponse]


class CycleAssignmentRequest(BaseModel):
    agent_id: str = Field(min_length=1, max_length=128)
    assignment_role: str = Field(default='primary', min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=500)


class CycleAssignmentResponse(BaseModel):
    assignment_id: str
    cycle_id: str
    agent_id: str
    assignment_role: str
    note: str | None = None
    actor_id: str | None = None
    actor_role: str | None = None
    occurred_at: datetime


class CycleAssignmentListResponse(BaseModel):
    cycle_id: str
    items: list[CycleAssignmentResponse] = Field(default_factory=list)
    has_more: bool = False


CycleAssignmentListEnvelope = OkEnvelope[CycleAssignmentListResponse]
CycleAssignmentEnvelope = OkEnvelope[CycleAssignmentResponse]


class AssignmentSuggestionResponse(BaseModel):
    agent_id: str
    name: str
    recommended_role: str
    rationale: str
    current_load: int
    queue_pressure: str
    status: str
    capacity_hint: str | None = None
    specialties: list[str] = Field(default_factory=list)
    score: int = 0
    autofill_note: str | None = None
    last_feedback: str | None = None
    feedback_note: str | None = None
    feedback_actor_id: str | None = None
    feedback_occurred_at: datetime | None = None
    learned_weight: float = 0.0
    weighted_feedback_score: float = 0.0
    recency_weight: float = 0.0
    last_feedback_at: datetime | None = None
    accepted_count: int = 0
    dismissed_count: int = 0
    applied_count: int = 0
    remote_success_count: int = 0
    remote_failure_count: int = 0
    remote_total_count: int = 0
    remote_success_rate: float | None = None
    last_remote_status: str | None = None
    last_remote_at: datetime | None = None


class AssignmentSuggestionListResponse(BaseModel):
    cycle_id: str
    board_column: str
    items: list[AssignmentSuggestionResponse] = Field(default_factory=list)


class AssignmentLearningWeightResponse(BaseModel):
    agent_id: str
    name: str
    learned_weight: float = 0.0
    weighted_accepted_count: float = 0.0
    weighted_dismissed_count: float = 0.0
    weighted_applied_count: float = 0.0
    recency_weight: float = 0.0
    last_feedback_at: datetime | None = None
    accepted_count: int = 0
    dismissed_count: int = 0
    applied_count: int = 0
    recommendation_count: int = 0
    remote_success_count: int = 0
    remote_failure_count: int = 0
    remote_total_count: int = 0
    remote_success_rate: float | None = None
    last_remote_status: str | None = None
    last_remote_at: datetime | None = None
    rationale: str


class AssignmentLearningWeightListResponse(BaseModel):
    cycle_id: str
    project_id: str | None = None
    items: list[AssignmentLearningWeightResponse] = Field(default_factory=list)


AssignmentSuggestionListEnvelope = OkEnvelope[AssignmentSuggestionListResponse]
AssignmentLearningWeightListEnvelope = OkEnvelope[AssignmentLearningWeightListResponse]
