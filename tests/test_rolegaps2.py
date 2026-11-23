from tests.test_flow import TODAY, app, c, entry, world  # noqa: F401


def test_risk_issue_edit(c, world):
    w, h = world, world["h"]
    pm, pid = h["pm1"], w["pid"]
    r = c.post(f"/projects/{pid}/risks", headers=pm, json={"title": "R", "probability": 2, "impact": 2}).json()
    u = c.patch(f"/projects/{pid}/risks/{r['id']}", headers=pm, json={"title": "R2", "category": "technical", "owner_id": w["ids"]["s1"], "response": "mitigate"})
    assert u.status_code == 200 and u.json()["title"] == "R2" and u.json()["owner_id"] == w["ids"]["s1"]
    assert c.patch(f"/projects/{pid}/risks/{r['id']}", headers=pm, json={"owner_id": 99999}).status_code == 422
    i = c.post(f"/projects/{pid}/issues", headers=pm, json={"title": "I", "severity": "low"}).json()
    u = c.patch(f"/projects/{pid}/issues/{i['id']}", headers=pm, json={"title": "I2", "description": "d", "owner_id": w["ids"]["s1"]})
    assert u.status_code == 200 and u.json()["description"] == "d"


def test_admin_extras_and_program_manager(c, world):
    w, h = world, world["h"]
    ad, pmo = h["admin"], h["pmo1"]
    assert c.get("/admin/permissions", headers=h["s1"]).status_code == 403
    assert len(c.get("/admin/permissions", headers=ad).json()["matrix"]) > 5
    csv_text = "staff_id,full_name,role,job_title,email\nimp1,Imp One,STAFF,Analyst,imp1@x.com\nimp2,Imp Two,BOSS,,\nimp1,Dup,STAFF,,\n"
    r = c.post("/admin/users/import", headers=ad, json={"csv_text": csv_text})
    assert r.status_code == 200, r.text
    out = r.json()
    assert len(out["created"]) == 1 and out["created"][0]["password"] and len(out["errors"]) == 2
    assert c.post("/admin/users/import", headers=h["pm1"], json={"csv_text": csv_text}).status_code == 403
    assert c.post("/admin/users/import", headers=ad, json={"csv_text": "a,b\n1,2"}).status_code == 422
    # the imported user can log in with the generated password
    assert c.post("/auth/login", json={"staff_id": "imp1", "password": out["created"][0]["password"]}).status_code == 200
    # program manager: only own programs
    pm_id = c.post("/users", headers=ad, json={"staff_id": "pg1", "full_name": "Prog One", "password": "password123", "role": "PROGRAM_MANAGER"}).json()["id"]
    tok = c.post("/auth/login", json={"staff_id": "pg1", "password": "password123"}).json()["access_token"]
    pg = {"Authorization": f"Bearer {tok}"}
    mine = c.post("/programs", headers=pmo, json={"code": "PG-A", "name": "A", "manager_id": pm_id}).json()["id"]
    other = c.post("/programs", headers=pmo, json={"code": "PG-B", "name": "B"}).json()["id"]
    assert [g["id"] for g in c.get("/programs?mine=true", headers=pg).json()] == [mine]
    assert c.put(f"/projects/{w['pid']}/program", headers=pg, json={"program_id": mine}).status_code == 200
    assert c.put(f"/projects/{w['pid']}/program", headers=pg, json={"program_id": other}).status_code == 403
    assert c.patch(f"/programs/{other}", headers=pg, json={"description": "x"}).status_code == 403
    assert c.patch(f"/programs/{mine}", headers=pg, json={"description": "x"}).status_code == 200
    ru = c.get(f"/programs/{mine}/rollup", headers=pg).json()
    assert "risks" in ru and "benefits" in ru
    inv = c.get("/dashboards/investment", headers=pg).json()
    assert any(x["project_id"] == w["pid"] for x in inv)
    assert c.get("/dashboards/investment", headers=h["s1"]).status_code == 403
    assert "by_project" in (c.get("/allocations/load", headers=pmo).json()["staff"] or [{"by_project": []}])[0]
