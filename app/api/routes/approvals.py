from fastapi import APIRouter, Depends, Header, HTTPException, Query

from app.api.deps import enforce_approval_confirm_rate_limit, get_approval_service, get_auth_context, get_request_id
from app.core.auth import AuthContext
from app.schemas.approvals import ApprovalDecisionEnvelope, ApprovalDecisionRequest, ApprovalDecisionResponse, PendingApprovalListEnvelope, PendingApprovalListResponse
from app.schemas.common import ErrorEnvelope, envelope_ok
from app.services.approvals import ApprovalConflictError, ApprovalExpiredError, ApprovalNotFoundError, ApprovalService

router = APIRouter(tags=["approvals"])


@router.get(
    "/approvals/pending",
    response_model=PendingApprovalListEnvelope,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 429: {"model": ErrorEnvelope}},
)
def list_pending_approvals(
    project_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: ApprovalService = Depends(get_approval_service),
):
    data = service.list_pending(
        actor_id=auth.user_id,
        actor_role=auth.role,
        actor_tenant_id=auth.tenant_id,
        project_id=project_id,
        limit=limit,
    )
    return envelope_ok(data=PendingApprovalListResponse.model_validate(data), request_id=request_id)


@router.post(
    "/approvals/{approval_id}/confirm",
    response_model=ApprovalDecisionEnvelope,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}, 409: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}, 429: {"model": ErrorEnvelope}},
)
def confirm_approval(
    approval_id: str,
    payload: ApprovalDecisionRequest,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    _rate_limit: None = Depends(enforce_approval_confirm_rate_limit),
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: ApprovalService = Depends(get_approval_service),
):
    try:
        data = service.confirm(
            approval_id=approval_id,
            decision=payload.decision,
            actor_id=auth.user_id,
            actor_role=auth.role,
            actor_tenant_id=auth.tenant_id,
            comment=payload.comment,
            reason_code=payload.reason_code,
            idempotency_key=idempotency_key,
        )
    except ApprovalNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ApprovalExpiredError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ApprovalConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return envelope_ok(data=ApprovalDecisionResponse.model_validate(data), request_id=request_id)
