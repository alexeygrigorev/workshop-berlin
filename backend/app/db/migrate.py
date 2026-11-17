"""Programmatic Alembic helpers (used for auto-migrate on startup and by tests)."""
from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text

BACKEND_DIR = Path(__file__).resolve().parents[2]


def alembic_config() -> Config:
    cfg = Config()  # no ini file: no logging reconfiguration when embedded in the app
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return cfg


STARTUP_LOCK_KEY = 0x7773776500000001  # arbitrary constant: "wswe" + 1


def lock_startup(conn) -> None:
    """Serialise startup work (migrations, demo seed) across app processes: two containers overlap during a
    zero-downtime rollout. Transaction-scoped Postgres advisory lock, released on commit/rollback; a no-op elsewhere
    (SQLite has a single writer anyway). ``conn`` is a Connection or a Session."""
    dialect = conn.get_bind().dialect if hasattr(conn, "get_bind") else conn.dialect  # Session / Connection
    if dialect.name == "postgresql":
        conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": STARTUP_LOCK_KEY})


def upgrade(engine: Engine, revision: str = "head") -> None:
    """Apply migrations on ``engine`` (migrations run in one transaction where the backend supports it)."""
    cfg = alembic_config()
    with engine.begin() as conn:
        lock_startup(conn)  # a concurrent starter waits here, then finds the schema already at head
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, revision)
