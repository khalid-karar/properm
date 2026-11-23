from datetime import date, timedelta

import pytest

from app.models import BaselineRate
from tests.test_flow import TODAY, app, c, login, mkuser, world, entry   # noqa: F401  (shared fixtures)


@pytest.fixture()
def costed(c, world):
    """A baselined project with two priced activities, one costed staff member and 50% of the window elapsed."""
    h, ids = world["h"], world["ids"]
    r = c.post("/admin/rates", headers=h["admin"], json={"grade": "G1", "hourly_rate": 250, "currency": "SAR", "effective_from": "2020-01-01"})
    assert r.status_code == 201, r.text
    ids["s3"] = mkuser(c, h["admin"], "s3", "STAFF", rate_grade="G1", line_manager_id=ids["pm"])
    h["s3"] = login(c, "s3")
    r = c.post("/projects", headers=h["pm1"], json={"number": "P-COST", "name": "Costed", "state": "planning",
        "planned_start": str(TODAY - timedelta(days=50)), "planned_end": str(TODAY + timedelta(days=50))})
    pid = r.json()["id"]
    c.post(f"/projects/{pid}/assignments", headers=h["pm1"], json={"user_id": ids["s3"]})
    a = c.post(f"/projects/{pid}/activities", headers=h["pm1"], json={"code": "A", "name": "A", "planned_hours": 100, "baseline_cost": 60000}).json()
    b = c.post(f"/projects/{pid}/activities", headers=h["pm1"], json={"code": "B", "name": "B", "planned_hours": 50, "baseline_cost": 40000}).json()
    assert c.post(f"/projects/{pid}/baseline/lock", headers=h["pm1"]).status_code == 200
    return {**world, "cpid": pid, "a": a["id"], "b": b["id"]}


def approved_hours(c, w, activity, day_offset, hours=8):
    h = w["h"]
    r = c.post("/timesheets", headers=h["s3"], json={"project_id": w["cpid"], "activity_id": activity,
                "entry_date": str(TODAY - timedelta(days=day_offset)), "hours": hours})
    assert r.status_code == 201, r.text
    assert c.post(f"/timesheets/{r.json()['id']}/decision", headers=h["pm1"], json={"action": "approve"}).status_code == 200


def progress(c, w, a_pct, b_pct, **kw):
    return c.put(f"/projects/{w['cpid']}/progress", headers=w["h"]["pm1"], json={"week_of": str(TODAY), "updates": [
        {"activity_id": w["a"], "pct_complete": a_pct, **kw}, {"activity_id": w["b"], "pct_complete": b_pct}]})


def test_evm_numbers(c, costed):
    h, pid = costed["h"], costed["cpid"]
    approved_hours(c, costed, costed["a"], 14)
    approved_hours(c, costed, costed["a"], 21)                      # 16h x 250 = 4000 labor
    assert progress(c, costed, 50, 25).status_code == 200            # EV = 30000 + 10000
    r = c.post(f"/projects/{pid}/costs", headers=h["pm1"], json={"category": "licences", "amount": 6000, "entry_date": str(TODAY)})
    assert r.status_code == 201 and r.json()["approval"] == "approved"
    e = c.get(f"/projects/{pid}/evm", headers=h["pm1"]).json()
    assert (e["BAC"], e["PV"], e["EV"], e["AC"]) == (100000, 50000, 40000, 10000)
    assert (e["AC_labor"], e["AC_nonlabor"]) == (4000, 6000)
    assert (e["CPI"], e["SPI"], e["EAC"], e["VAC"]) == (4.0, 0.8, 25000, 75000)
    assert (e["CV"], e["SV"], e["TCPI"]) == (30000, -10000, 0.667)


def test_evm_unavailable_without_baseline_cost(c, world):
    e = c.get(f"/projects/{world['pid']}/evm", headers=world["h"]["pm1"]).json()
    assert e["available"] is False


def test_cost_data_hidden_from_staff(c, costed):
    h, pid = costed["h"], costed["cpid"]
    assert c.get(f"/projects/{pid}/evm", headers=h["s3"]).status_code == 403
    assert c.get(f"/projects/{pid}/costs", headers=h["s3"]).status_code == 403
    acts = c.get(f"/projects/{pid}", headers=h["s3"]).json()["activities"]
    assert all("baseline_cost" not in a for a in acts)
    acts = c.get(f"/projects/{pid}", headers=h["pm1"]).json()["activities"]
    assert any(a.get("baseline_cost") == 60000 for a in acts)


