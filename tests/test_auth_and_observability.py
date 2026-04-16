import base64
import hashlib
import hmac
import json
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi.testclient import TestClient

from app.core.auth import clear_auth_caches
from app.core.config import get_settings
from app.core.telemetry import render_metrics



def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")



def _mint_hs256_jwt(secret: str, payload: dict[str, Any]) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    encoded_header = _b64url(json.dumps(header, separators=(",", ":")).encode())
    encoded_payload = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{encoded_header}.{encoded_payload}".encode()
    signature = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    return f"{encoded_header}.{encoded_payload}.{_b64url(signature)}"



def _rsa_public_jwk(private_key, *, kid: str) -> dict[str, str]:
    public_numbers = private_key.public_key().public_numbers()
    n = public_numbers.n.to_bytes((public_numbers.n.bit_length() + 7) // 8, "big")
    e = public_numbers.e.to_bytes((public_numbers.e.bit_length() + 7) // 8, "big")
    return {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": kid,
        "n": _b64url(n),
        "e": _b64url(e),
    }



def _ec_public_jwk(private_key, *, kid: str) -> dict[str, str]:
    payload = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(private_key.public_key()))
    payload.update({"use": "sig", "alg": "ES256", "kid": kid})
    return payload



def _make_traceparent(trace_id: str, span_id: str, flags: str = "01") -> str:
    return f"00-{trace_id}-{span_id}-{flags}"



class _OidcHandler(BaseHTTPRequestHandler):
    jwks_payload: dict[str, Any] = {"keys": []}
    discovery_payload: dict[str, Any] | None = None

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/jwks.json":
            body = json.dumps(self.jwks_payload).encode("utf-8")
        elif self.path == "/.well-known/openid-configuration" and self.discovery_payload is not None:
            body = json.dumps(self.discovery_payload).encode("utf-8")
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args, **_kwargs) -> None:
        return


class LocalOidcServer:
    def __init__(
        self,
        jwks_payload: dict[str, Any],
        *,
        issuer: str | None = None,
        with_discovery: bool = False,
        discovery_payload: dict[str, Any] | None = None,
    ):
        handler = type(
            "DynamicOidcHandler",
            (_OidcHandler,),
            {
                "jwks_payload": jwks_payload,
                "discovery_payload": None,
            },
        )
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        port = self._server.server_port
        self.jwks_url = f"http://127.0.0.1:{port}/jwks.json"
        self.issuer = issuer or f"http://127.0.0.1:{port}"
        self.discovery_url = f"http://127.0.0.1:{port}/.well-known/openid-configuration"
        if with_discovery:
            handler.discovery_payload = discovery_payload or {
                "issuer": self.issuer,
                "jwks_uri": self.jwks_url,
                "id_token_signing_alg_values_supported": ["RS256"],
            }
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._server.shutdown()
        self._thread.join(timeout=5)
        self._server.server_close()


def test_bearer_jwt_auth_succeeds_and_propagates_request_id(client: TestClient, monkeypatch) -> None:
    secret = "top-secret-key-material-32-bytes!!"
    monkeypatch.setenv("AUTH_MODE", "bearer_jwt")
    monkeypatch.setenv("AUTH_HEADER_FALLBACK_ENABLED", "false")
    monkeypatch.setenv("AUTH_JWT_SECRET", secret)
    monkeypatch.setenv("AUTH_JWT_ISSUER", "tests")
    monkeypatch.setenv("AUTH_JWT_AUDIENCE", "tests-api")
    get_settings.cache_clear()

    token = _mint_hs256_jwt(
        secret,
        {
            "sub": "jwt-user-1",
            "role": "supervisor",
            "tenant_id": "tenant-jwt",
            "iss": "tests",
            "aud": "tests-api",
            "exp": int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp()),
        },
    )

    traceparent = _make_traceparent("a" * 32, "b" * 16)
    response = client.post(
        "/v1/cycles",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "jwt-create-1",
            "X-Request-Id": "req-jwt-1",
            "traceparent": traceparent,
        },
        json={"project_id": "proj-1", "user_input": "jwt-backed request"},
    )

    assert response.status_code == 201
    assert response.headers["x-request-id"] == "req-jwt-1"
    assert response.json()["data"]["cycle_id"]
    returned_traceparent = response.headers["traceparent"]
    assert returned_traceparent.startswith("00-" + "a" * 32 + "-")
    assert returned_traceparent != traceparent

    monkeypatch.delenv("AUTH_MODE", raising=False)
    monkeypatch.delenv("AUTH_HEADER_FALLBACK_ENABLED", raising=False)
    monkeypatch.delenv("AUTH_JWT_SECRET", raising=False)
    monkeypatch.delenv("AUTH_JWT_ISSUER", raising=False)
    monkeypatch.delenv("AUTH_JWT_AUDIENCE", raising=False)
    get_settings.cache_clear()
    clear_auth_caches()



