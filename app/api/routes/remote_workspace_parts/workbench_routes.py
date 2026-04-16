from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import (
    get_auth_context,
    get_remote_workspace_query_service,
    get_remote_workspace_write_service,
    get_request_id,
)
from app.core.auth import AuthContext
from app.schemas.common import ErrorEnvelope, envelope_ok
from app.schemas.remote_workspace import (
    WorkbenchSavedViewEnvelope,
    WorkbenchSavedViewListEnvelope,
    WorkbenchSavedViewListResponse,
    WorkbenchSavedViewRequest,
    WorkbenchSavedViewResponse,
)
from app.services.remote_workspace import RemoteWorkspaceQueryService, RemoteWorkspaceWriteService


def _normalize_snapshot(data: dict) -> dict:
    return {
        **data,
        "patch_present": bool(data.get("patch") or data.get("patch_stack")),
        "artifact_count": len(data.get("artifacts", [])),
        "artifact_history": data.get("artifact_history") or data.get("artifacts") or [],
    }

router = APIRouter(prefix="/workbench", tags=["workbench"])

@router.get("/views", response_model=WorkbenchSavedViewListEnvelope, responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}})
def list_workbench_views(
    limit: int = Query(default=50, ge=1, le=200),
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: RemoteWorkspaceQueryService = Depends(get_remote_workspace_query_service),
):
    data = service.list_workbench_views(auth=auth, limit=limit)
    return envelope_ok(data=WorkbenchSavedViewListResponse.model_validate(data), request_id=request_id)

@router.post("/views", response_model=WorkbenchSavedViewEnvelope, responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}})
def save_workbench_view(
    payload: WorkbenchSavedViewRequest,
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: RemoteWorkspaceWriteService = Depends(get_remote_workspace_write_service),
):
    data = service.save_workbench_view(payload=payload.model_dump(), auth=auth)
    return envelope_ok(data=WorkbenchSavedViewResponse.model_validate(data), request_id=request_id)

@router.patch("/views/{view_id}", response_model=WorkbenchSavedViewEnvelope, responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}})
def update_workbench_view(
    view_id: str,
    payload: WorkbenchSavedViewRequest,
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: RemoteWorkspaceWriteService = Depends(get_remote_workspace_write_service),
):
    data = service.update_workbench_view(view_id=view_id, payload=payload.model_dump(), auth=auth)
    return envelope_ok(data=WorkbenchSavedViewResponse.model_validate(data), request_id=request_id)

@router.delete("/views/{view_id}", response_model=WorkbenchSavedViewEnvelope, responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}})
def delete_workbench_view(
    view_id: str,
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: RemoteWorkspaceWriteService = Depends(get_remote_workspace_write_service),
):
    data = service.delete_workbench_view(view_id=view_id, auth=auth)
    return envelope_ok(data=WorkbenchSavedViewResponse.model_validate(data), request_id=request_id)

@router.post("/views/{view_id}/use", response_model=WorkbenchSavedViewEnvelope, responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}})
def use_workbench_view(
    view_id: str,
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: RemoteWorkspaceWriteService = Depends(get_remote_workspace_write_service),
):
    data = service.mark_workbench_view_used(view_id=view_id, auth=auth)
    return envelope_ok(data=WorkbenchSavedViewResponse.model_validate(data), request_id=request_id)
