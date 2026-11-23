from tests.test_flow import TODAY, app, c, world  # noqa: F401


def mk(c, h, role, sid):
    c.post("/users", headers=h["admin"], json={"staff_id": sid, "full_name": sid.upper(), "password": "password123", "role": role})
    return {"Authorization": "Bearer " + c.post("/auth/login", json={"staff_id": sid, "password": "password123"}).json()["access_token"]}


def test_intake_flow(c, world):
    h = world["h"]
    pm, ad = h["pm1"], h["admin"]
    dm = mk(c, h, "DECISION_MAKER", "dmx")
    assert c.put("/admin/settings/intake_required", headers=ad, json={"value": 1}).status_code == 200
    assert c.post("/projects", headers=pm, json={"number": "NOPE-1", "name": "x"}).status_code == 403
    body = {"number": "PRO-1", "name": "New portal", "business_case": "Citizens need online services fast.", "est_cost": 500000,
            "strategic_fit": 5, "value": 4, "urgency": 3, "risk_level": 2, "sponsor": "Deputy Minister"}
    x = c.post("/proposals", headers=pm, json=body)
    assert x.status_code == 201, x.text
    x = x.json()
    assert 0 < x["score"] <= 100
    low = c.post("/proposals", headers=pm, json={**body, "number": "PRO-2", "strategic_fit": 1, "value": 1}).json()
    rows = c.get("/proposals", headers=dm).json()
    assert rows[0]["id"] == x["id"] and rows[0]["rank"] == 1
    assert c.post("/proposals", headers=pm, json=body).status_code == 409
    # decision rules
    assert c.post(f"/proposals/{x['id']}/decision", headers=pm, json={"outcome": "approve"}).status_code == 403
    assert c.post(f"/proposals/{x['id']}/decision", headers=dm, json={"outcome": "reject"}).status_code == 422
    assert c.post(f"/proposals/{x['id']}/decision", headers=dm, json={"outcome": "approve_conditions", "rationale": "ok"}).status_code == 422
    r = c.post(f"/proposals/{x['id']}/decision", headers=dm, json={"outcome": "request_info", "rationale": "Need cost breakdown"}).json()
    assert r["status"] == "info_requested"
    assert c.post(f"/proposals/{x['id']}/decision", headers=dm, json={"outcome": "approve"}).status_code == 409
    r = c.patch(f"/proposals/{x['id']}", headers=pm, json={"response": "Breakdown attached", "est_cost": 450000}).json()
    assert r["status"] == "submitted" and "Breakdown" in r["business_case"]
    r = c.post(f"/proposals/{x['id']}/decision", headers=dm, json={"outcome": "approve_conditions", "rationale": "Good fit", "conditions": "Phase 1 only"}).json()
    assert r["status"] == "approved_conditions" and r["project_id"]
    p = c.get(f"/projects/{r['project_id']}", headers=pm).json()
    assert p["state"] == "planning" and p["budget_ceiling"] == 450000 and "Phase 1 only" in p["scope_statement"]
    assert c.post(f"/proposals/{low['id']}/decision", headers=dm, json={"outcome": "reject", "rationale": "Low value"}).json()["status"] == "rejected"
    log = c.get("/decision-log?entity=proposal", headers=dm).json()
    assert len(log) == 3 and log[0]["outcome"] == "reject"
    q = c.get("/dashboards/decisions", headers=dm).json()
    assert q["proposals"] == []


def test_stage_gate(c, world):
    h = world["h"]
    pm, ad, pmo = h["pm1"], h["admin"], h["pmo1"]
    pid = c.post("/projects", headers=pm, json={"number": "GATE-1", "name": "Gate test", "planned_start": str(TODAY), "planned_end": str(TODAY.replace(year=TODAY.year + 1))}).json()["id"]
    c.post(f"/projects/{pid}/activities", headers=pm, json={"code": "A1", "name": "Build", "planned_hours": 100, "baseline_cost": 1000, "planned_start": str(TODAY), "planned_end": str(TODAY.replace(year=TODAY.year + 1))})
    assert c.put("/admin/settings/stage_gates", headers=ad, json={"value": 1}).status_code == 200
    assert c.post(f"/projects/{pid}/baseline/lock", headers=pm).status_code == 409
    g = c.get(f"/projects/{pid}/gates", headers=pm).json()
    assert g["required"] and g["next_gate"] == "planning_execution" and not all(x["ok"] for x in g["preview"])
    gid = c.post(f"/projects/{pid}/gates", headers=pm, json={"note": "Ready"}).json()["id"]
    assert c.post(f"/projects/{pid}/gates", headers=pm, json={}).status_code == 409
    assert c.post(f"/projects/{pid}/gates/{gid}/decision", headers=pmo, json={"outcome": "approve"}).status_code == 422
    assert c.get("/dashboards/decisions", headers=pmo).json()["gates"][0]["id"] == gid
    r = c.post(f"/projects/{pid}/gates/{gid}/decision", headers=pmo, json={"outcome": "approve_conditions", "rationale": "Small project", "conditions": "Add risks in week 1"})
    assert r.status_code == 200 and r.json()["status"] == "approved_conditions"
    assert c.post(f"/projects/{pid}/baseline/lock", headers=pm).status_code == 200
    assert c.post(f"/projects/{pid}/transition", headers=pm, json={"to_state": "closing"}).status_code == 409
    assert c.get(f"/decision-log?project_id={pid}", headers=pm).json()[0]["conditions"] == "Add risks in week 1"


def test_change_outcomes(c, world):
    h, pid = world["h"], world["pid"]
    pm, ccb = h["pm1"], h["ccb1"]
    cid = c.post(f"/projects/{pid}/changes", headers=pm, json={"change_type": "scope", "description": "Add module", "impact_hours_delta": 10}).json()["id"]
    assert c.post(f"/projects/{pid}/changes/{cid}/decision", headers=ccb, json={"outcome": "defer"}).status_code == 422
    r = c.post(f"/projects/{pid}/changes/{cid}/decision", headers=ccb, json={"outcome": "request_info", "reason": "Which module?"}).json()
    assert r["status"] == "info_requested"
    assert c.post(f"/projects/{pid}/changes/{cid}/resubmit", headers=pm, json={"note": "The reporting module"}).json()["status"] == "requested"
    r = c.post(f"/projects/{pid}/changes/{cid}/decision", headers=ccb, json={"outcome": "approve_conditions", "reason": "Fine", "conditions": "Within budget"}).json()
    assert r["status"] == "approved"
    assert c.post(f"/projects/{pid}/changes/{cid}/decision", headers=ccb, json={"approve": True}).status_code == 409
    assert any(x["entity"] == "change" for x in c.get(f"/decision-log?project_id={pid}", headers=pm).json())
