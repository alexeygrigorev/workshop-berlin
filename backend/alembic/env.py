"""Alembic environment. The URL comes from ``WSWE_DATABASE_URL`` (via app Settings, so ``.env`` works too), unless
a live connection is passed in (``config.attributes["connection"]``, used by the app's auto-migrate and by tests)."""
from alembic import context

from app.config import Settings
from app.db.models import Base
from app.db.session import make_engine

config = context.config
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=Settings().database_url, target_metadata=target_metadata, literal_binds=True,
                      render_as_batch=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    engine = make_engine(Settings().database_url)
    try:
        with engine.begin() as connection:
            _run(connection)
    finally:
        engine.dispose()


def _run(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True,
                      compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
