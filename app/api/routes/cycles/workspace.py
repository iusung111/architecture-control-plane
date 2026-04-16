from .common import *

@router.get(
    "/workspace/overview",
    response_model=WorkspaceOverviewEnvelope,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}},
)
def get_workspace_overview(
    project_id: str | None = None,
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: CycleQueryService = Depends(get_cycle_query_service),
):
    data = service.get_workspace_overview(auth=auth, project_id=project_id)
    return envelope_ok(data=WorkspaceOverviewResponse.model_validate(data), request_id=request_id)

@router.get(
    "/agents/profiles",
    response_model=AgentProfileListEnvelope,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}},
)
def list_agent_profiles(
    project_id: str | None = None,
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: CycleQueryService = Depends(get_cycle_query_service),
):
    data = service.get_agent_profiles(auth=auth, project_id=project_id)
    return envelope_ok(data=AgentProfileListResponse.model_validate(data), request_id=request_id)

@router.get(
    "/runtime/panel",
    response_model=RuntimePanelEnvelope,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}},
)
def get_runtime_panel(
    project_id: str | None = None,
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: CycleQueryService = Depends(get_cycle_query_service),
):
    data = service.get_runtime_panel(auth=auth, project_id=project_id)
    return envelope_ok(data=RuntimePanelResponse.model_validate(data), request_id=request_id)

@router.get(
    "/workspace/discussions",
    response_model=WorkspaceDiscussionListEnvelope,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}},
)
def list_workspace_discussions(
    project_id: str | None = None,
    mention: str | None = None,
    query: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: CycleQueryService = Depends(get_cycle_query_service),
):
    data = service.list_workspace_discussions(auth=auth, project_id=project_id, mention=mention, query=query, limit=limit)
    return envelope_ok(data=WorkspaceDiscussionListResponse.model_validate(data), request_id=request_id)

@router.get(
    "/workspace/discussions/groups",
    response_model=WorkspaceDiscussionGroupListEnvelope,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}},
)
def list_workspace_discussion_groups(
    project_id: str | None = None,
    mention: str | None = None,
    query: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: CycleQueryService = Depends(get_cycle_query_service),
):
    data = service.group_workspace_discussions(auth=auth, project_id=project_id, mention=mention, query=query, limit=limit)
    return envelope_ok(data=WorkspaceDiscussionGroupListResponse.model_validate(data), request_id=request_id)

@router.get(
    "/workspace/discussion-filters",
    response_model=WorkspaceDiscussionSavedFilterListEnvelope,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}},
)
def list_workspace_discussion_saved_filters(
    limit: int = Query(default=50, ge=1, le=200),
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: CycleQueryService = Depends(get_cycle_query_service),
):
    data = service.list_workspace_discussion_saved_filters(auth=auth, limit=limit)
    return envelope_ok(data=WorkspaceDiscussionSavedFilterListResponse.model_validate(data), request_id=request_id)

@router.post(
    "/workspace/discussion-filters",
    response_model=WorkspaceDiscussionSavedFilterEnvelope,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}},
)
def save_workspace_discussion_filter(
    payload: WorkspaceDiscussionSavedFilterRequest,
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: CycleWriteService = Depends(get_cycle_write_service),
):
    data = service.save_workspace_discussion_filter(name=payload.name, project_id=payload.project_id, mention=payload.mention, query=payload.query, auth=auth)
    return envelope_ok(data=WorkspaceDiscussionSavedFilterResponse.model_validate(data), request_id=request_id)

@router.patch(
    "/workspace/discussion-filters/{filter_id}",
    response_model=WorkspaceDiscussionSavedFilterEnvelope,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}},
)
def update_workspace_discussion_filter(
    filter_id: str,
    payload: WorkspaceDiscussionSavedFilterUpdateRequest,
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: CycleWriteService = Depends(get_cycle_write_service),
):
    try:
        data = service.update_workspace_discussion_filter(filter_id=filter_id, name=payload.name, project_id=payload.project_id, mention=payload.mention, query=payload.query, auth=auth)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return envelope_ok(data=WorkspaceDiscussionSavedFilterResponse.model_validate(data), request_id=request_id)

