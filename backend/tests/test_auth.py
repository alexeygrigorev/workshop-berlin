from datetime import timedelta
from uuid import UUID


def test_sign_up_in_out_flow(client, api, app):
    r = client.post("/v1/auth/sign-up", json={"email": "  Anna@Company.com ", "password": "correct-horse"})
    assert r.status_code == 201
    body = r.json()
    assert body["token_type"] == "Bearer" and body["user"]["email"] == "anna@company.com"
    assert body["user"]["display_name"] == "anna"
    assert "wswe_session" in r.headers["set-cookie"] and "HttpOnly" in r.headers["set-cookie"]
    client.cookies.clear()
    h = {"Authorization": f"Bearer {body['access_token']}"}
    assert client.get("/v1/me", headers=h).json()["email"] == "anna@company.com"

    r = client.post("/v1/auth/sign-in", json={"email": "anna@company.com", "password": "correct-horse"})
    assert r.status_code == 200
    client.cookies.clear()
    tok2 = r.json()["access_token"]
    assert tok2 != body["access_token"]

    assert client.post("/v1/auth/sign-out", headers={"Authorization": f"Bearer {tok2}"}).status_code == 204
    assert client.get("/v1/me", headers={"Authorization": f"Bearer {tok2}"}).status_code == 401
    # the other session is unaffected
    assert client.get("/v1/me", headers=h).status_code == 200


def test_passwords_are_hashed_with_argon2(client, app):
    client.post("/v1/auth/sign-up", json={"email": "h@x.io", "password": "plaintext-pw"})
    with app.state.uow() as store:
        user = store.user_by_email("h@x.io")
        assert user.password_hash.startswith("$argon2id$")
        assert "plaintext-pw" not in user.password_hash


def test_duplicate_email_and_validation(client):
    ok = {"email": "a@b.co", "password": "123456"}
    assert client.post("/v1/auth/sign-up", json=ok).status_code == 201
    r = client.post("/v1/auth/sign-up", json={"email": "A@B.co", "password": "abcdef"})
    assert r.status_code == 409 and r.json()["code"] == "email_taken"
    assert r.headers["content-type"].startswith("application/problem+json")
    r = client.post("/v1/auth/sign-up", json={"email": "c@d.co", "password": "123"})
    assert r.status_code == 422 and r.json()["code"] == "validation_failed"
    assert r.json()["errors"][0] == {"pointer": "/password", "code": "too_short",
                                     "message": r.json()["errors"][0]["message"]}
    r = client.post("/v1/auth/sign-up", json={"email": "not-an-email", "password": "123456"})
    assert r.status_code == 422 and r.json()["errors"][0]["pointer"] == "/email"
    assert client.post("/v1/auth/sign-up", content=b"{oops", headers={"content-type": "application/json"}
                       ).status_code == 422


def test_bad_credentials_are_indistinguishable(client):
    client.post("/v1/auth/sign-up", json={"email": "a@b.co", "password": "123456"})
    wrong = client.post("/v1/auth/sign-in", json={"email": "a@b.co", "password": "nope-nope"})
    unknown = client.post("/v1/auth/sign-in", json={"email": "zzz@b.co", "password": "nope-nope"})
    for r in (wrong, unknown):
        assert r.status_code == 401 and r.json()["code"] == "invalid_credentials"
    assert wrong.json()["title"] == unknown.json()["title"]


def test_unauthenticated(client):
    for h in ({}, {"Authorization": "Bearer nope"}, {"Authorization": "Bearer wswe_pat_nope"}):
        r = client.get("/v1/me", headers=h)
        assert r.status_code == 401 and r.json()["code"] == "unauthenticated"


def test_session_is_30_days_and_sliding(client, api, clock):
    u = api.signup()
    clock.advance(days=29)
    assert client.get("/v1/me", headers=u["h"]).status_code == 200  # renews to day 59
    clock.advance(days=29)
    assert client.get("/v1/me", headers=u["h"]).status_code == 200  # 58 < 59
    clock.advance(days=30, seconds=1)
    r = client.get("/v1/me", headers=u["h"])
    assert r.status_code == 401 and r.json()["code"] == "unauthenticated"


def test_update_display_name(client, api):
    u = api.signup()
    r = client.patch("/v1/me", json={"display_name": "Anna K."}, headers=u["h"])
    assert r.status_code == 200 and r.json()["display_name"] == "Anna K."
    assert client.patch("/v1/me", json={}, headers=u["h"]).status_code == 422


