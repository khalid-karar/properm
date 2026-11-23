from datetime import timedelta

from tests.test_flow import TODAY, app, c, world  # noqa: F401


def test_templates(c, world):
    h, pid = world["h"], world["pid"]
    pm, pmo = h["pm1"], h["pmo1"]
    data = {"activities": [{"code": "REQ", "name": "Requirements", "planned_hours": 80, "start_offset_days": 0, "duration_days": 20},
                           {"code": "BLD", "name": "Build", "planned_hours": 200, "start_offset_days": 20, "duration_days": 60, "after": "REQ"}],
            "milestones": [{"name": "Requirements signed", "offset_days": 20}], "kpis": [{"name": "Defects", "unit": "#", "target": 10, "higher_is_better": False}],
            "risks": [{"title": "Unclear scope", "probability": 3, "impact": 4}]}
    assert c.post("/templates", headers=pm, json={"code": "T1", "name": "x", "data": data}).status_code == 403
    assert c.post("/templates", headers=pmo, json={"code": "BAD", "name": "x", "data": {"activities": [{"name": "no code"}]}}).status_code == 422
    t = c.post("/templates", headers=pmo, json={"code": "SW", "name": "Software project", "data": data}).json()
    assert t["counts"] == {"activities": 2, "milestones": 1, "kpis": 1, "risks": 1}
    assert any(x["id"] == t["id"] for x in c.get("/templates", headers=pm).json())
    np_ = c.post("/projects", headers=pm, json={"number": "TPL-1", "name": "From template", "planned_start": str(TODAY)}).json()["id"]
    r = c.post(f"/projects/{np_}/apply-template/{t['id']}", headers=pm).json()
    assert r["activities"] == 2 and r["risks"] == 1
    again = c.post(f"/projects/{np_}/apply-template/{t['id']}", headers=pm).json()
    assert set(again["skipped"]) == {"REQ", "BLD"}
    assert c.post(f"/projects/{pid}/apply-template/{t['id']}", headers=pm).status_code == 409    # baselined
    cp = c.get(f"/projects/{np_}/critical-path", headers=pm).json()
    assert cp["critical"] == ["REQ", "BLD"]
    t2 = c.post(f"/templates/from-project/{np_}", headers=pmo, json={"code": "SW2", "name": "Copy"}).json()
    assert t2["counts"]["activities"] == 2 and t2["data"]["activities"][1]["after"] == "REQ"
    assert c.patch(f"/templates/{t['id']}", headers=pmo, json={"active": False}).json()["active"] is False
    assert c.post(f"/projects/{np_}/apply-template/{t['id']}", headers=pm).status_code == 404


def test_resource_requests_raci_comms(c, world):
    w, h, pid = world, world["h"], world["pid"]
    pm, pmo = h["pm1"], h["pmo1"]
    rr = c.post(f"/projects/{pid}/resource-requests", headers=pm, json={"skill": "Data engineer", "hours_per_week": 20, "start": str(TODAY), "end": str(TODAY + timedelta(days=20))}).json()
    assert any(x["id"] == rr["id"] for x in c.get("/resource-requests", headers=pmo).json())
    assert c.post(f"/resource-requests/{rr['id']}/decision", headers=pm, json={"approve": True, "user_id": w["ids"]["s2"]}).status_code == 403
    assert c.post(f"/resource-requests/{rr['id']}/decision", headers=pmo, json={"approve": True}).status_code == 422
    r = c.post(f"/resource-requests/{rr['id']}/decision", headers=pmo, json={"approve": True, "user_id": w["ids"]["s2"]}).json()
    assert r["status"] == "fulfilled" and r["weeks_planned"] >= 3
    assert w["ids"]["s2"] in c.get(f"/projects/{pid}", headers=pm).json()["assigned_user_ids"]
    # RACI
    c.put(f"/projects/{pid}/raci", headers=pm, json={"item": "Design", "person": "Sara", "letter": "A"})
    x = c.put(f"/projects/{pid}/raci", headers=pm, json={"item": "Design", "person": "Faisal", "letter": "R"}).json()
    assert x["items"] == ["Design"] and x["warnings"] == []
    x = c.put(f"/projects/{pid}/raci", headers=pm, json={"item": "Design", "person": "Faisal", "letter": "A"}).json()
    assert {wn["problem"] for wn in x["warnings"]} == {"many_accountable", "no_responsible"}
    assert c.put(f"/projects/{pid}/raci", headers=pm, json={"item": "Design", "person": "X", "letter": "Z"}).status_code == 422
    assert c.put(f"/projects/{pid}/raci", headers=h["s1"], json={"item": "Design", "person": "X", "letter": "R"}).status_code == 403
    # comms
    cm = c.post(f"/projects/{pid}/comms", headers=pm, json={"audience": "Steering committee", "information": "Status report", "method": "Meeting", "frequency": "monthly", "owner_id": w["ids"]["s1"]}).json()
    assert c.post(f"/projects/{pid}/comms", headers=pm, json={"audience": "x", "information": "y", "method": "z", "frequency": "daily"}).status_code == 422
    s = c.post(f"/projects/{pid}/comms/{cm['id']}/sent", headers=h["s1"]).json()
    assert s["last_sent"] and s["next_due"]
