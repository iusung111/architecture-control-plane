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
    RemoteWorkspaceExecutorListEnvelope,
    RemoteWorkspaceExecutorListResponse,
    RemoteWorkspaceSnapshotEnvelope,
    RemoteWorkspaceSnapshotListEnvelope,
    RemoteWorkspaceSnapshotListResponse,
    RemoteWorkspaceSnapshotRequest,
    RemoteWorkspaceSnapshotResponse,
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

@router.get("/executors", response_model=RemoteWorkspaceExecutorListEnvelope, responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}})
def list_remote_workspace_executors(
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: RemoteWorkspaceQueryService = Depends(get_remote_workspace_query_service),
):
    del auth
    data = service.list_executors()
    return envelope_ok(data=RemoteWorkspaceExecutorListResponse.model_validate(data), request_id=request_id)

@router.get("/snapshots", response_model=RemoteWorkspaceSnapshotListEnvelope, responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}})
def list_remote_workspace_snapshots(
    project_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: RemoteWorkspaceQueryService = Depends(get_remote_workspace_query_service),
):
    data = service.list_snapshots(auth=auth, project_id=project_id, limit=limit)
    normalized = {**data, "items": [_normalize_snapshot(item) for item in data.get("items", [])]}
    return envelope_ok(data=RemoteWorkspaceSnapshotListResponse.model_validate(normalized), request_id=request_id)

@router.get("/snapshots/{workspace_id}", response_model=RemoteWorkspaceSnapshotEnvelope, responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}})
def get_remote_workspace_snapshot(
    workspace_id: str,
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: RemoteWorkspaceQueryService = Depends(get_remote_workspace_query_service),
):
    item = service.get_snapshot(workspace_id=workspace_id, auth=auth)
    if item is None:
        raise HTTPException(status_code=404, detail="remote workspace not found")
    return envelope_ok(data=RemoteWorkspaceSnapshotResponse.model_validate(_normalize_snapshot(item)), request_id=request_id)

@router.post("/snapshots", response_model=RemoteWorkspaceSnapshotEnvelope, responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}})
def save_remote_workspace_snapshot(
    payload: RemoteWorkspaceSnapshotRequest,
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: RemoteWorkspaceWriteService = Depends(get_remote_workspace_write_service),
):
    data = service.save_snapshot(payload=payload.model_dump(), auth=auth)
    return envelope_ok(data=RemoteWorkspaceSnapshotResponse.model_validate(_normalize_snapshot(data)), request_id=request_id)