def test_api_tokens_scopes(client, api):
    u = api.signup()
    r = client.post("/v1/me/api-tokens", json={"name": "ro", "scopes": ["read"]}, headers=u["h"])
    assert r.status_code == 201
    ro = r.json()
    assert ro["token"].startswith("wswe_pat_") and ro["token_prefix"] == ro["token"][:13]
    ro_h = {"Authorization": f"Bearer {ro['token']}"}
    rw = client.post("/v1/me/api-tokens", json={"name": "rw"}, headers=u["h"]).json()
    assert rw["scopes"] == ["read", "write"]
    rw_h = {"Authorization": f"Bearer {rw['token']}"}

    assert client.get("/v1/me", headers=ro_h).status_code == 200
    r = client.post("/v1/teams", json={"name": "T", "timezone": "Europe/Berlin"}, headers=ro_h)
    assert r.status_code == 403 and r.json()["code"] == "insufficient_scope"
    r = client.patch("/v1/me", json={"display_name": "x"}, headers=ro_h)
    assert r.status_code == 403 and r.json()["code"] == "insufficient_scope"
    assert client.post("/v1/teams", json={"name": "T", "timezone": "Europe/Berlin"}, headers=rw_h).status_code == 201

    # token management and sign-out need a session
    r = client.get("/v1/me/api-tokens", headers=rw_h)
    assert r.status_code == 403 and r.json()["code"] == "insufficient_scope"
    r = client.post("/v1/me/api-tokens", json={"name": "x"}, headers=rw_h)
    assert r.status_code == 403
    assert client.post("/v1/auth/sign-out", headers=rw_h).status_code == 204
    assert client.get("/v1/me", headers=rw_h).status_code == 200  # token NOT revoked by sign-out

    listed = client.get("/v1/me/api-tokens", headers=u["h"]).json()["items"]
    assert {t["name"] for t in listed} == {"ro", "rw"} and all("token" not in t for t in listed)
    assert listed[0]["last_used_at"] is not None


def test_revoke_token_and_expiry(client, api, clock):
    u, other = api.signup(), api.signup()
    t = client.post("/v1/me/api-tokens", json={"name": "t", "expires_at": "2026-11-20T00:00:00Z"}, headers=u["h"]).json()
    h = {"Authorization": f"Bearer {t['token']}"}
    assert client.get("/v1/me", headers=h).status_code == 200
    assert client.delete(f"/v1/me/api-tokens/{t['id']}", headers=other["h"]).status_code == 404
    assert client.delete(f"/v1/me/api-tokens/{t['id']}", headers=u["h"]).status_code == 204
    assert client.delete(f"/v1/me/api-tokens/{t['id']}", headers=u["h"]).status_code == 204  # idempotent
    assert client.get("/v1/me", headers=h).status_code == 401
    assert client.get("/v1/me/api-tokens", headers=u["h"]).json()["items"] == []

    t2 = client.post("/v1/me/api-tokens", json={"name": "t2", "expires_at": "2026-11-20T00:00:00Z"}, headers=u["h"]).json()
    h2 = {"Authorization": f"Bearer {t2['token']}"}
    clock.advance(days=4)
    assert client.get("/v1/me", headers=h2).status_code == 401
    r = client.post("/v1/me/api-tokens", json={"name": "past", "expires_at": "2020-01-01T00:00:00Z"}, headers=u["h"])
    assert r.status_code == 422
    r = client.post("/v1/me/api-tokens", json={"name": "dup", "scopes": ["read", "read"]}, headers=u["h"])
    assert r.status_code == 422 and r.json()["errors"][0]["code"] == "duplicate_items"


def test_cookie_auth_requires_origin_for_unsafe_methods(client):
    r = client.post("/v1/auth/sign-up", json={"email": "c@c.co", "password": "123456"})
    assert r.status_code == 201  # cookie now stored in the client
    assert client.get("/v1/me").status_code == 200
    body = {"name": "T", "timezone": "Europe/Berlin"}
    r = client.post("/v1/teams", json=body)
    assert r.status_code == 403 and r.json()["code"] == "forbidden"
    r = client.post("/v1/teams", json=body, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    r = client.post("/v1/teams", json=body, headers={"Origin": "http://localhost:8080"})
    assert r.status_code == 201
    assert client.post("/v1/auth/sign-out", headers={"Origin": "http://localhost:8080"}).status_code == 204
    assert client.get("/v1/me").status_code == 401


def test_idempotency_key_for_creates(client, api):
    u = api.signup()
    h = {**u["h"], "Idempotency-Key": "k-1"}
    body = {"name": "Once", "timezone": "Europe/Berlin"}
    a = client.post("/v1/teams", json=body, headers=h)
    b = client.post("/v1/teams", json=body, headers=h)
    assert a.status_code == b.status_code == 201 and a.json()["id"] == b.json()["id"]
    assert len(client.get("/v1/me/teams", headers=u["h"]).json()["items"]) == 1
    r = client.post("/v1/teams", json={**body, "name": "Different"}, headers=h)
    assert r.status_code == 409 and r.json()["code"] == "idempotency_key_reused"
    UUID(a.json()["id"])
