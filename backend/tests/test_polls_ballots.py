from datetime import datetime, timedelta, timezone

import pytest

# Berlin is CET (UTC+1) on 2026-11-17: opens 07:00Z, closes 10:30Z.
OPEN = datetime(2026, 11, 17, 7, 0, tzinfo=timezone.utc)
CLOSE = datetime(2026, 11, 17, 10, 30, tzinfo=timezone.utc)


def standings(client, crew, poll_id, user="admin"):
    return client.get(f"/v1/teams/{crew['tid']}/polls/{poll_id}/standings", headers=crew[user]["h"]).json()


def test_poll_lifecycle_scheduled_open_closed(client, api, crew, clock):
    tid, admin = crew["tid"], crew["admin"]
    p = api.poll(tid, admin)
    assert p["status"] == "scheduled" and p["poll_date"] == "2026-11-17" and p["timezone"] == "Europe/Berlin"
    assert p["final_scores"] is None and p["winner_id"] is None and p["tie_break"] is None
    assert [c["name"] for c in p["candidates"]] == ["Alpha", "Bravo", "Charlie"]
    assert all(s["score"] == 0 for s in p["standings"]) and len(p["standings"]) == 3  # zero rows while scheduled
    clock.set(OPEN)
    assert api.poll(tid, admin)["status"] == "open"
    clock.set(CLOSE - timedelta(milliseconds=1))
    assert api.poll(tid, admin)["status"] == "open"
    clock.set(CLOSE)
    p = api.poll(tid, admin)
    assert p["status"] == "closed" and p["no_winner"] is True and p["winner_id"] is None and p["finalized_at"]
    # same poll id returned throughout (one poll per day)
    assert client.get(f"/v1/teams/{tid}/polls-by-date/2026-11-17", headers=admin["h"]).json()["id"] == p["id"]
    assert client.get(f"/v1/teams/{tid}/polls-by-date/2026-11-14", headers=admin["h"]).status_code == 404


def test_weekend_returns_next_monday_and_no_poll_for_saturday(client, api, crew, clock):
    clock.set(datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc))  # Saturday
    p = api.poll(crew["tid"], crew["admin"])
    assert p["poll_date"] == "2026-11-23" and p["status"] == "scheduled"
    r = client.get(f"/v1/teams/{crew['tid']}/polls-by-date/2026-11-21", headers=crew["admin"]["h"])
    assert r.status_code == 404
    clock.set(datetime(2026, 11, 20, 14, 0, tzinfo=timezone.utc))  # Friday afternoon, after close
    p = api.poll(crew["tid"], crew["admin"])  # team existed during today's window -> its (closed) poll
    assert p["poll_date"] == "2026-11-20" and p["status"] == "closed" and p["no_winner"]


def test_dst_keeps_local_boundaries(client, api, clock):
    clock.set(datetime(2026, 3, 30, 3, 0, tzinfo=timezone.utc))
    u = api.signup()
    t = api.team(u, timezone="Europe/Berlin")
    # Monday 2026-03-30 is CEST (UTC+2): 08:00 local = 06:00Z, 11:30 local = 09:30Z
    clock.set(datetime(2026, 3, 30, 3, 0, tzinfo=timezone.utc))
    p = api.poll(t["id"], u)
    assert (p["opens_at"], p["closes_at"]) == ("2026-03-30T06:00:00Z", "2026-03-30T09:30:00Z")
    # Friday before the switch (2026-03-27 is CET)
    r = client.get(f"/v1/teams/{t['id']}/polls-by-date/2026-03-27", headers=u["h"])
    assert r.status_code == 404  # before the team existed
    # a team in New York keeps 08:00-11:30 local across the DST shift
    ny = api.team(u, timezone="America/New_York", name="NY")
    p = api.poll(ny["id"], u)
    assert (p["opens_at"], p["closes_at"]) == ("2026-03-30T12:00:00Z", "2026-03-30T15:30:00Z")  # EDT, UTC-4


