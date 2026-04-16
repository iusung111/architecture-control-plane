from urllib.parse import urljoin, urlparse

import httpx
import jwt
from jwt import InvalidTokenError

from app.core.config import Settings

from .bearer import auth_algorithm_set, auth_algorithms, claims_to_auth_context
from .cache import _DISCOVERY_CACHE, _JWKS_CACHE, get_cached, set_cached
from .models import AuthContext, AuthError


def is_url(value: str | None) -> bool:
    if not value:
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def is_loopback_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}


def validate_metadata_url(url: str, settings: Settings, *, field_name: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise AuthError(f"invalid oidc discovery {field_name}")
    if settings.auth_oidc_require_https and parsed.scheme != "https" and not is_loopback_http_url(url):
        raise AuthError(f"oidc discovery {field_name} must use https")
    return url


def validate_discovery_document(payload: dict[str, object], settings: Settings) -> dict[str, object]:
    issuer = payload.get("issuer")
    if not isinstance(issuer, str) or not issuer:
        raise AuthError("invalid oidc discovery document")
    validate_metadata_url(issuer, settings, field_name="issuer")
    if settings.auth_jwt_issuer and is_url(settings.auth_jwt_issuer) and issuer != settings.auth_jwt_issuer:
        raise AuthError("oidc discovery issuer mismatch")

    jwks_uri = payload.get("jwks_uri")
    if not isinstance(jwks_uri, str) or not jwks_uri:
        raise AuthError("invalid oidc discovery document")
    validate_metadata_url(jwks_uri, settings, field_name="jwks_uri")

    supported_algs = payload.get("id_token_signing_alg_values_supported")
    if supported_algs is not None:
        if not isinstance(supported_algs, list) or not all(isinstance(item, str) for item in supported_algs):
            raise AuthError("invalid oidc discovery document")
        if set(auth_algorithms(settings)).isdisjoint(set(supported_algs)):
            raise AuthError("oidc discovery does not advertise a supported signing algorithm")

    return payload


def default_discovery_url(issuer: str | None) -> str | None:
    if not is_url(issuer):
        return None
    return urljoin(issuer.rstrip("/") + "/", ".well-known/openid-configuration")


def discovery_url(settings: Settings) -> str | None:
    if settings.auth_oidc_discovery_url:
        return settings.auth_oidc_discovery_url
    if settings.auth_jwks_url:
        return None
    return default_discovery_url(settings.auth_jwt_issuer)


def fetch_json_document(url: str, *, invalid_message: str) -> dict[str, object]:
    try:
        response = httpx.get(url, timeout=5.0)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise AuthError(invalid_message) from exc
    if not isinstance(payload, dict):
        raise AuthError(invalid_message)
    return payload


def fetch_discovery_document(settings: Settings) -> dict[str, object] | None:
    url = discovery_url(settings)
    if not url:
        return None
    cached = get_cached(_DISCOVERY_CACHE, url)
    if cached is not None:
        return cached
    payload = validate_discovery_document(fetch_json_document(url, invalid_message="failed to fetch oidc discovery document"), settings)
    set_cached(_DISCOVERY_CACHE, url, settings.auth_oidc_discovery_cache_ttl_seconds, payload)
    return payload


def resolved_jwks_url(settings: Settings) -> str:
    if settings.auth_jwks_url:
        return settings.auth_jwks_url
    discovery = fetch_discovery_document(settings)
    if discovery and isinstance(discovery.get("jwks_uri"), str):
        return discovery["jwks_uri"]
    raise AuthError("server auth configuration is incomplete")


def resolved_issuer(settings: Settings) -> str | None:
    if settings.auth_oidc_discovery_url or not settings.auth_jwks_url:
        discovery = fetch_discovery_document(settings)
        if discovery and isinstance(discovery.get("issuer"), str):
            return discovery["issuer"]
    return settings.auth_jwt_issuer


def fetch_jwks(settings: Settings) -> dict[str, object]:
    url = resolved_jwks_url(settings)
    cached = get_cached(_JWKS_CACHE, url)
    if cached is not None:
        return cached
    payload = fetch_json_document(url, invalid_message="failed to fetch jwks")
    if not isinstance(payload.get("keys"), list):
        raise AuthError("invalid jwks document")
    set_cached(_JWKS_CACHE, url, settings.auth_jwks_cache_ttl_seconds, payload)
    return payload


def find_signing_key(token: str, settings: Settings):
    try:
        header = jwt.get_unverified_header(token)
    except InvalidTokenError as exc:
        raise AuthError("malformed bearer token") from exc

    kid = header.get("kid")
    if not isinstance(kid, str) or not kid:
        raise AuthError("missing kid header")
    algorithm = header.get("alg")
    if not isinstance(algorithm, str) or algorithm not in auth_algorithm_set(settings):
        raise AuthError("unsupported bearer token algorithm")

    for jwk_dict in fetch_jwks(settings)["keys"]:
        if isinstance(jwk_dict, dict) and jwk_dict.get("kid") == kid:
            try:
                return jwt.PyJWK.from_dict(jwk_dict, algorithm=algorithm).key
            except Exception as exc:  # noqa: BLE001
                raise AuthError("invalid jwks signing key") from exc
    raise AuthError("signing key not found")


def authenticate_oidc_token(token: str, settings: Settings) -> AuthContext:
    try:
        payload = jwt.decode(
            token,
            key=find_signing_key(token, settings),
            algorithms=auth_algorithms(settings),
            audience=settings.auth_jwt_audience,
            issuer=resolved_issuer(settings),
            leeway=settings.auth_jwt_leeway_seconds,
            options={"require": ["sub", "exp"]},
        )
    except InvalidTokenError as exc:
        raise AuthError(str(exc)) from exc

    if not isinstance(payload, dict):
        raise AuthError("invalid token claims")
    return claims_to_auth_context(payload, settings)
