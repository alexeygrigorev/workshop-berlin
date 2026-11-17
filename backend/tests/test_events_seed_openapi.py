import asyncio
import json
from datetime import timedelta
from uuid import UUID

import pytest
import yaml
from fastapi.testclient import TestClient

from app.config import Settings
from app.events import EventBus, event_stream
from app.main import create_app

from .conftest import FAST, OPENAPI, SPEC_PATH, START, ContractClient

NOW = START


def frames(text: str):
    out = []
    for block in text.strip().split("\n\n"):
        if block.startswith(":"):
            continue
        d = dict(line.split(": ", 1) for line in block.splitlines())
        out.append((d["id"], d["event"], json.loads(d["data"])))
    return out


async def collect(gen, n, timeout=2):
    got = []

    async def run():
        async for chunk in gen:
            if chunk.startswith(":"):
                continue
            got.append(chunk)
            if len(got) == n:
                return
    await asyncio.wait_for(run(), timeout)
    return "".join(got)


def test_bus_ids_monotonic_replay_and_resync():
    bus, team = EventBus(), UUID(int=7)
    for i in range(3):
        bus.publish(team, "ballot.submitted", NOW, None, {"i": i})
    assert [e["id"] for e in bus.replay_after(team, 1)] == ["2", "3"]
    assert bus.replay_after(team, 3) == []
    assert bus.replay_after(team, 99) is None  # unknown future id (server restarted) -> resync
    bus.publish(team, "poll.opened", NOW + timedelta(minutes=30))  # old events expire after 10 minutes
    assert bus.replay_after(team, 1) is None


def test_event_stream_live_replay_and_membership_end():
    async def scenario():
        bus, team, user = EventBus(), UUID(int=7), UUID(int=1)
        member = {"v": True}
        bus.publish(team, "restaurant.created", NOW, None, {"restaurant_id": "x"})
        bus.publish(team, "ballot.submitted", NOW, UUID(int=9), {"ballot_count": 1})
        # replay after Last-Event-ID
        gen = event_stream(bus, team, user, "1", lambda: member["v"], lambda: NOW)
        text = await collect(gen, 1)
        assert frames(text)[0][:2] == ("2", "ballot.submitted")
        # live delivery after replay
        live = asyncio.ensure_future(collect(gen, 1))
        await asyncio.sleep(0.05)
        bus.publish(team, "poll.closed", NOW, UUID(int=9), {"winner_id": None, "no_winner": True, "tie_break": None})
        text = await asyncio.wait_for(live, 2)
        assert frames(text)[0][1] == "poll.closed"
        await gen.aclose()
        # unknown Last-Event-ID -> resync
        gen = event_stream(bus, team, user, "9999", lambda: True, lambda: NOW)
        assert frames(await collect(gen, 1))[0][1] == "resync"
        await gen.aclose()
        # stream ends once the caller loses membership
        gen = event_stream(bus, team, user, None, lambda: member["v"], lambda: NOW, keepalive_seconds=0.05)
        task = asyncio.ensure_future(collect_all(gen))
        await asyncio.sleep(0.02)
        member["v"] = False
        bus.publish(team, "member.removed", NOW, None, {"user_id": str(user)})
        out = await asyncio.wait_for(task, 2)
        assert "member.removed" in out

    asyncio.run(scenario())


async def collect_all(gen):
    return "".join([c async for c in gen])


def test_routes_publish_events(client, api, crew, app, clock):
    tid = crew["tid"]
    bus = app.state.bus
    types = [e[2]["type"] for e in bus._buffers[UUID(tid)]]
    assert types.count("member.joined") == 2 and types.count("restaurant.created") == 3
    before = bus.last_id(UUID(tid))
    api.vote(tid, api.poll(tid, crew["admin"])["id"], crew["admin"], crew["r"][:1])  # scheduled -> rejected, no event
    assert bus.last_id(UUID(tid)) == before
    clock.set(clock.now().replace(hour=7))
    p = api.poll(tid, crew["admin"])
    assert api.vote(tid, p["id"], crew["admin"], crew["r"][:1]).status_code == 201
    last = list(bus._buffers[UUID(tid)])[-1][2]
    assert last["type"] == "ballot.submitted" and last["data"]["ballot_count"] == 1 and last["poll_id"] == p["id"]
    assert "token" not in json.dumps(last)


def test_events_endpoint_requires_membership(client, api, crew):
    other = api.signup()
    r = client.get(f"/v1/teams/{crew['tid']}/events", headers=other["h"])
    assert r.status_code == 403 and r.json()["code"] == "not_a_member"
    assert client.get(f"/v1/teams/{crew['tid']}/events").status_code == 401