def test_ballot_rules(client, api, crew, clock):
    tid, m1 = crew["tid"], crew["m1"]
    a, b, c = crew["r"]
    p = api.poll(tid, m1)
    # not open yet
    r = api.vote(tid, p["id"], m1, [a])
    assert r.status_code == 409 and r.json()["code"] == "poll_not_open"
    clock.set(OPEN)
    r = api.vote(tid, p["id"], m1, [a, b])
    assert r.status_code == 201 and r.json()["choices"] == [a, b] and r.json()["display_name"] == "m1"
    # replace -> 200, never duplicates
    r = api.vote(tid, p["id"], m1, [c, a])
    assert r.status_code == 200 and r.json()["choices"] == [c, a]
    assert len(client.get(f"/v1/teams/{tid}/polls/{p['id']}/ballots", headers=m1["h"]).json()["items"]) == 1
    assert client.get(f"/v1/teams/{tid}/polls/{p['id']}/ballots/me", headers=m1["h"]).json()["choices"] == [c, a]
    assert client.get(f"/v1/teams/{tid}/polls/{p['id']}/ballots/me", headers=crew["m2"]["h"]).status_code == 404
    # same choices twice is idempotent
    assert api.vote(tid, p["id"], m1, [c, a]).status_code == 200
    # validation: 0, 4, duplicates, malformed, unknown candidate
    for choices, code in [([], "validation_failed"), ([a, b, c, a], "validation_failed"), ([a, a], "validation_failed"),
                          (["nope"], "validation_failed"), ([a, "7d0f6a52-8a8e-4f43-b0a3-2b5f3e1d9c10"], "invalid_candidate")]:
        r = api.vote(tid, p["id"], m1, choices)
        assert r.status_code == 422 and r.json()["code"] == code, choices
    r = api.vote(tid, p["id"], m1, [a, "7d0f6a52-8a8e-4f43-b0a3-2b5f3e1d9c10"])
    assert r.json()["errors"][0]["pointer"] == "/choices/1"
    r = client.put(f"/v1/teams/{tid}/polls/{p['id']}/ballots/me", json={"choices": [a, b, c, a]}, headers=m1["h"])
    assert r.json()["errors"][0]["code"] == "too_many_items"
    r = api.vote(tid, p["id"], m1, [a, a])
    assert r.json()["errors"][0]["code"] == "duplicate_items"
    # withdraw (idempotent)
    assert client.delete(f"/v1/teams/{tid}/polls/{p['id']}/ballots/me", headers=m1["h"]).status_code == 204
    assert client.delete(f"/v1/teams/{tid}/polls/{p['id']}/ballots/me", headers=m1["h"]).status_code == 204
    assert client.get(f"/v1/teams/{tid}/polls/{p['id']}/ballots/me", headers=m1["h"]).status_code == 404
    # unknown poll / outsiders
    assert api.vote(tid, "7d0f6a52-8a8e-4f43-b0a3-2b5f3e1d9c10", m1, [a]).status_code == 404
    assert api.vote(tid, p["id"], api.signup(), [a]).json()["code"] == "not_a_member"


def test_ballot_boundary_at_close(client, api, crew, clock):
    tid, m1 = crew["tid"], crew["m1"]
    a = crew["r"][0]
    p = api.poll(tid, m1)
    clock.set(CLOSE - timedelta(milliseconds=1))  # 11:29:59.999 local
    assert api.vote(tid, p["id"], m1, [a]).status_code == 201
    clock.set(CLOSE)  # 11:30:00 local, even though no scheduler/read finalized the poll yet
    r = api.vote(tid, p["id"], m1, [a])
    assert r.status_code == 409 and r.json()["code"] == "poll_closed"
    assert client.delete(f"/v1/teams/{tid}/polls/{p['id']}/ballots/me", headers=m1["h"]).json()["code"] == "poll_closed"


def test_scoring_3_2_1_and_revote(client, api, crew, clock):
    tid, admin, m1, m2 = crew["tid"], crew["admin"], crew["m1"], crew["m2"]
    a, b, c = crew["r"]
    clock.set(OPEN)
    p = api.poll(tid, admin)
    api.vote(tid, p["id"], admin, [a, b, c])
    s = {x["name"]: x for x in standings(client, crew, p["id"])["items"]}
    assert (s["Alpha"]["score"], s["Bravo"]["score"], s["Charlie"]["score"]) == (3, 2, 1)
    api.vote(tid, p["id"], admin, [c, a])  # re-vote replaces: old points removed
    st = standings(client, crew, p["id"])
    s = {x["name"]: x for x in st["items"]}
    assert (s["Alpha"]["score"], s["Bravo"]["score"], s["Charlie"]["score"]) == (2, 0, 3)
    assert st["ballot_count"] == 1 and st["member_count"] == 3 and st["final"] is False
    assert st["leader_ids"] == [c] and st["winner_id"] is None and st["status"] == "open"
    assert [x["name"] for x in st["items"]] == ["Charlie", "Alpha", "Bravo"]
    assert [x["position"] for x in st["items"]] == [1, 2, 3]
    # live leader tie
    clock.advance(minutes=1)
    api.vote(tid, p["id"], m1, [a, c])
    st = standings(client, crew, p["id"])
    assert set(st["leader_ids"]) == {a, c}
    # named ballots visible to all members, ordered by submission
    d = client.get(f"/v1/teams/{tid}/polls/current", headers=m2["h"]).json()
    assert [bl["display_name"] for bl in d["ballots"]] == ["admin", "m1"] and d["my_ballot"] is None
    assert d["ballot_count"] == 2 and d["server_time"] == "2026-11-17T07:01:00Z"


