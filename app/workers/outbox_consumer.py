from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from time import perf_counter

from sqlalchemy.orm import Session

from app.core.logging import get_logger, log_event
from app.core.telemetry import record_outbox_delivery, timed_span
from app.db.models import NotificationOutbox
from app.repositories.outbox import OutboxRepository

logger = get_logger(__name__)


class OutboxDeliveryError(Exception):
    def __init__(self, message: str, *, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


OutboxHandler = Callable[[NotificationOutbox], None]


@dataclass(slots=True)
class OutboxDeliveryResult:
    delivered_ids: list[str]
    processed: int
    failed: int
    dead_lettered: int


class OutboxConsumer:
    def __init__(self, db: Session, handlers: Mapping[str, OutboxHandler] | None = None):
        self._db = db
        self._outbox = OutboxRepository(db)
        self._handlers = dict(handlers or {})

    def deliver_once(self, limit: int = 10) -> OutboxDeliveryResult:
        items = self._outbox.claim_pending(limit=limit)
        delivered_ids: list[str] = []
        failed = 0
        dead_lettered = 0

        for item in items:
            traceparent_header = item.payload.get("traceparent") if isinstance(item.payload, dict) else None
            with timed_span(
                traceparent_header,
                name=f"outbox {item.event_type}",
                kind="consumer",
                attributes={
                    "messaging.system": "acp-outbox",
                    "messaging.operation": "process",
                    "messaging.destination": item.event_type,
                    "outbox.id": item.outbox_id,
                },
            ):
                started_at = perf_counter()
                log_event(logger, logging.INFO, "outbox.claimed", outbox_id=item.outbox_id, event_type=item.event_type)
                handler = self._handlers.get(item.event_type)
                if handler is None:
                    self._outbox.mark_failed(item, error=f"No handler registered for event_type={item.event_type}", retryable=False)
                else:
                    try:
                        handler(item)
                        self._outbox.mark_delivered(item)
                    except OutboxDeliveryError as exc:
                        self._outbox.mark_failed(item, error=str(exc), retryable=exc.retryable)
                    except Exception as exc:  # noqa: BLE001
                        self._outbox.mark_failed(item, error=str(exc), retryable=True)

                duration_seconds = perf_counter() - started_at
                if item.delivery_state == "delivered":
                    outcome = "delivered"
                    delivered_ids.append(item.outbox_id)
                    log_event(logger, logging.INFO, "outbox.delivered", outbox_id=item.outbox_id, event_type=item.event_type)
                elif item.delivery_state == "dead_lettered":
                    outcome = "dead_lettered"
                    dead_lettered += 1
                    log_event(logger, logging.ERROR, "outbox.dead_lettered", outbox_id=item.outbox_id, event_type=item.event_type, last_error=item.last_error)
                else:
                    outcome = "failed"
                    failed += 1
                    log_event(logger, logging.WARNING, "outbox.failed", outbox_id=item.outbox_id, event_type=item.event_type, last_error=item.last_error)
                record_outbox_delivery(item.event_type, outcome, duration_seconds)

        self._db.commit()
        return OutboxDeliveryResult(
            delivered_ids=delivered_ids,
            processed=len(items),
            failed=failed,
            dead_lettered=dead_lettered,
        )
