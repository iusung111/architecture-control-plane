from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import DBAPIError

from app.api.routes.admin_audit import router as admin_audit_router
from app.api.routes.admin_llm import router as admin_llm_router
from app.api.routes.admin_ops import router as admin_ops_router
from app.api.routes.approvals import router as approvals_router
from app.api.routes.cycles import router as cycles_router
from app.api.routes.remote_workspace import router as remote_workspace_router, workbench_router
from app.bootstrap.errors import (
    dbapi_exception_handler,
    http_exception_handler,
    json_error_response,
    rate_limit_backend_unavailable_handler,
    rate_limit_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.bootstrap.lifespan import lifespan
from app.bootstrap.middleware import request_context_middleware
from app.bootstrap.system_routes import router as system_router
from app.core.logging import configure_logging
from app.core.rate_limit import RateLimitBackendUnavailable, RateLimitExceeded

configure_logging()

app = FastAPI(title="Architecture Control Plane API", version="0.1.0", lifespan=lifespan)
for router, prefix in (
    (cycles_router, "/v1"),
    (approvals_router, "/v1"),
    (admin_llm_router, "/v1"),
    (admin_audit_router, "/v1"),
    (admin_ops_router, "/v1"),
    (remote_workspace_router, "/v1"),
    (workbench_router, "/v1"),
    (system_router, ""),
):
    app.include_router(router, prefix=prefix)


@app.middleware("http")
async def request_context(request: Request, call_next):
    return await request_context_middleware(request, call_next, json_error_response)


app.exception_handler(HTTPException)(http_exception_handler)
app.exception_handler(RequestValidationError)(validation_exception_handler)
app.exception_handler(RateLimitExceeded)(rate_limit_exception_handler)
app.exception_handler(RateLimitBackendUnavailable)(rate_limit_backend_unavailable_handler)
app.exception_handler(DBAPIError)(dbapi_exception_handler)
app.exception_handler(Exception)(unhandled_exception_handler)
