"""Static frontend serving (WSWE_STATIC_DIR)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import make_app


@pytest.fixture
def static_dir(tmp_path):
    d = tmp_path / "site"
    (d / "assets").mkdir(parents=True)
    (d / "index.html").write_text("<html>SHELL</html>")
    (d / "assets" / "app-abc123.js").write_text("console.log(1)")
    (d / "robots.txt").write_text("User-agent: *")
    (tmp_path / "secret.txt").write_text("secret")
    return d


@pytest.fixture
def client(tmp_path, static_dir):
    return TestClient(make_app(tmp_path / "t.db", static_dir=str(static_dir)))


def test_index_and_no_cache(client):
    r = client.get("/")
    assert r.status_code == 200 and "SHELL" in r.text
    assert r.headers["cache-control"] == "no-cache"
    assert r.headers["content-type"].startswith("text/html")


def test_assets_immutable_and_other_files_short_cache(client):
    r = client.get("/assets/app-abc123.js")
    assert r.status_code == 200 and "immutable" in r.headers["cache-control"]
    r = client.get("/robots.txt")
    assert r.status_code == 200 and "immutable" not in r.headers["cache-control"]


def test_spa_fallback(client):
    for path in ("/teams", "/auth", "/t/abc/restaurants", "/join/some-token"):
        r = client.get(path)
        assert r.status_code == 200 and "SHELL" in r.text and r.headers["cache-control"] == "no-cache"


def test_missing_files_are_404(client):
    assert client.get("/assets/nope.js").status_code == 404
    assert client.get("/nope.png").status_code == 404


def test_api_not_shadowed(client):
    r = client.get("/v1/health")
    assert r.status_code == 200 and "version" in r.json()
    r = client.get("/v1/does-not-exist")
    assert r.status_code == 404 and "SHELL" not in r.text


def test_path_traversal_blocked(client):
    for p in ("/../secret.txt", "/%2e%2e/secret.txt", "/assets/..%2f..%2fsecret.txt", "/..%2fsecret.txt"):
        r = client.get(p)
        assert r.text != "secret" and r.status_code in (200, 404)
        if r.status_code == 200:
            assert "SHELL" in r.text


def test_disabled_when_unset(tmp_path):
    c = TestClient(make_app(tmp_path / "t.db"))
    assert c.get("/").status_code == 404
    assert c.get("/teams").status_code == 404
    assert c.get("/v1/health").status_code == 200


def test_missing_index_fails_fast(tmp_path):
    with pytest.raises(RuntimeError):
        make_app(tmp_path / "t.db", static_dir=str(tmp_path))


def test_head_supported(client):
    r = client.head("/assets/app-abc123.js")
    assert r.status_code == 200 and "immutable" in r.headers["cache-control"]
