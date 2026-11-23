from datetime import timedelta

from tests.test_flow import TODAY, app, c, world  # noqa: F401
from tests.test_gates import mk


def test_objectives_and_coverage(c, world):
    h, pid = world["h"], world["pid"]
    pm, pmo, dm = h["pm1"], h["pmo1"], mk(c, h, "DECISION_MAKER", "dmy")
    assert c.post("/objectives", headers=pm, json={"code": "O1", "name": "x"}).status_code == 403
    o1 = c.post("/objectives", headers=pmo, json={"code": "O1", "name": "Digital government services", "horizon": "2030"}).json()
    o2 = c.post("/objectives", headers=dm, json={"code": "O2", "name": "Localise supply chain"}).json()
    assert c.post("/objectives", headers=pmo, json={"code": "O1", "name": "dup"}).status_code == 409
    assert c.put(f"/projects/{pid}/objectives", headers=pm, json={"objective_ids": [o1["id"], 9999]}).status_code == 422
    assert c.put(f"/projects/{pid}/objectives", headers=h["s1"], json={"objective_ids": [o1["id"]]}).status_code == 403
    assert c.put(f"/projects/{pid}/objectives", headers=pm, json={"objective_ids": [o1["id"]]}).json()["selected"] == [o1["id"]]
    cov = c.get("/objectives/coverage", headers=pmo).json()
    assert cov["uncovered"] == [o2["id"]]
    assert next(o for o in cov["objectives"] if o["id"] == o1["id"])["projects"][0]["id"] == pid
    assert c.get("/objectives/coverage", headers=h["s1"]).status_code == 403
    # a proposal supports the second objective
    pr = c.post("/proposals", headers=pm, json={"number": "PROP-L1", "name": "Local sourcing portal", "business_case": "Cut import dependence", "strategic_fit": 4, "value": 4, "urgency": 3, "risk_level": 2}).json()
    assert c.put(f"/proposals/{pr['id']}/objectives", headers=pm, json={"objective_ids": [o2["id"]]}).status_code == 200
    cov = c.get("/objectives/coverage", headers=pmo).json()
    assert cov["uncovered"] == [] and next(o for o in cov["objectives"] if o["id"] == o2["id"])["proposals"]
    c.patch(f"/objectives/{o2['id']}", headers=pmo, json={"active": False})
    assert [o["code"] for o in c.get("/objectives", headers=pm).json()] == ["O1"]


def test_compliance(c, world):
    h, pid = world["h"], world["pid"]
    pm, pmo, dm, s1 = h["pm1"], h["pmo1"], mk(c, h, "DECISION_MAKER", "dmz"), h["s1"]
    assert c.post("/compliance-library", headers=pm, json={"code": "PDPL-1", "framework": "PDPL", "title": "Lawful basis recorded"}).status_code == 403
    r1 = c.post("/compliance-library", headers=pmo, json={"code": "PDPL-1", "framework": "PDPL", "title": "Lawful basis recorded"}).json()
    c.post("/compliance-library", headers=pmo, json={"code": "PDPL-2", "framework": "PDPL", "title": "Data subject requests process"})
    c.post("/compliance-library", headers=pmo, json={"code": "ECC-1", "framework": "NCA-ECC", "title": "Access control"})
    assert c.post(f"/projects/{pid}/compliance/apply-framework", headers=pm, json={"framework": "NOPE"}).status_code == 404
    assert c.post(f"/projects/{pid}/compliance/apply-framework", headers=pm, json={"framework": "PDPL"}).json()["added"] == 2
    assert c.post(f"/projects/{pid}/compliance/apply-framework", headers=pm, json={"framework": "PDPL"}).json()["added"] == 0
    rows = c.get(f"/projects/{pid}/compliance", headers=pm).json()
    assert [x["code"] for x in rows] == ["PDPL-1", "PDPL-2"]
    assert c.post(f"/projects/{pid}/compliance", headers=pm, json={"requirement_id": r1["id"]}).status_code == 409
    a = rows[0]["id"]
    assert c.patch(f"/projects/{pid}/compliance/{a}", headers=pm, json={"status": "compliant"}).status_code == 422
    done = c.patch(f"/projects/{pid}/compliance/{a}", headers=pm, json={"status": "compliant", "evidence": "DPIA v2 signed 12 May"}).json()
    assert done["status"] == "compliant" and done["reviewed_on"] == str(TODAY)
    c.patch(f"/projects/{pid}/compliance/{rows[1]['id']}", headers=pm, json={"status": "in_progress", "due_date": str(TODAY - timedelta(days=2))})
    assert c.patch(f"/projects/{pid}/compliance/{a}", headers=s1, json={"status": "in_progress"}).status_code == 403
    ov = c.get("/compliance/overview", headers=dm).json()
    f = ov["frameworks"][0]
    assert f["framework"] == "PDPL" and f["compliant"] == 1 and f["open"] == 1 and f["overdue"] == 1
    assert ov["projects"][0]["pct"] == 50
    assert c.get("/compliance/overview", headers=pm).status_code == 403
