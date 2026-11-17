"""Programmatic Alembic helpers (used for auto-migrate on startup and by tests)."""
from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine

BACKEND_DIR = Path(__file__).resolve().parents[2]


def alembic_config() -> Config:
    cfg = Config()  # no ini file: no logging reconfiguration when embedded in the app
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return cfg


def upgrade(engine: Engine, revision: str = "head") -> None:
    """Apply migrations on ``engine`` (migrations run in one transaction where the backend supports it)."""
    cfg = alembic_config()
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, revision)
