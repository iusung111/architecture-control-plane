from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import ensure_runtime_settings_valid, get_settings
from app.core.rate_limit import initialize_rate_limit_backend, reset_rate_limits
from app.core.telemetry import initialize_tracing, shutdown_tracing
from app.db.session import dispose_db_resources


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    ensure_runtime_settings_valid(settings)
    initialize_tracing()
    initialize_rate_limit_backend(settings)
    try:
        yield
    finally:
        shutdown_tracing()
        reset_rate_limits()
        dispose_db_resources()