def test_finalization_winner_and_idempotency(client, api, crew, clock):
    tid, admin, m1, m2 = crew["tid"], crew["admin"], crew["m1"], crew["m2"]
    a, b, c = crew["r"]
    clock.set(OPEN)
    p = api.poll(tid, admin)
    api.vote(tid, p["id"], admin, [b, a])
    api.vote(tid, p["id"], m1, [b, c])
    api.vote(tid, p["id"], m2, [a])
    url = f"/v1/teams/{tid}/polls/{p['id']}/finalize"
    early = client.post(url, headers=m1["h"])
    assert early.status_code == 409 and early.json()["code"] == "poll_not_closable"
    assert api.poll(tid, admin)["status"] == "open"  # never closes early
    clock.set(CLOSE + timedelta(minutes=5))
    f1 = client.post(url, headers=m1["h"])
    assert f1.status_code == 200 and f1.json()["status"] == "closed"
    f2 = client.post(url, headers=m2["h"])
    clock.advance(hours=2)
    f3 = client.post(url, headers=admin["h"])
    for f in (f2, f3):
        assert f.status_code == 200
        assert {k: f.json()[k] for k in ("winner_id", "final_scores", "tie_break", "finalized_at", "no_winner")} == \
               {k: f1.json()[k] for k in ("winner_id", "final_scores", "tie_break", "finalized_at", "no_winner")}
    j = f1.json()
    assert j["winner_id"] == b and j["winner"]["name"] == "Bravo" and j["tie_break"] is None
    assert [s["name"] for s in j["final_scores"]] == ["Bravo", "Alpha", "Charlie"]
    assert [s["score"] for s in j["final_scores"]] == [6, 5, 2]  # Bravo 3+3, Alpha 2+3, Charlie 2
    assert j["final_scores"][0]["position"] == 1
    # lazy finalization on read reaches the same result; ballots rejected afterwards
    assert api.vote(tid, p["id"], m1, [a]).status_code == 409
    d = client.get(f"/v1/teams/{tid}/polls/{p['id']}", headers=m1["h"]).json()
    assert d["standings"] == d["final_scores"] and len(d["ballots"]) == 3
    st = standings(client, crew, p["id"])
    assert st["final"] and st["winner_id"] == b and st["leader_ids"] == []


def test_lazy_finalization_without_scheduler(client, api, crew, clock):
    tid, admin, m1 = crew["tid"], crew["admin"], crew["m1"]
    clock.set(OPEN)
    p = api.poll(tid, admin)
    api.vote(tid, p["id"], m1, [crew["r"][2]])
    clock.set(datetime(2026, 11, 17, 18, 0, tzinfo=timezone.utc))  # worker was down all day
    d = api.poll(tid, admin)
    assert d["status"] == "closed" and d["winner_id"] == crew["r"][2]
    polls = client.get(f"/v1/teams/{tid}/polls", headers=admin["h"]).json()["items"]
    assert len(polls) == 1  # no duplicate polls


def test_tie_break_via_api_first_place_votes(client, api, crew, clock):
    # A: 3 (1st) + 1 (3rd) = 4 (one first); B: 2 + 2 = 4 (no firsts) -> A wins on first-place votes
    tid, admin, m1 = crew["tid"], crew["admin"], crew["m1"]
    a, b, c = crew["r"]
    clock.set(OPEN)
    p = api.poll(tid, admin)
    api.vote(tid, p["id"], admin, [a, b])
    api.vote(tid, p["id"], m1, [c, b, a])
    clock.set(CLOSE)
    d = api.poll(tid, admin)
    assert d["winner_id"] == a and d["tie_break"] == "first_place_votes"


