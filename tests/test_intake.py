import base64

from tests.test_flow import TODAY, app, c, entry, login, mkuser, world   # noqa: F401


def newp(c, h, number="IN-1", **kw):
    r = c.post("/projects", headers=h["pm1"], json={"number": number, "name": "Intake", "state": "planning", **kw})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_intake_fields_and_edit_rules(c, world):
    h = world["h"]
    pid = newp(c, h, client="MoH", sponsor="Dr Ali", scope_statement="Build X", budget_ceiling=1000)
    got = c.get(f"/projects/{pid}", headers=h["pm1"]).json()
    assert (got["client"], got["sponsor"], got["scope_statement"]) == ("MoH", "Dr Ali", "Build X")
    r = c.patch(f"/projects/{pid}", headers=h["pm1"], json={"name": "Renamed", "planned_start": "2027-01-01", "planned_end": "2027-06-01", "budget_ceiling": 5000})
    assert r.status_code == 200 and r.json()["name"] == "Renamed" and r.json()["budget_ceiling"] == 5000
    assert c.patch(f"/projects/{pid}", headers=h["pm1"], json={"planned_end": "2026-01-01"}).status_code == 422
    assert c.patch(f"/projects/{pid}", headers=h["pm1"], json={"project_type": "waterfall"}).status_code == 422
    assert c.patch(f"/projects/{pid}", headers=h["s1"], json={"name": "x"}).status_code == 403
    assert c.patch(f"/projects/{pid}", headers=h["pm2"] if "pm2" in h else h["s2"], json={"name": "x"}).status_code in (403, 404)
    # after the baseline, dates and budget need change control but the name is still editable
    wp = world["pid"]
    assert c.patch(f"/projects/{wp}", headers=h["pm1"], json={"budget_ceiling": 1}).status_code == 409
    assert c.patch(f"/projects/{wp}", headers=h["pm1"], json={"client": "New client"}).status_code == 200


def test_manager_reassignment(c, world):
    h = world["h"]
    pid = newp(c, h, "IN-2")
    assert c.put(f"/projects/{pid}/manager", headers=h["pm1"], json={"user_id": world["ids"]["pmo"]}).status_code == 403
    assert c.put(f"/projects/{pid}/manager", headers=h["pmo1"], json={"user_id": world["ids"]["s1"]}).status_code == 422   # staff cannot manage
    r = c.put(f"/projects/{pid}/manager", headers=h["pmo1"], json={"user_id": world["ids"]["pmo"]})
    assert r.status_code == 200 and r.json()["pm_id"] == world["ids"]["pmo"]
    assert any(n["title"] == "You are now the project manager" for n in c.get("/notifications", headers=h["pmo1"]).json())


def test_documents(c, world):
    h = world["h"]
    pid = newp(c, h, "IN-3")
    good = base64.b64encode(b"%PDF-1.4 hello").decode()
    r = c.post(f"/projects/{pid}/documents", headers=h["pm1"], json={"kind": "contract", "filename": "../../etc/contract.pdf", "content_b64": good})
    assert r.status_code == 201 and r.json()["filename"] == "contract.pdf"                  # path stripped
    assert c.post(f"/projects/{pid}/documents", headers=h["pm1"], json={"kind": "contract", "filename": "a.exe", "content_b64": good}).status_code == 422
    assert c.post(f"/projects/{pid}/documents", headers=h["pm1"], json={"kind": "contract", "filename": "a.pdf", "content_b64": "!!notb64"}).status_code == 422
    big = base64.b64encode(b"x" * (3 * 1024 * 1024 + 1)).decode()
    assert c.post(f"/projects/{pid}/documents", headers=h["pm1"], json={"kind": "other", "filename": "b.pdf", "content_b64": big}).status_code == 422
    assert c.post(f"/projects/{pid}/documents", headers=h["pm1"], json={"kind": "bogus", "filename": "a.pdf", "content_b64": good}).status_code == 422
    d = c.get(f"/projects/{pid}/documents/{r.json()['id']}/download", headers=h["pm1"])
    assert d.content == b"%PDF-1.4 hello" and "attachment" in d.headers["content-disposition"] and d.headers["content-type"] == "application/octet-stream"
    assert c.get(f"/projects/{pid}/documents/{r.json()['id']}/download", headers=h["s1"]).status_code in (403, 404)   # not on the project
    assert c.delete(f"/projects/{pid}/documents/{r.json()['id']}", headers=h["pm1"]).status_code == 204


def test_stakeholders_activity_edit_and_unassign(c, world):
    h = world["h"]
    pid = newp(c, h, "IN-4")
    s = c.post(f"/projects/{pid}/stakeholders", headers=h["pm1"], json={"name": "Ministry", "power": 5, "interest": 4})
    assert s.status_code == 201
    assert c.post(f"/projects/{pid}/stakeholders", headers=h["pm1"], json={"name": "x", "power": 9}).status_code == 422
    assert len(c.get(f"/projects/{pid}/stakeholders", headers=h["pm1"]).json()) == 1
    assert c.delete(f"/projects/{pid}/stakeholders/{s.json()['id']}", headers=h["pm1"]).status_code == 204
    a = c.post(f"/projects/{pid}/activities", headers=h["pm1"], json={"code": "X1", "name": "One", "planned_hours": 10}).json()
    r = c.patch(f"/projects/{pid}/activities/{a['id']}", headers=h["pm1"], json={"name": "Uno", "planned_hours": 20})
    assert r.status_code == 200 and (r.json()["name"], r.json()["planned_hours"]) == ("Uno", 20)
    assert c.delete(f"/projects/{pid}/activities/{a['id']}", headers=h["pm1"]).status_code == 204
    assert c.patch(f"/projects/{world['pid']}/activities/{world['aid']}", headers=h["pm1"], json={"name": "z"}).status_code in (404, 409)   # locked baseline
    c.post(f"/projects/{pid}/assignments", headers=h["pm1"], json={"user_id": world["ids"]["s1"]})
    assert c.delete(f"/projects/{pid}/assignments/{world['ids']['s1']}", headers=h["pm1"]).status_code == 204
    assert c.delete(f"/projects/{pid}/assignments/{world['ids']['s1']}", headers=h["pm1"]).status_code == 404
    pm_id = c.get(f"/projects/{pid}", headers=h["pm1"]).json()["pm_id"]
    assert c.delete(f"/projects/{pid}/assignments/{pm_id}", headers=h["pm1"]).status_code == 409
