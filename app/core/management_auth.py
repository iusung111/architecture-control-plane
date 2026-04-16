from __future__ import annotations

import hmac
import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Literal

from fastapi import HTTPException

from app.core.config import Settings

ManagementRole = Literal["viewer", "operator", "admin"]
_ROLE_RANKS: dict[ManagementRole, int] = {"viewer": 10, "operator": 20, "admin": 30}


@dataclass(frozen=True)
class ManagementAuthContext:
    role: ManagementRole
    key_source: str
    key_fingerprint: str

    @property
    def actor_id(self) -> str:
        return f"management:{self.role}:{self.key_fingerprint}"


@dataclass(frozen=True)
class ManagementKeyRecord:
    presented_key: str
    role: ManagementRole
    key_source: str


def _parse_management_key_records(settings: Settings) -> list[ManagementKeyRecord]:
    records: list[ManagementKeyRecord] = []
    if settings.management_api_key:
        records.append(ManagementKeyRecord(settings.management_api_key, "admin", "legacy"))
    if settings.management_api_keys_json:
        payload = json.loads(settings.management_api_keys_json)
        if isinstance(payload, dict):
            for key, role in payload.items():
                if isinstance(key, str) and isinstance(role, str) and role in _ROLE_RANKS:
                    records.append(ManagementKeyRecord(key, role, "json"))
    return records


def _fingerprint_key(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()[:16]


def resolve_management_access(presented_key: str | None, settings: Settings, *, required_role: ManagementRole) -> ManagementAuthContext:
    if not settings.management_endpoints_require_api_key:
        return ManagementAuthContext(role="admin", key_source="disabled", key_fingerprint="disabled")
    if not presented_key:
        raise HTTPException(status_code=401, detail="missing or invalid management API key")

    matched: ManagementKeyRecord | None = None
    for record in _parse_management_key_records(settings):
        if hmac.compare_digest(presented_key, record.presented_key):
            matched = record
            break
    if matched is None:
        raise HTTPException(status_code=401, detail="missing or invalid management API key")
    if _ROLE_RANKS[matched.role] < _ROLE_RANKS[required_role]:
        raise HTTPException(status_code=403, detail="management role is insufficient")
    return ManagementAuthContext(role=matched.role, key_source=matched.key_source, key_fingerprint=_fingerprint_key(matched.presented_key))