def test_progress_rules(c, costed, world):
    assert progress(c, costed, 60, 30).status_code == 200
    # decrease in a later week needs a reason
    nxt = str(TODAY + timedelta(days=7))
    body = {"week_of": nxt, "updates": [{"activity_id": costed["a"], "pct_complete": 40}]}
    r = c.put(f"/projects/{costed['cpid']}/progress", headers=costed["h"]["pm1"], json=body)
    assert r.status_code == 422
    body["updates"][0]["reason"] = "rework after review"
    assert c.put(f"/projects/{costed['cpid']}/progress", headers=costed["h"]["pm1"], json=body).status_code == 200
    # staff cannot update progress; planning-state project is refused
    assert c.put(f"/projects/{costed['cpid']}/progress", headers=costed["h"]["s3"], json=body).status_code == 403
    r = c.post("/projects", headers=costed["h"]["pm1"], json={"number": "PL", "name": "Planning", "state": "planning"})
    assert c.put(f"/projects/{r.json()['id']}/progress", headers=costed["h"]["pm1"], json=body).status_code == 409


def test_stale_progress_flag(c, costed):
    rows = c.get(f"/projects/{costed['cpid']}/progress", headers=costed["h"]["pm1"]).json()
    assert all(r["stale"] for r in rows)                             # never updated
    progress(c, costed, 10, 10)
    rows = c.get(f"/projects/{costed['cpid']}/progress", headers=costed["h"]["pm1"]).json()
    assert not any(r["stale"] for r in rows)


def test_cost_ledger_threshold_and_committed(c, costed):
    h, pid = costed["h"], costed["cpid"]
    r = c.post(f"/projects/{pid}/costs", headers=h["pm1"], json={"category": "subcontract", "amount": 60000, "entry_date": str(TODAY)})
    assert r.json()["approval"] == "pending"                         # above 50,000: second approver needed
    cid = r.json()["id"]
    progress(c, costed, 50, 25)
    assert c.get(f"/projects/{pid}/evm", headers=h["pm1"]).json()["AC"] == 0           # pending is not counted
    assert c.post(f"/projects/{pid}/costs/{cid}/approve", headers=h["pm1"]).status_code == 403
    assert c.post(f"/projects/{pid}/costs/{cid}/approve", headers=h["pmo1"]).status_code == 200
    assert c.get(f"/projects/{pid}/evm", headers=h["pm1"]).json()["AC"] == 60000
    c.post(f"/projects/{pid}/costs", headers=h["pm1"], json={"category": "po", "amount": 5000, "entry_date": str(TODAY), "cost_status": "committed"})
    assert c.get(f"/projects/{pid}/evm", headers=h["pm1"]).json()["AC"] == 60000      # commitments are not actuals


def test_missing_rate_is_reported_not_hidden(c, costed):
    ids, h = costed["ids"], costed["h"]
    c.post(f"/projects/{costed['cpid']}/assignments", headers=h["pm1"], json={"user_id": ids["s1"]})
    r = c.post("/timesheets", headers=h["s1"], json={"project_id": costed["cpid"], "activity_id": costed["a"], "entry_date": str(TODAY), "hours": 4})
    c.post(f"/timesheets/{r.json()['id']}/decision", headers=h["pm1"], json={"action": "approve"})
    progress(c, costed, 10, 10)
    e = c.get(f"/projects/{costed['cpid']}/evm", headers=h["pm1"]).json()
    assert any("without a rate grade" in w for w in e["warnings"])


def test_allocation_over_capacity_warning_and_load(c, costed):
    h, ids = costed["h"], costed["ids"]
    r = c.put(f"/projects/{costed['cpid']}/allocations", headers=h["pm1"], json={"user_id": ids["s3"], "week_of": str(TODAY), "hours": 30})
    assert r.status_code == 200 and r.json()["warnings"] == []
    # second project pushes s3 over 40h
    r2 = c.post("/projects", headers=h["pm1"], json={"number": "P-2", "name": "Two", "state": "planning"})
    p2 = r2.json()["id"]
    c.post(f"/projects/{p2}/assignments", headers=h["pm1"], json={"user_id": ids["s3"]})
    r = c.put(f"/projects/{p2}/allocations", headers=h["pm1"], json={"user_id": ids["s3"], "week_of": str(TODAY), "hours": 20})
    assert r.json()["total_planned_that_week"] == 50 and "Over-allocated" in r.json()["warnings"][0]
    load = c.get(f"/allocations/load?week_of={TODAY}", headers=h["pmo1"]).json()["staff"]
    assert next(s for s in load if s["user_id"] == ids["s3"])["over_allocated"] is True
    # unassigned user is refused
    r = c.put(f"/projects/{costed['cpid']}/allocations", headers=h["pm1"], json={"user_id": ids["s2"], "week_of": str(TODAY), "hours": 5})
    assert r.status_code == 422
    assert c.get("/allocations/load", headers=h["s3"]).status_code == 403


