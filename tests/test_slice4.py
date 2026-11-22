from tests.test_flow import TODAY, app, c, login, mkuser, world   # noqa: F401
from tests.test_slice2 import costed, progress                     # noqa: F401


def test_change_list_pending_and_cost_hidden(c, costed):
    h, pid = costed["h"], costed["cpid"]
    r = c.post(f"/projects/{pid}/changes", headers=h["pm1"], json={"change_type": "scope", "description": "More", "impact_cost_delta": 5000, "impact_hours_delta": 10})
    assert r.status_code == 201
    lst = c.get(f"/projects/{pid}/changes", headers=h["pm1"]).json()
    assert len(lst) == 1 and lst[0]["impact_cost_delta"] == 5000
    # assigned staff may see the request, but not its cost impact
    s = c.get(f"/projects/{pid}/changes", headers=h["s3"]).json()
    assert len(s) == 1 and "impact_cost_delta" not in s[0]
    assert c.get(f"/projects/{pid}/changes", headers=h["s2"]).status_code == 403
    # pending queue: CCB/PMO see it, the requester and staff do not get in
    assert len(c.get("/changes/pending", headers=h["ccb1"]).json()) == 1
    assert len(c.get("/changes/pending", headers=h["pmo1"]).json()) == 1
    assert c.get("/changes/pending", headers=h["pm1"]).status_code == 403
    assert c.get("/changes/pending", headers=h["s1"]).status_code == 403
    cid = r.json()["id"]
    assert c.post(f"/projects/{pid}/changes/{cid}/decision", headers=h["ccb1"], json={"approve": True}).status_code == 200
    assert c.get("/changes/pending", headers=h["ccb1"]).json() == []


def test_own_request_not_in_own_pending_queue(c, costed):
    h, pid = costed["h"], costed["cpid"]
    # make pm1 the CCB requester scenario via the CCB user managing a project of their own
    r = c.post("/projects", headers=h["ccb1"], json={"number": "P-CCB", "name": "Own", "state": "planning", "planned_start": str(TODAY), "planned_end": str(TODAY)})
    own = r.json()["id"]
    c.post(f"/projects/{own}/activities", headers=h["ccb1"], json={"code": "A", "name": "A", "planned_hours": 10, "baseline_cost": 1000, "planned_start": str(TODAY), "planned_end": str(TODAY)})
    lk = c.post(f"/projects/{own}/baseline/lock", headers=h["ccb1"])
    assert lk.status_code == 200, lk.text
    assert c.post(f"/projects/{own}/changes", headers=h["ccb1"], json={"change_type": "cost", "description": "x", "impact_cost_delta": 1}).status_code == 201
    assert c.get("/changes/pending", headers=h["ccb1"]).json() == []


def test_allocations_list_and_assigned_ids(c, costed):
    h, pid, ids = costed["h"], costed["cpid"], costed["ids"]
    assert c.put(f"/projects/{pid}/allocations", headers=h["pm1"], json={"user_id": ids["s3"], "week_of": str(TODAY), "hours": 20}).status_code == 200
    rows = c.get(f"/projects/{pid}/allocations", headers=h["pm1"]).json()
    assert len(rows) == 1 and rows[0]["hours"] == 20 and rows[0]["user_id"] == ids["s3"]
    assert c.get(f"/projects/{pid}/allocations", headers=h["s3"]).status_code == 403     # staff cannot see planning data
    assert ids["s3"] in c.get(f"/projects/{pid}", headers=h["pm1"]).json()["assigned_user_ids"]
    assert "assigned_user_ids" not in c.get(f"/projects/{pid}", headers=h["s3"]).json()


def test_demo_login_off_by_default_and_on_with_flag(c, world, monkeypatch):
    monkeypatch.delenv("PROPERM_DEMO_LOGIN", raising=False)
    assert c.get("/auth/demo-users").status_code == 404
    assert c.post("/auth/demo-login", json={"staff_id": "pm1"}).status_code == 404
    monkeypatch.setenv("PROPERM_DEMO_LOGIN", "1")
    users = c.get("/auth/demo-users").json()
    assert {"pm1", "pmo1", "s1"} <= {u["staff_id"] for u in users}
    r = c.post("/auth/demo-login", json={"staff_id": "pm1"})
    assert r.status_code == 200 and r.json()["role"] == "PM"
    assert c.get("/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"}).json()["staff_id"] == "pm1"
    assert c.post("/auth/demo-login", json={"staff_id": "nobody"}).status_code == 401
