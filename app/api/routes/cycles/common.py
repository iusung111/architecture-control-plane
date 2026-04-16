# ruff: noqa: F401
from __future__ import annotations

import asyncio
import json
from time import monotonic
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse

from app.api.deps import (
    get_auth_context,
    get_cycle_query_service,
    get_cycle_write_service,
    get_cycle_stream_service,
    get_request_id,
    enforce_create_cycle_rate_limit,
    enforce_replan_cycle_rate_limit,
    enforce_retry_cycle_rate_limit,
)
from app.core.auth import AuthContext
from app.domain.guards import StateConflictError
from app.schemas.common import ErrorEnvelope, envelope_accepted, envelope_ok
from app.schemas.cycles import *  # noqa: F403
from app.services.cycles import CycleQueryService, CycleStreamService, CycleWriteService

router = APIRouter(tags=["cycles"])


def _format_sse_event(event: str, data: dict[str, Any], event_id: int) -> str:
    payload = json.dumps(jsonable_encoder(data), separators=(",", ":"), sort_keys=True)
    return f"id: {event_id}\nevent: {event}\ndata: {payload}\n\n"


def _snapshot_version(summary: dict[str, Any]) -> str:
    updated_at = summary.get("updated_at")
    if isinstance(updated_at, datetime):
        return f"{updated_at.isoformat()}:{summary.get('state')}:{summary.get('user_status')}"
    return json.dumps(jsonable_encoder(summary), separators=(",", ":"), sort_keys=True)


def _board_snapshot_version(snapshot: dict[str, Any]) -> str:
    comparable = {
        "project_id": snapshot.get("project_id"),
        "total_count": snapshot.get("total_count"),
        "columns": [
            {
                "key": column.get("key"),
                "count": column.get("count"),
                "items": [
                    {
                        "cycle_id": item.get("cycle_id"),
                        "state": item.get("state"),
                        "user_status": item.get("user_status"),
                        "updated_at": item.get("updated_at"),
                    }
                    for item in column.get("items", [])
                ],
            }
            for column in snapshot.get("columns", [])
        ],
    }
    return json.dumps(jsonable_encoder(comparable), separators=(",", ":"), sort_keys=True)


COMMON_ERROR_RESPONSES = {
    401: {"model": ErrorEnvelope},
    403: {"model": ErrorEnvelope},
    404: {"model": ErrorEnvelope},
    409: {"model": ErrorEnvelope},
    422: {"model": ErrorEnvelope},
    429: {"model": ErrorEnvelope},
}


__all__ = [name for name in globals() if not name.startswith("__")]
