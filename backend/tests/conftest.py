"""Test fixtures: an app with a controllable clock, and a client that validates every response against
api/openapi.yaml (so every functional test doubles as a contract test)."""
from __future__ import annotations

import os
import uuid
import warnings
from datetime import datetime, timezone
from pathlib import Path

import pytest

warnings.filterwarnings("ignore", message=".*httpx.*")

from fastapi.testclient import TestClient  # noqa: E402
import json  # noqa: E402

from openapi_core import Config, OpenAPI  # noqa: E402
from openapi_core.exceptions import OpenAPIError  # noqa: E402
from openapi_core.testing import MockRequest, MockResponse  # noqa: E402

from app.clock import FrozenClock  # noqa: E402
from app.config import Settings  # noqa: E402
from app.db.session import Database  # noqa: E402
from app.main import create_app as _create_app  # noqa: E402

SPEC_PATH = Path(__file__).resolve().parents[2] / "api" / "openapi.yaml"
OPENAPI = OpenAPI.from_file_path(
    str(SPEC_PATH), config=Config(extra_media_type_deserializers={"application/problem+json": json.loads}))

# Tuesday 2026-11-17 06:00Z == 07:00 Europe/Berlin (CET): one hour before the default poll opens (08:00 local).
START = datetime(2026, 11, 17, 6, 0, tzinfo=timezone.utc)
FAST = dict(scheduler_interval_seconds=0, argon2_time_cost=1, argon2_memory_kib=1024, argon2_parallelism=1)



# Set WSWE_TEST_DATABASE_URL (e.g. postgresql+psycopg://wswe:wswe@localhost:5432/wswe) to run the suite on
# PostgreSQL. Each test then gets its own throw-away database (wswe_test_<random>) on that server, dropped
# afterwards; the database named in the URL itself is only used to connect and is never modified.
PG_URL = os.environ.get("WSWE_TEST_DATABASE_URL") or None
ON_PG = PG_URL is not None


def make_app(db_url, clock=None, **overrides):
    """App on a test database (SQLite file path or SQLAlchemy URL); the schema is created straight from the models
    (migrations are tested separately)."""
    url = db_url if isinstance(db_url, str) else f"sqlite:///{Path(db_url).as_posix()}"
    Database(url).create_all()
    opts = {**FAST, "database_url": url, "auto_migrate": False, "seed_demo_data": False, **overrides}
    return _create_app(Settings(**opts), clock)


UNDOCUMENTED: list[str] = []  # (method path status) combos the spec does not declare; reported at the end


class ContractClient(TestClient):
    validate = True

    def request(self, method, url, *args, **kwargs):  # type: ignore[override]
        resp = super().request(method, url, *args, **kwargs)
        if self.validate:
            self._validate(method, str(resp.request.url), resp)
        return resp

    def _validate(self, method, url, resp):
        from urllib.parse import urlsplit
        parts = urlsplit(url)
        ctype = resp.headers.get("content-type", "").split(";")[0] or "application/json"
        req = MockRequest("http://localhost:8787", method.lower(), parts.path)
        out = MockResponse(resp.content, status_code=resp.status_code, content_type=ctype,
                           headers=dict(resp.headers))
        try:
            OPENAPI.validate_response(req, out)
        except OpenAPIError as e:  # pragma: no cover - reported as failures with context
            msg = f"{type(e).__name__}"
            if "ResponseNotFound" in msg or "not found" in str(e).lower() and "status" in str(e).lower():
                UNDOCUMENTED.append(f"{method} {parts.path} -> {resp.status_code}")
                return
            raise AssertionError(f"Response violates OpenAPI spec: {method} {parts.path} -> {resp.status_code}\n"
                                 f"{type(e).__name__}: {e}\n{e.__cause__!r}\nbody={resp.text[:500]}") from e


@pytest.fixture()
def clock():
    return FrozenClock(START)