# ----------------------------------------------------------------------------- seed data
def test_seed_data_gives_frontend_something_to_show(make):
    app = make(seed_demo_data=True)
    from app.clock import FrozenClock
    app.state.clock = FrozenClock(START.replace(hour=9))  # Tuesday 10:00 Berlin: poll open
    c = ContractClient(app)
    r = c.post("/v1/auth/sign-in", json={"email": "anna@example.com", "password": "password123"})
    assert r.status_code == 200
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    c.cookies.clear()
    teams = c.get("/v1/me/teams", headers=h).json()["items"]
    assert {t["team"]["name"] for t in teams} == {"Design crew", "Platform team"}
    tid = next(t["team"]["id"] for t in teams if t["team"]["name"] == "Design crew")
    poll = c.get(f"/v1/teams/{tid}/polls/current", headers=h).json()
    assert poll["status"] == "closed" or poll["status"] == "open"
    hist = c.get(f"/v1/teams/{tid}/polls?limit=100", headers=h).json()["items"]
    assert len(hist) >= 8 and all(p["final_scores"] for p in hist)
    assert {p["tie_break"] for p in hist} >= {"random_draw", "first_place_votes"} and any(p["no_winner"] for p in hist)
    assert c.get(f"/v1/teams/{tid}/restaurants?status=archived", headers=h).json()["items"]
    # seeded passwords are argon2 hashes
    with app.state.uow() as store:
        assert store.user_by_email("ben@example.com").password_hash.startswith("$argon2")
    assert c.post("/v1/auth/sign-in", json={"email": "anna@example.com", "password": "wrong-one"}).status_code == 401


def test_seed_open_poll_has_live_ballots(make):
    from app.clock import FrozenClock
    clock = FrozenClock(START.replace(hour=8, minute=45))  # 09:45 Berlin on a Tuesday
    app = make(clock, seed_demo_data=True)
    c = ContractClient(app)
    h = {"Authorization": "Bearer " + c.post("/v1/auth/sign-in",
         json={"email": "ben@example.com", "password": "password123"}).json()["access_token"]}
    c.cookies.clear()
    tid = next(t["team"]["id"] for t in c.get("/v1/me/teams", headers=h).json()["items"] if t["team"]["name"] == "Design crew")
    p = c.get(f"/v1/teams/{tid}/polls/current", headers=h).json()
    assert p["status"] == "open" and p["ballot_count"] == 3 and p["my_ballot"] is not None
    assert any(s["score"] > 0 for s in p["standings"])


def test_new_teams_via_api_start_empty_even_with_seed_enabled(make):
    app = make(seed_demo_data=True)
    c = ContractClient(app)
    tok = c.post("/v1/auth/sign-up", json={"email": "fresh@example.com", "password": "123456"}).json()["access_token"]
    h = {"Authorization": "Bearer " + tok}
    c.cookies.clear()
    t = c.post("/v1/teams", json={"name": "Fresh", "timezone": "Europe/Berlin"}, headers=h).json()
    assert c.get(f"/v1/teams/{t['id']}/restaurants?status=all", headers=h).json()["items"] == []
    assert c.get(f"/v1/teams/{t['id']}/polls/current", headers=h).json()["candidates"] == []


# ----------------------------------------------------------------------------- contract vs openapi.yaml
SPEC = yaml.safe_load(SPEC_PATH.read_text(encoding="utf8"))
SPEC_OPS = {(m.upper(), path): op["operationId"] for path, item in SPEC["paths"].items()
            for m, op in item.items() if m in ("get", "post", "put", "patch", "delete")}


def test_every_operation_in_spec_has_a_route_with_same_method_path_and_operation_id(make):
    app = make()
    routes = {(m.upper(), path): op.get("operationId")
              for path, item in app.openapi()["paths"].items() for m, op in item.items()}
    # FastAPI route paths use the spec's own parameter names (aliases), so they compare directly
    missing = {k: v for k, v in SPEC_OPS.items() if k not in routes}
    assert not missing, f"operations without a route: {missing}"
    wrong_id = {k: (v, routes[k]) for k, v in SPEC_OPS.items() if routes[k] != v}
    assert not wrong_id, f"operationId mismatch: {wrong_id}"
    assert len(SPEC_OPS) == 40
    extra = {k for k in routes if k not in SPEC_OPS and k[1].startswith("/v1")}
    assert not extra, f"routes not in spec: {extra}"


def test_contract_validation_actually_detects_violations():
    from openapi_core.testing import MockRequest, MockResponse
    from openapi_core.exceptions import OpenAPIError
    req = MockRequest("http://localhost:8787", "get", "/v1/health")
    good = MockResponse(b'{"status":"ok","version":"1","server_time":"2026-11-17T09:14:03Z"}', status_code=200,
                        content_type="application/json")
    OPENAPI.validate_response(req, good)
    bad = MockResponse(b'{"status":"nope"}', status_code=200, content_type="application/json")
    with pytest.raises(OpenAPIError):
        OPENAPI.validate_response(req, bad)


def test_error_responses_are_problem_json_with_known_codes(client, api, crew):
    codes = set(SPEC["components"]["schemas"]["Problem"]["properties"]["code"]["enum"])
    u = api.signup()
    client.validate = False  # unknown routes / methods are outside the spec
    for r in (client.get("/v1/me"), client.get("/v1/nope", headers=u["h"]),
              client.get(f"/v1/teams/{crew['tid']}", headers=u["h"]),
              client.post("/v1/auth/sign-in", json={"email": "x@y.zz", "password": "123456"}),
              client.put("/v1/health")):
        assert r.headers["content-type"].startswith("application/problem+json"), r.text
        j = r.json()
        assert j["code"] in codes and j["status"] == r.status_code and j["type"].startswith("https://")
