from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import OkEnvelope


class ArtifactRef(BaseModel):
    artifact_id: str
    artifact_type: str
    uri: str
    content_type: str | None = None


class CreateCycleRequest(BaseModel):
    project_id: str
    user_input: str
    tenant_id: str | None = None
    input_artifacts: list[ArtifactRef] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateCycleResponse(BaseModel):
    cycle_id: str
    state: str
    user_status: str
    next_action: str | None = None
    approval_required: bool = False
    created_at: datetime


CreateCycleEnvelope = OkEnvelope[CreateCycleResponse]


class CycleSummaryResponse(BaseModel):
    cycle_id: str
    state: str
    user_status: str
    next_action: str | None = None
    approval_required: bool
    retry_allowed: bool
    replan_allowed: bool
    updated_at: datetime


CycleSummaryEnvelope = OkEnvelope[CycleSummaryResponse]


class CycleListItemResponse(BaseModel):
    cycle_id: str
    project_id: str
    tenant_id: str | None = None
    state: str
    user_status: str
    next_action: str | None = None
    approval_required: bool
    retry_allowed: bool
    replan_allowed: bool
    latest_iteration_no: int
    created_at: datetime
    updated_at: datetime


class CycleListResponse(BaseModel):
    items: list[CycleListItemResponse] = Field(default_factory=list)
    next_cursor: str | None = None
    has_more: bool = False


CycleListEnvelope = OkEnvelope[CycleListResponse]


class CycleBoardColumnResponse(BaseModel):
    key: str
    title: str
    description: str | None = None
    count: int
    items: list[CycleListItemResponse] = Field(default_factory=list)


class CycleBoardResponse(BaseModel):
    project_id: str | None = None
    generated_at: datetime
    total_count: int
    columns: list[CycleBoardColumnResponse] = Field(default_factory=list)


CycleBoardEnvelope = OkEnvelope[CycleBoardResponse]


class CycleTimelineEventResponse(BaseModel):
    event_id: str
    source: str
    event_type: str
    title: str
    detail: str | None = None
    actor_id: str | None = None
    status: str | None = None
    occurred_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class CycleTimelineResponse(BaseModel):
    cycle_id: str
    events: list[CycleTimelineEventResponse] = Field(default_factory=list)
    has_more: bool = False


CycleTimelineEnvelope = OkEnvelope[CycleTimelineResponse]




class CycleCommentRequest(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    mentions: list[str] = Field(default_factory=list)


class CycleCommentResponse(BaseModel):
    comment_id: str
    cycle_id: str
    body: str
    mentions: list[str] = Field(default_factory=list)
    actor_id: str | None = None
    actor_role: str | None = None
    occurred_at: datetime


class CycleCommentListResponse(BaseModel):
    cycle_id: str
    items: list[CycleCommentResponse] = Field(default_factory=list)
    has_more: bool = False


CycleCommentListEnvelope = OkEnvelope[CycleCommentListResponse]
CycleCommentEnvelope = OkEnvelope[CycleCommentResponse]


class WorkspaceProjectSummaryResponse(BaseModel):
    project_id: str
    total_cycles: int
    active_cycles: int
    pending_reviews: int
    completed_cycles: int
    failed_cycles: int
    updated_at: datetime | None = None


class WorkspaceOverviewResponse(BaseModel):
    tenant_id: str | None = None
    selected_project_id: str | None = None
    totals: dict[str, int] = Field(default_factory=dict)
    projects: list[WorkspaceProjectSummaryResponse] = Field(default_factory=list)
    recent_comments: list[CycleCommentResponse] = Field(default_factory=list)
    generated_at: datetime


WorkspaceOverviewEnvelope = OkEnvelope[WorkspaceOverviewResponse]


class AgentProfileResponse(BaseModel):
    agent_id: str
    name: str
    persona: str
    status: str
    focus: str | None = None
    current_load: int
    capacity_hint: str | None = None
    specialties: list[str] = Field(default_factory=list)
    metrics: dict[str, int] = Field(default_factory=dict)


class AgentProfileListResponse(BaseModel):
    generated_at: datetime
    items: list[AgentProfileResponse] = Field(default_factory=list)


AgentProfileListEnvelope = OkEnvelope[AgentProfileListResponse]


class RuntimeQueueMetricResponse(BaseModel):
    key: str
    label: str
    value: int
    detail: str | None = None


class RuntimePanelResponse(BaseModel):
    generated_at: datetime
    selected_project_id: str | None = None
    queue_metrics: list[RuntimeQueueMetricResponse] = Field(default_factory=list)
    recent_jobs: list[CycleTimelineEventResponse] = Field(default_factory=list)
    outbox_metrics: dict[str, int] = Field(default_factory=dict)
    signals: list[str] = Field(default_factory=list)


RuntimePanelEnvelope = OkEnvelope[RuntimePanelResponse]

