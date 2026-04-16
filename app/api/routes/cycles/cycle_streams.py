from .common import *

@router.get(
    "/cycles/board/events",
    responses={
        200: {
            "content": {
                "text/event-stream": {
                    "schema": {"type": "string"},
                    "example": 'id: 1\nevent: board.snapshot\ndata: {"total_count":2}\n\n',
                }
            },
            "description": "Server-sent event stream for the cycle board view.",
        },
        401: {"model": ErrorEnvelope},
        403: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
    },
)
async def stream_cycle_board(
    request: Request,
    project_id: str | None = None,
    limit_per_column: int = Query(default=12, ge=1, le=50),
    poll_interval_seconds: float = Query(default=2.0, ge=0.05, le=30.0),
    heartbeat_seconds: float = Query(default=15.0, ge=0.05, le=120.0),
    stream_timeout_seconds: float = Query(default=300.0, ge=0.05, le=3600.0),
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: CycleQueryService = Depends(get_cycle_query_service),
):
    initial_snapshot = await run_in_threadpool(service.get_board_snapshot, auth=auth, project_id=project_id, limit_per_column=limit_per_column)

    async def event_generator():
        event_id = 0
        started_at = monotonic()
        last_emitted_at = monotonic()
        last_snapshot_key: str | None = None
        snapshot = initial_snapshot

        while True:
            if await request.is_disconnected():
                return

            snapshot_key = _board_snapshot_version(snapshot)
            if snapshot_key != last_snapshot_key:
                event_id += 1
                yield _format_sse_event("board.snapshot", {"board": snapshot, "request_id": request_id}, event_id)
                last_snapshot_key = snapshot_key
                last_emitted_at = monotonic()

            now = monotonic()
            if now - started_at >= stream_timeout_seconds:
                event_id += 1
                yield _format_sse_event(
                    "stream.timeout",
                    {"request_id": request_id, "timed_out_at": datetime.now(timezone.utc)},
                    event_id,
                )
                return

            if now - last_emitted_at >= heartbeat_seconds:
                event_id += 1
                yield _format_sse_event(
                    "heartbeat",
                    {"request_id": request_id, "timestamp": datetime.now(timezone.utc)},
                    event_id,
                )
                last_emitted_at = monotonic()

            await asyncio.sleep(poll_interval_seconds)
            snapshot = await run_in_threadpool(service.get_board_snapshot, auth=auth, project_id=project_id, limit_per_column=limit_per_column)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

@router.get(
    "/cycles/{cycle_id}/events",
    responses={
        200: {
            "content": {
                "text/event-stream": {
                    "schema": {"type": "string"},
                    "example": 'id: 1\nevent: cycle.snapshot\ndata: {"cycle":{"cycle_id":"...","state":"intent_accepted"}}\n\n',
                }
            },
            "description": "Server-sent event stream for cycle state changes.",
        },
        401: {"model": ErrorEnvelope},
        403: {"model": ErrorEnvelope},
        404: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
    },
)
async def stream_cycle_events(
    cycle_id: str,
    request: Request,
    poll_interval_seconds: float = Query(default=1.0, ge=0.01, le=30.0),
    heartbeat_seconds: float = Query(default=15.0, ge=0.01, le=120.0),
    stream_timeout_seconds: float = Query(default=300.0, ge=0.01, le=3600.0),
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: CycleStreamService = Depends(get_cycle_stream_service),
):
    try:
        initial_snapshot = await run_in_threadpool(service.get_snapshot, cycle_id, auth)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if initial_snapshot is None:
        raise HTTPException(status_code=404, detail="cycle not found")

    async def event_generator():
        event_id = 0
        started_at = monotonic()
        last_emitted_at = monotonic()
        last_snapshot_key: str | None = None
        result_sent = False
        snapshot = initial_snapshot

        while True:
            if await request.is_disconnected():
                return

            summary_key = _snapshot_version(snapshot.summary)
            if summary_key != last_snapshot_key:
                event_id += 1
                yield _format_sse_event(
                    "cycle.snapshot",
                    {"cycle": snapshot.summary, "request_id": request_id},
                    event_id,
                )
                last_snapshot_key = summary_key
                last_emitted_at = monotonic()

            if snapshot.result is not None and not result_sent:
                event_id += 1
                yield _format_sse_event(
                    "cycle.result",
                    {"result": snapshot.result, "request_id": request_id},
                    event_id,
                )
                result_sent = True
                last_emitted_at = monotonic()

            if snapshot.terminal and (result_sent or snapshot.result is None):
                return

            now = monotonic()
            if now - started_at >= stream_timeout_seconds:
                event_id += 1
                yield _format_sse_event(
                    "stream.timeout",
                    {
                        "cycle_id": cycle_id,
                        "request_id": request_id,
                        "timed_out_at": datetime.now(timezone.utc),
                    },
                    event_id,
                )
                return

            if now - last_emitted_at >= heartbeat_seconds:
                event_id += 1
                yield _format_sse_event(
                    "heartbeat",
                    {
                        "cycle_id": cycle_id,
                        "request_id": request_id,
                        "timestamp": datetime.now(timezone.utc),
                    },
                    event_id,
                )
                last_emitted_at = monotonic()

            await asyncio.sleep(poll_interval_seconds)
            try:
                refreshed_snapshot = await run_in_threadpool(service.get_snapshot, cycle_id, auth)
            except PermissionError as exc:
                event_id += 1
                yield _format_sse_event(
                    "stream.error",
                    {"cycle_id": cycle_id, "request_id": request_id, "message": str(exc)},
                    event_id,
                )
                return
            if refreshed_snapshot is None:
                event_id += 1
                yield _format_sse_event(
                    "stream.error",
                    {"cycle_id": cycle_id, "request_id": request_id, "message": "cycle not found"},
                    event_id,
                )
                return
            snapshot = refreshed_snapshot

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