def test_risk_occurred_creates_linked_issue(c, world):
    h, pid = world["h"], world["pid"]
    r = c.post(f"/projects/{pid}/risks", headers=h["pm1"], json={"title": "Vendor delay", "probability": 4, "impact": 4})
    assert r.json()["score"] == 16
    rid = r.json()["id"]
    r = c.patch(f"/projects/{pid}/risks/{rid}", headers=h["pm1"], json={"status": "occurred"})
    iid = r.json()["created_issue_id"]
    issues = c.get(f"/projects/{pid}/issues", headers=h["pm1"]).json()
    assert issues[0]["id"] == iid and issues[0]["linked_risk_id"] == rid and issues[0]["severity"] == "high"
    assert c.patch(f"/projects/{pid}/risks/{rid}", headers=h["pm1"], json={"status": "bogus"}).status_code == 422
    assert c.post(f"/projects/{pid}/risks", headers=h["s1"], json={"title": "x", "probability": 1, "impact": 1}).status_code == 403
    assert len(c.get(f"/projects/{pid}/risks", headers=h["s1"]).json()) == 1          # assigned staff can read


def test_issue_validation(c, world):
    h, pid = world["h"], world["pid"]
    assert c.post(f"/projects/{pid}/issues", headers=h["pm1"], json={"title": "t", "severity": "urgent"}).status_code == 422
    iid = c.post(f"/projects/{pid}/issues", headers=h["pm1"], json={"title": "t", "severity": "low"}).json()["id"]
    r = c.patch(f"/projects/{pid}/issues/{iid}", headers=h["pm1"], json={"status": "resolved"})
    assert r.status_code == 200 and r.json()["status"] == "resolved"


def test_weekly_report_requires_progress_then_snapshots(c, costed):
    h, pid = costed["h"], costed["cpid"]
    body = {"week_of": str(TODAY), "accomplishments": "done", "next_week": "more"}
    r = c.post(f"/projects/{pid}/reports/weekly", headers=h["pm1"], json=body)
    assert r.status_code == 409 and "Progress update missing" in r.json()["detail"]
    approved_hours(c, costed, costed["a"], 14)
    progress(c, costed, 50, 25)
    c.post(f"/projects/{pid}/risks", headers=h["pm1"], json={"title": "r", "probability": 2, "impact": 3})
    r = c.post(f"/projects/{pid}/reports/weekly", headers=h["pm1"], json=body)
    assert r.status_code == 201, r.text
    snap = r.json()["snapshot"]
    assert snap["open_risks"] == 1 and snap["top_risk_score"] == 6
    assert snap["overall_pct_complete"] == 41.7                      # hours-weighted: (100x50 + 50x25) / 150
    assert snap["evm"]["EV"] == 40000
    assert c.post(f"/projects/{pid}/reports/weekly", headers=h["pm1"], json=body).status_code == 409
    # assigned staff can read the report but not its cost figures
    rep = c.get(f"/projects/{pid}/reports/weekly", headers=h["s3"]).json()[0]
    assert "evm" not in rep["snapshot"] and rep["narrative"]["accomplishments"] == "done"
    assert "evm" in c.get(f"/projects/{pid}/reports/weekly", headers=h["pm1"]).json()[0]["snapshot"]


def test_pv_is_phased_per_activity_not_evenly(c, world):
    h = world["h"]
    pid = c.post("/projects", headers=h["pm1"], json={"number": "P-PV", "name": "PV", "state": "planning",
        "planned_start": str(TODAY - timedelta(days=50)), "planned_end": str(TODAY + timedelta(days=50))}).json()["id"]
    x = c.post(f"/projects/{pid}/activities", headers=h["pm1"], json={"code": "X", "name": "x", "planned_hours": 10, "baseline_cost": 100000,
               "planned_start": str(TODAY - timedelta(days=10)), "planned_end": str(TODAY + timedelta(days=10))}).json()["id"]
    y = c.post(f"/projects/{pid}/activities", headers=h["pm1"], json={"code": "Y", "name": "y", "planned_hours": 10, "baseline_cost": 100000,
               "planned_start": str(TODAY - timedelta(days=40)), "planned_end": str(TODAY - timedelta(days=20))}).json()["id"]
    c.post(f"/projects/{pid}/baseline/lock", headers=h["pm1"])
    c.put(f"/projects/{pid}/progress", headers=h["pm1"], json={"week_of": str(TODAY), "updates": [
        {"activity_id": x, "pct_complete": 50}, {"activity_id": y, "pct_complete": 100}]})
    e = c.get(f"/projects/{pid}/evm", headers=h["pm1"]).json()
    # X is half through its own window (50k planned), Y finished (100k planned). A linear spread of 200k over the
    # project window would have given 100k and misreported this project as ahead of schedule.
    assert (e["BAC"], e["PV"], e["EV"], e["SPI"]) == (200000, 150000, 150000, 1.0)
    assert not any("project window" in w for w in e["warnings"])