def test_bearer_jwt_auth_rejects_invalid_signature(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("AUTH_MODE", "bearer_jwt")
    monkeypatch.setenv("AUTH_HEADER_FALLBACK_ENABLED", "false")
    monkeypatch.setenv("AUTH_JWT_SECRET", "expected-secret-key-material-32b")
    monkeypatch.setenv("AUTH_JWT_ISSUER", "tests")
    monkeypatch.setenv("AUTH_JWT_AUDIENCE", "tests-api")
    get_settings.cache_clear()

    token = _mint_hs256_jwt(
        "different-secret-key-material-32b",
        {
            "sub": "jwt-user-1",
            "role": "supervisor",
            "iss": "tests",
            "aud": "tests-api",
            "exp": int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp()),
        },
    )

    response = client.post(
        "/v1/cycles",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "jwt-create-invalid"},
        json={"project_id": "proj-1", "user_input": "jwt-backed request"},
    )

    assert response.status_code == 401
    body = response.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "unauthorized"
    assert body["error"]["message"] == "invalid bearer token signature"

    monkeypatch.delenv("AUTH_MODE", raising=False)
    monkeypatch.delenv("AUTH_HEADER_FALLBACK_ENABLED", raising=False)
    monkeypatch.delenv("AUTH_JWT_SECRET", raising=False)
    monkeypatch.delenv("AUTH_JWT_ISSUER", raising=False)
    monkeypatch.delenv("AUTH_JWT_AUDIENCE", raising=False)
    get_settings.cache_clear()
    clear_auth_caches()



def test_oidc_jwks_auth_succeeds(client: TestClient, monkeypatch) -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    kid = "oidc-key-1"
    jwks = {"keys": [_rsa_public_jwk(private_key, kid=kid)]}

    with LocalOidcServer(jwks) as server:
        monkeypatch.setenv("AUTH_MODE", "oidc_jwks")
        monkeypatch.setenv("AUTH_HEADER_FALLBACK_ENABLED", "false")
        monkeypatch.setenv("AUTH_JWKS_URL", server.jwks_url)
        monkeypatch.setenv("AUTH_JWT_ISSUER", "https://issuer.example.test")
        monkeypatch.setenv("AUTH_JWT_AUDIENCE", "control-plane-api")
        monkeypatch.setenv("AUTH_JWT_ALLOWED_ALGORITHMS", "RS256")
        get_settings.cache_clear()

        token = jwt.encode(
            {
                "sub": "oidc-user-1",
                "role": "admin",
                "tenant_id": "tenant-oidc",
                "iss": "https://issuer.example.test",
                "aud": "control-plane-api",
                "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            },
            private_key,
            algorithm="RS256",
            headers={"kid": kid},
        )

        response = client.post(
            "/v1/cycles",
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "oidc-create-1"},
            json={"project_id": "proj-oidc", "user_input": "oidc-backed request"},
        )

        assert response.status_code == 201
        assert response.json()["data"]["cycle_id"]

    monkeypatch.delenv("AUTH_MODE", raising=False)
    monkeypatch.delenv("AUTH_HEADER_FALLBACK_ENABLED", raising=False)
    monkeypatch.delenv("AUTH_JWKS_URL", raising=False)
    monkeypatch.delenv("AUTH_JWT_ISSUER", raising=False)
    monkeypatch.delenv("AUTH_JWT_AUDIENCE", raising=False)
    monkeypatch.delenv("AUTH_JWT_ALLOWED_ALGORITHMS", raising=False)
    get_settings.cache_clear()
    clear_auth_caches()



