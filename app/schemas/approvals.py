from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.common import OkEnvelope


class ApprovalDecisionRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    comment: str | None = None
    reason_code: str | None = None


class ApprovalDecisionResponse(BaseModel):
    approval_id: str
    decision: str
    approval_state: str
    cycle_id: str
    resume_enqueued: bool
    acted_at: datetime


ApprovalDecisionEnvelope = OkEnvelope[ApprovalDecisionResponse]


class ApprovalListItem(BaseModel):
    approval_id: str
    cycle_id: str
    project_id: str
    required_role: str
    approval_state: str
    cycle_state: str
    user_status: str
    expires_at: datetime
    created_at: datetime


class PendingApprovalListResponse(BaseModel):
    items: list[ApprovalListItem]


PendingApprovalListEnvelope = OkEnvelope[PendingApprovalListResponse]
