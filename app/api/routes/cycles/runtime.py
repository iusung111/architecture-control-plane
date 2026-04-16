from .common import *

@router.get(
    "/runtime/registrations",
    response_model=RuntimeRegistrationListEnvelope,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}},
)
def list_runtime_registrations(
    project_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: CycleQueryService = Depends(get_cycle_query_service),
):
    data = service.list_runtime_registrations(auth=auth, project_id=project_id, limit=limit)
    return envelope_ok(data=RuntimeRegistrationListResponse.model_validate(data), request_id=request_id)

@router.post(
    "/runtime/registrations",
    response_model=RuntimeRegistrationEnvelope,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}},
)
def register_runtime(
    payload: RuntimeRegistrationRequest,
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: CycleWriteService = Depends(get_cycle_write_service),
):
    data = service.register_runtime(payload=payload.model_dump(mode="json"), auth=auth)
    return envelope_ok(data=RuntimeRegistrationResponse.model_validate(data), request_id=request_id)

@router.get(
    "/runtime/registrations/{runtime_id}/actions",
    response_model=RuntimeActionListEnvelope,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}},
)
def list_runtime_actions(
    runtime_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: CycleQueryService = Depends(get_cycle_query_service),
):
    try:
        data = service.list_runtime_actions(auth=auth, runtime_id=runtime_id, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return envelope_ok(data=RuntimeActionListResponse.model_validate(data), request_id=request_id)

@router.post(
    "/runtime/registrations/{runtime_id}/actions",
    response_model=RuntimeActionEnvelope,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}},
)
def enqueue_runtime_action(
    runtime_id: str,
    payload: RuntimeActionRequest,
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: CycleWriteService = Depends(get_cycle_write_service),
):
    try:
        data = service.enqueue_runtime_action(runtime_id=runtime_id, action=payload.action, arguments=payload.arguments, auth=auth)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return envelope_ok(data=RuntimeActionResponse.model_validate(data), request_id=request_id)

@router.post(
    "/runtime/registrations/{runtime_id}/actions/{action_id}/acknowledge",
    response_model=RuntimeActionEnvelope,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}},
)
def acknowledge_runtime_action(
    runtime_id: str,
    action_id: str,
    payload: RuntimeActionAcknowledgeRequest,
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: CycleWriteService = Depends(get_cycle_write_service),
):
    try:
        data = service.acknowledge_runtime_action(runtime_id=runtime_id, action_id=action_id, note=payload.note, auth=auth)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return envelope_ok(data=RuntimeActionResponse.model_validate(data), request_id=request_id)

@router.post(
    "/runtime/registrations/{runtime_id}/actions/{action_id}/state",
    response_model=RuntimeActionEnvelope,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}},
)
def transition_runtime_action_state(
    runtime_id: str,
    action_id: str,
    payload: RuntimeActionStateRequest,
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: CycleWriteService = Depends(get_cycle_write_service),
):
    try:
        data = service.transition_runtime_action_state(runtime_id=runtime_id, action_id=action_id, status=payload.status, note=payload.note, metadata=payload.metadata, auth=auth)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return envelope_ok(data=RuntimeActionResponse.model_validate(data), request_id=request_id)

@router.get(
    "/runtime/registrations/{runtime_id}/actions/{action_id}/timeline",
    response_model=RuntimeActionTimelineEnvelope,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}},
)
def list_runtime_action_timeline(
    runtime_id: str,
    action_id: str,
    limit: int = Query(default=100, ge=1, le=300),
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: CycleQueryService = Depends(get_cycle_query_service),
):
    try:
        data = service.get_runtime_action_timeline(auth=auth, runtime_id=runtime_id, action_id=action_id, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return envelope_ok(data=RuntimeActionTimelineResponse.model_validate(data), request_id=request_id)

@router.get(
    "/runtime/registrations/{runtime_id}/actions/{action_id}/receipts",
    response_model=RuntimeActionReceiptListEnvelope,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}},
)
def list_runtime_action_receipts(
    runtime_id: str,
    action_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: CycleQueryService = Depends(get_cycle_query_service),
):
    try:
        data = service.list_runtime_action_receipts(auth=auth, runtime_id=runtime_id, action_id=action_id, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return envelope_ok(data=RuntimeActionReceiptListResponse.model_validate(data), request_id=request_id)

@router.post(
    "/runtime/registrations/{runtime_id}/actions/{action_id}/receipts",
    response_model=RuntimeActionReceiptEnvelope,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}},
)
def add_runtime_action_receipt(
    runtime_id: str,
    action_id: str,
    payload: RuntimeActionReceiptRequest,
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: CycleWriteService = Depends(get_cycle_write_service),
):
    try:
        data = service.add_runtime_action_receipt(runtime_id=runtime_id, action_id=action_id, summary=payload.summary, status=payload.status, metadata=payload.metadata, auth=auth)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return envelope_ok(data=RuntimeActionReceiptResponse.model_validate(data), request_id=request_id)
