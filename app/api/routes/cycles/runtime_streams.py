from .common import *

@router.get(
    "/runtime/registrations/{runtime_id}/actions/{action_id}/events",
    responses={
        200: {
            "content": {
                "text/event-stream": {
                    "schema": {"type": "string"},
                    "example": 'id: 1\nevent: runtime.action.snapshot\ndata: {"action_id":"abc"}\n\n',
                }
            },
            "description": "Server-sent event stream for runtime action timeline updates.",
        },
        401: {"model": ErrorEnvelope},
        403: {"model": ErrorEnvelope},
        404: {"model": ErrorEnvelope},
    },
)
async def stream_runtime_action_events(
    request: Request,
    runtime_id: str,
    action_id: str,
    poll_interval_seconds: float = Query(default=1.0, ge=0.05, le=30.0),
    heartbeat_seconds: float = Query(default=15.0, ge=0.05, le=120.0),
    stream_timeout_seconds: float = Query(default=300.0, ge=0.05, le=3600.0),
    timeline_limit: int = Query(default=100, ge=1, le=300),
    auth: AuthContext = Depends(get_auth_context),
    request_id: str = Depends(get_request_id),
    service: CycleQueryService = Depends(get_cycle_query_service),
):
    try:
        initial_snapshot = await run_in_threadpool(service.get_runtime_action_live_snapshot, auth=auth, runtime_id=runtime_id, action_id=action_id, timeline_limit=timeline_limit)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    def snapshot_version(snapshot: dict[str, Any]) -> str:
        comparable = {
            "action": {
                "action_id": snapshot.get("action", {}).get("action_id"),
                "status": snapshot.get("action", {}).get("status"),
                "last_updated_at": snapshot.get("action", {}).get("last_updated_at"),
                "receipt_count": snapshot.get("action", {}).get("receipt_count"),
                "latest_receipt_status": snapshot.get("action", {}).get("latest_receipt_status"),
            },
            "timeline": [
                {
                    "event_id": item.get("event_id"),
                    "status": item.get("status"),
                    "occurred_at": item.get("occurred_at"),
                }
                for item in snapshot.get("timeline", [])
            ],
        }
        return json.dumps(jsonable_encoder(comparable), separators=(",", ":"), sort_keys=True)

    async def event_generator():
        event_id = 0
        started_at = monotonic()
        last_emitted_at = monotonic()
        last_snapshot_key: str | None = None
        snapshot = initial_snapshot

        while True:
            if await request.is_disconnected():
                return

            current_key = snapshot_version(snapshot)
            if current_key != last_snapshot_key:
                event_id += 1
                yield _format_sse_event("runtime.action.snapshot", {"runtime_action": snapshot, "request_id": request_id}, event_id)
                last_snapshot_key = current_key
                last_emitted_at = monotonic()

            now = monotonic()
            if now - started_at >= stream_timeout_seconds:
                event_id += 1
                yield _format_sse_event("stream.timeout", {"request_id": request_id, "timed_out_at": datetime.now(timezone.utc)}, event_id)
                return

            if now - last_emitted_at >= heartbeat_seconds:
                event_id += 1
                yield _format_sse_event("heartbeat", {"request_id": request_id, "timestamp": datetime.now(timezone.utc)}, event_id)
                last_emitted_at = monotonic()

            await asyncio.sleep(poll_interval_seconds)
            try:
                snapshot = await run_in_threadpool(service.get_runtime_action_live_snapshot, auth=auth, runtime_id=runtime_id, action_id=action_id, timeline_limit=timeline_limit)
            except ValueError:
                event_id += 1
                yield _format_sse_event("stream.error", {"request_id": request_id, "message": "action not found"}, event_id)
                return

    return StreamingResponse(event_generator(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
