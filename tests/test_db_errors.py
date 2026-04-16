from types import SimpleNamespace

from app.db.errors import is_lock_conflict


def test_is_lock_conflict_detects_postgres_sqlstate() -> None:
    exc = Exception("db")
    exc.orig = SimpleNamespace(sqlstate="55P03")  # type: ignore[attr-defined]
    assert is_lock_conflict(exc) is True


def test_is_lock_conflict_detects_message_fallback() -> None:
    exc = Exception("canceling statement due to lock timeout")
    assert is_lock_conflict(exc) is True


def test_is_lock_conflict_rejects_other_database_errors() -> None:
    exc = Exception("duplicate key value violates unique constraint")
    assert is_lock_conflict(exc) is False