def test_oidc_jwks_auth_supports_es256_keys(client: TestClient, monkeypatch) -> None:
    private_key = ec.generate_private_key(ec.SECP256R1())
    kid = "oidc-ec-key-1"
    jwks = {"keys": [_ec_public_jwk(private_key, kid=kid)]}

    with LocalOidcServer(jwks) as server:
        monkeypatch.setenv("AUTH_MODE", "oidc_jwks")
        monkeypatch.setenv("AUTH_HEADER_FALLBACK_ENABLED", "false")
        monkeypatch.setenv("AUTH_JWKS_URL", server.jwks_url)
        monkeypatch.setenv("AUTH_JWT_ISSUER", "https://issuer.example.test")
        monkeypatch.setenv("AUTH_JWT_AUDIENCE", "control-plane-api")
        monkeypatch.setenv("AUTH_JWT_ALLOWED_ALGORITHMS", "ES256")
        get_settings.cache_clear()
        clear_auth_caches()

        token = jwt.encode(
            {
                "sub": "oidc-user-ec-1",
                "role": "admin",
                "tenant_id": "tenant-oidc",
                "iss": "https://issuer.example.test",
                "aud": "control-plane-api",
                "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            },
            private_key,
            algorithm="ES256",
            headers={"kid": kid},
        )

        response = client.post(
            "/v1/cycles",
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "oidc-create-es256-1"},
            json={"project_id": "proj-oidc-es256", "user_input": "oidc ES256-backed request"},
        )

        assert response.status_code == 201
        assert response.json()["data"]["cycle_id"]

    monkeypatch.delenv("AUTH_MODE", raising=False)
    monkeypatch.delenv("AUTH_HEADER_FALLBACK_ENABLED", raising=False)
    monkeypatch.delenv("AUTH_JWKS_URL", raising=False)
    monkeypatch.delenv("AUTH_JWT_ISSUER", raising=False)
    monkeypatch.delenv("AUTH_JWT_AUDIENCE", raising=False)
    monkeypatch.delenv("AUTH_JWT_ALLOWED_ALGORITHMS", raising=False)
    get_settings.cache_clear()
    clear_auth_caches()



def test_oidc_discovery_auth_succeeds_without_explicit_jwks_url(client: TestClient, monkeypatch) -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    kid = "oidc-key-discovery"
    jwks = {"keys": [_rsa_public_jwk(private_key, kid=kid)]}

    with LocalOidcServer(jwks, with_discovery=True) as server:
        monkeypatch.setenv("AUTH_MODE", "oidc_jwks")
        monkeypatch.setenv("AUTH_HEADER_FALLBACK_ENABLED", "false")
        monkeypatch.delenv("AUTH_JWKS_URL", raising=False)
        monkeypatch.setenv("AUTH_JWT_ISSUER", server.issuer)
        monkeypatch.setenv("AUTH_JWT_AUDIENCE", "control-plane-api")
        monkeypatch.setenv("AUTH_JWT_ALLOWED_ALGORITHMS", "RS256")
        get_settings.cache_clear()
        clear_auth_caches()

        token = jwt.encode(
            {
                "sub": "oidc-user-discovery",
                "role": "admin",
                "tenant_id": "tenant-oidc",
                "iss": server.issuer,
                "aud": "control-plane-api",
                "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            },
            private_key,
            algorithm="RS256",
            headers={"kid": kid},
        )

        response = client.post(
            "/v1/cycles",
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "oidc-create-discovery-1"},
            json={"project_id": "proj-oidc-discovery", "user_input": "oidc discovery-backed request"},
        )

        assert response.status_code == 201
        assert response.json()["data"]["cycle_id"]

    monkeypatch.delenv("AUTH_MODE", raising=False)
    monkeypatch.delenv("AUTH_HEADER_FALLBACK_ENABLED", raising=False)
    monkeypatch.delenv("AUTH_JWT_ISSUER", raising=False)
    monkeypatch.delenv("AUTH_JWT_AUDIENCE", raising=False)
    monkeypatch.delenv("AUTH_JWT_ALLOWED_ALGORITHMS", raising=False)
    get_settings.cache_clear()
    clear_auth_caches()