def test_random_draw_is_stable_and_symmetric_tie(client, api, crew, clock):
    tid, admin, m1 = crew["tid"], crew["admin"], crew["m1"]
    a, b, _ = crew["r"]
    clock.set(OPEN)
    p = api.poll(tid, admin)
    api.vote(tid, p["id"], admin, [a, b])
    api.vote(tid, p["id"], m1, [b, a])
    clock.set(CLOSE)
    d1 = api.poll(tid, admin)
    assert d1["tie_break"] == "random_draw" and d1["winner_id"] in (a, b)
    clock.advance(days=1)
    d2 = client.get(f"/v1/teams/{tid}/polls/{p['id']}", headers=admin["h"]).json()
    assert d2["winner_id"] == d1["winner_id"] and d2["final_scores"] == d1["final_scores"]
    assert "seed" not in str(d1)  # seed never exposed


def test_zero_ballots_no_winner_and_single_candidate(client, api, clock):
    u = api.signup()
    t = api.team(u)
    api.restaurant(t["id"], u, "Only")
    clock.set(OPEN)
    p = api.poll(t["id"], u)
    only = p["candidates"][0]["id"]
    assert api.vote(t["id"], p["id"], u, [only]).status_code == 201  # one candidate: valid 1-choice ballot
    clock.set(CLOSE)
    d = api.poll(t["id"], u)
    assert d["winner_id"] == only and d["tie_break"] is None
    # the next day with no ballots -> no winner, zero rows kept
    clock.set(datetime(2026, 11, 18, 11, 0, tzinfo=timezone.utc))
    d = api.poll(t["id"], u)
    assert d["status"] == "closed" and d["no_winner"] and d["winner"] is None
    assert [s["score"] for s in d["final_scores"]] == [0]


def test_candidate_snapshot_rules(client, api, crew, clock):
    tid, admin, m1 = crew["tid"], crew["admin"], crew["m1"]
    a, b, c = crew["r"]
    clock.set(OPEN)
    p = api.poll(tid, admin)
    api.vote(tid, p["id"], m1, [a, b])
    # new restaurant while open: candidate immediately, existing ballots unchanged
    d = api.restaurant(tid, m1, "Delta")
    cur = api.poll(tid, admin)
    assert d["id"] in [x["id"] for x in cur["candidates"]]
    assert cur["my_ballot"] is None and cur["ballots"][0]["choices"] == [a, b]
    assert api.vote(tid, p["id"], m1, [d["id"], a]).status_code == 200
    # archive while open: still a candidate, ballots stay valid
    client.post(f"/v1/teams/{tid}/restaurants/{a}/archive", headers=admin["h"])
    cur = api.poll(tid, admin)
    cand = {x["id"]: x for x in cur["candidates"]}
    assert cand[a]["archived"] is True
    assert api.vote(tid, p["id"], m1, [a, d["id"]]).status_code == 200
    assert {s["restaurant_id"] for s in cur["standings"]} >= {a}
    # rename shows immediately while open
    client.patch(f"/v1/teams/{tid}/restaurants/{b}", json={"name": "Bravo 2"}, headers=admin["h"])
    assert "Bravo 2" in [x["name"] for x in api.poll(tid, admin)["candidates"]]
    # closed: names are frozen; adds appear only from next poll
    clock.set(CLOSE)
    closed = api.poll(tid, admin)
    client.patch(f"/v1/teams/{tid}/restaurants/{b}", json={"name": "Bravo 3"}, headers=admin["h"])
    e = api.restaurant(tid, m1, "Echo")
    again = client.get(f"/v1/teams/{tid}/polls/{p['id']}", headers=admin["h"]).json()
    assert "Bravo 2" in [x["name"] for x in again["candidates"]] and "Bravo 3" not in str(again["final_scores"])
    assert e["id"] not in [x["id"] for x in again["candidates"]] and closed["status"] == "closed"
    nxt = api.poll(tid, admin)  # same weekday after close shows today's closed poll; tomorrow has new snapshot
    clock.set(datetime(2026, 11, 18, 5, 0, tzinfo=timezone.utc))
    nxt = api.poll(tid, admin)
    names = [x["name"] for x in nxt["candidates"]]
    assert nxt["poll_date"] == "2026-11-18" and "Echo" in names and "Alpha" not in names and "Bravo 3" in names


