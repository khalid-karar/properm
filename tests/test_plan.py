from datetime import date, timedelta

from tests.test_flow import app, c, world  # noqa: F401


def test_milestones_kpis_deps_limits(c, world):
    h, pid, aid = world["h"], world["pid"], world["aid"]
    pm, s1 = h["pm1"], h["s1"]
    today = date.today()
    # milestones
    r = c.post(f"/projects/{pid}/milestones", json={"name": "Design sign-off", "due_date": str(today + timedelta(days=10))}, headers=pm)
    assert r.status_code == 201 and r.json()["status"] == "upcoming"
    mid = r.json()["id"]
    late = c.post(f"/projects/{pid}/milestones", json={"name": "Kickoff", "due_date": str(today - timedelta(days=5))}, headers=pm).json()
    assert late["status"] == "missed" and late["slip_days"] == 5
    r = c.patch(f"/projects/{pid}/milestones/{late['id']}", json={"achieved_on": str(today - timedelta(days=2))}, headers=pm)
    assert r.json()["status"] == "achieved" and r.json()["slip_days"] == 3
    assert c.patch(f"/projects/{pid}/milestones/{mid}", json={"achieved_on": str(today + timedelta(days=1))}, headers=pm).status_code == 422
    assert c.post(f"/projects/{pid}/milestones", json={"name": "x", "due_date": str(today), "activity_id": 99999}, headers=pm).status_code == 422
    assert c.post(f"/projects/{pid}/milestones", json={"name": "x", "due_date": str(today)}, headers=s1).status_code == 403
    assert len(c.get(f"/projects/{pid}/milestones", headers=s1).json()) == 2
    assert c.delete(f"/projects/{pid}/milestones/{mid}", headers=pm).status_code == 204
    # KPIs
    k = c.post(f"/projects/{pid}/kpis", json={"name": "Defects", "unit": "#", "target": 10, "higher_is_better": False}, headers=pm).json()
    assert k["rag"] is None
    assert c.put(f"/projects/{pid}/kpis/{k['id']}/actual", json={"actual": 11}, headers=pm).json()["rag"] == "amber"
    assert c.put(f"/projects/{pid}/kpis/{k['id']}/actual", json={"actual": 8}, headers=pm).json()["rag"] == "green"
    assert c.put(f"/projects/{pid}/kpis/{k['id']}/actual", json={"actual": 30}, headers=pm).json()["rag"] == "red"
    assert c.post(f"/projects/{pid}/kpis", json={"name": "z", "target": 0}, headers=pm).status_code == 422
    # dependencies
    q = c.post("/projects", headers=pm, json={"number": "PL-1", "name": "Plan", "state": "planning"}).json()["id"]
    mk = lambda code: c.post(f"/projects/{q}/activities", json={"code": code, "name": code, "planned_hours": 10}, headers=pm).json()["id"]
    b1, a2, a3 = mk("B1"), mk("B2"), mk("B3")
    pid_main, pid = pid, q
    assert c.post(f"/projects/{pid}/dependencies", json={"activity_id": a2, "predecessor_id": b1}, headers=pm).status_code == 201
    assert c.post(f"/projects/{pid}/dependencies", json={"activity_id": a2, "predecessor_id": b1}, headers=pm).status_code == 409
    assert c.post(f"/projects/{pid}/dependencies", json={"activity_id": a3, "predecessor_id": a2}, headers=pm).status_code == 201
    assert c.post(f"/projects/{pid}/dependencies", json={"activity_id": b1, "predecessor_id": a3}, headers=pm).status_code == 422  # cycle
    assert c.post(f"/projects/{pid}/dependencies", json={"activity_id": a2, "predecessor_id": a2}, headers=pm).status_code == 422
    deps = c.get(f"/projects/{pid}/dependencies", headers=pm).json()
    assert len(deps) == 2
    assert c.delete(f"/projects/{pid}/dependencies/{deps[0]['id']}", headers=pm).status_code == 204
    # limits listing and clearing
    pid = pid_main
    uid = world["ids"]["s1"]
    assert c.put(f"/projects/{pid}/activities/{aid}/limits", json={"user_id": uid, "max_hours": 5}, headers=pm).status_code == 200
    lim = c.get(f"/projects/{pid}/limits", headers=pm).json()
    assert any(l["user_id"] == uid and l["max_hours"] == 5 for l in lim)
    assert c.get(f"/projects/{pid}/limits", headers=s1).status_code == 403
    assert c.delete(f"/projects/{pid}/activities/{aid}/limits/{uid}", headers=pm).status_code == 204
    assert c.delete(f"/projects/{pid}/activities/{aid}/limits/{uid}", headers=pm).status_code == 404
