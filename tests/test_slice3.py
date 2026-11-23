from datetime import timedelta

import pytest

from app.models import Outbox
from tests.test_flow import TODAY, app, c, login, mkuser, world, entry   # noqa: F401
from tests.test_slice2 import costed, progress                              # noqa: F401


def poor_performance(c, w):
    """EV 10,000 vs AC 40,000 (CPI 0.25) and PV 50,000 (SPI 0.2)."""
    h, pid = w["h"], w["cpid"]
    assert progress(c, w, 10, 10).status_code == 200
    r = c.post(f"/projects/{pid}/costs", headers=h["pm1"], json={"category": "licences", "amount": 40000, "entry_date": str(TODAY)})
    assert r.status_code == 201 and r.json()["approval"] == "approved"


def evaluate(c, w, **kw):
    r = c.post(f"/projects/{w['cpid']}/alerts/evaluate", headers=w["h"]["pm1"], **kw)
    assert r.status_code == 200, r.text
    return r.json()


def risk_alert(c, w):
    return next(a for a in alerts_of(c, w) if a["rule"] == "risk_score_high")


def alerts_of(c, w, **params):
    return c.get("/alerts", headers=w["h"]["pm1"], params={"project_id": w["cpid"], **params}).json()


def test_cost_and_schedule_alerts_and_red_status(c, costed):
    poor_performance(c, costed)
    assert evaluate(c, costed)["created"] >= 2
    rules = {a["rule"]: a for a in alerts_of(c, costed)}
    assert rules["cpi_low"]["severity"] == "critical" and "0.25" in rules["cpi_low"]["cause"]
    assert rules["spi_low"]["severity"] == "critical"
    d = c.get(f"/dashboards/project/{costed['cpid']}", headers=costed["h"]["pm1"]).json()
    assert d["rag"] == "RED" and d["evm"]["CPI"] == 0.25
    assert any("CPI" in r["cause"] for r in d["health_reasons"])


def test_healthy_project_is_green(c, costed):
    progress(c, costed, 60, 60)                                  # EV 60,000 vs PV 50,000, nothing spent
    evaluate(c, costed)
    assert alerts_of(c, costed) == []
    d = c.get(f"/dashboards/project/{costed['cpid']}", headers=costed["h"]["pm1"]).json()
    assert d["rag"] == "GREEN" and d["progress_pct"] == 60.0 and d["hours"]["planned"] == 150


def test_evaluation_is_deduplicated(c, costed):
    poor_performance(c, costed)
    first = evaluate(c, costed)
    second = evaluate(c, costed)
    assert first["created"] > 0 and second["created"] == 0 and second["updated"] == first["created"]
    assert len(alerts_of(c, costed)) == first["created"]


def test_thresholds_are_configurable(c, costed):
    poor_performance(c, costed)
    h = costed["h"]
    assert c.put("/admin/settings/cpi_warning", headers=h["pm1"], json={"value": 0.2}).status_code == 403
    c.put("/admin/settings/cpi_warning", headers=h["admin"], json={"value": 0.2})
    c.put("/admin/settings/cpi_critical", headers=h["admin"], json={"value": 0.1})
    evaluate(c, costed)
    assert "cpi_low" not in {a["rule"] for a in alerts_of(c, costed)}       # 0.25 is now above both thresholds
    assert "spi_low" in {a["rule"] for a in alerts_of(c, costed)}


