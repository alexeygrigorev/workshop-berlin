import pytest


def test_create_team_defaults_and_empty_restaurants(client, api):
    u = api.signup()
    r = client.post("/v1/teams", json={"name": " Design crew ", "timezone": "Europe/Berlin", "office": "Mitte"},
                    headers=u["h"])
    assert r.status_code == 201
    t = r.json()
    assert t["name"] == "Design crew" and t["my_role"] == "admin" and t["member_count"] == 1
    assert t["schedule"] == {"open_time": "08:00", "close_time": "11:30", "weekdays": [1, 2, 3, 4, 5]}
    assert r.headers["location"] == f"/v1/teams/{t['id']}" and r.headers["etag"]
    # new teams start EMPTY: no seeding through the API
    assert client.get(f"/v1/teams/{t['id']}/restaurants?status=all", headers=u["h"]).json() == {"items": []}
    inv = client.get(f"/v1/teams/{t['id']}/invite", headers=u["h"]).json()
    assert inv["active"] and inv["url"].endswith("/join/" + inv["token"])


@pytest.mark.parametrize("body,pointer", [
    ({"name": "", "timezone": "Europe/Berlin"}, "/name"),
    ({"name": "x", "timezone": "Mars/Base"}, "/timezone"),
    ({"name": "x", "timezone": "+02:00"}, "/timezone"),
    ({"name": "x", "timezone": "Europe/Berlin", "open_time": "9:00"}, "/open_time"),
    ({"name": "x", "timezone": "Europe/Berlin", "open_time": "12:00", "close_time": "11:00"}, "/close_time"),
])
def test_create_team_validation(client, api, body, pointer):
    u = api.signup()
    r = client.post("/v1/teams", json=body, headers=u["h"])
    assert r.status_code == 422 and r.json()["code"] == "validation_failed"
    assert r.json()["errors"][0]["pointer"] == pointer


def test_invalid_timezone_error_code(client, api):
    u = api.signup()
    r = client.post("/v1/teams", json={"name": "x", "timezone": "Mars/Base"}, headers=u["h"])
    assert r.json()["errors"][0]["code"] == "invalid_timezone"


def test_member_admin_nonmember_authorization(client, api, crew):
    tid, admin, m1 = crew["tid"], crew["admin"], crew["m1"]
    outsider = api.signup()
    # member can read
    assert client.get(f"/v1/teams/{tid}", headers=m1["h"]).json()["my_role"] == "member"
    assert len(client.get(f"/v1/teams/{tid}/members", headers=m1["h"]).json()["items"]) == 3
    # non-member: 403 not_a_member on everything team scoped (also for unknown teams)
    for method, path in [("get", f"/v1/teams/{tid}"), ("get", f"/v1/teams/{tid}/members"),
                         ("get", f"/v1/teams/{tid}/restaurants"), ("get", f"/v1/teams/{tid}/polls/current"),
                         ("get", f"/v1/teams/{tid}/invite"), ("get", f"/v1/teams/{tid}/events"),
                         ("get", f"/v1/teams/{tid}/stats/restaurants"),
                         ("get", "/v1/teams/7d0f6a52-8a8e-4f43-b0a3-2b5f3e1d9c10")]:
        r = getattr(client, method)(path, headers=outsider["h"])
        assert r.status_code == 403 and r.json()["code"] == "not_a_member", path
    # member vs admin
    r = client.patch(f"/v1/teams/{tid}", json={"name": "New"}, headers=m1["h"])
    assert r.status_code == 403 and r.json()["code"] == "admins_only"
    assert client.patch(f"/v1/teams/{tid}", json={"name": "New"}, headers=admin["h"]).json()["name"] == "New"
    assert client.delete(f"/v1/teams/{tid}/invite", headers=m1["h"]).json()["code"] == "admins_only"
    assert client.post(f"/v1/teams/{tid}/invite/regenerate", headers=m1["h"]).status_code == 403
    assert client.patch(f"/v1/teams/{tid}/members/{m1['id']}", json={"role": "admin"}, headers=m1["h"]).status_code == 403
    assert client.delete(f"/v1/teams/{tid}/members/{admin['id']}", headers=m1["h"]).status_code == 403
    # unauthenticated beats everything
    assert client.get(f"/v1/teams/{tid}").status_code == 401


