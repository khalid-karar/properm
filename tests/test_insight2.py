from datetime import timedelta

from app import rules
from tests.test_flow import TODAY, app, c, world  # noqa: F401


def test_search_pack_calendar_upcoming_whatif(c, world):
    w, h, pid = world, world["h"], world["pid"]
    pm, pmo, s1 = h["pm1"], h["pmo1"], h["s1"]
    c.post(f"/projects/{pid}/risks", headers=pm, json={"title": "Vendor insolvency", "probability": 2, "impact": 5})
    r = c.get("/search?q=vendor", headers=pm).json()
    assert r["risks"] and r["risks"][0]["link"] == f"#/projects/{pid}"
    assert c.get("/search?q=alpha", headers=s1).json()["projects"]          # s1 is assigned
    assert "proposals" not in c.get("/search?q=alpha", headers=s1).json()
    assert c.get("/search?q=a", headers=pm).status_code == 422
    html = c.get("/reports/board-pack.html", headers=pmo)
    assert html.status_code == 200 and "Steering committee pack" in html.text and "P-001" in html.text
    assert c.get("/reports/board-pack.html", headers=pm).status_code == 403
    cal = c.get("/me/calendar", headers=pm).json()
    assert any(x["kind"] == "weekly_report" for x in cal)
    assert any(x["kind"] == "timesheet_week" for x in c.get("/me/calendar", headers=s1).json())
    nxt = rules.week_start(TODAY, True) + timedelta(days=7)
    c.put(f"/projects/{pid}/allocations", headers=pm, json={"user_id": w["ids"]["s1"], "week_of": str(nxt), "hours": 50})
    up = c.get("/me/upcoming", headers=s1).json()
    assert up["projects"][0]["hours"][1] == 50
    wi = c.post("/portfolio/what-if", headers=pmo, json={"changes": [{"project_id": pid, "action": "stop"}]}).json()
    assert wi["before"]["over_allocated_weeks"] >= 1 and wi["after"]["over_allocated_weeks"] == 0 and wi["effects"][0]["hours_freed"] == 50
    wi = c.post("/portfolio/what-if", headers=pmo, json={"changes": [{"project_id": pid, "action": "delay", "weeks": 2}]}).json()
    assert wi["effects"][0]["new_end"] and wi["after"]["weeks"][3]["demand"] == 50
    assert c.post("/portfolio/what-if", headers=pm, json={"changes": [{"project_id": pid, "action": "stop"}]}).status_code == 403
