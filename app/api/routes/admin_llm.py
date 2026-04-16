from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import (
    get_audit_event_repository,
    get_llm_routing_service,
    get_request_id,
    require_management_admin,
    require_management_operator,
)
from app.schemas.common import ErrorEnvelope, envelope_ok
from app.core.management_auth import ManagementAuthContext
from app.repositories.audit import AuditEventRepository
from app.schemas.llm_management import (
    LLMProviderPolicyEnvelope,
    LLMProviderPolicyListEnvelope,
    LLMProviderPolicyListResponse,
    LLMProviderPolicyResponse,
    LLMProviderPolicyUpdateRequest,
    LLMRoutingPreviewEnvelope,
    LLMRoutingPreviewRequest,
    LLMRoutingPreviewResponse,
    LLMScopeOverrideEnvelope,
    LLMScopeOverrideListEnvelope,
    LLMScopeOverrideListResponse,
    LLMScopeOverrideResponse,
    LLMScopeOverrideUpdateRequest,
)
from app.services.llm_management import LLMRoutingService



def _record_management_audit(
    audit_repo: AuditEventRepository,
    *,
    management_ctx: ManagementAuthContext,
    event_type: str,
    request_id: str,
    payload: dict,
) -> None:
    audit_repo.add(
        actor_id=management_ctx.actor_id,
        event_type=event_type,
        event_payload={
            "request_id": request_id,
            "management_role": management_ctx.role,
            "management_key_source": management_ctx.key_source,
            "management_key_fingerprint": management_ctx.key_fingerprint,
            **payload,
        },
    )

router = APIRouter(prefix="/admin/llm", tags=["admin-llm"])


@router.get(
    "/providers",
    response_model=LLMProviderPolicyListEnvelope,
    responses={403: {"model": ErrorEnvelope}},
)
def list_llm_providers(
    request_id: str = Depends(get_request_id),
    _: ManagementAuthContext = Depends(require_management_operator),
    service: LLMRoutingService = Depends(get_llm_routing_service),
    tenant_id: str | None = None,
    project_id: str | None = None,
):
    providers = [
        LLMProviderPolicyResponse.model_validate(asdict(status))
        for status in service.list_provider_statuses(tenant_id=tenant_id, project_id=project_id)
    ]
    return envelope_ok(data=LLMProviderPolicyListResponse(providers=providers), request_id=request_id)


@router.post(
    "/providers/{provider}/refresh-quota",
    response_model=LLMProviderPolicyEnvelope,
    responses={403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}},
)
def refresh_llm_provider_quota(
    provider: str,
    request_id: str = Depends(get_request_id),
    management_ctx: ManagementAuthContext = Depends(require_management_operator),
    audit_repo: AuditEventRepository = Depends(get_audit_event_repository),
    service: LLMRoutingService = Depends(get_llm_routing_service),
):
    try:
        before = next((item for item in service.list_provider_statuses() if item.provider == provider), None)
        status = service.refresh_provider_quota(provider=provider)  # type: ignore[arg-type]
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _record_management_audit(
        audit_repo,
        management_ctx=management_ctx,
        event_type="management.llm_provider_quota.refreshed",
        request_id=request_id,
        payload={
            "provider": provider,
            "before": asdict(before) if before else None,
            "after": asdict(status),
        },
    )
    return envelope_ok(data=LLMProviderPolicyResponse.model_validate(asdict(status)), request_id=request_id)


