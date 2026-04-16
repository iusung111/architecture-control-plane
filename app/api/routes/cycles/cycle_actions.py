from .common import *

@router.post(
    "/cycles/{cycle_id}/comments",
    response_model=CycleCommentEnvelope,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}},
)
def add_cycle_comment(
    cycle_id: str,
    payload: CycleCommentRequest,
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: CycleWriteService = Depends(get_cycle_write_service),
):
    try:
        data = service.add_cycle_comment(cycle_id, body=payload.body, mentions=payload.mentions, auth=auth)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return envelope_ok(data=CycleCommentResponse.model_validate(data), request_id=request_id)

@router.post(
    "/cycles/{cycle_id}/assignment-suggestions/feedback",
    response_model=AssignmentSuggestionFeedbackEnvelope,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}},
)
def record_cycle_assignment_suggestion_feedback(
    cycle_id: str,
    payload: AssignmentSuggestionFeedbackRequest,
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: CycleWriteService = Depends(get_cycle_write_service),
):
    try:
        data = service.record_assignment_suggestion_feedback(cycle_id, agent_id=payload.agent_id, feedback=payload.feedback, note=payload.note, auth=auth)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        status_code = 404 if str(exc) == "cycle not found" else 422
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return envelope_ok(data=AssignmentSuggestionFeedbackResponse.model_validate(data), request_id=request_id)

@router.post(
    "/cycles/{cycle_id}/assignments",
    response_model=CycleAssignmentEnvelope,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}},
)
def assign_cycle_agent(
    cycle_id: str,
    payload: CycleAssignmentRequest,
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: CycleWriteService = Depends(get_cycle_write_service),
):
    try:
        data = service.assign_cycle_agent(cycle_id, agent_id=payload.agent_id, assignment_role=payload.assignment_role, note=payload.note, auth=auth)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return envelope_ok(data=CycleAssignmentResponse.model_validate(data), request_id=request_id)

@router.get(
    "/cycles/{cycle_id}/result",
    response_model=CycleResultEnvelope,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}, 409: {"model": ErrorEnvelope}},
)
def get_cycle_result(
    cycle_id: str,
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: CycleQueryService = Depends(get_cycle_query_service),
):
    try:
        data = service.get_cycle_result(cycle_id, auth)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except StateConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not data:
        raise HTTPException(status_code=404, detail="cycle result not found")
    return envelope_ok(data=CycleResultResponse.model_validate(data), request_id=request_id)

@router.post(
    "/cycles/{cycle_id}/retry",
    response_model=ActionAcceptedEnvelope,
    responses=COMMON_ERROR_RESPONSES,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_cycle(
    cycle_id: str,
    payload: RetryCycleRequest,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    _rate_limit: None = Depends(enforce_retry_cycle_rate_limit),
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: CycleWriteService = Depends(get_cycle_write_service),
):
    try:
        data = service.retry_cycle(cycle_id, payload.reason, idempotency_key, auth)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except StateConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return envelope_accepted(data=ActionAcceptedResponse.model_validate(data), request_id=request_id)

@router.post(
    "/cycles/{cycle_id}/replan",
    response_model=ActionAcceptedEnvelope,
    responses=COMMON_ERROR_RESPONSES,
    status_code=status.HTTP_202_ACCEPTED,
)
def replan_cycle(
    cycle_id: str,
    payload: ReplanCycleRequest,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    _rate_limit: None = Depends(enforce_replan_cycle_rate_limit),
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: CycleWriteService = Depends(get_cycle_write_service),
):
    try:
        data = service.replan_cycle(cycle_id, payload.reason, payload.override_input or {}, idempotency_key, auth)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except StateConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return envelope_accepted(data=ActionAcceptedResponse.model_validate(data), request_id=request_id)