@router.post(
    "/workspace/discussion-filters/{filter_id}/favorite",
    response_model=WorkspaceDiscussionSavedFilterEnvelope,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}},
)
def favorite_workspace_discussion_filter(
    filter_id: str,
    payload: WorkspaceDiscussionSavedFilterFavoriteRequest,
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: CycleWriteService = Depends(get_cycle_write_service),
):
    try:
        data = service.set_workspace_discussion_filter_favorite(filter_id=filter_id, is_favorite=payload.is_favorite, auth=auth)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return envelope_ok(data=WorkspaceDiscussionSavedFilterResponse.model_validate(data), request_id=request_id)

@router.post(
    "/workspace/discussion-filters/{filter_id}/use",
    response_model=WorkspaceDiscussionSavedFilterEnvelope,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}},
)
def mark_workspace_discussion_filter_used(
    filter_id: str,
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: CycleWriteService = Depends(get_cycle_write_service),
):
    try:
        data = service.mark_workspace_discussion_filter_used(filter_id=filter_id, auth=auth)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return envelope_ok(data=WorkspaceDiscussionSavedFilterResponse.model_validate(data), request_id=request_id)

@router.delete(
    "/workspace/discussion-filters/{filter_id}",
    response_model=WorkspaceDiscussionSavedFilterEnvelope,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}},
)
def delete_workspace_discussion_filter(
    filter_id: str,
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: CycleWriteService = Depends(get_cycle_write_service),
):
    try:
        data = service.delete_workspace_discussion_filter(filter_id=filter_id, auth=auth)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return envelope_ok(data=WorkspaceDiscussionSavedFilterResponse.model_validate(data), request_id=request_id)

@router.post(
    "/workspace/discussions",
    response_model=WorkspaceDiscussionEnvelope,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}},
)
def add_workspace_discussion(
    payload: WorkspaceDiscussionRequest,
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: CycleWriteService = Depends(get_cycle_write_service),
):
    data = service.add_workspace_discussion(project_id=payload.project_id, body=payload.body, mentions=payload.mentions, auth=auth)
    return envelope_ok(data=WorkspaceDiscussionResponse.model_validate(data), request_id=request_id)

@router.post(
    "/workspace/discussions/{discussion_id}/resolve",
    response_model=WorkspaceDiscussionEnvelope,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}},
)
def set_workspace_discussion_resolved(
    discussion_id: str,
    payload: WorkspaceDiscussionResolutionRequest,
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: CycleWriteService = Depends(get_cycle_write_service),
):
    try:
        data = service.set_workspace_discussion_resolved(discussion_id=discussion_id, resolved=payload.resolved, note=payload.note, auth=auth)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return envelope_ok(data=WorkspaceDiscussionResponse.model_validate(data), request_id=request_id)

@router.post(
    "/workspace/discussions/{discussion_id}/pin",
    response_model=WorkspaceDiscussionEnvelope,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}},
)
def set_workspace_discussion_pinned(
    discussion_id: str,
    payload: WorkspaceDiscussionPinRequest,
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: CycleWriteService = Depends(get_cycle_write_service),
):
    try:
        data = service.set_workspace_discussion_pinned(discussion_id=discussion_id, pinned=payload.pinned, note=payload.note, auth=auth)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return envelope_ok(data=WorkspaceDiscussionResponse.model_validate(data), request_id=request_id)

@router.get(
    "/workspace/discussions/{discussion_id}/replies",
    response_model=WorkspaceDiscussionReplyListEnvelope,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}},
)
def list_workspace_discussion_replies(
    discussion_id: str,
    mention: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: CycleQueryService = Depends(get_cycle_query_service),
):
    try:
        data = service.list_workspace_discussion_replies(auth=auth, discussion_id=discussion_id, mention=mention, limit=limit)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return envelope_ok(data=WorkspaceDiscussionReplyListResponse.model_validate(data), request_id=request_id)

@router.post(
    "/workspace/discussions/{discussion_id}/replies",
    response_model=WorkspaceDiscussionReplyEnvelope,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}},
)
def add_workspace_discussion_reply(
    discussion_id: str,
    payload: WorkspaceDiscussionReplyRequest,
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: CycleWriteService = Depends(get_cycle_write_service),
):
    try:
        data = service.add_workspace_discussion_reply(discussion_id=discussion_id, body=payload.body, mentions=payload.mentions, auth=auth)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return envelope_ok(data=WorkspaceDiscussionReplyResponse.model_validate(data), request_id=request_id)
