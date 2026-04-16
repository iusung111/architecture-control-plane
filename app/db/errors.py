from __future__ import annotations

LOCK_CONFLICT_SQLSTATES = {"55P03", "40P01"}


def _extract_sqlstate(exc: Exception) -> str | None:
    orig = getattr(exc, "orig", None)
    for candidate in (exc, orig):
        if candidate is None:
            continue
        sqlstate = getattr(candidate, "sqlstate", None) or getattr(candidate, "pgcode", None)
        if sqlstate:
            return str(sqlstate)
    return None


def is_lock_conflict(exc: Exception) -> bool:
    sqlstate = _extract_sqlstate(exc)
    if sqlstate in LOCK_CONFLICT_SQLSTATES:
        return True

    message_parts: list[str] = []
    for candidate in (exc, getattr(exc, "orig", None)):
        if candidate is not None:
            message_parts.append(str(candidate).lower())
    message = " ".join(message_parts)
    return "lock timeout" in message or "could not obtain lock" in message or "deadlock detected" in message
