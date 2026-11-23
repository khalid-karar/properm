from datetime import timedelta

from tests.test_flow import TODAY, app, c, world  # noqa: F401


def test_charter_and_assumptions(c, world):
    h, pid = world["h"], world["pid"]
    pm, pmo, s1 = h["pm1"], h["pmo1"], h["s1"]
    assert c.get(f"/projects/{pid}/charter", headers=pm).json()["status"] == "draft"
    assert c.put(f"/projects/{pid}/charter", headers=s1, json={"purpose": "x"}).status_code == 403
    r = c.put(f"/projects/{pid}/charter", headers=pm, json={"purpose": "Modernise ERP", "objectives": "Cut close time"}).json()
    assert r["complete"] is False
    assert c.post(f"/projects/{pid}/charter/decision", headers=pmo, json={"action": "approve"}).status_code == 409
    c.put(f"/projects/{pid}/charter", headers=pm, json={"purpose": "Modernise ERP", "objectives": "Cut close time", "success_criteria": "Close in 3 days", "in_scope": "Finance modules"})
    assert c.post(f"/projects/{pid}/charter/decision", headers=pm, json={"action": "approve"}).status_code == 403
    assert c.post(f"/projects/{pid}/charter/decision", headers=pmo, json={"action": "approve"}).json()["status"] == "approved"
    assert c.put(f"/projects/{pid}/charter", headers=pm, json={"purpose": "y"}).status_code == 409
    assert c.post(f"/projects/{pid}/charter/decision", headers=pm, json={"action": "reopen"}).json()["status"] == "draft"
    a = c.post(f"/projects/{pid}/assumptions", headers=pm, json={"text": "Vendor delivers by Q2", "validate_by": str(TODAY - timedelta(days=1))}).json()
    assert a["kind"] == "assumption" and a["status"] == "open"
    assert c.post(f"/projects/{pid}/assumptions", headers=pm, json={"text": "z", "kind": "wish"}).status_code == 422
    assert c.post(f"/projects/{pid}/assumptions", headers=s1, json={"text": "z"}).status_code == 403
    assert c.patch(f"/projects/{pid}/assumptions/{a['id']}", headers=pm, json={"status": "invalid"}).json()["status"] == "invalid"
    assert c.get(f"/projects/{pid}/scope-summary", headers=pm).json()["assumptions"]["invalid"] == 1
    assert c.delete(f"/projects/{pid}/assumptions/{a['id']}", headers=pm).status_code == 204


def test_wbs_acceptance_and_requirements(c, world):
    h, pid = world["h"], world["pid"]
    pm, pmo, s1 = h["pm1"], h["pmo1"], h["s1"]
    d = c.post(f"/projects/{pid}/wbs", headers=pm, json={"code": "1", "name": "Finance module", "acceptance_criteria": "UAT passed"}).json()
    wp = c.post(f"/projects/{pid}/wbs", headers=pm, json={"code": "1.1", "name": "Ledger", "kind": "work_package", "parent_id": d["id"]}).json()
    assert c.post(f"/projects/{pid}/wbs", headers=pm, json={"code": "1", "name": "dup"}).status_code == 409
    assert c.patch(f"/projects/{pid}/wbs/{d['id']}", headers=pm, json={"parent_id": wp["id"]}).status_code == 422     # cycle
    assert c.patch(f"/projects/{pid}/wbs/{d['id']}", headers=pm, json={"status": "accepted"}).json()["status"] == "planned"   # ignored
    req = c.post(f"/projects/{pid}/requirements", headers=pm, json={"code": "R1", "title": "Auto reconcile", "deliverable_id": d["id"]}).json()
    assert req["deliverable"].startswith("1 ")
    assert c.patch(f"/projects/{pid}/requirements/{req['id']}", headers=pm, json={"status": "verified"}).status_code == 422
    assert c.patch(f"/projects/{pid}/requirements/{req['id']}", headers=pm, json={"status": "verified", "test_ref": "UAT-12"}).json()["status"] == "verified"
    c.post(f"/projects/{pid}/requirements", headers=pm, json={"code": "R2", "title": "Orphan"})
    sm = c.get(f"/projects/{pid}/scope-summary", headers=pm).json()
    assert sm["requirements"]["without_deliverable"] == ["R2"] and sm["work_packages_without_activity"] == ["1.1"]
    # acceptance
    assert c.post(f"/projects/{pid}/wbs/{wp['id']}/submit", headers=pm).status_code == 409
    assert c.post(f"/projects/{pid}/wbs/{d['id']}/decision", headers=pmo, json={"accept": True}).status_code == 409   # not submitted
    assert c.post(f"/projects/{pid}/wbs/{d['id']}/submit", headers=pm).json()["status"] == "submitted"
    assert c.post(f"/projects/{pid}/wbs/{d['id']}/decision", headers=pm, json={"accept": True}).status_code == 403
    assert c.post(f"/projects/{pid}/wbs/{d['id']}/decision", headers=pmo, json={"accept": False}).status_code == 422
    assert c.post(f"/projects/{pid}/wbs/{d['id']}/decision", headers=pmo, json={"accept": False, "note": "Reports missing"}).json()["status"] == "rejected"
    c.post(f"/projects/{pid}/wbs/{d['id']}/submit", headers=pm)
    r = c.post(f"/projects/{pid}/wbs/{d['id']}/decision", headers=pmo, json={"accept": True, "note": "OK"}).json()
    assert r["status"] == "accepted" and r["decided_by_name"]
    assert c.get(f"/projects/{pid}/scope-summary", headers=pm).json()["deliverables"]["accepted_pct"] == 100
    assert c.get(f"/projects/{pid}/wbs", headers=s1).status_code in (200, 403)
