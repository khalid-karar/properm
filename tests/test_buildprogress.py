from tests.test_flow import app, c   # noqa: F401

import json


def test_build_progress_needs_password(c, monkeypatch):
    assert c.get("/build-progress/enabled").json() == {"enabled": False}
    assert c.post("/build-progress", json={"password": "x"}).status_code == 404          # off until the server has a password
    monkeypatch.setenv("PROPERM_BUILD_PASSWORD", "s3cret-owner")
    assert c.get("/build-progress/enabled").json() == {"enabled": True}
    assert c.post("/build-progress", json={"password": "wrong"}).status_code == 403
    r = c.post("/build-progress", json={"password": "s3cret-owner"})
    assert r.status_code == 200 and r.json()["milestones"]
    assert c.get("/ui/milestones.json").status_code == 404                                # no longer a public file


def test_build_progress_locks_after_wrong_guesses(c, monkeypatch):
    from app.routers import buildprogress
    buildprogress._FAILS.clear()
    monkeypatch.setenv("PROPERM_BUILD_PASSWORD", "s3cret-owner")
    for _ in range(buildprogress.MAX_FAILS):
        assert c.post("/build-progress", json={"password": "no"}).status_code == 403
    assert c.post("/build-progress", json={"password": "s3cret-owner"}).status_code == 429
    buildprogress._FAILS.clear()
