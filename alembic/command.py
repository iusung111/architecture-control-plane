from sqlalchemy import create_engine

from app.db.base import Base


def _engine_from_config(cfg):
    url = cfg.get_main_option('sqlalchemy.url')
    if not url:
        raise RuntimeError('sqlalchemy.url is required for alembic shim')
    return create_engine(url, future=True)


def upgrade(cfg, revision):
    del revision
    engine = _engine_from_config(cfg)
    try:
        Base.metadata.create_all(bind=engine)
    finally:
        engine.dispose()


def downgrade(cfg, revision):
    del revision
    engine = _engine_from_config(cfg)
    try:
        Base.metadata.drop_all(bind=engine)
    finally:
        engine.dispose()
