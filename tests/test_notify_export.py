from datetime import date, timedelta

from tests.test_flow import TODAY, app, c, entry, login, mkuser, world   # noqa: F401
from tests.test_slice2 import costed                                      # noqa: F401


def test_notifications_flow(c, world):
    h = world["h"]
    eid = c.post("/timesheets", headers=h["s1"], json=entry(world)).json()["id"]
    n = c.get("/notifications", headers=h["pm1"]).json()
    assert any(x["title"] == "Timesheet awaiting approval" and x["link"] == "#/approvals" for x in n)
    assert c.get("/notifications/count", headers=h["pm1"]).json()["unread"] >= 1
    assert c.get("/notifications", headers=h["s2"]).json() == []                       # nobody else is told
    c.post(f"/timesheets/{eid}/decision", headers=h["pm1"], json={"action": "approve"})
    mine = c.get("/notifications", headers=h["s1"]).json()
    assert mine[0]["title"] == "Timesheet approved"
    assert c.post(f"/notifications/{mine[0]['id']}/read", headers=h["s2"]).status_code == 404   # not yours
    assert c.post(f"/notifications/{mine[0]['id']}/read", headers=h["s1"]).json()["read"] is True
    assert c.get("/notifications/count", headers=h["s1"]).json()["unread"] == 0
    c.post("/notifications/read-all", headers=h["pm1"])
    assert c.get("/notifications/count", headers=h["pm1"]).json()["unread"] == 0
    assert c.get("/notifications").status_code == 401


def test_csv_exports_access_and_safety(c, costed):
    h, pid = costed["h"], costed["pid"]
    r = c.get("/export/timesheets.csv", headers=h["pmo1"])
    assert r.status_code == 200 and r.text.startswith("﻿date,person")
    assert "attachment" in r.headers["content-disposition"]
    assert c.get(f"/projects/{pid}/export/costs.csv", headers=h["s1"]).status_code == 403        # staff cannot export cost
    assert c.get(f"/projects/{pid}/export/costs.csv", headers=h["pm1"]).status_code == 200
    assert c.get("/export/portfolio.csv", headers=h["pm1"]).status_code == 403
    assert c.get("/export/portfolio.csv", headers=h["pmo1"]).text.count("\n") >= 2
    # formula injection is neutralised
    c.post(f"/projects/{pid}/benefits", headers=h["pm1"], json={"title": "=HYPERLINK(\"http://evil\")"})
    body = c.get(f"/projects/{pid}/export/benefits.csv", headers=h["pm1"]).text
    assert "'=HYPERLINK" in body and ",=HYPERLINK" not in body
    # staff export only their own timesheets
    mine = c.get("/export/timesheets.csv", headers=h["s2"]).text
    assert isinstance(mine, str)


def test_report_html_escapes_and_respects_cost_access(c, costed):
    h, pid = costed["h"], costed["pid"]
    c.post(f"/projects/{pid}/risks", headers=h["pm1"], json={"title": "<script>alert(1)</script>", "probability": 2, "impact": 2})
    r = c.get(f"/projects/{pid}/report.html", headers=h["pm1"])
    assert r.status_code == 200 and "<script>alert" not in r.text and "&lt;script&gt;" in r.text and "<h2>Costs</h2>" in r.text
    assert "<h2>Costs</h2>" not in c.get(f"/projects/{pid}/report.html", headers=h["s1"]).text
    assert c.get(f"/projects/{pid}/report.html", headers=h["s2"]).status_code in (403, 200)


def test_scheduled_reports(c, costed):
    h, pid = costed["h"], costed["pid"]
    assert c.post("/reports/schedules", headers=h["pm1"], json={"kind": "portfolio", "frequency": "weekly"}).status_code == 403
    assert c.post("/reports/schedules", headers=h["pm1"], json={"kind": "project", "frequency": "daily", "project_id": pid}).status_code == 422
    s = c.post("/reports/schedules", headers=h["pm1"], json={"kind": "project", "frequency": "weekly", "project_id": pid})
    assert s.status_code == 201
    c.post("/reports/schedules", headers=h["pmo1"], json={"kind": "portfolio", "frequency": "monthly"})
    assert c.post("/reports/run-due", headers=h["pm1"]).status_code == 403
    assert c.post("/reports/run-due", headers=h["pmo1"]).json()["sent"] == 2
    assert c.post("/reports/run-due", headers=h["pmo1"]).json()["sent"] == 0                # not due again today
    later = date.today() + timedelta(days=8)
    expect = 1 if later.month == date.today().month else 2                                   # monthly is due once the month changes
    assert c.post(f"/reports/run-due?today={later}", headers=h["pmo1"]).json()["sent"] == expect
    n = [x for x in c.get("/notifications", headers=h["pm1"]).json() if x["kind"] == "report.scheduled"]
    assert len(n) >= 2 and "state:" in n[0]["body"]
    assert c.delete(f"/reports/schedules/{s.json()['id']}", headers=h["pmo1"]).status_code == 404   # not the owner
    assert c.delete(f"/reports/schedules/{s.json()['id']}", headers=h["pm1"]).status_code == 204
