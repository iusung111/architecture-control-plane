from pathlib import Path

from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import dispose_db_resources, get_db, get_engine, get_session_factory


def test_engine_and_session_factory_are_lazy_and_cache_per_database_url(monkeypatch, tmp_path: Path) -> None:
    first_db = tmp_path / "first.db"
    second_db = tmp_path / "second.db"
    first_url = f"sqlite+pysqlite:///{first_db}"
    second_url = f"sqlite+pysqlite:///{second_db}"

    dispose_db_resources()
    monkeypatch.setenv("DATABASE_URL", first_url)
    get_settings.cache_clear()

    first_engine = get_engine()
    first_session_factory = get_session_factory()

    assert str(first_engine.url) == first_url
    assert first_session_factory.kw["bind"] is first_engine
    assert get_engine() is first_engine
    assert get_session_factory() is first_session_factory

    monkeypatch.setenv("DATABASE_URL", second_url)
    get_settings.cache_clear()

    second_engine = get_engine()
    second_session_factory = get_session_factory()

    assert str(second_engine.url) == second_url
    assert second_session_factory.kw["bind"] is second_engine
    assert second_engine is not first_engine
    assert second_session_factory is not first_session_factory

    dispose_db_resources()
    get_settings.cache_clear()


def test_get_db_uses_current_database_url_after_settings_change(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "runtime_switch.db"
    database_url = f"sqlite+pysqlite:///{db_path}"

    dispose_db_resources()
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()

    db_generator = get_db()
    session = next(db_generator)
    try:
        assert str(session.get_bind().url) == database_url
        assert session.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        try:
            next(db_generator)
        except StopIteration:
            pass

    dispose_db_resources()
    get_settings.cache_clear()
