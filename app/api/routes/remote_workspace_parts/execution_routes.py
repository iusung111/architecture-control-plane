from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from app.api.deps import (
    get_auth_context,
    get_remote_workspace_query_service,
    get_remote_workspace_write_service,
    get_request_id,
)
from app.core.auth import AuthContext
from app.core.config import get_settings
from app.schemas.common import ErrorEnvelope, envelope_accepted, envelope_ok
from app.schemas.remote_workspace import (
    RemoteWorkspaceExecutionEnvelope,
    RemoteWorkspaceExecutionListEnvelope,
    RemoteWorkspaceExecutionListResponse,
    RemoteWorkspaceExecutionRequest,
    RemoteWorkspaceExecutionResponse,
    RemoteWorkspaceExecutionResultCallbackRequest,
    RemoteWorkspaceResumeEnvelope,
    RemoteWorkspaceResumeRequest,
    RemoteWorkspaceResumeResponse,
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

@router.get("/executions/{execution_id}", response_model=RemoteWorkspaceExecutionEnvelope, responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}})
def get_remote_workspace_execution(
    execution_id: str,
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: RemoteWorkspaceQueryService = Depends(get_remote_workspace_query_service),
):
    item = service.get_execution(execution_id=execution_id, auth=auth)
    if item is None:
        raise HTTPException(status_code=404, detail="remote workspace execution not found")
    return envelope_ok(data=RemoteWorkspaceExecutionResponse.model_validate(item), request_id=request_id)

@router.get("/{workspace_id}/executions", response_model=RemoteWorkspaceExecutionListEnvelope, responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}})
def list_remote_workspace_executions(
    workspace_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: RemoteWorkspaceQueryService = Depends(get_remote_workspace_query_service),
):
    data = service.list_executions(workspace_id=workspace_id, auth=auth, limit=limit)
    return envelope_ok(data=RemoteWorkspaceExecutionListResponse.model_validate(data), request_id=request_id)

@router.get("/{workspace_id}/resume", response_model=RemoteWorkspaceResumeEnvelope, responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}})
def get_remote_workspace_resume(
    workspace_id: str,
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: RemoteWorkspaceQueryService = Depends(get_remote_workspace_query_service),
):
    item = service.get_resume(workspace_id=workspace_id, auth=auth)
    if item is None:
        raise HTTPException(status_code=404, detail="remote workspace not found")
    return envelope_ok(data=RemoteWorkspaceResumeResponse.model_validate(item), request_id=request_id)

@router.post("/{workspace_id}/resume", response_model=RemoteWorkspaceResumeEnvelope, responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}})
def resume_remote_workspace(
    workspace_id: str,
    payload: RemoteWorkspaceResumeRequest,
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: RemoteWorkspaceWriteService = Depends(get_remote_workspace_write_service),
):
    data = service.mark_resumed(workspace_id=workspace_id, auth=auth, note=payload.note)
    return envelope_ok(data=RemoteWorkspaceResumeResponse.model_validate(data), request_id=request_id)

@router.post("/executions", response_model=RemoteWorkspaceExecutionEnvelope, responses={202: {"model": RemoteWorkspaceExecutionEnvelope}, 401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}})
def request_remote_workspace_execution(
    payload: RemoteWorkspaceExecutionRequest,
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: RemoteWorkspaceWriteService = Depends(get_remote_workspace_write_service),
):
    data = service.request_execution(payload=payload.model_dump(), auth=auth)
    return envelope_accepted(data=RemoteWorkspaceExecutionResponse.model_validate(data), request_id=request_id)

@router.post("/executions/{execution_id}/cancel", response_model=RemoteWorkspaceExecutionEnvelope, responses={202: {"model": RemoteWorkspaceExecutionEnvelope}, 401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}, 409: {"model": ErrorEnvelope}})
def cancel_remote_workspace_execution(
    execution_id: str,
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: RemoteWorkspaceWriteService = Depends(get_remote_workspace_write_service),
):
    data = service.cancel_execution(execution_id=execution_id, auth=auth)
    return envelope_accepted(data=RemoteWorkspaceExecutionResponse.model_validate(data), request_id=request_id)

@router.post("/executions/{execution_id}/result", response_model=RemoteWorkspaceExecutionEnvelope, responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}, 409: {"model": ErrorEnvelope}})
def record_remote_workspace_execution_result(
    execution_id: str,
    payload: RemoteWorkspaceExecutionResultCallbackRequest,
    x_remote_workspace_callback_token: str | None = Header(default=None, alias="X-Remote-Workspace-Callback-Token"),
    request_id: str = Depends(get_request_id),
    service: RemoteWorkspaceWriteService = Depends(get_remote_workspace_write_service),
):
    settings = get_settings()
    expected = settings.remote_workspace_callback_token
    if not expected or x_remote_workspace_callback_token != expected:
        raise HTTPException(status_code=403, detail="invalid remote workspace callback token")
    data = service.record_result_callback(execution_id=execution_id, payload=payload.model_dump(mode="json"))
    return envelope_ok(data=RemoteWorkspaceExecutionResponse.model_validate(data), request_id=request_id)
