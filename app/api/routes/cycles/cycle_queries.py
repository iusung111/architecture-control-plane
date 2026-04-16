from .common import *

@router.post(
    "/cycles",
    response_model=CreateCycleEnvelope,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 409: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}, 429: {"model": ErrorEnvelope}},
    status_code=status.HTTP_201_CREATED,
)
def create_cycle(
    payload: CreateCycleRequest,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    _rate_limit: None = Depends(enforce_create_cycle_rate_limit),
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: CycleWriteService = Depends(get_cycle_write_service),
):
    try:
        created, data = service.create_cycle(payload=payload, auth=auth, idempotency_key=idempotency_key)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except StateConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not created:
        response.status_code = status.HTTP_200_OK
    return envelope_ok(data=CreateCycleResponse.model_validate(data), request_id=request_id)

@router.get(
    "/cycles",
    response_model=CycleListEnvelope,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}},
)
def list_cycles(
    project_id: str | None = None,
    state: str | None = None,
    user_status: str | None = None,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
    updated_after: datetime | None = None,
    updated_before: datetime | None = None,
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: CycleQueryService = Depends(get_cycle_query_service),
):
    try:
        data = service.list_cycles(
            auth=auth,
            project_id=project_id,
            state=state,
            user_status=user_status,
            created_after=created_after,
            created_before=created_before,
            updated_after=updated_after,
            updated_before=updated_before,
            cursor=cursor,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return envelope_ok(data=CycleListResponse.model_validate(data), request_id=request_id)

@router.get(
    "/cycles/board",
    response_model=CycleBoardEnvelope,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}},
)
def get_cycle_board(
    project_id: str | None = None,
    limit_per_column: int = Query(default=12, ge=1, le=50),
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: CycleQueryService = Depends(get_cycle_query_service),
):
    data = service.get_board_snapshot(auth=auth, project_id=project_id, limit_per_column=limit_per_column)
    return envelope_ok(data=CycleBoardResponse.model_validate(data), request_id=request_id)

@router.get(
    "/cycles/{cycle_id}/comments",
    response_model=CycleCommentListEnvelope,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}},
)
def list_cycle_comments(
    cycle_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: CycleQueryService = Depends(get_cycle_query_service),
):
    try:
        data = service.list_cycle_comments(cycle_id, auth, limit=limit)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if not data:
        raise HTTPException(status_code=404, detail="cycle not found")
    return envelope_ok(data=CycleCommentListResponse.model_validate(data), request_id=request_id)

@router.get(
    "/cycles/{cycle_id}/assignments",
    response_model=CycleAssignmentListEnvelope,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}},
)
def list_cycle_assignments(
    cycle_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: CycleQueryService = Depends(get_cycle_query_service),
):
    try:
        data = service.list_cycle_assignments(cycle_id, auth, limit=limit)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if not data:
        raise HTTPException(status_code=404, detail="cycle not found")
    return envelope_ok(data=CycleAssignmentListResponse.model_validate(data), request_id=request_id)

@router.get(
    "/cycles/{cycle_id}/assignment-suggestions",
    response_model=AssignmentSuggestionListEnvelope,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}},
)
def list_cycle_assignment_suggestions(
    cycle_id: str,
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: CycleQueryService = Depends(get_cycle_query_service),
):
    try:
        data = service.get_cycle_assignment_suggestions(cycle_id, auth)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if not data:
        raise HTTPException(status_code=404, detail="cycle not found")
    return envelope_ok(data=AssignmentSuggestionListResponse.model_validate(data), request_id=request_id)

@router.get(
    "/cycles/{cycle_id}/assignment-learning-weights",
    response_model=AssignmentLearningWeightListEnvelope,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}},
)
def get_cycle_assignment_learning_weights(
    cycle_id: str,
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: CycleQueryService = Depends(get_cycle_query_service),
):
    data = service.get_assignment_learning_weights(cycle_id, auth)
    if data is None:
        raise HTTPException(status_code=404, detail="cycle not found")
    return envelope_ok(data=AssignmentLearningWeightListResponse.model_validate(data), request_id=request_id)

@router.get(
    "/cycles/{cycle_id}/timeline",
    response_model=CycleTimelineEnvelope,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}},
)
def get_cycle_timeline(
    cycle_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: CycleQueryService = Depends(get_cycle_query_service),
):
    try:
        data = service.get_cycle_timeline(cycle_id, auth, limit=limit)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if not data:
        raise HTTPException(status_code=404, detail="cycle not found")
    return envelope_ok(data=CycleTimelineResponse.model_validate(data), request_id=request_id)

@router.get(
    "/cycles/{cycle_id}/card",
    response_model=CycleCardEnvelope,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}},
)
def get_cycle_card(
    cycle_id: str,
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: CycleQueryService = Depends(get_cycle_query_service),
):
    try:
        data = service.get_cycle_card(cycle_id, auth)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if not data:
        raise HTTPException(status_code=404, detail="cycle not found")
    return envelope_ok(data=CycleCardResponse.model_validate(data), request_id=request_id)

@router.get("/cycles/{cycle_id}", response_model=CycleSummaryEnvelope, responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}})
def get_cycle(
    cycle_id: str,
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: CycleQueryService = Depends(get_cycle_query_service),
):
    try:
        data = service.get_cycle_summary(cycle_id, auth)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if not data:
        raise HTTPException(status_code=404, detail="cycle not found")
    return envelope_ok(data=CycleSummaryResponse.model_validate(data), request_id=request_id)
