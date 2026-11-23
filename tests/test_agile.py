from datetime import timedelta

from tests.test_flow import TODAY, app, c, world  # noqa: F401


def test_agile_flow(c, world):
    w, h, pid = world, world["h"], world["pid"]
    pm, s1, s2 = h["pm1"], h["s1"], h["s2"]
    assert c.post(f"/projects/{pid}/backlog", headers=pm, json={"title": "x"}).status_code == 409      # predictive project
    ap = c.post("/projects", headers=pm, json={"number": "AGL-1", "name": "Citizen app", "planned_start": str(TODAY), "project_type": "adaptive"}).json()["id"]
    c.post(f"/projects/{ap}/assignments", headers=pm, json={"user_id": w["ids"]["s1"]})
    i1 = c.post(f"/projects/{ap}/backlog", headers=pm, json={"title": "Login", "points": 5, "rank": 1}).json()
    i2 = c.post(f"/projects/{ap}/backlog", headers=pm, json={"title": "Profile", "points": 3, "rank": 2}).json()
    i3 = c.post(f"/projects/{ap}/backlog", headers=pm, json={"title": "Settings", "points": 2, "rank": 3}).json()
    assert [x["title"] for x in c.get(f"/projects/{ap}/backlog", headers=pm).json()] == ["Login", "Profile", "Settings"]
    assert c.post(f"/projects/{ap}/backlog", headers=pm, json={"title": "bad", "kind": "saga"}).status_code == 422
    sp = c.post(f"/projects/{ap}/sprints", headers=pm, json={"name": "Sprint 1", "start_date": str(TODAY - timedelta(days=3)), "end_date": str(TODAY + timedelta(days=6))}).json()
    sp2 = c.post(f"/projects/{ap}/sprints", headers=pm, json={"name": "Sprint 2", "start_date": str(TODAY + timedelta(days=7)), "end_date": str(TODAY + timedelta(days=20))}).json()
    assert c.post(f"/projects/{ap}/sprints", headers=pm, json={"name": "bad", "start_date": str(TODAY), "end_date": str(TODAY - timedelta(days=1))}).status_code == 422
    assert c.post(f"/projects/{ap}/backlog/{i1['id']}/move", headers=pm, json={"status": "in_progress"}).status_code == 409   # not in a sprint
    for i in (i1, i2, i3):
        assert c.patch(f"/projects/{ap}/backlog/{i['id']}", headers=pm, json={"sprint_id": sp["id"]}).status_code == 200
    started = c.post(f"/projects/{ap}/sprints/{sp['id']}/start", headers=pm).json()
    assert started["status"] == "active" and started["committed_points"] == 10
    assert c.post(f"/projects/{ap}/sprints/{sp2['id']}/start", headers=pm).status_code == 409           # one active at a time
    assert c.post(f"/projects/{ap}/backlog/{i1['id']}/move", headers=s1, json={"status": "in_progress"}).json()["assignee"]
    assert c.post(f"/projects/{ap}/backlog/{i1['id']}/move", headers=s2, json={"status": "done"}).status_code == 403
    assert c.post(f"/projects/{ap}/backlog/{i1['id']}/move", headers=s1, json={"status": "done"}).json()["done_on"] == str(TODAY)
    c.post(f"/projects/{ap}/backlog/{i2['id']}/move", headers=pm, json={"status": "done"})
    sm = c.get(f"/projects/{ap}/agile-summary", headers=pm).json()
    assert sm["burndown"]["total"] == 10 and sm["burndown"]["done"] == 8 and sm["remaining_points"] == 2
    today_pt = next(p for p in sm["burndown"]["points"] if p["date"] == str(TODAY))
    assert today_pt["remaining"] == 2
    r = c.post(f"/projects/{ap}/sprints/{sp['id']}/close", headers=pm, json={"move_to": sp2["id"], "retro_note": "Estimate smaller"}).json()
    assert r["status"] == "closed" and r["moved"] == 1
    assert c.patch(f"/projects/{ap}/sprints/{sp['id']}", headers=pm, json={"goal": "x"}).status_code == 409
    sm = c.get(f"/projects/{ap}/agile-summary", headers=pm).json()
    assert sm["velocity"] == [{"sprint": "Sprint 1", "committed": 10, "done": 8}] and sm["average_velocity"] == 8 and sm["sprints_to_go"] == 0.2
    assert next(x for x in c.get(f"/projects/{ap}/backlog", headers=pm).json() if x["id"] == i3["id"])["sprint"] == "Sprint 2"
