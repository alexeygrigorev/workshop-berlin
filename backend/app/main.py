"""App factory. Run with: uvicorn app.main:create_app --factory --port 8000"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .auth import Passwords
from .clock import Clock, FrozenClock
from .config import Settings
from .db import migrate
from .db.session import Database
from .errors import install_error_handlers
from .events import EventBus
from .routers import auth, ballots, events, health, invites, me, members, polls, restaurants, stats, teams
from .seed import seed as seed_data
from .store import unit_of_work

log = logging.getLogger("wswe")


def create_app(settings: Settings | None = None, clock: Clock | None = None) -> FastAPI:
    settings = settings or Settings()
    if clock is None:
        clock = FrozenClock(settings.fixed_now) if settings.fixed_now else Clock()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = None
        if settings.scheduler_interval_seconds > 0:
            async def loop():
                while True:  # idempotent reconciliation: create/open/finalize polls
                    try:
                        with app.state.uow() as store:
                            store.tick(app.state.clock.now())
                    except Exception:  # pragma: no cover
                        log.exception("scheduler tick failed")
                    await asyncio.sleep(settings.scheduler_interval_seconds)
            task = asyncio.create_task(loop())
        yield
        if task:
            task.cancel()

    app = FastAPI(title="Where Should We Eat? API", version=settings.version, lifespan=lifespan)
    app.state.settings = settings
    app.state.clock = clock
    app.state.passwords = Passwords(settings)
    # In-process pub/sub for SSE: events reach only clients connected to this process (see README).
    app.state.bus = EventBus()
    app.state.db = Database(settings.database_url)
    app.state.uow = lambda: unit_of_work(app.state.db, app.state.bus)  # one transaction (commit / rollback)
    if settings.should_auto_migrate:
        migrate.upgrade(app.state.db.engine)
    if settings.seed_demo_data:  # startup only, never from an endpoint; skipped unless the DB is empty
        with app.state.uow() as store:
            if store.is_empty():
                seed_data(store, app.state.passwords, clock.now())

    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"],
                       allow_headers=["*"], expose_headers=["ETag", "Location", "Retry-After"], allow_credentials=True)
    install_error_handlers(app)
    for r in (health.router, auth.router, me.router, me.tokens_router, invites.public_router, teams.router,
              members.router, invites.team_router, restaurants.router, polls.router, ballots.router, stats.router,
              events.router):
        app.include_router(r)
    return app
