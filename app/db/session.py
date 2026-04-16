from collections.abc import Generator
from threading import RLock

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import URL, make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_ENGINE_CACHE: dict[str, Engine] = {}
_SESSION_FACTORY_CACHE: dict[str, sessionmaker[Session]] = {}
_CACHE_LOCK = RLock()


def get_database_url() -> str:
    return get_settings().database_url


def _database_url_with_connect_timeout(database_url: str) -> str:
    settings = get_settings()
    url = make_url(database_url)
    if url.get_backend_name() != "postgresql":
        return database_url
    if url.query.get("connect_timeout"):
        return str(url)
    updated: URL = url.set(query={**url.query, "connect_timeout": str(settings.db_connect_timeout_seconds)})
    return str(updated)


def _engine_kwargs_for_url(database_url: str) -> dict[str, object]:
    settings = get_settings()
    url = make_url(database_url)
    kwargs: dict[str, object] = {"future": True, "pool_pre_ping": True}
    if url.get_backend_name() != "sqlite":
        kwargs.update(
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout_seconds,
            pool_recycle=settings.db_pool_recycle_seconds,
        )
    return kwargs


def _attach_postgres_session_timeouts(engine: Engine, database_url: str) -> None:
    settings = get_settings()
    url = make_url(database_url)
    if url.get_backend_name() != "postgresql":
        return

    statement_timeout_ms = settings.db_statement_timeout_ms
    idle_in_tx_timeout_ms = settings.db_idle_in_transaction_session_timeout_ms

    @event.listens_for(engine, "connect")
    def _set_postgres_timeouts(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(f"SET statement_timeout = {statement_timeout_ms}")
            cursor.execute(
                f"SET idle_in_transaction_session_timeout = {idle_in_tx_timeout_ms}"
            )
        finally:
            cursor.close()



def get_engine(database_url: str | None = None) -> Engine:
    raw_url = database_url or get_database_url()
    url = _database_url_with_connect_timeout(raw_url)
    engine = _ENGINE_CACHE.get(url)
    if engine is not None:
        return engine

    with _CACHE_LOCK:
        engine = _ENGINE_CACHE.get(url)
        if engine is None:
            engine = create_engine(url, **_engine_kwargs_for_url(url))
            _attach_postgres_session_timeouts(engine, url)
            _ENGINE_CACHE[url] = engine
        return engine



def get_session_factory(database_url: str | None = None) -> sessionmaker[Session]:
    raw_url = database_url or get_database_url()
    url = _database_url_with_connect_timeout(raw_url)
    session_factory = _SESSION_FACTORY_CACHE.get(url)
    if session_factory is not None:
        return session_factory

    with _CACHE_LOCK:
        session_factory = _SESSION_FACTORY_CACHE.get(url)
        if session_factory is None:
            session_factory = sessionmaker(
                bind=get_engine(url),
                autoflush=False,
                autocommit=False,
                expire_on_commit=False,
            )
            _SESSION_FACTORY_CACHE[url] = session_factory
        return session_factory



def dispose_db_resources() -> None:
    with _CACHE_LOCK:
        engines = list(_ENGINE_CACHE.values())
        _ENGINE_CACHE.clear()
        _SESSION_FACTORY_CACHE.clear()

    for engine in engines:
        engine.dispose()



def get_db() -> Generator[Session, None, None]:
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()
