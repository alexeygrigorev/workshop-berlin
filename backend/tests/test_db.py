"""Persistence: restart durability, database URL configuration, Alembic migrations vs the ORM models."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text

from app.config import Settings
from app.db import migrate
from app.db.models import Base
from app.db.session import Database, make_engine
from app.main import create_app

from .conftest import FAST, ON_PG, START, ContractClient, make_app


def sqlite_url(path) -> str:
    return path if isinstance(path, str) else f"sqlite:///{path.as_posix()}"


# ----------------------------------------------------------------------------- restart durability
def test_data_survives_app_restart(db_url, clock):
    app1 = make_app(db_url, clock)
    c1 = ContractClient(app1)
    r = c1.post("/v1/auth/sign-up", json={"email": "p@x.io", "password": "secret123"})
    assert r.status_code == 201
    token = r.json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}
    c1.cookies.clear()
    team = c1.post("/v1/teams", json={"name": "Persist", "timezone": "Europe/Berlin"}, headers=h).json()
    rest = c1.post(f"/v1/teams/{team['id']}/restaurants", json={"name": "Alpha"}, headers=h).json()
    pat = c1.post("/v1/me/api-tokens", json={"name": "ci", "scopes": ["read"]}, headers=h).json()
    poll = c1.get(f"/v1/teams/{team['id']}/polls/current", headers=h).json()
    clock.set(datetime(2026, 11, 17, 8, 0, tzinfo=timezone.utc))  # 09:00 Berlin: open
    assert c1.put(f"/v1/teams/{team['id']}/polls/{poll['id']}/ballots/me", json={"choices": [rest["id"]]},
                  headers=h).status_code == 201
    app1.state.db.dispose()

    # a brand new app instance on the same database file: nothing in memory carries over
    app2 = make_app(db_url, clock)
    c2 = ContractClient(app2)
    assert c2.get("/v1/me", headers=h).json()["email"] == "p@x.io"  # session persisted (hash only in DB)
    assert c2.get("/v1/me", headers={"Authorization": f"Bearer {pat['token']}"}).status_code == 200  # PAT persisted
    assert c2.post("/v1/auth/sign-in", json={"email": "p@x.io", "password": "secret123"}).status_code == 200
    assert c2.get(f"/v1/teams/{team['id']}", headers=h).json()["name"] == "Persist"
    cur = c2.get(f"/v1/teams/{team['id']}/polls/current", headers=h).json()
    assert cur["id"] == poll["id"] and cur["ballot_count"] == 1 and cur["my_ballot"]["choices"] == [rest["id"]]
    # closing after the restart finalizes from persisted ballots
    clock.set(datetime(2026, 11, 17, 11, 0, tzinfo=timezone.utc))
    closed = c2.get(f"/v1/teams/{team['id']}/polls/current", headers=h).json()
    assert closed["status"] == "closed" and closed["winner_id"] == rest["id"]
    app2.state.db.dispose()

    app3 = make_app(db_url, clock)
    again = ContractClient(app3).get(f"/v1/teams/{team['id']}/polls/{poll['id']}", headers=h).json()
    assert again["status"] == "closed" and again["final_scores"][0]["restaurant_id"] == rest["id"]
    app3.state.db.dispose()


def test_tokens_are_stored_hashed_only(db_url, clock):
    app = make_app(db_url, clock)
    c = ContractClient(app)
    tok = c.post("/v1/auth/sign-up", json={"email": "h@x.io", "password": "secret123"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    secret = c.post("/v1/me/api-tokens", json={"name": "n", "scopes": ["read"]}, headers=h).json()["token"]
    with app.state.db.engine.connect() as conn:
        dump = " ".join(str(v) for t in ("sessions", "api_tokens") for row in conn.execute(text(f"select * from {t}"))
                        for v in row)
    assert tok not in dump and secret not in dump
    app.state.db.dispose()


def test_seed_runs_only_into_empty_database(db_url, clock):
    app = make_app(db_url, clock, seed_demo_data=True)
    c = ContractClient(app)
    tok = c.post("/v1/auth/sign-in", json={"email": "anna@example.com", "password": "password123"}).json()
    c.cookies.clear()
    h = {"Authorization": f"Bearer {tok['access_token']}"}
    anna_id = tok["user"]["id"]
    assert c.patch("/v1/me", json={"display_name": "Anna Changed"}, headers=h).status_code == 200
    app.state.db.dispose()
    app2 = make_app(db_url, clock, seed_demo_data=True)  # non-empty: no reseed, edits and sessions survive
    c2 = ContractClient(app2)
    me = c2.get("/v1/me", headers=h).json()
    assert me["id"] == anna_id and me["display_name"] == "Anna Changed"
    with app2.state.uow() as store:
        assert len(store.teams_of(store.user_by_email("anna@example.com").id)) == 2
    app2.state.db.dispose()


def test_seed_disabled_leaves_database_empty(db_url):
    app = make_app(db_url, None, seed_demo_data=False)
    with app.state.uow() as store:
        assert store.is_empty()
    app.state.db.dispose()


# ----------------------------------------------------------------------------- configuration
@pytest.mark.skipif(ON_PG, reason="SQLite file URL")
def test_database_url_is_read_from_env(monkeypatch, tmp_path):
    assert Settings().database_url == "sqlite:///./wswe.db"
    url = sqlite_url(tmp_path / "from-env.db")
    monkeypatch.setenv("WSWE_DATABASE_URL", url)
    assert Settings().database_url == url
    monkeypatch.setenv("WSWE_SEED_DEMO_DATA", "false")
    monkeypatch.setenv("WSWE_SCHEDULER_INTERVAL_SECONDS", "0")
    app = create_app()  # everything (including auto-migrate for SQLite) from the environment
    assert str(app.state.db.engine.url) == url
    assert (tmp_path / "from-env.db").exists()
    assert "users" in inspect(app.state.db.engine).get_table_names()  # schema created by the migration
    app.state.db.dispose()


def test_auto_migrate_default_depends_on_backend():
    assert Settings(database_url="sqlite:///x.db").should_auto_migrate is True
    assert Settings(database_url="postgresql+psycopg://u:p@h/db").should_auto_migrate is False
    assert Settings(database_url="postgresql+psycopg://u:p@h/db", auto_migrate=True).should_auto_migrate is True
    assert Settings(database_url="sqlite:///x.db", auto_migrate=False).should_auto_migrate is False


@pytest.mark.skipif(ON_PG, reason="SQLite only")
def test_sqlite_foreign_keys_are_enforced(db_url):
    db = Database(sqlite_url(db_url))
    db.create_all()
    with db.engine.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
    db.dispose()


# ----------------------------------------------------------------------------- migrations
def test_alembic_upgrade_head_on_empty_database_and_matches_models(db_url):
    engine = make_engine(db_url)
    migrate.upgrade(engine)
    tables = set(inspect(engine).get_table_names())
    assert set(Base.metadata.tables) <= tables and "alembic_version" in tables
    with engine.connect() as conn:
        assert conn.execute(text("select version_num from alembic_version")).scalar() == "0001"
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    assert diff == [], f"migrations are out of sync with the models: {diff}"
    migrate.upgrade(engine)  # idempotent
    engine.dispose()


def test_migrated_schema_works_end_to_end(db_url, clock):
    # auto-migrates (explicitly on: it is off by default for PostgreSQL), seeds
    app = create_app(Settings(database_url=db_url, seed_demo_data=True, auto_migrate=True, **FAST), clock)
    c = ContractClient(app)
    r = c.post("/v1/auth/sign-in", json={"email": "anna@example.com", "password": "password123"})
    assert r.status_code == 200
    app.state.db.dispose()


def test_alembic_cli_env_uses_database_url(db_url, monkeypatch):
    from alembic import command

    url = db_url
    monkeypatch.setenv("WSWE_DATABASE_URL", url)
    command.upgrade(migrate.alembic_config(), "head")  # same path as `uv run alembic upgrade head`
    engine = make_engine(url)
    assert "teams" in inspect(engine).get_table_names()
    engine.dispose()


# ----------------------------------------------------------------------------- transactions / events
def test_failed_request_rolls_back_and_publishes_nothing(api, crew, app, monkeypatch):
    tid = crew["tid"]
    from uuid import UUID
    before = app.state.bus.last_id(UUID(tid))
    # duplicate restaurant -> 409 raised after nothing was written; the team list stays at 3 restaurants
    r = api.c.post(f"/v1/teams/{tid}/restaurants", json={"name": "Alpha"}, headers=crew["admin"]["h"])
    assert r.status_code == 409
    assert app.state.bus.last_id(UUID(tid)) == before
    listed = api.c.get(f"/v1/teams/{tid}/restaurants", headers=crew["admin"]["h"]).json()["items"]
    assert len(listed) == 3


def test_events_published_only_after_commit(api, crew, app):
    from uuid import UUID
    seen = []
    bus = app.state.bus
    orig = bus.publish

    def spy(*a, **kw):
        with app.state.db.engine.connect() as conn:  # a separate connection sees only committed data
            seen.append(conn.execute(text("select count(*) from restaurants")).scalar())
        return orig(*a, **kw)

    bus.publish = spy
    api.restaurant(crew["tid"], crew["admin"], "Delta")
    assert seen and all(n == 4 for n in seen)
    assert bus.last_id(UUID(crew["tid"])) > 0


def test_ballot_replace_keeps_one_row_per_member(api, crew, app, clock):
    tid, admin = crew["tid"], crew["admin"]
    clock.set(datetime(2026, 11, 17, 8, 0, tzinfo=timezone.utc))
    p = api.poll(tid, admin)
    assert api.vote(tid, p["id"], admin, crew["r"][:2]).status_code == 201
    assert api.vote(tid, p["id"], admin, crew["r"][2:]).status_code == 200
    with app.state.db.engine.connect() as conn:
        assert conn.execute(text("select count(*) from ballots")).scalar() == 1


def test_database_constraints(db_url):
    import uuid
    from sqlalchemy import insert
    from sqlalchemy.exc import IntegrityError
    from app.db.models import Membership, User
    db = Database(db_url)
    db.create_all()
    now = START

    def new_user():
        return insert(User).values(id=uuid.uuid4(), email="dup@x.io", display_name="D", password_hash="h",
                                   created_at=now)
    with db.engine.begin() as conn:
        conn.execute(new_user())
    with pytest.raises(IntegrityError):  # unique email
        with db.engine.begin() as conn:
            conn.execute(new_user())
    with pytest.raises(IntegrityError):  # foreign key (SQLite needs PRAGMA foreign_keys=ON)
        with db.engine.begin() as conn:
            conn.execute(insert(Membership).values(team_id=uuid.uuid4(), user_id=uuid.uuid4(), role="admin",
                                                   joined_at=now))
    db.dispose()


def test_postgres_urls_are_normalised_to_psycopg():
    from app.db.session import normalize_url
    for u in ("postgres://u:p%40@h:5432/d", "postgresql://u:p%40@h:5432/d", "postgresql+psycopg://u:p%40@h:5432/d"):
        assert normalize_url(u) == "postgresql+psycopg://u:p%40@h:5432/d"
    assert normalize_url("sqlite:///x.db") == "sqlite:///x.db"
    assert make_engine("postgresql://u:p@localhost/d").dialect.driver == "psycopg"  # lazy: does not connect


# ----------------------------------------------------------------------------- two containers during a rollout
def test_concurrent_startups_migrate_and_seed_once(db_url, clock):
    """Old and new app containers overlap during a zero-downtime rollout: both run migrations and the (idempotent)
    seed at boot. A Postgres advisory lock serialises them; on SQLite the runs are simply sequential."""
    import threading

    errors: list[BaseException] = []
    apps = []

    def boot():
        try:
            apps.append(create_app(Settings(database_url=db_url, seed_demo_data=True, auto_migrate=True, **FAST),
                                   clock))
        except BaseException as e:  # pragma: no cover - only on failure
            errors.append(e)

    n = 1 if not ON_PG else 4
    threads = [threading.Thread(target=boot) for _ in range(n)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert errors == []
    with apps[0].state.uow() as store:
        assert len(store.teams_of(store.user_by_email("anna@example.com").id)) == 2
    for a in apps:
        a.state.db.dispose()


def test_scheduler_tick_is_idempotent(db_url, clock):
    from sqlalchemy import func, select
    from app.db.models import Poll

    app = make_app(db_url, clock, seed_demo_data=True)

    def polls() -> int:
        with app.state.uow() as store:
            return store.db.scalar(select(func.count()).select_from(Poll))

    with app.state.uow() as store:
        store.tick(clock.now())
    first = polls()
    assert first > 0
    for _ in range(2):  # a second container's scheduler (or a retry) changes nothing
        with app.state.uow() as store:
            store.tick(clock.now())
    assert polls() == first
    app.state.db.dispose()
