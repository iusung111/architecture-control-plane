from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import AcceptedEnvelope, OkEnvelope


class ManagementConfigResponseModel(BaseModel):
    namespace: str
    effective: dict[str, Any]
    overrides: dict[str, Any]
    applies_immediately: bool
    applies_on_restart: bool


class ManagementConfigUpdateRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


class BackupDrillPreviewResponse(BaseModel):
    command: list[str]
    effective_backup_config: dict[str, Any]


class BackupDrillRunRequest(BaseModel):
    target_name: str | None = None
    label: str | None = None
    restore_from_object_store: bool | None = None


class BackupDrillRunResponse(BaseModel):
    target_name: str
    started_at: str
    completed_at: str
    duration_seconds: float
    source_database_url: str
    target_database_url: str
    backup: dict[str, Any]
    restore: dict[str, Any]
    verification: dict[str, Any]
    status: str
    report_file: str


class BackupDrillAcceptedResponse(BaseModel):
    job_id: str
    action: str = "backup_restore_drill"
    accepted: bool = True
    deduplicated: bool = False
    target_name: str
    state: str
    stage: str
    status_url: str


class BackupDrillJobStatusResponse(BaseModel):
    job_id: str
    target_name: str
    state: str
    stage: str
    accepted_at: str
    updated_at: str
    attempt_count: int
    max_attempts: int
    cancellation_requested: bool = False
    report: BackupDrillRunResponse | None = None
    last_error: str | None = None


ManagementConfigEnvelope = OkEnvelope[ManagementConfigResponseModel]
BackupDrillPreviewEnvelope = OkEnvelope[BackupDrillPreviewResponse]
BackupDrillRunEnvelope = AcceptedEnvelope[BackupDrillAcceptedResponse]
BackupDrillJobStatusEnvelope = OkEnvelope[BackupDrillJobStatusResponse]