def test_overdue_activity_alert_tiers(c, world):
    h = world["h"]
    pid = c.post("/projects", headers=h["pm1"], json={"number": "P-LATE", "name": "late", "state": "planning",
                 "planned_start": str(TODAY - timedelta(days=90)), "planned_end": str(TODAY + timedelta(days=30))}).json()["id"]
    for code, ago in (("MILD", 10), ("SEVERE", 25), ("FINE", 3)):
        c.post(f"/projects/{pid}/activities", headers=h["pm1"], json={"code": code, "name": code, "planned_hours": 10,
               "planned_start": str(TODAY - timedelta(days=60)), "planned_end": str(TODAY - timedelta(days=ago))})
    c.post(f"/projects/{pid}/baseline/lock", headers=h["pm1"])
    c.post(f"/projects/{pid}/alerts/evaluate", headers=h["pm1"])
    found = c.get("/alerts", headers=h["pm1"], params={"project_id": pid}).json()
    got = {a["cause"].split()[1]: a["severity"] for a in found if a["rule"] == "activity_overdue"}
    assert got == {"MILD": "warning", "SEVERE": "critical"}                  # 3 days late is within tolerance


def test_risk_and_issue_alerts(c, costed):
    h, pid = costed["h"], costed["cpid"]
    c.post(f"/projects/{pid}/risks", headers=h["pm1"], json={"title": "warn", "probability": 4, "impact": 4})     # 16
    c.post(f"/projects/{pid}/risks", headers=h["pm1"], json={"title": "crit", "probability": 5, "impact": 4})     # 20
    c.post(f"/projects/{pid}/risks", headers=h["pm1"], json={"title": "minor", "probability": 2, "impact": 2})    # 4
    c.post(f"/projects/{pid}/issues", headers=h["pm1"], json={"title": "outage", "severity": "critical"})
    evaluate(c, costed)
    by = {a["cause"]: a["severity"] for a in alerts_of(c, costed)}
    assert by["Risk 'warn' has score 16"] == "warning" and by["Risk 'crit' has score 20"] == "critical"
    assert not any("minor" in k for k in by) and by["Critical issue open: outage"] == "critical"


def test_triage_loop_end_to_end(c, costed, app):
    h, pid, ids = costed["h"], costed["cpid"], costed["ids"]
    rid = c.post(f"/projects/{pid}/risks", headers=h["pm1"], json={"title": "vendor", "probability": 4, "impact": 4}).json()["id"]
    evaluate(c, costed)
    a = risk_alert(c, costed)
    aid = a["id"]
    act = lambda who, **b: c.post(f"/alerts/{aid}/actions", headers=h[who], json=b)
    assert act("pm1", action="resolve").status_code == 409                    # nothing assigned yet
    assert act("pm1", action="acknowledge").json()["status"] == "acknowledged"
    assert act("pm1", action="assign", assignee_id=ids["pmo"]).status_code == 422          # due date missing
    r = act("pm1", action="assign", assignee_id=ids["pmo"], due_date=str(TODAY + timedelta(days=5)))
    assert r.json()["status"] == "assigned" and r.json()["assignee_id"] == ids["pmo"]
    assert act("pmo1", action="resolve").json()["status"] == "resolved"
    assert act("pmo1", action="verify").status_code == 403                     # assignee cannot verify own closure
    assert act("admin", action="verify").status_code == 409                    # condition still holds
    assert act("admin", action="reject_verification").status_code == 422      # reason required
    assert act("admin", action="reject_verification", note="risk still open").json()["status"] == "assigned"
    act("pmo1", action="resolve")
    c.post(f"/projects/{pid}/risks/{rid}/close", headers=h["pm1"], json={"what_happened": "It happened", "how_handled": "We fixed it", "outcome": "Resolved fully"})
    res = evaluate(c, costed)
    assert res["cleared"] == 1
    closed = act("admin", action="verify").json()
    assert closed["status"] == "closed" and closed["active"] is False
    hist = [x["action"] for x in c.get(f"/alerts/{aid}/history", headers=h["pm1"]).json()]
    assert hist == ["acknowledge", "assign", "resolve", "reject_verification", "resolve", "verify"]
    with app.state.Session() as db:
        events = {o.event for o in db.query(Outbox).all()}
    assert {"alert.raised", "action.assigned", "alert.closed"} <= events


