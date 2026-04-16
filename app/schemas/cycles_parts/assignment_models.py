from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

class CycleAssignmentRequest(BaseModel):
    actor_id: str
    assignment_reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CycleAssignmentResponse(BaseModel):
    assignment_id: str
    cycle_id: str
    actor_id: str
    assigned_at: str | None = None
    assignment_reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    assigned_by: str | None = None


class CycleAssignmentListResponse(BaseModel):
    items: list[CycleAssignmentResponse]
    total: int
    next_cursor: str | None = None


class AssignmentSuggestionResponse(BaseModel):
    actor_id: str
    display_name: str | None = None
    role: str | None = None
    score: float
    confidence: float | None = None
    rationale: list[str] = Field(default_factory=list)
    explanation: str | None = None
    workload: dict[str, Any] = Field(default_factory=dict)
    skill_match: dict[str, Any] = Field(default_factory=dict)
    availability: dict[str, Any] = Field(default_factory=dict)
    learning_weight: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    source: str | None = None
    remote_outcome_score: float | None = None
    review_outcome_score: float | None = None
    workspace_score: float | None = None
    recent_assignment_count: int | None = None
    suggested_queue: str | None = None
    tenant_id: str | None = None
    project_id: str | None = None


class AssignmentSuggestionListResponse(BaseModel):
    items: list[AssignmentSuggestionResponse]
    total: int
    generated_at: str | None = None


class AssignmentLearningWeightResponse(BaseModel):
    actor_id: str
    tenant_id: str | None = None
    project_id: str | None = None
    skill_weight: float | None = None
    workload_weight: float | None = None
    workspace_weight: float | None = None
    recency_weight: float | None = None
    remote_outcome_weight: float | None = None
    review_outcome_weight: float | None = None
    updated_at: str | None = None
    source: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AssignmentLearningWeightListResponse(BaseModel):
    items: list[AssignmentLearningWeightResponse]
    total: int
    next_cursor: str | None = None


class AssignmentSuggestionFeedbackRequest(BaseModel):
    actor_id: str
    accepted: bool
    feedback: str | None = None


class AssignmentSuggestionFeedbackResponse(BaseModel):
    feedback_id: str
    cycle_id: str
    actor_id: str
    accepted: bool
    feedback: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CycleCardResponse(BaseModel):
    cycle_id: str
    project_id: str
    current_state: str
    user_status: str
    current_assignee: str | None = None
    score: float | None = None
    rank: int | None = None
    created_at: str | None = None
    updated_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