def test_invite_flow_is_idempotent(client, api, crew):
    tid, admin = crew["tid"], crew["admin"]
    inv = client.get(f"/v1/teams/{tid}/invite", headers=admin["h"]).json()
    newbie = api.signup()
    r = client.get(f"/v1/invites/{inv['token']}", headers=newbie["h"])
    assert r.json() == {"team_id": tid, "team_name": "Crew", "member_count": 3, "already_member": False}
    r = client.post(f"/v1/invites/{inv['token']}/accept", headers=newbie["h"])
    assert r.status_code == 201 and r.json()["joined"] is True and r.json()["role"] == "member"
    r = client.post(f"/v1/invites/{inv['token']}/accept", headers=newbie["h"])
    assert r.status_code == 200 and r.json()["joined"] is False
    r = client.post(f"/v1/invites/{inv['token']}/accept", headers=admin["h"])
    assert r.status_code == 200 and r.json()["role"] == "admin"  # role unchanged
    assert client.get(f"/v1/teams/{tid}", headers=newbie["h"]).json()["member_count"] == 4

    # regenerate invalidates the old token; revoke disables all
    new = client.post(f"/v1/teams/{tid}/invite/regenerate", headers=admin["h"]).json()
    assert new["token"] != inv["token"]
    r = client.get(f"/v1/invites/{inv['token']}", headers=newbie["h"])
    assert r.status_code == 404 and r.json()["code"] == "invite_invalid"
    rev = client.delete(f"/v1/teams/{tid}/invite", headers=admin["h"]).json()
    assert rev["active"] is False and rev["token"] is None and rev["url"] is None
    assert client.delete(f"/v1/teams/{tid}/invite", headers=admin["h"]).status_code == 200  # idempotent
    assert client.get(f"/v1/invites/{new['token']}", headers=newbie["h"]).status_code == 404
    assert client.post("/v1/invites/short/accept", headers=newbie["h"]).status_code == 422


def test_roles_and_last_admin(client, api, crew):
    tid, admin, m1 = crew["tid"], crew["admin"], crew["m1"]
    r = client.patch(f"/v1/teams/{tid}/members/{admin['id']}", json={"role": "member"}, headers=admin["h"])
    assert r.status_code == 409 and r.json()["code"] == "last_admin"
    assert client.delete(f"/v1/teams/{tid}/members/me", headers=admin["h"]).json()["code"] == "last_admin"
    assert client.delete(f"/v1/teams/{tid}/members/{admin['id']}", headers=admin["h"]).json()["code"] == "last_admin"
    r = client.patch(f"/v1/teams/{tid}/members/{m1['id']}", json={"role": "admin"}, headers=admin["h"])
    assert r.status_code == 200 and r.json()["role"] == "admin"
    assert client.patch(f"/v1/teams/{tid}/members/{m1['id']}", json={"role": "admin"}, headers=admin["h"]).status_code == 200
    assert client.patch(f"/v1/teams/{tid}/members/{m1['id']}", json={"role": "boss"}, headers=admin["h"]).status_code == 422
    assert client.patch(f"/v1/teams/{tid}/members/{api.signup()['id']}", json={"role": "admin"},
                        headers=admin["h"]).status_code == 404
    # now the original admin may leave
    assert client.delete(f"/v1/teams/{tid}/members/me", headers=admin["h"]).status_code == 204
    assert client.get(f"/v1/teams/{tid}", headers=admin["h"]).json()["code"] == "not_a_member"
    assert client.delete(f"/v1/teams/{tid}/members/{crew['m2']['id']}", headers=m1["h"]).status_code == 204
    assert client.delete(f"/v1/teams/{tid}/members/{crew['m2']['id']}", headers=m1["h"]).status_code == 404
    # sole member may leave
    assert client.delete(f"/v1/teams/{tid}/members/me", headers=m1["h"]).status_code == 204
    assert client.get("/v1/me/teams", headers=m1["h"]).json() == {"items": []}


def test_update_team_etag_and_validation(client, api, crew):
    tid, admin = crew["tid"], crew["admin"]
    r = client.get(f"/v1/teams/{tid}", headers=admin["h"])
    etag = r.headers["etag"]
    ok = client.patch(f"/v1/teams/{tid}", json={"office": None, "close_time": "11:45"},
                      headers={**admin["h"], "If-Match": etag})
    assert ok.status_code == 200 and ok.json()["schedule"]["close_time"] == "11:45" and ok.json()["office"] is None
    stale = client.patch(f"/v1/teams/{tid}", json={"name": "Again"}, headers={**admin["h"], "If-Match": etag})
    assert stale.status_code == 412 and stale.json()["code"] == "precondition_failed"
    assert client.patch(f"/v1/teams/{tid}", json={}, headers=admin["h"]).status_code == 422
    r = client.patch(f"/v1/teams/{tid}", json={"open_time": "12:00"}, headers=admin["h"])
    assert r.status_code == 422  # open must be before close (11:45)


def test_schedule_change_only_affects_polls_not_yet_open(client, api, crew, clock):
    tid, admin = crew["tid"], crew["admin"]
    p = api.poll(tid, admin)
    assert (p["opens_at"], p["closes_at"]) == ("2026-11-17T07:00:00Z", "2026-11-17T10:30:00Z")
    client.patch(f"/v1/teams/{tid}", json={"open_time": "09:00", "close_time": "12:00"}, headers=admin["h"])
    p = api.poll(tid, admin)
    assert (p["opens_at"], p["closes_at"]) == ("2026-11-17T08:00:00Z", "2026-11-17T11:00:00Z")
    clock.set(clock.now().replace(hour=8, minute=30))  # open now
    client.patch(f"/v1/teams/{tid}", json={"close_time": "13:00"}, headers=admin["h"])
    p = api.poll(tid, admin)
    assert p["status"] == "open" and p["closes_at"] == "2026-11-17T11:00:00Z"  # active window stays stable


def test_my_teams_listing(client, api, crew):
    items = client.get("/v1/me/teams", headers=crew["m1"]["h"]).json()["items"]
    assert [(i["role"], i["team"]["name"]) for i in items] == [("member", "Crew")]
