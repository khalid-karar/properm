from tests.test_flow import TODAY, app, c, entry, world  # noqa: F401


def test_lists_and_ai_admin(c, world):
    h = world["h"]
    pmo, pm, s1 = h["pmo1"], h["pm1"], h["s1"]
    # reading the lists is open to all; changing them is ADMIN only
    lists = c.get("/config/lists", headers=s1).json()
    assert {"nonproject_code", "risk_category", "kpi_template", "closure_item", "department"} == set(lists) and any(x["code"] == "LEAVE" for x in lists["nonproject_code"])
    assert c.put("/admin/lists/risk_category/Legal", json={"label": "Legal"}, headers=pmo).status_code == 403
    a = h["admin"]
    assert c.put("/admin/lists/risk_category/Legal", json={"label": "Legal"}, headers=a).status_code == 200
    assert any(x["code"] == "Legal" for x in c.get("/config/lists", headers=s1).json()["risk_category"])
    # non-project codes: custom code is usable in timesheets, LEAVE cannot be switched off, built-ins cannot be deleted
    assert c.put("/admin/lists/nonproject_code/ONCALL", json={"label": "On call"}, headers=a).status_code == 200
    assert c.get("/config/codes", headers=s1).json()["ONCALL"] == "On call"
    assert c.put("/admin/lists/nonproject_code/LEAVE", json={"label": "Leave", "active": False}, headers=a).status_code == 409
    assert c.delete("/admin/lists/nonproject_code/ADMIN", headers=a).status_code == 409
    assert c.put("/admin/lists/nonproject_code/TRAINING", json={"label": "Training", "active": False}, headers=a).status_code == 200
    assert "TRAINING" not in c.get("/config/codes", headers=s1).json()
    r = c.post("/timesheets", headers=s1, json={"code": "TRAINING", "entry_date": str(TODAY), "hours": 1})
    assert r.status_code == 422                                 # switched off -> rejected by the rule engine
    assert c.delete("/admin/lists/nonproject_code/ONCALL", headers=a).status_code == 204
    assert c.put("/admin/lists/nope/X", json={"label": "x"}, headers=a).status_code == 404
    assert c.put("/admin/lists/risk_category/bad%24code", json={"label": "x"}, headers=a).status_code == 422
    # custom closure item appears on closing projects
    assert c.put("/admin/lists/closure_item/legal_signoff", json={"label": "Legal sign-off obtained"}, headers=a).status_code == 200
    # AI administration
    st = c.get("/admin/ai", headers=pmo).json()
    assert st["mode"] == "stub" and st["enabled"] is True and "usage_30d" in st
    assert c.post("/admin/ai/test", headers=pmo).status_code == 403
    t = c.post("/admin/ai/test", headers=a).json()
    assert t["ok"] is True and "stub" in t["sample"]
    assert c.put("/admin/settings/ai_enabled", json={"value": 0}, headers=a).status_code == 200
    assert c.get("/ai/status", headers=pm).json()["enabled"] is False
    r = c.post("/ai/narrative", headers=pm, json={"project_id": world["pid"]})
    assert r.status_code == 403


def test_custom_closure_item(c, world):
    h, pid = world["h"], world["pid"]
    assert c.put("/admin/lists/closure_item/legal_signoff", json={"label": "Legal sign-off obtained"}, headers=h["admin"]).status_code == 200
    assert c.post(f"/projects/{pid}/transition", headers=h["pm1"], json={"to_state": "closing"}).status_code == 200
    items = c.get(f"/projects/{pid}/closure", headers=h["pm1"]).json()["items"]
    mine = next(i for i in items if i["key"] == "x:LEGAL_SIGNOFF")
    assert mine["label"] == "Legal sign-off obtained" and mine["satisfied"] is False and len(items) == 9
    assert c.put(f"/projects/{pid}/closure/x:LEGAL_SIGNOFF", headers=h["pm1"], json={"done": True}).status_code == 200
    assert c.put(f"/projects/{pid}/closure/x:NOPE", headers=h["pm1"], json={"done": True}).status_code == 404
    # switching it off removes it from the checklist
    assert c.put("/admin/lists/closure_item/LEGAL_SIGNOFF", json={"label": "Legal", "active": False}, headers=h["admin"]).status_code == 200
    assert len(c.get(f"/projects/{pid}/closure", headers=h["pm1"]).json()["items"]) == 8