def test_pv_fallback_is_reported(c, costed):
    e = c.get(f"/projects/{costed['cpid']}/evm", headers=costed["h"]["pm1"]).json()
    assert any("project window" in w for w in e["warnings"])
    assert e["PV"] == 50000                                          # 100000 BAC, 50% of the project window


def test_activity_dates_validation(c, world):
    h = world["h"]
    pid = c.post("/projects", headers=h["pm1"], json={"number": "P-D", "name": "d", "state": "planning"}).json()["id"]
    base = {"code": "Z", "name": "z", "planned_hours": 1}
    assert c.post(f"/projects/{pid}/activities", headers=h["pm1"], json={**base, "planned_start": str(TODAY)}).status_code == 422
    assert c.post(f"/projects/{pid}/activities", headers=h["pm1"], json={**base, "planned_start": str(TODAY), "planned_end": str(TODAY - timedelta(days=1))}).status_code == 422


def test_rate_change_does_not_reprice_history(c, costed):
    h, pid = costed["h"], costed["cpid"]
    approved_hours(c, costed, costed["a"], 14)                       # 8h at 250 = 2000
    r = c.post("/admin/rates", headers=h["admin"], json={"grade": "G1", "hourly_rate": 400, "currency": "SAR",
                                                         "effective_from": str(TODAY - timedelta(days=7))})
    assert r.status_code == 201
    approved_hours(c, costed, costed["a"], 3)                        # 8h at 400 = 3200
    e = c.get(f"/projects/{pid}/evm", headers=h["pm1"]).json()
    assert e["AC_labor"] == 5200                                     # 2000 + 3200, not 6400 at the new rate


def test_rate_card_is_append_only_and_restricted(c, costed):
    h = costed["h"]
    for eff in ("2019-01-01", "2020-01-01"):                         # earlier than, or equal to, the latest rate
        r = c.post("/admin/rates", headers=h["admin"], json={"grade": "G1", "hourly_rate": 1, "effective_from": eff})
        assert r.status_code == 409
    assert c.post("/admin/rates", headers=h["pm1"], json={"grade": "G9", "hourly_rate": 1, "effective_from": "2020-01-01"}).status_code == 403
    assert c.get("/admin/rates", headers=h["s3"]).status_code == 403
    assert len(c.get("/admin/rates", headers=h["pmo1"]).json()) == 1


def test_missing_rate_in_effect_is_reported(c, costed):
    h = costed["h"]
    approved_hours(c, costed, costed["a"], 14)
    c.post("/admin/rates", headers=h["admin"], json={"grade": "G2", "hourly_rate": 100, "effective_from": str(TODAY + timedelta(days=5))})
    h2 = c.post("/users", headers=h["admin"], json={"staff_id": "s4", "full_name": "s4", "password": "password1", "role": "STAFF", "rate_grade": "G2"})
    sid = h2.json()["id"]
    c.post(f"/projects/{costed['cpid']}/assignments", headers=h["pm1"], json={"user_id": sid})
    r = c.post("/timesheets", headers=login(c, "s4"),
               json={"project_id": costed["cpid"], "activity_id": costed["a"], "entry_date": str(TODAY), "hours": 2})
    assert r.status_code == 201, r.text
    c.post(f"/timesheets/{r.json()['id']}/decision", headers=h["pm1"], json={"action": "approve"})
    e = c.get(f"/projects/{costed['cpid']}/evm", headers=h["pm1"]).json()
    assert any("No rate in effect" in w and "G2" in w for w in e["warnings"])


def test_baseline_locks_rate_snapshot(app, costed):
    with app.state.Session() as db:
        rows = db.query(BaselineRate).filter_by(project_id=costed["cpid"]).all()
    assert [(r.grade, r.hourly_rate, r.baseline_version) for r in rows] == [("G1", 250.0, 1)]
