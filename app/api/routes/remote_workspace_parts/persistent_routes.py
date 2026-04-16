from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import (
    get_auth_context,
    get_remote_workspace_query_service,
    get_remote_workspace_write_service,
    get_request_id,
)
from app.core.auth import AuthContext
from app.schemas.common import ErrorEnvelope, envelope_ok
from app.schemas.remote_workspace import (
    PersistentWorkspaceSessionEnvelope,
    PersistentWorkspaceSessionListResponse,
    PersistentWorkspaceSessionListEnvelope,
    PersistentWorkspaceSessionRequest,
    PersistentWorkspaceSessionResponse,
)
from app.services.remote_workspace import RemoteWorkspaceQueryService, RemoteWorkspaceWriteService


def _normalize_snapshot(data: dict) -> dict:
    return {
        **data,
        "patch_present": bool(data.get("patch") or data.get("patch_stack")),
        "artifact_count": len(data.get("artifacts", [])),
        "artifact_history": data.get("artifact_history") or data.get("artifacts") or [],
    }

router = APIRouter(prefix="/remote-workspaces", tags=["remote-workspaces"])

@router.get("/persistent/sessions", response_model=PersistentWorkspaceSessionListEnvelope, responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}})
def list_persistent_workspace_sessions(
    limit: int = Query(default=50, ge=1, le=200),
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: RemoteWorkspaceQueryService = Depends(get_remote_workspace_query_service),
):
    data = service.list_persistent_sessions(auth=auth, limit=limit)
    return envelope_ok(data=PersistentWorkspaceSessionListResponse.model_validate(data), request_id=request_id)

@router.get("/persistent/sessions/{workspace_id}", response_model=PersistentWorkspaceSessionEnvelope, responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}})
def get_persistent_workspace_session(
    workspace_id: str,
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: RemoteWorkspaceQueryService = Depends(get_remote_workspace_query_service),
):
    item = service.get_persistent_session(workspace_id=workspace_id, auth=auth)
    if item is None:
        raise HTTPException(status_code=404, detail="persistent workspace session not found")
    return envelope_ok(data=PersistentWorkspaceSessionResponse.model_validate(item), request_id=request_id)

@router.post("/persistent/sessions", response_model=PersistentWorkspaceSessionEnvelope, responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}})
def save_persistent_workspace_session(
    payload: PersistentWorkspaceSessionRequest,
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: RemoteWorkspaceWriteService = Depends(get_remote_workspace_write_service),
):
    data = service.save_persistent_session(payload=payload.model_dump(), auth=auth)
    return envelope_ok(data=PersistentWorkspaceSessionResponse.model_validate(data), request_id=request_id)

@router.post("/persistent/sessions/{workspace_id}/hibernate", response_model=PersistentWorkspaceSessionEnvelope, responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}, 409: {"model": ErrorEnvelope}})
def hibernate_persistent_workspace_session(
    workspace_id: str,
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: RemoteWorkspaceWriteService = Depends(get_remote_workspace_write_service),
):
    data = service.hibernate_persistent_session(workspace_id=workspace_id, auth=auth)
    return envelope_ok(data=PersistentWorkspaceSessionResponse.model_validate(data), request_id=request_id)

@router.delete("/persistent/sessions/{workspace_id}", response_model=PersistentWorkspaceSessionEnvelope, responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}, 409: {"model": ErrorEnvelope}})
def delete_persistent_workspace_session(
    workspace_id: str,
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: RemoteWorkspaceWriteService = Depends(get_remote_workspace_write_service),
):
    data = service.delete_persistent_session(workspace_id=workspace_id, auth=auth)
    return envelope_ok(data=PersistentWorkspaceSessionResponse.model_validate(data), request_id=request_id)
