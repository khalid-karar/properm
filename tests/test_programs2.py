from datetime import timedelta

from tests.test_flow import TODAY, app, c, world  # noqa: F401


def test_roadmap_dependencies_risks(c, world):
    w, h = world, world["h"]
    pmo, pm, pid = h["pmo1"], h["pm1"], w["pid"]
    g = c.post("/programs", headers=pmo, json={"code": "RM-1", "name": "Roadmap"}).json()["id"]
    p2 = c.post("/projects", headers=pm, json={"number": "RM-B", "name": "Second", "planned_start": str(TODAY), "planned_end": str(TODAY + timedelta(days=200))}).json()["id"]
    for x in (pid, p2):
        assert c.put(f"/projects/{x}/program", headers=pmo, json={"program_id": g}).status_code == 200
    m = c.post(f"/projects/{pid}/milestones", headers=pm, json={"name": "API ready", "due_date": str(TODAY + timedelta(days=60))}).json()
    assert c.post(f"/programs/{g}/dependencies", headers=pm, json={"project_id": p2, "predecessor_id": pid, "needed_by": str(TODAY)}).status_code == 403
    assert c.post(f"/programs/{g}/dependencies", headers=pmo, json={"project_id": p2, "predecessor_id": p2, "needed_by": str(TODAY)}).status_code == 422
    assert c.post(f"/programs/{g}/dependencies", headers=pmo, json={"project_id": p2, "predecessor_id": pid, "milestone_id": 99999, "needed_by": str(TODAY)}).status_code == 422
    d = c.post(f"/programs/{g}/dependencies", headers=pmo, json={"project_id": p2, "predecessor_id": pid, "milestone_id": m["id"], "needed_by": str(TODAY + timedelta(days=30))})
    assert d.status_code == 201 and d.json()["status"] == "conflict" and d.json()["gap_days"] == 30
    assert c.post(f"/programs/{g}/dependencies", headers=pmo, json={"project_id": pid, "predecessor_id": p2, "needed_by": str(TODAY)}).status_code == 409
    rm = c.get(f"/programs/{g}/roadmap", headers=pmo).json()
    assert len(rm["projects"]) == 2 and rm["conflicts"] == 1 and rm["can_manage"]
    assert c.get(f"/programs/{g}/roadmap", headers=h["s1"]).status_code == 403
    c.patch(f"/projects/{pid}/milestones/{m['id']}", headers=pm, json={"achieved_on": str(TODAY)})
    assert c.get(f"/programs/{g}/roadmap", headers=pmo).json()["dependencies"][0]["status"] == "met"
    r = c.post(f"/programs/{g}/risks", headers=pmo, json={"title": "Shared vendor capacity", "probability": 4, "impact": 5}).json()
    assert r["score"] == 20
    assert c.patch(f"/programs/{g}/risks/{r['id']}", headers=pmo, json={"status": "mitigating", "response": "Second vendor"}).json()["status"] == "mitigating"
    assert c.get(f"/programs/{g}/rollup", headers=pmo).json()["risks"][0]["project"] == "PROGRAM"
    assert c.delete(f"/programs/{g}/dependencies/{d.json()['id']}", headers=pmo).status_code == 204