def test_history_pagination_and_filters(app, client, api, crew, clock):
    tid, admin = crew["tid"], crew["admin"]
    app.state.store.teams[__import__("uuid").UUID(tid)].created_at = datetime(2026, 10, 1, tzinfo=timezone.utc)
    # create 7 closed weekday polls by visiting each weekday after close
    days = [d for d in (datetime(2026, 11, 2 + i, 12, 0, tzinfo=timezone.utc) for i in range(0, 12)) if d.weekday() < 5]
    for d in days:
        clock.set(d.replace(hour=5))
        poll = api.poll(tid, admin)
        clock.set(d.replace(hour=8))
        api.vote(tid, poll["id"], admin, [crew["r"][d.day % 3]])
    clock.set(datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc))  # Saturday after
    url = f"/v1/teams/{tid}/polls"
    p1 = client.get(url + "?limit=3", headers=admin["h"]).json()
    assert [x["poll_date"] for x in p1["items"]] == ["2026-11-13", "2026-11-12", "2026-11-11"] and p1["next_cursor"]
    p2 = client.get(url + f"?limit=3&cursor={p1['next_cursor']}", headers=admin["h"]).json()
    assert [x["poll_date"] for x in p2["items"]] == ["2026-11-10", "2026-11-09", "2026-11-06"]
    seen = [x["poll_date"] for x in p1["items"] + p2["items"]]
    cur, rest = p2["next_cursor"], []
    while cur:
        page = client.get(url + f"?limit=3&cursor={cur}", headers=admin["h"]).json()
        rest += [x["poll_date"] for x in page["items"]]
        cur = page["next_cursor"]
    all_dates = seen + rest
    assert all_dates == sorted(set(all_dates), reverse=True) and len(all_dates) == 10
    last = client.get(url + "?limit=100", headers=admin["h"]).json()
    assert last["next_cursor"] is None and len(last["items"]) == 10
    assert all(x["status"] == "closed" and x["final_scores"] is not None and x["winner_id"] for x in last["items"])
    rng = client.get(url + "?from=2026-11-10&to=2026-11-12", headers=admin["h"]).json()["items"]
    assert [x["poll_date"] for x in rng] == ["2026-11-12", "2026-11-11", "2026-11-10"]
    assert client.get(url + "?status=open", headers=admin["h"]).json()["items"] == []
    nxt = client.get(url + "?status=any&limit=1", headers=admin["h"]).json()["items"][0]
    assert nxt["poll_date"] == "2026-11-13"
    assert client.get(url + "?limit=0", headers=admin["h"]).status_code == 422
    assert client.get(url + "?cursor=!!!", headers=admin["h"]).status_code == 422
    assert client.get(url + "?from=notadate", headers=admin["h"]).status_code == 422


def test_restaurant_stats(client, api, crew, clock):
    tid, admin = crew["tid"], crew["admin"]
    a, b, c = crew["r"]
    for day, pick in ((17, a), (18, a), (19, b)):
        clock.set(datetime(2026, 11, day, 5, 0, tzinfo=timezone.utc))
        p = api.poll(tid, admin)
        clock.set(datetime(2026, 11, day, 8, 0, tzinfo=timezone.utc))
        api.vote(tid, p["id"], admin, [pick])
    clock.set(datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc))
    s = client.get(f"/v1/teams/{tid}/stats/restaurants", headers=admin["h"]).json()
    assert s["closed_poll_count"] == 3 and s["recent_window"] == 30
    by = {i["name"]: i for i in s["items"]}
    assert (by["Alpha"]["wins_total"], by["Alpha"]["total_points"], by["Alpha"]["last_won_on"]) == (2, 6, "2026-11-18")
    assert by["Bravo"]["wins_recent"] == 1 and by["Charlie"]["wins_total"] == 0
    assert s["items"][0]["name"] == "Alpha"
    s = client.get(f"/v1/teams/{tid}/stats/restaurants?recent_window=1", headers=admin["h"]).json()
    assert {i["name"]: i["wins_recent"] for i in s["items"]} == {"Alpha": 0, "Bravo": 1, "Charlie": 0}
    assert client.get(f"/v1/teams/{tid}/stats/restaurants?recent_window=0", headers=admin["h"]).status_code == 422


def test_scheduler_tick_creates_and_finalizes(app, client, api, crew, clock):
    tid, admin = crew["tid"], crew["admin"]
    clock.set(OPEN)
    app.state.store.tick(clock.now())
    clock.set(CLOSE + timedelta(seconds=1))
    app.state.store.tick(clock.now())
    app.state.store.tick(clock.now())  # idempotent
    polls = client.get(f"/v1/teams/{tid}/polls?status=any", headers=admin["h"]).json()["items"]
    assert [(p["poll_date"], p["status"]) for p in polls] == [("2026-11-18", "scheduled"), ("2026-11-17", "closed")]