@pytest.fixture()
def db_url(tmp_path):
    """URL of a fresh, empty database for this test (SQLite file, or a throw-away PostgreSQL database)."""
    if not ON_PG:
        yield f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
        return
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url
    from app.db.session import normalize_url
    base = make_url(normalize_url(PG_URL))
    name = f"wswe_test_{uuid.uuid4().hex[:12]}"
    admin = create_engine(base, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        yield base.set(database=name).render_as_string(hide_password=False)
    finally:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture()
def make(db_url):
    """Factory for apps on this test's own database: make(clock=None, **settings_overrides)."""
    apps = []

    def factory(clock=None, **overrides):
        a = make_app(db_url, clock, **overrides)
        apps.append(a)
        return a
    yield factory
    for a in apps:
        a.state.db.dispose()


@pytest.fixture()
def app(make, clock):
    return make(clock)


@pytest.fixture()
def client(app):
    c = ContractClient(app)
    return c


class Api:
    """Small helper around the client for readable tests."""

    def __init__(self, client: ContractClient, app):
        self.c, self.app, self._n = client, app, 0
        self._by_id: dict[str, dict] = {}

    def signup(self, email: str | None = None, password: str = "secret123") -> dict:
        self._n += 1
        email = email or f"user{self._n}@example.com"
        r = self.c.post("/v1/auth/sign-up", json={"email": email, "password": password})
        assert r.status_code == 201, r.text
        self.c.cookies.clear()
        body = r.json()
        user = {"id": body["user"]["id"], "email": email, "h": {"Authorization": f"Bearer {body['access_token']}"},
                "token": body["access_token"]}
        self._by_id[user["id"]] = user
        return user

    def team(self, owner: dict, **kw) -> dict:
        body = {"name": "Crew", "timezone": "Europe/Berlin", **kw}
        r = self.c.post("/v1/teams", json=body, headers=owner["h"])
        assert r.status_code == 201, r.text
        return r.json()

    def join(self, team_id: str, user: dict) -> None:
        token = self.c.get(f"/v1/teams/{team_id}/invite", headers=self._admin_h(team_id)).json()["token"]
        r = self.c.post(f"/v1/invites/{token}/accept", headers=user["h"])
        assert r.status_code in (200, 201), r.text

    def _admin_h(self, team_id: str) -> dict:
        """Headers of any admin of the team (looked up in the store; test convenience)."""
        import uuid
        with self.app.state.uow() as store:
            team = store.get_team(uuid.UUID(team_id))
            admin = next(uid for uid, m in team.members.items() if m.role == "admin")
        return self._by_id[str(admin)]["h"]

    def restaurant(self, team_id: str, user: dict, name: str, **kw) -> dict:
        r = self.c.post(f"/v1/teams/{team_id}/restaurants", json={"name": name, **kw}, headers=user["h"])
        assert r.status_code == 201, r.text
        return r.json()

    def poll(self, team_id: str, user: dict) -> dict:
        r = self.c.get(f"/v1/teams/{team_id}/polls/current", headers=user["h"])
        assert r.status_code == 200, r.text
        return r.json()

    def vote(self, team_id: str, poll_id: str, user: dict, choices: list[str]):
        return self.c.put(f"/v1/teams/{team_id}/polls/{poll_id}/ballots/me", json={"choices": choices},
                          headers=user["h"])


@pytest.fixture()
def api(client, app):
    return Api(client, app)


@pytest.fixture()
def crew(api):
    """A team with admin + two members and three restaurants (A, B, C)."""
    admin, m1, m2 = api.signup("admin@example.com"), api.signup("m1@example.com"), api.signup("m2@example.com")
    team = api.team(admin)
    api.join(team["id"], m1)
    api.join(team["id"], m2)
    rs = [api.restaurant(team["id"], admin, n) for n in ("Alpha", "Bravo", "Charlie")]
    return {"team": team, "tid": team["id"], "admin": admin, "m1": m1, "m2": m2, "r": [r["id"] for r in rs]}


def pytest_sessionfinish(session, exitstatus):
    if UNDOCUMENTED:
        uniq = sorted(set(UNDOCUMENTED))
        print("\nResponses with statuses not declared in openapi.yaml (spec gaps):")
        for u in uniq:
            print("  ", u)
