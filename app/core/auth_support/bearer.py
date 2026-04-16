from typing import Any

import jwt
from jwt import InvalidTokenError
from jwt.exceptions import ExpiredSignatureError, ImmatureSignatureError, InvalidAlgorithmError, InvalidAudienceError, InvalidIssuerError, InvalidSignatureError

from app.core.config import Settings

from .models import AuthContext, AuthError


def coerce_audience(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        return {value}
    if isinstance(value, list):
        return {str(item) for item in value}
    raise AuthError("invalid aud claim")


def coerce_role(payload: dict[str, Any], settings: Settings) -> str:
    role_claim = payload.get(settings.auth_required_role_claim)
    if isinstance(role_claim, str) and role_claim:
        return role_claim

    roles_claim = payload.get("roles")
    if isinstance(roles_claim, list) and roles_claim:
        first_role = roles_claim[0]
        if isinstance(first_role, str) and first_role:
            return first_role

    realm_access = payload.get("realm_access")
    if isinstance(realm_access, dict):
        roles = realm_access.get("roles")
        if isinstance(roles, list) and roles:
            first_role = roles[0]
            if isinstance(first_role, str) and first_role:
                return first_role

    raise AuthError("missing role claim")


def auth_algorithms(settings: Settings) -> list[str]:
    return [value.strip() for value in settings.auth_jwt_allowed_algorithms.split(",") if value.strip()]


def auth_algorithm_set(settings: Settings) -> set[str]:
    return set(auth_algorithms(settings))


def claims_to_auth_context(payload: dict[str, Any], settings: Settings) -> AuthContext:
    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject:
        raise AuthError("missing sub claim")

    tenant_id = payload.get("tenant_id") or payload.get("tenant")
    if tenant_id is not None and not isinstance(tenant_id, str):
        raise AuthError("invalid tenant claim")

    return AuthContext(user_id=subject, role=coerce_role(payload, settings), tenant_id=tenant_id)


def authenticate_bearer_token(token: str, settings: Settings) -> AuthContext:
    if not settings.auth_jwt_secret:
        raise AuthError("server auth configuration is incomplete")

    try:
        header = jwt.get_unverified_header(token)
    except InvalidTokenError as exc:
        raise AuthError("malformed bearer token") from exc

    algorithm = header.get("alg")
    if not isinstance(algorithm, str) or algorithm not in auth_algorithm_set(settings):
        raise AuthError("unsupported bearer token algorithm")

    try:
        payload = jwt.decode(
            token,
            key=settings.auth_jwt_secret,
            algorithms=auth_algorithms(settings),
            audience=settings.auth_jwt_audience,
            issuer=settings.auth_jwt_issuer,
            leeway=settings.auth_jwt_leeway_seconds,
            options={"require": ["sub"]},
        )
    except InvalidSignatureError as exc:
        raise AuthError("invalid bearer token signature") from exc
    except ExpiredSignatureError as exc:
        raise AuthError("bearer token expired") from exc
    except ImmatureSignatureError as exc:
        raise AuthError("bearer token not active yet") from exc
    except InvalidIssuerError as exc:
        raise AuthError("invalid bearer token issuer") from exc
    except InvalidAudienceError as exc:
        raise AuthError("invalid bearer token audience") from exc
    except InvalidAlgorithmError as exc:
        raise AuthError("unsupported bearer token algorithm") from exc
    except InvalidTokenError as exc:
        raise AuthError(str(exc) or "malformed bearer token") from exc

    if not isinstance(payload, dict):
        raise AuthError("invalid token claims")
    return claims_to_auth_context(payload, settings)
