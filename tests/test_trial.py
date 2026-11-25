from datetime import datetime, timedelta, timezone

from tests.test_flow import TODAY, app, c, world  # noqa: F401

import pytest

from app.routers import trial as trial_mod

BODY = {"name": "Nora Test", "organization": "Acme Delivery", "email": "nora@acme.example"}


@pytest.fixture(autouse=True)
def _fresh_limits():
    trial_mod._HITS.clear()
    yield


def _login(c, sid, pw):
    return c.post("/auth/login", json={"staff_id": sid, "password": pw})


def test_trial_is_off_by_default(c, world, monkeypatch):
    monkeypatch.delenv("PROPERM_TRIALS", raising=False)
    assert c.get("/public/trial/config").json()["enabled"] is False
    assert c.post("/public/trial", json=BODY).status_code == 404


def test_trial_gives_isolated_seeded_sandbox_that_expires(c, world, app, monkeypatch):
    monkeypatch.setenv("PROPERM_TRIALS", "1")
    h = world["h"]
    assert c.get("/public/trial/config").json() == {"enabled": True, "days": 14}
    r = c.post("/public/trial", json=BODY)
    assert r.status_code == 201, r.text
    t = r.json()
    assert t["slug"].startswith("trial-") and len(t["accounts"]) == 4
    assert c.get(f"/public/trial/status?slug={t['slug']}").json()["state"] == "ready"
    adm = _login(c, t["accounts"][0]["staff_id"], t["password"])
    assert adm.status_code == 200
    th = {"Authorization": "Bearer " + adm.json()["access_token"]}
    pm = _login(c, t["slug"] + "-pm1", t["password"]).json()["access_token"]
    mine = c.get("/projects", headers={"Authorization": "Bearer " + pm}).json()
    nums = {p["number"] for p in mine}
    assert {"ALPHA-01", "BETA-02"} <= nums
    # isolation: the trial sees none of the platform owner's projects, and the owner sees none of the trial's
    assert not any(p["name"] == "ERP Rollout" for p in c.get("/projects", headers=h["admin"]).json())
    assert len(c.get("/users", headers=th).json()) == 8 and all(u["staff_id"].startswith(t["slug"]) for u in c.get("/users", headers=th).json())
    # the owner gets a lead
    leads = c.get("/consultations", headers=h["admin"]).json()
    assert any(x["interest"] == "trial" and x["email"] == BODY["email"] for x in leads)
    # one live trial per e-mail
    assert c.post("/public/trial", json=BODY).status_code == 409
    # expiry blocks sign-in
    with app.state.Session() as db:
        db.info["unscoped"] = True
        from app.models import Tenant
        db.query(Tenant).filter_by(slug=t["slug"]).first().trial_until = datetime.now(timezone.utc) - timedelta(days=1)
        db.commit()
    blocked = _login(c, t["accounts"][0]["staff_id"], t["password"])
    assert blocked.status_code == 403 and "trial has ended" in blocked.json()["detail"]


def test_trial_limits_and_honeypot(c, world, monkeypatch):
    monkeypatch.setenv("PROPERM_TRIALS", "1")
    monkeypatch.setenv("PROPERM_TRIAL_MAX", "1")
    bot = c.post("/public/trial", json={**BODY, "email": "bot@x.example", "website": "http://spam"})
    assert bot.status_code == 201 and bot.json()["ok"] and bot.json().get("login") is None and "password" not in bot.json()
    assert c.post("/public/trial", json={**BODY, "email": "bad"}).status_code == 422
    assert c.post("/public/trial", json={**BODY, "email": "one@x.example"}).status_code == 201
    assert c.get("/public/trial/config").json()["enabled"] is False
    assert c.post("/public/trial", json={**BODY, "email": "two@x.example"}).status_code == 503


def test_trial_limits_per_address(c, world, monkeypatch):
    monkeypatch.setenv("PROPERM_TRIALS", "1")
    codes = [c.post("/public/trial", json={**BODY, "email": f"p{i}@x.example"}).status_code for i in range(4)]
    assert codes == [201, 201, 201, 429]


def test_two_trials_and_the_owner_can_all_use_the_same_project_numbers(c, world, monkeypatch):
    monkeypatch.setenv("PROPERM_TRIALS", "1")
    a = c.post("/public/trial", json={**BODY, "email": "a@x.example"}).json()
    b = c.post("/public/trial", json={**BODY, "email": "b@x.example"}).json()
    for t in (a, b):
        assert c.get(f"/public/trial/status?slug={t['slug']}").json()["state"] == "ready"
        tok = _login(c, t["slug"] + "-pm1", t["password"]).json()["access_token"]
        assert "ALPHA-01" in {p["number"] for p in c.get("/projects", headers={"Authorization": "Bearer " + tok}).json()}
