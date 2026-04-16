from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger, log_event

logger = get_logger(__name__)

SIGNATURE_HEADER = "X-ACP-Signature"
TIMESTAMP_HEADER = "X-ACP-Timestamp"
NONCE_HEADER = "X-ACP-Nonce"


class NotificationDeliveryError(Exception):
    def __init__(self, message: str, *, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


@dataclass(slots=True)
class NotificationDispatchResult:
    channel: str
    status_code: int | None = None


def build_notification_signature(*, secret: str, timestamp: str, nonce: str, body: bytes) -> str:
    mac = hmac.new(secret.encode("utf-8"), digestmod=hashlib.sha256)
    mac.update(timestamp.encode("utf-8"))
    mac.update(b".")
    mac.update(nonce.encode("utf-8"))
    mac.update(b".")
    mac.update(body)
    return "sha256=" + mac.hexdigest()


class NotificationDispatcher:
    def __init__(
        self,
        *,
        webhook_url: str | None = None,
        timeout_seconds: float | None = None,
        signing_secret: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        settings = get_settings()
        self._webhook_url = webhook_url if webhook_url is not None else settings.notification_webhook_url
        self._timeout_seconds = timeout_seconds if timeout_seconds is not None else settings.notification_timeout_seconds
        self._signing_secret = signing_secret if signing_secret is not None else settings.notification_webhook_signing_secret
        self._client = client
        self._owns_client = client is None and self._webhook_url is not None

    def dispatch(self, event_type: str, payload: dict[str, Any], *, outbox_id: str, cycle_id: str | None) -> NotificationDispatchResult:
        envelope = {
            "outbox_id": outbox_id,
            "cycle_id": cycle_id,
            "event_type": event_type,
            "payload": payload,
        }
        log_event(logger, logging.INFO, "notification.dispatch", **envelope, channel="log")

        if not self._webhook_url:
            return NotificationDispatchResult(channel="log")

        body = json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self._signing_secret:
            timestamp = str(int(time.time()))
            nonce = uuid4().hex
            headers[TIMESTAMP_HEADER] = timestamp
            headers[NONCE_HEADER] = nonce
            headers[SIGNATURE_HEADER] = build_notification_signature(
                secret=self._signing_secret,
                timestamp=timestamp,
                nonce=nonce,
                body=body,
            )

        client = self._client or httpx.Client(timeout=self._timeout_seconds)
        try:
            response = client.post(self._webhook_url, content=body, headers=headers)
        except httpx.TimeoutException as exc:
            raise NotificationDeliveryError("notification webhook timed out", retryable=True) from exc
        except httpx.TransportError as exc:
            raise NotificationDeliveryError(f"notification webhook transport error: {exc}", retryable=True) from exc
        finally:
            if self._owns_client and self._client is None:
                client.close()

        if 200 <= response.status_code < 300:
            log_event(
                logger,
                logging.INFO,
                "notification.dispatched",
                outbox_id=outbox_id,
                cycle_id=cycle_id,
                event_type=event_type,
                channel="webhook",
                status_code=response.status_code,
                signed=bool(self._signing_secret),
            )
            return NotificationDispatchResult(channel="webhook", status_code=response.status_code)

        retryable = response.status_code >= 500 or response.status_code == 429
        raise NotificationDeliveryError(
            f"notification webhook rejected payload with status={response.status_code}",
            retryable=retryable,
        )
