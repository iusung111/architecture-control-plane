from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import OkEnvelope


class LLMProviderPolicyResponse(BaseModel):
    provider: str
    configured: bool
    enabled: bool
    allow_work: bool
    allow_review: bool
    usage_mode: Literal["free_only", "paid"]
    priority: int
    daily_limit: int | None = None
    used_today: int
    remaining_today: int | None = None
    model: str
    external_quota_source: str | None = None
    external_requests_limit: int | None = None
    external_requests_remaining: int | None = None
    external_tokens_limit: int | None = None
    external_tokens_remaining: int | None = None
    external_daily_limit: int | None = None
    external_daily_used: int | None = None
    external_daily_remaining: int | None = None
    external_spend_limit_usd: float | None = None
    external_spend_used_usd: float | None = None
    external_spend_remaining_usd: float | None = None
    external_usage_tokens_input: int | None = None
    external_usage_tokens_output: int | None = None
    external_observed_at: str | None = None
    effective_scope: str = "global"


class LLMProviderPolicyUpdateRequest(BaseModel):
    enabled: bool | None = None
    allow_work: bool | None = None
    allow_review: bool | None = None
    usage_mode: Literal["free_only", "paid"] | None = None
    priority: int | None = None
    daily_request_limit_override: int | None = Field(default=None, ge=1)


class LLMScopeOverrideResponse(BaseModel):
    scope_type: Literal["tenant", "project"]
    scope_id: str
    provider: str
    enabled_override: bool | None = None
    allow_work_override: bool | None = None
    allow_review_override: bool | None = None
    usage_mode_override: Literal["free_only", "paid"] | None = None
    priority_offset: int
    daily_request_limit_override: int | None = None


class LLMScopeOverrideUpdateRequest(BaseModel):
    enabled_override: bool | None = None
    allow_work_override: bool | None = None
    allow_review_override: bool | None = None
    usage_mode_override: Literal["free_only", "paid"] | None = None
    priority_offset: int | None = None
    daily_request_limit_override: int | None = Field(default=None, ge=1)


class LLMScopeOverrideListResponse(BaseModel):
    overrides: list[LLMScopeOverrideResponse]


class LLMProviderPolicyListResponse(BaseModel):
    providers: list[LLMProviderPolicyResponse]


class LLMRoutingPreviewRequest(BaseModel):
    prompt_type: str = "review"
    complexity: Literal["low", "medium", "high"] = "medium"
    review_required: bool = True
    cycle_id: str | None = None
    tenant_id: str | None = None
    project_id: str | None = None


class LLMRoutingDecisionResponse(BaseModel):
    stage: Literal["work", "review"]
    complexity: Literal["low", "medium", "high"]
    provider: str
    model: str
    usage_mode: Literal["free_only", "paid"]
    session_id: str
    session_mode: Literal["job_session", "fresh_review_session"]
    source_session_id: str | None = None
    requires_fresh_session: bool = False
    remaining_requests: int | None = None
    rationale: dict


class LLMRoutingPreviewResponse(BaseModel):
    cycle_id: str | None = None
    prompt_type: str
    complexity: Literal["low", "medium", "high"]
    assignment_group_id: str
    tenant_id: str | None = None
    project_id: str | None = None
    work: LLMRoutingDecisionResponse | None = None
    review: LLMRoutingDecisionResponse | None = None


LLMProviderPolicyEnvelope = OkEnvelope[LLMProviderPolicyResponse]
LLMProviderPolicyListEnvelope = OkEnvelope[LLMProviderPolicyListResponse]
LLMScopeOverrideEnvelope = OkEnvelope[LLMScopeOverrideResponse]
LLMScopeOverrideListEnvelope = OkEnvelope[LLMScopeOverrideListResponse]
LLMRoutingPreviewEnvelope = OkEnvelope[LLMRoutingPreviewResponse]
