from __future__ import annotations

import argparse
import json
import os
import time
from collections import deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from urllib.parse import parse_qs, urlparse

from app.services.notifications import NONCE_HEADER, SIGNATURE_HEADER, TIMESTAMP_HEADER, build_notification_signature

_EVENTS: deque[dict] = deque(maxlen=500)
_ALERTS: deque[dict] = deque(maxlen=200)
_SEEN_NONCES: dict[str, float] = {}
_LOCK = Lock()
_WEBHOOK_SECRET = os.getenv("WEBHOOK_SINK_HMAC_SECRET")
_TIMESTAMP_TOLERANCE_SECONDS = int(os.getenv("WEBHOOK_SINK_TIMESTAMP_TOLERANCE_SECONDS", "300"))


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: object) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _cleanup_seen_nonces(now: float) -> None:
    cutoff = now - max(_TIMESTAMP_TOLERANCE_SECONDS, 1)
    expired = [nonce for nonce, seen_at in _SEEN_NONCES.items() if seen_at < cutoff]
    for nonce in expired:
        _SEEN_NONCES.pop(nonce, None)


def _verify_signed_webhook(headers: BaseHTTPRequestHandler.headers.__class__, raw_body: bytes) -> tuple[bool, str | None]:
    if not _WEBHOOK_SECRET:
        return True, None
    timestamp = headers.get(TIMESTAMP_HEADER)
    nonce = headers.get(NONCE_HEADER)
    signature = headers.get(SIGNATURE_HEADER)
    if not timestamp or not nonce or not signature:
        return False, "missing_signature_headers"
    try:
        timestamp_value = int(timestamp)
    except ValueError:
        return False, "invalid_timestamp"
    now = time.time()
    if abs(now - timestamp_value) > _TIMESTAMP_TOLERANCE_SECONDS:
        return False, "stale_timestamp"
    expected = build_notification_signature(
        secret=_WEBHOOK_SECRET,
        timestamp=timestamp,
        nonce=nonce,
        body=raw_body,
    )
    if not signature or not signature.startswith("sha256="):
        return False, "invalid_signature_format"
    import hmac
    if not hmac.compare_digest(signature, expected):
        return False, "invalid_signature"
    with _LOCK:
        _cleanup_seen_nonces(now)
        if nonce in _SEEN_NONCES:
            return False, "replayed_nonce"
        _SEEN_NONCES[nonce] = now
    return True, None


class WebhookSinkHandler(BaseHTTPRequestHandler):
    server_version = "WebhookSink/1.0"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/healthz":
            _json_response(self, HTTPStatus.OK, {"status": "ok"})
            return
        if parsed.path == "/events":
            query = parse_qs(parsed.query)
            event_type = query.get("event_type", [None])[0]
            cycle_id = query.get("cycle_id", [None])[0]
            with _LOCK:
                events = list(_EVENTS)
            if event_type is not None:
                events = [event for event in events if event.get("event_type") == event_type]
            if cycle_id is not None:
                events = [event for event in events if event.get("cycle_id") == cycle_id]
            _json_response(self, HTTPStatus.OK, {"count": len(events), "events": events})
            return
        if parsed.path == "/alerts":
            with _LOCK:
                alerts = list(_ALERTS)
            _json_response(self, HTTPStatus.OK, {"count": len(alerts), "alerts": alerts})
            return
        _json_response(self, HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path not in {"/webhook", "/alertmanager"}:
            _json_response(self, HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"
        if parsed.path == "/webhook":
            valid, reason = _verify_signed_webhook(self.headers, raw_body)
            if not valid:
                _json_response(self, HTTPStatus.UNAUTHORIZED, {"error": reason})
                return
        try:
            payload = json.loads(raw_body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "invalid_json"})
            return

        with _LOCK:
            if parsed.path == "/alertmanager":
                _ALERTS.append(payload)
                count = len(_ALERTS)
            else:
                _EVENTS.append(payload)
                count = len(_EVENTS)
        _json_response(self, HTTPStatus.ACCEPTED, {"stored": True, "path": parsed.path, "count": count})

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="Simple webhook sink for docker smoke tests")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8081)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), WebhookSinkHandler)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