@router.put(
    "/providers/{provider}",
    response_model=LLMProviderPolicyEnvelope,
    responses={403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}},
)
def update_llm_provider_policy(
    provider: str,
    payload: LLMProviderPolicyUpdateRequest,
    request_id: str = Depends(get_request_id),
    management_ctx: ManagementAuthContext = Depends(require_management_admin),
    audit_repo: AuditEventRepository = Depends(get_audit_event_repository),
    service: LLMRoutingService = Depends(get_llm_routing_service),
):
    try:
        before = next((item for item in service.list_provider_statuses() if item.provider == provider), None)
        status = service.update_policy(
            provider=provider,  # type: ignore[arg-type]
            enabled=payload.enabled,
            allow_work=payload.allow_work,
            allow_review=payload.allow_review,
            usage_mode=payload.usage_mode,
            priority=payload.priority,
            daily_request_limit_override=payload.daily_request_limit_override,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _record_management_audit(
        audit_repo,
        management_ctx=management_ctx,
        event_type="management.llm_provider_policy.updated",
        request_id=request_id,
        payload={
            "provider": provider,
            "before": asdict(before) if before else None,
            "after": asdict(status),
            "requested_changes": payload.model_dump(exclude_none=True),
        },
    )
    return envelope_ok(data=LLMProviderPolicyResponse.model_validate(asdict(status)), request_id=request_id)


@router.get(
    "/scopes/{scope_type}/{scope_id}",
    response_model=LLMScopeOverrideListEnvelope,
    responses={403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}},
)
def list_llm_scope_overrides(
    scope_type: str,
    scope_id: str,
    request_id: str = Depends(get_request_id),
    _: ManagementAuthContext = Depends(require_management_operator),
    service: LLMRoutingService = Depends(get_llm_routing_service),
):
    if scope_type not in {"tenant", "project"}:
        raise HTTPException(status_code=404, detail=f"unsupported scope_type '{scope_type}'")
    overrides = [
        LLMScopeOverrideResponse.model_validate(asdict(item))
        for item in service.list_scope_overrides(scope_type=scope_type, scope_id=scope_id)  # type: ignore[arg-type]
    ]
    return envelope_ok(data=LLMScopeOverrideListResponse(overrides=overrides), request_id=request_id)


@router.put(
    "/scopes/{scope_type}/{scope_id}/providers/{provider}",
    response_model=LLMScopeOverrideEnvelope,
    responses={403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}},
)
def upsert_llm_scope_override(
    scope_type: str,
    scope_id: str,
    provider: str,
    payload: LLMScopeOverrideUpdateRequest,
    request_id: str = Depends(get_request_id),
    management_ctx: ManagementAuthContext = Depends(require_management_admin),
    audit_repo: AuditEventRepository = Depends(get_audit_event_repository),
    service: LLMRoutingService = Depends(get_llm_routing_service),
):
    if scope_type not in {"tenant", "project"}:
        raise HTTPException(status_code=404, detail=f"unsupported scope_type '{scope_type}'")
    try:
        before = next((item for item in service.list_scope_overrides(scope_type, scope_id) if item.provider == provider), None)
        override = service.upsert_scope_override(
            scope_type=scope_type,  # type: ignore[arg-type]
            scope_id=scope_id,
            provider=provider,  # type: ignore[arg-type]
            enabled_override=payload.enabled_override,
            allow_work_override=payload.allow_work_override,
            allow_review_override=payload.allow_review_override,
            usage_mode_override=payload.usage_mode_override,
            priority_offset=payload.priority_offset,
            daily_request_limit_override=payload.daily_request_limit_override,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _record_management_audit(
        audit_repo,
        management_ctx=management_ctx,
        event_type="management.llm_scope_override.upserted",
        request_id=request_id,
        payload={
            "scope_type": scope_type,
            "scope_id": scope_id,
            "provider": provider,
            "before": asdict(before) if before else None,
            "after": asdict(override),
            "requested_changes": payload.model_dump(exclude_none=True),
        },
    )
    return envelope_ok(data=LLMScopeOverrideResponse.model_validate(asdict(override)), request_id=request_id)


@router.post(
    "/routing/preview",
    response_model=LLMRoutingPreviewEnvelope,
    responses={403: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}},
)
def preview_llm_routing(
    payload: LLMRoutingPreviewRequest,
    request_id: str = Depends(get_request_id),
    _: ManagementAuthContext = Depends(require_management_operator),
    service: LLMRoutingService = Depends(get_llm_routing_service),
):
    preview = service.preview_assignment(
        prompt_type=payload.prompt_type,
        complexity=payload.complexity,
        review_required=payload.review_required,
        cycle_id=payload.cycle_id,
        tenant_id=payload.tenant_id,
        project_id=payload.project_id,
    )
    return envelope_ok(data=LLMRoutingPreviewResponse.model_validate(preview), request_id=request_id)
