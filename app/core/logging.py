from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

from app.core.config import get_settings
from app.core.telemetry import get_trace_context

_request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = _request_id_ctx.get()
        if request_id:
            payload["request_id"] = request_id
        trace_id, span_id, _ = get_trace_context()
        if trace_id:
            payload["trace_id"] = trace_id
        if span_id:
            payload["span_id"] = span_id
        event_payload = getattr(record, "event_payload", None)
        if isinstance(event_payload, dict):
            payload.update(event_payload)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)



def configure_logging() -> None:
    settings = get_settings()
    root_logger = logging.getLogger()
    if getattr(root_logger, "_architecture_logging_configured", False):
        return

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    root_logger._architecture_logging_configured = True  # type: ignore[attr-defined]



def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)



def set_request_id(request_id: str | None):
    return _request_id_ctx.set(request_id)



def reset_request_id(token) -> None:
    _request_id_ctx.reset(token)



def log_event(logger: logging.Logger, level: int, message: str, **event_payload: Any) -> None:
    logger.log(level, message, extra={"event_payload": event_payload})
