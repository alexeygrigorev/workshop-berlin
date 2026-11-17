"""Engine / session setup. The database is chosen by a standard SQLAlchemy URL (``WSWE_DATABASE_URL``).

SQLite-only tweaks (``check_same_thread``, ``PRAGMA foreign_keys``, explicit BEGIN so SAVEPOINTs work) are applied
only when the URL is a SQLite one; every other backend (e.g. ``postgresql+psycopg://...``) gets plain defaults.
"""
from __future__ import annotations

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .models import Base


def normalize_url(url: str) -> str:
    """Accept ``postgresql://`` and ``postgres://`` (as given by most hosts) and use the psycopg 3 driver for them."""
    parsed = make_url(url)
    if parsed.drivername in ("postgres", "postgresql"):
        parsed = parsed.set(drivername="postgresql+psycopg")
    return parsed.render_as_string(hide_password=False)


def is_sqlite(url: str) -> bool:
    return make_url(url).get_backend_name() == "sqlite"


def make_engine(url: str) -> Engine:
    url = normalize_url(url)
    if not is_sqlite(url):
        # pre-ping drops connections that went away (DB restart, idle timeout); recycle before typical proxy limits
        return create_engine(url, pool_pre_ping=True, pool_recycle=1800)
    parsed = make_url(url)
    kwargs: dict = {"connect_args": {"check_same_thread": False}}
    if parsed.database in (None, "", ":memory:"):  # a private in-memory DB must share its one connection
        kwargs["poolclass"] = StaticPool
    engine = create_engine(url, **kwargs)

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection, _record):  # pragma: no cover - trivial
        dbapi_connection.isolation_level = None  # take over transaction control (pysqlite recipe for SAVEPOINT)
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    @event.listens_for(engine, "begin")
    def _on_begin(conn):  # pragma: no cover - trivial
        conn.exec_driver_sql("BEGIN")

    return engine


class Database:
    def __init__(self, url: str) -> None:
        self.url = url
        self.engine = make_engine(url)
        self.session_factory: sessionmaker[Session] = sessionmaker(self.engine, expire_on_commit=False)

    def create_all(self) -> None:
        """Create tables straight from the models (tests / throw-away DBs; real schemas use Alembic)."""
        Base.metadata.create_all(self.engine)

    def dispose(self) -> None:
        self.engine.dispose()
