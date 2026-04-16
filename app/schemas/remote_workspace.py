from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import AcceptedEnvelope, OkEnvelope


class RemoteWorkspaceArtifactResponse(BaseModel):
    artifact_id: str
    artifact_type: str
    uri: str
    content_type: str | None = None


class RemoteWorkspaceSnapshotRequest(BaseModel):
    workspace_id: str | None = Field(default=None, max_length=128)
    cycle_id: str | None = Field(default=None, max_length=64)
    project_id: str | None = Field(default=None, max_length=64)
    repo_url: str | None = Field(default=None, max_length=500)
    repo_branch: str | None = Field(default=None, max_length=255)
    repo_ref: str | None = Field(default=None, max_length=255)
    patch: str | None = None
    patch_stack: list[str] = Field(default_factory=list)
    execution_profile: str | None = Field(default=None, max_length=64)
    executor_key: str | None = Field(default=None, max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RemoteWorkspaceSnapshotResponse(BaseModel):
    workspace_id: str
    cycle_id: str | None = None
    project_id: str | None = None
    repo_url: str | None = None
    repo_branch: str | None = None
    repo_ref: str | None = None
    patch: str | None = None
    patch_stack: list[str] = Field(default_factory=list)
    patch_present: bool = False
    execution_profile: str | None = None
    executor_key: str | None = None
    last_execution_status: str | None = None
    last_execution_kind: str | None = None
    last_execution_requested_at: datetime | None = None
    artifact_count: int = 0
    artifacts: list[RemoteWorkspaceArtifactResponse] = Field(default_factory=list)
    artifact_history: list[RemoteWorkspaceArtifactResponse] = Field(default_factory=list)
    updated_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)
    last_failed_command: str | None = None
    last_result_summary: str | None = None
    last_execution_id: str | None = None
    resume_count: int = 0
    last_resumed_at: datetime | None = None


class RemoteWorkspaceSnapshotListResponse(BaseModel):
    items: list[RemoteWorkspaceSnapshotResponse] = Field(default_factory=list)
    has_more: bool = False