def test_dismiss_needs_reason_and_cooldown_prevents_reraise(c, costed):
    h, pid = costed["h"], costed["cpid"]
    c.post(f"/projects/{pid}/risks", headers=h["pm1"], json={"title": "noisy", "probability": 4, "impact": 4})
    evaluate(c, costed)
    aid = risk_alert(c, costed)["id"]
    assert c.post(f"/alerts/{aid}/actions", headers=h["pm1"], json={"action": "dismiss"}).status_code == 422
    assert c.post(f"/alerts/{aid}/actions", headers=h["pm1"], json={"action": "dismiss", "note": "accepted risk"}).json()["status"] == "dismissed"
    assert evaluate(c, costed)["created"] == 0                                 # cooldown: not raised again


def test_escalate_raises_severity(c, costed):
    h, pid = costed["h"], costed["cpid"]
    c.post(f"/projects/{pid}/risks", headers=h["pm1"], json={"title": "r", "probability": 4, "impact": 4})
    evaluate(c, costed)
    a = risk_alert(c, costed)
    r = c.post(f"/alerts/{a['id']}/actions", headers=h["pm1"], json={"action": "escalate", "note": "sponsor attention"}).json()
    assert a["severity"] == "warning" and r["severity"] == "critical" and r["escalated"] is True


def test_alert_visibility_and_permissions(c, costed):
    h, pid = costed["h"], costed["cpid"]
    c.post(f"/projects/{pid}/risks", headers=h["pm1"], json={"title": "r", "probability": 4, "impact": 4})
    evaluate(c, costed)
    aid = risk_alert(c, costed)["id"]
    assert c.get("/alerts", headers=h["s1"]).json() == []                      # staff see none
    assert c.post(f"/alerts/{aid}/actions", headers=h["s1"], json={"action": "acknowledge"}).status_code == 404
    assert c.get("/alerts", headers=h["ccb1"]).json() == []                    # a PM of another project sees none
    assert len(c.get("/alerts", headers=h["pmo1"]).json()) >= 1
    assert c.post(f"/projects/{pid}/alerts/evaluate", headers=h["s1"]).status_code == 403
    assert c.post("/alerts/evaluate", headers=h["pm1"]).status_code == 403
    assert c.post("/alerts/evaluate", headers=h["pmo1"]).json()["projects"] >= 1


def test_portfolio_dashboard(c, costed):
    h, ids = costed["h"], costed["ids"]
    poor_performance(c, costed)
    c.post("/projects", headers=h["pm1"], json={"number": "BID", "name": "bid", "state": "tendering"})
    c.post("/alerts/evaluate", headers=h["pmo1"])
    mkuser(c, h["admin"], "dm1", "DECISION_MAKER")
    dm = login(c, "dm1")
    d = c.get("/dashboards/portfolio", headers=dm).json()
    assert d["rag_counts"]["RED"] == 1 and d["rag_counts"]["GREY"] >= 1
    assert d["projects"][0]["rag"] == "RED" and d["projects"][0]["cpi"] == 0.25
    assert d["projects"][0]["open_alerts"]["critical"] >= 2
    only_red = c.get("/dashboards/portfolio", headers=dm, params={"rag": "red"}).json()["projects"]
    assert [p["rag"] for p in only_red] == ["RED"]
    assert c.get("/dashboards/portfolio", headers=h["pm1"]).status_code == 403
    assert c.get("/dashboards/portfolio", headers=h["s1"]).status_code == 403
    assert c.get(f"/dashboards/project/{costed['cpid']}", headers=h["s3"]).status_code == 403
    assert c.get(f"/dashboards/project/{costed['cpid']}", headers=dm).status_code == 200
    tr = c.get("/dashboards/top-risks", headers=dm)
    assert tr.status_code == 200


def test_no_progress_against_a_running_plan_is_critical(c, costed):
    evaluate(c, costed)                                           # nothing reported, half the window gone
    rules = {a["rule"]: a["severity"] for a in alerts_of(c, costed)}
    assert rules["spi_low"] == "critical" and rules["progress_stale"] == "info"
