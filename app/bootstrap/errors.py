from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError

from app.core.logging import get_logger
from app.core.rate_limit import RateLimitBackendUnavailable, RateLimitExceeded
from app.core.telemetry import record_db_lock_conflict
from app.db.errors import is_lock_conflict
from app.schemas.common import envelope_error

logger = get_logger(__name__)


def request_id_from_request(request: Request) -> str:
    return getattr(request.state, "request_id", None) or request.headers.get("x-request-id", "unknown-request-id")


def traceparent_from_request(request: Request) -> str | None:
    return getattr(request.state, "traceparent", None)


def error_code_from_status(status_code: int) -> str:
    return {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        422: "validation_error",
        429: "too_many_requests",
        500: "internal_error",
        503: "service_unavailable",
    }.get(status_code, "http_error")


def json_error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    *,
    retryable: bool,
    extra_headers: dict[str, str] | None = None,
) -> JSONResponse:
    request.state.response_status_code = status_code
    headers = {"x-request-id": request_id_from_request(request)}
    traceparent = traceparent_from_request(request)
    if traceparent:
        headers["traceparent"] = traceparent
    if extra_headers:
        headers.update(extra_headers)
    return JSONResponse(
        status_code=status_code,
        content=envelope_error(
            code=code,
            message=message,
            request_id=request_id_from_request(request),
            retryable=retryable,
        ).model_dump(mode="json"),
        headers=headers,
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return json_error_response(
        request,
        exc.status_code,
        error_code_from_status(exc.status_code),
        message,
        retryable=exc.status_code >= 500,
        extra_headers=dict(exc.headers or {}),
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return json_error_response(request, 422, "validation_error", str(exc), retryable=False)


async def rate_limit_exception_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return json_error_response(
        request,
        429,
        "too_many_requests",
        str(exc.detail),
        retryable=True,
        extra_headers=dict(exc.headers or {}),
    )


async def rate_limit_backend_unavailable_handler(
    request: Request,
    exc: RateLimitBackendUnavailable,
) -> JSONResponse:
    return json_error_response(
        request,
        503,
        "rate_limit_backend_unavailable",
        str(exc.detail),
        retryable=True,
        extra_headers=dict(exc.headers or {}),
    )


async def dbapi_exception_handler(request: Request, exc: DBAPIError) -> JSONResponse:
    if is_lock_conflict(exc):
        record_db_lock_conflict()
        return json_error_response(
            request,
            409,
            "resource_locked",
            "resource is locked by another transaction",
            retryable=True,
        )
    return json_error_response(request, 500, "database_error", "database operation failed", retryable=True)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled.exception", exc_info=exc)
    return json_error_response(request, 500, "internal_error", "internal server error", retryable=True)