def test_metrics_endpoint_exposes_http_and_auth_counters(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("AUTH_MODE", "header")
    monkeypatch.setenv("METRICS_ENABLED", "true")
    get_settings.cache_clear()

    unauthorized = client.post(
        "/v1/cycles",
        headers={"Idempotency-Key": "missing-user-1"},
        json={"project_id": "proj-1", "user_input": "missing header request"},
    )
    assert unauthorized.status_code == 403

    healthy = client.get("/healthz")
    assert healthy.status_code == 200

    metrics_response = client.get("/metrics")
    assert metrics_response.status_code == 200
    assert "text/plain" in metrics_response.headers["content-type"]
    metrics_text = metrics_response.text
    assert "acp_http_requests_total" in metrics_text
    assert 'path="/healthz"' in metrics_text
    assert "acp_auth_failures_total" in metrics_text
    assert 'reason="missing_x-user-id_header"' in metrics_text

    payload, _ = render_metrics()
    assert b"acp_http_request_duration_seconds" in payload
    assert "acp_slo_events_total" in metrics_text
    assert "slo=\"api_availability\"" in metrics_text
    assert "slo=\"api_latency\"" in metrics_text

    monkeypatch.delenv("AUTH_MODE", raising=False)
    monkeypatch.delenv("METRICS_ENABLED", raising=False)
    get_settings.cache_clear()



def test_oidc_discovery_rejects_unsupported_signing_alg(client: TestClient, monkeypatch) -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    kid = "oidc-key-bad-alg"
    jwks = {"keys": [_rsa_public_jwk(private_key, kid=kid)]}

    with LocalOidcServer(jwks, with_discovery=True) as server:
        server._server.RequestHandlerClass.discovery_payload = {
            "issuer": server.issuer,
            "jwks_uri": server.jwks_url,
            "id_token_signing_alg_values_supported": ["ES256"],
        }
        monkeypatch.setenv("AUTH_MODE", "oidc_jwks")
        monkeypatch.setenv("AUTH_HEADER_FALLBACK_ENABLED", "false")
        monkeypatch.delenv("AUTH_JWKS_URL", raising=False)
        monkeypatch.setenv("AUTH_JWT_ISSUER", server.issuer)
        monkeypatch.setenv("AUTH_JWT_AUDIENCE", "control-plane-api")
        monkeypatch.setenv("AUTH_JWT_ALLOWED_ALGORITHMS", "RS256")
        get_settings.cache_clear()
        clear_auth_caches()

        token = jwt.encode(
            {
                "sub": "oidc-user-discovery",
                "role": "admin",
                "tenant_id": "tenant-oidc",
                "iss": server.issuer,
                "aud": "control-plane-api",
                "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            },
            private_key,
            algorithm="RS256",
            headers={"kid": kid},
        )

        response = client.post(
            "/v1/cycles",
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "oidc-create-discovery-bad-alg"},
            json={"project_id": "proj-oidc-discovery", "user_input": "oidc discovery-backed request"},
        )

        assert response.status_code == 401
        assert response.json()["error"]["message"] == "oidc discovery does not advertise a supported signing algorithm"

    monkeypatch.delenv("AUTH_MODE", raising=False)
    monkeypatch.delenv("AUTH_HEADER_FALLBACK_ENABLED", raising=False)
    monkeypatch.delenv("AUTH_JWT_ISSUER", raising=False)
    monkeypatch.delenv("AUTH_JWT_AUDIENCE", raising=False)
    monkeypatch.delenv("AUTH_JWT_ALLOWED_ALGORITHMS", raising=False)
    get_settings.cache_clear()
    clear_auth_caches()



def test_runbook_routes_expose_index_and_detail(client: TestClient) -> None:
    index_response = client.get("/runbooks")
    assert index_response.status_code == 200
    assert index_response.json()["count"] >= 1

    detail_response = client.get("/runbooks/api-availability-fast-burn")
    assert detail_response.status_code == 200
    assert "API availability fast burn" in detail_response.text
    assert detail_response.headers["content-type"].startswith("text/markdown")