class RemoteWorkspaceExecutionRequest(BaseModel):
    workspace_id: str = Field(min_length=1, max_length=128)
    execution_kind: str = Field(default="run_checks", min_length=1, max_length=64)
    command: str | None = Field(default=None, max_length=500)
    patch: str | None = None
    repo_url: str | None = Field(default=None, max_length=500)
    repo_branch: str | None = Field(default=None, max_length=255)
    repo_ref: str | None = Field(default=None, max_length=255)
    cycle_id: str | None = Field(default=None, max_length=64)
    project_id: str | None = Field(default=None, max_length=64)
    execution_profile: str | None = Field(default=None, max_length=64)
    executor_key: str | None = Field(default=None, max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RemoteWorkspaceExecutionResultCallbackRequest(BaseModel):
    workspace_id: str
    execution_kind: str = Field(default="run_checks", min_length=1, max_length=64)
    status: str = Field(min_length=1, max_length=64)
    command: str | None = None
    message: str | None = None
    result_summary: str | None = None
    external_url: str | None = None
    logs_url: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    exit_code: int | None = None
    timed_out: bool = False
    artifacts: list[RemoteWorkspaceArtifactResponse] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    cycle_id: str | None = None
    project_id: str | None = None
    repo_url: str | None = None
    repo_branch: str | None = None
    repo_ref: str | None = None
    patch: str | None = None
    execution_profile: str | None = None
    executor_key: str | None = None
    tenant_id: str | None = None


class RemoteWorkspaceExecutionResponse(BaseModel):
    execution_id: str
    workspace_id: str
    execution_kind: str
    status: str
    executor_key: str
    requested_at: datetime
    message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    command: str | None = None
    cycle_id: str | None = None
    project_id: str | None = None
    execution_profile: str | None = None
    assigned_agent_id: str | None = None
    assignment_role: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    external_url: str | None = None
    logs_url: str | None = None
    artifacts: list[RemoteWorkspaceArtifactResponse] = Field(default_factory=list)
    artifact_count: int = 0
    result_summary: str | None = None
    exit_code: int | None = None
    timed_out: bool = False
    can_cancel: bool = False
    last_updated_at: datetime | None = None
    source: str | None = None


class RemoteWorkspaceExecutionListResponse(BaseModel):
    workspace_id: str
    items: list[RemoteWorkspaceExecutionResponse] = Field(default_factory=list)
    has_more: bool = False


class RemoteWorkspaceResumeRequest(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class RemoteWorkspaceResumeResponse(BaseModel):
    workspace_id: str
    cycle_id: str | None = None
    project_id: str | None = None
    repo_url: str | None = None
    repo_branch: str | None = None
    repo_ref: str | None = None
    patch_stack: list[str] = Field(default_factory=list)
    patch_present: bool = False
    last_execution_id: str | None = None
    last_successful_execution_id: str | None = None
    last_failed_execution_id: str | None = None
    last_failed_command: str | None = None
    last_result_summary: str | None = None
    artifacts: list[RemoteWorkspaceArtifactResponse] = Field(default_factory=list)
    recent_executions: list[RemoteWorkspaceExecutionResponse] = Field(default_factory=list)
    resume_count: int = 0
    last_resumed_at: datetime | None = None
    updated_at: datetime | None = None


class WorkbenchSavedViewRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    project_id: str | None = Field(default=None, max_length=64)
    cycle_id: str | None = Field(default=None, max_length=64)
    workspace_id: str | None = Field(default=None, max_length=128)
    query: str | None = Field(default=None, max_length=255)
    discussion_filter_id: str | None = Field(default=None, max_length=64)
    layout: dict[str, Any] = Field(default_factory=dict)
    selected_panels: list[str] = Field(default_factory=list)
    notes: str | None = Field(default=None, max_length=500)


class WorkbenchSavedViewResponse(BaseModel):
    view_id: str
    name: str
    project_id: str | None = None
    cycle_id: str | None = None
    workspace_id: str | None = None
    query: str | None = None
    discussion_filter_id: str | None = None
    layout: dict[str, Any] = Field(default_factory=dict)
    selected_panels: list[str] = Field(default_factory=list)
    notes: str | None = None
    is_deleted: bool = False
    use_count: int = 0
    last_used_at: datetime | None = None
    updated_at: datetime


class WorkbenchSavedViewListResponse(BaseModel):
    items: list[WorkbenchSavedViewResponse] = Field(default_factory=list)
    has_more: bool = False


class RemoteWorkspaceExecutorInfoResponse(BaseModel):
    key: str
    name: str
    mode: str
    enabled: bool
    description: str
    capabilities: list[str] = Field(default_factory=list)


class RemoteWorkspaceExecutorListResponse(BaseModel):
    default_executor_key: str
    items: list[RemoteWorkspaceExecutorInfoResponse] = Field(default_factory=list)


RemoteWorkspaceSnapshotEnvelope = OkEnvelope[RemoteWorkspaceSnapshotResponse]
RemoteWorkspaceSnapshotListEnvelope = OkEnvelope[RemoteWorkspaceSnapshotListResponse]
RemoteWorkspaceExecutionEnvelope = AcceptedEnvelope[RemoteWorkspaceExecutionResponse] | OkEnvelope[RemoteWorkspaceExecutionResponse]
RemoteWorkspaceExecutionListEnvelope = OkEnvelope[RemoteWorkspaceExecutionListResponse]
RemoteWorkspaceResumeEnvelope = OkEnvelope[RemoteWorkspaceResumeResponse]
RemoteWorkspaceExecutorListEnvelope = OkEnvelope[RemoteWorkspaceExecutorListResponse]
WorkbenchSavedViewEnvelope = OkEnvelope[WorkbenchSavedViewResponse]
WorkbenchSavedViewListEnvelope = OkEnvelope[WorkbenchSavedViewListResponse]

class PersistentWorkspaceSessionRequest(BaseModel):
    workspace_id: str = Field(min_length=1, max_length=128)
    cycle_id: str | None = Field(default=None, max_length=64)
    project_id: str | None = Field(default=None, max_length=64)
    repo_url: str | None = Field(default=None, max_length=500)
    repo_branch: str | None = Field(default=None, max_length=255)
    repo_ref: str | None = Field(default=None, max_length=255)
    note: str | None = Field(default=None, max_length=500)
    provider: str | None = Field(default=None, max_length=64)


class PersistentWorkspaceSessionResponse(BaseModel):
    workspace_id: str
    cycle_id: str | None = None
    project_id: str | None = None
    repo_url: str | None = None
    repo_branch: str | None = None
    repo_ref: str | None = None
    provider: str
    status: str
    note: str | None = None
    created_at: datetime
    updated_at: datetime
    last_resumed_at: datetime | None = None
    idle_timeout_minutes: int
    ttl_hours: int
    expires_at: datetime | None = None
    hibernate_supported: bool = True
    is_persistent: bool = True


class PersistentWorkspaceSessionListResponse(BaseModel):
    items: list[PersistentWorkspaceSessionResponse] = Field(default_factory=list)
    has_more: bool = False

PersistentWorkspaceSessionEnvelope = OkEnvelope[PersistentWorkspaceSessionResponse]
PersistentWorkspaceSessionListEnvelope = OkEnvelope[PersistentWorkspaceSessionListResponse]
