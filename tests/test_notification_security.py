from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx

from app.services.notifications import (
    NONCE_HEADER,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    NotificationDispatcher,
    build_notification_signature,
)


def test_notification_dispatch_signs_webhook_payload() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["signature"] = request.headers[SIGNATURE_HEADER]
        captured["timestamp"] = request.headers[TIMESTAMP_HEADER]
        captured["nonce"] = request.headers[NONCE_HEADER]
        captured["body"] = request.content.decode("utf-8")
        return httpx.Response(202, json={"ok": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    dispatcher = NotificationDispatcher(
        webhook_url="https://example.test/hook",
        signing_secret="0123456789abcdef",
        client=client,
    )

    result = dispatcher.dispatch(
        "cycle.completed",
        {"completed_at": datetime.now(timezone.utc).isoformat()},
        outbox_id="outbox-1",
        cycle_id="cycle-1",
    )

    assert result.channel == "webhook"
    expected = build_notification_signature(
        secret="0123456789abcdef",
        timestamp=captured["timestamp"],
        nonce=captured["nonce"],
        body=captured["body"].encode("utf-8"),
    )
    assert captured["signature"] == expected
    assert json.loads(captured["body"])["event_type"] == "cycle.completed"


def test_notification_dispatch_omits_signature_headers_when_secret_missing() -> None:
    captured: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["signature"] = request.headers.get(SIGNATURE_HEADER)
        captured["timestamp"] = request.headers.get(TIMESTAMP_HEADER)
        captured["nonce"] = request.headers.get(NONCE_HEADER)
        return httpx.Response(202, json={"ok": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    dispatcher = NotificationDispatcher(webhook_url="https://example.test/hook", client=client)

    dispatcher.dispatch("cycle.completed", {"ok": True}, outbox_id="outbox-1", cycle_id="cycle-1")

    assert captured["signature"] is None
    assert captured["timestamp"] is None
    assert captured["nonce"] is None
