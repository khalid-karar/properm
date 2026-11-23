from datetime import timedelta

from tests.test_flow import TODAY, app, c, world  # noqa: F401


def test_departments_mail_export_home(c, world):
    h, ids = world["h"], world["ids"]
    ad = h["admin"]
    assert c.patch(f"/users/{ids['s1']}", headers=ad, json={"department": "Anything"}).status_code == 200   # no list yet: free text
    assert c.put("/admin/lists/department/DEL", headers=ad, json={"label": "Delivery"}).status_code in (200, 201)
    assert c.patch(f"/users/{ids['s1']}", headers=ad, json={"department": "Anything"}).status_code == 422
    assert c.patch(f"/users/{ids['s1']}", headers=ad, json={"department": "Delivery"}).status_code == 200
    m = c.get("/admin/mail", headers=ad).json()
    assert m["source"] in ("none", "environment")
    m = c.put("/admin/mail", headers=ad, json={"host": "smtp.invalid", "port": 2525, "username": "u", "password": "secret-1", "from_addr": "pmo@example.sa"}).json()
    assert m["password_set"] and "password" not in m and m["source"] == "settings"
    assert c.put("/admin/mail", headers=ad, json={"host": "smtp.invalid", "port": 2525}).json()["password_set"]    # kept
    r = c.post("/admin/mail/test", headers=ad, json={"to": "x@example.sa"}).json()
    assert r["ok"] is False and r["error"]
    assert c.get("/admin/mail", headers=h["pmo1"]).status_code == 403
    ex = c.get("/admin/export", headers=ad).json()
    assert ex["counts"]["users"] >= 5 and "password_hash" not in ex["tables"]["users"][0]
    assert all("password" not in r for r in ex["tables"]["mail_config"])
    assert c.get("/admin/export", headers=h["pmo1"]).status_code == 403
    assert c.put("/me/home", headers=h["pm1"], json={"page": "portfolio"}).status_code == 200
    assert c.get("/me", headers=h["pm1"]).json()["home_page"] == "portfolio"


def test_program_issues_budget_benefits(c, world):
    h, pid = world["h"], world["pid"]
    pmo, pm = h["pmo1"], h["pm1"]
    g = c.post("/programs", headers=pmo, json={"code": "PB-1", "name": "Budget"}).json()["id"]
    c.put(f"/projects/{pid}/program", headers=pmo, json={"program_id": g})
    i = c.post(f"/programs/{g}/issues", headers=pmo, json={"title": "Shared test environment down", "severity": "high", "due_date": str(TODAY - timedelta(days=1))}).json()
    assert i["overdue"]
    assert c.post(f"/programs/{g}/issues", headers=pmo, json={"title": "x", "severity": "huge"}).status_code == 422
    assert c.patch(f"/programs/{g}/issues/{i['id']}", headers=pmo, json={"status": "resolved"}).json()["status"] == "resolved"
    assert c.put(f"/programs/{g}/budget", headers=pm, json={"envelope": 1}).status_code == 403
    b = c.put(f"/programs/{g}/budget", headers=pmo, json={"envelope": 1000000, "currency": "SAR"}).json()
    assert b["envelope"] == 1000000 and b["headroom"] is not None
    c.post(f"/projects/{pid}/benefits", headers=pm, json={"title": "Faster close", "metric": "days", "baseline": 10, "target": 5, "due_date": str(TODAY + timedelta(days=100))})
    bp = c.get(f"/programs/{g}/benefits-plan", headers=pmo).json()
    assert bp["benefits"][0]["quarter"].count("Q") == 1 and bp["no_owner"] == 1
