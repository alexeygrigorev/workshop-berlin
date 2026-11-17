"""Application settings (environment variables prefixed WSWE_)."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import field_validator
from sqlalchemy.engine import make_url
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WSWE_", env_file=".env", extra="ignore")

    version: str = "1.0.0"
    # Comma separated list of allowed CORS origins (also trusted for cookie-authenticated unsafe requests).
    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:8080",
        "http://localhost:5173",
        "http://localhost:3000",
    ]
    # Origin used to build invite URLs: <app_origin>/join/<token>. Defaults to the first CORS origin.
    app_origin: str | None = None
    cookie_secure: bool = False  # set true behind HTTPS
    # Standard SQLAlchemy URL. SQLite by default; e.g. postgresql+psycopg://user:pw@host/db once a driver is installed.
    database_url: str = "sqlite:///./wswe.db"
    # Create/upgrade the schema with Alembic at startup. Default (unset): on for SQLite, off for other databases
    # (run `alembic upgrade head` as a deploy step there).
    auto_migrate: bool | None = None
    seed_demo_data: bool = True  # seed demo users/teams/polls on startup, only into an empty database
    scheduler_interval_seconds: float = 30.0  # 0 disables the background tick
    session_days: int = 30
    # Directory with a built SPA (index.html + assets/) to serve at / with index.html fallback. Unset = disabled.
    static_dir: str | None = None
    # Freeze server time at this UTC instant (e.g. 2026-11-17T09:00:00Z) for demos; unset = real clock.
    fixed_now: datetime | None = None
    # argon2 cost parameters (argon2-cffi defaults); tests lower them for speed.
    argon2_time_cost: int = 3
    argon2_memory_kib: int = 65536
    argon2_parallelism: int = 4

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split(cls, v):
        if isinstance(v, str):
            return [o.strip().rstrip("/") for o in v.split(",") if o.strip()]
        return v

    @property
    def should_auto_migrate(self) -> bool:
        if self.auto_migrate is not None:
            return self.auto_migrate
        return make_url(self.database_url).get_backend_name() == "sqlite"

    @property
    def invite_origin(self) -> str:
        return (self.app_origin or self.cors_origins[0]).rstrip("/")
