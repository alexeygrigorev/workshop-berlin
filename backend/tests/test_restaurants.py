def test_add_list_and_search(client, api, crew):
    tid, m1 = crew["tid"], crew["m1"]
    r = client.post(f"/v1/teams/{tid}/restaurants", headers=m1["h"], json={
        "name": " Pho  Saigon ", "cuisine": "Vietnamese", "address": "Reinhardtstraße 12, 10117 Berlin",
        "website_url": None, "map_url": "https://maps.example/x", "notes": ""})
    assert r.status_code == 201
    rest = r.json()
    assert rest["name"] == "Pho  Saigon" and rest["notes"] is None and rest["created_by"] == m1["id"]
    assert rest["archived_at"] is None and r.headers["etag"] and rest["id"] in r.headers["location"]
    names = [x["name"] for x in client.get(f"/v1/teams/{tid}/restaurants", headers=m1["h"]).json()["items"]]
    assert names == ["Alpha", "Bravo", "Charlie", "Pho  Saigon"]
    q = client.get(f"/v1/teams/{tid}/restaurants?q=VIETNAM", headers=m1["h"]).json()["items"]
    assert [x["name"] for x in q] == ["Pho  Saigon"]
    assert client.get(f"/v1/teams/{tid}/restaurants?q=reinhardt", headers=m1["h"]).json()["items"][0]["id"] == rest["id"]
    assert client.get(f"/v1/teams/{tid}/restaurants?status=bogus", headers=m1["h"]).status_code == 422


def test_url_and_name_validation(client, api, crew):
    tid, m1 = crew["tid"], crew["m1"]
    for body, ptr in [({"name": ""}, "/name"), ({"name": "x" * 121}, "/name"),
                      ({"name": "ok", "website_url": "ftp://x.y"}, "/website_url"),
                      ({"name": "ok", "map_url": "javascript:alert(1)"}, "/map_url"), ({}, "/name")]:
        r = client.post(f"/v1/teams/{tid}/restaurants", json=body, headers=m1["h"])
        assert r.status_code == 422 and r.json()["errors"][0]["pointer"] == ptr, body


def test_duplicate_rules(client, api, crew):
    tid, m1 = crew["tid"], crew["m1"]
    existing = api.restaurant(tid, m1, "Pho Saigon", address="Reinhardtstraße 12")
    r = client.post(f"/v1/teams/{tid}/restaurants", headers=m1["h"],
                    json={"name": "  pho   SAIGON ", "address": " reinhardtstraße  12 "})
    assert r.status_code == 409 and r.json()["code"] == "duplicate_restaurant"
    assert r.json()["existing_restaurant_id"] == existing["id"]
    # same name, no address given -> still a duplicate; different address -> allowed
    assert client.post(f"/v1/teams/{tid}/restaurants", headers=m1["h"], json={"name": "Pho Saigon"}).status_code == 409
    assert client.post(f"/v1/teams/{tid}/restaurants", headers=m1["h"],
                       json={"name": "Pho Saigon", "address": "Elsewhere 1"}).status_code == 201


def test_edit_permissions_etag_and_clearing(client, api, crew):
    tid, admin, m1, m2 = crew["tid"], crew["admin"], crew["m1"], crew["m2"]
    mine = api.restaurant(tid, m1, "Mine", notes="n", cuisine="c")
    url = f"/v1/teams/{tid}/restaurants/{mine['id']}"
    etag = client.get(url, headers=m1["h"]).headers["etag"]
    r = client.patch(url, json={"notes": None, "name": "Mine v2"}, headers={**m1["h"], "If-Match": etag})
    assert r.status_code == 200 and r.json()["notes"] is None and r.json()["name"] == "Mine v2"
    assert r.json()["cuisine"] == "c" and r.json()["updated_at"]
    assert client.patch(url, json={"name": "Stale"}, headers={**m1["h"], "If-Match": etag}).json()["code"] == "precondition_failed"
    # another member may not edit; admin may
    r = client.patch(url, json={"name": "Hijack"}, headers=m2["h"])
    assert r.status_code == 403 and r.json()["code"] == "forbidden"
    assert client.patch(url, json={"name": "By admin"}, headers=admin["h"]).status_code == 200
    # duplicate on rename, empty body, unknown id
    assert client.patch(url, json={"name": "alpha"}, headers=admin["h"]).json()["code"] == "duplicate_restaurant"
    assert client.patch(url, json={}, headers=admin["h"]).status_code == 422
    assert client.patch(f"/v1/teams/{tid}/restaurants/7d0f6a52-8a8e-4f43-b0a3-2b5f3e1d9c10", json={"name": "x"},
                        headers=admin["h"]).json()["code"] == "not_found"


def test_archive_unarchive(client, api, crew):
    tid, admin, m1, m2 = crew["tid"], crew["admin"], crew["m1"], crew["m2"]
    a = crew["r"][0]
    base = f"/v1/teams/{tid}/restaurants/{a}"
    assert client.post(base + "/archive", headers=m1["h"]).json()["code"] == "forbidden"  # created by admin
    r = client.post(base + "/archive", headers=admin["h"])
    assert r.status_code == 200 and r.json()["archived_at"] is not None
    assert client.post(base + "/archive", headers=admin["h"]).json()["archived_at"] == r.json()["archived_at"]  # idempotent
    active = [x["name"] for x in client.get(f"/v1/teams/{tid}/restaurants", headers=m1["h"]).json()["items"]]
    assert "Alpha" not in active
    assert [x["name"] for x in client.get(f"/v1/teams/{tid}/restaurants?status=archived", headers=m1["h"]).json()["items"]] == ["Alpha"]
    assert len(client.get(f"/v1/teams/{tid}/restaurants?status=all", headers=m1["h"]).json()["items"]) == 3
    assert client.get(base, headers=m1["h"]).json()["archived_at"] is not None  # still readable
    # a duplicate of an archived restaurant is allowed; unarchiving then conflicts
    api.restaurant(tid, m2, "Alpha")
    r = client.post(base + "/unarchive", headers=admin["h"])
    assert r.status_code == 409 and r.json()["code"] == "duplicate_restaurant"
    client.post(f"/v1/teams/{tid}/restaurants/{r.json()['existing_restaurant_id']}/archive", headers=admin["h"])
    assert client.post(base + "/unarchive", headers=admin["h"]).json()["archived_at"] is None
