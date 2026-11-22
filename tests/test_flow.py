from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.deps import hash_pw
from app.main import create_app
from app.models import AuditLog, Outbox, User

TODAY = date.today()
WEEK = TODAY - timedelta(days=(TODAY.weekday() + 1) % 7)   # Sunday of this week


@pytest.fixture()
def app():
    app = create_app("sqlite:///:memory:")
    with app.state.Session() as db:
        db.add(User(staff_id="admin", full_name="Admin", role="ADMIN", password_hash=hash_pw("password1")))
        db.commit()
    return app


@pytest.fixture()
def c(app):
    return TestClient(app)


def login(c, sid, pw="password1"):
    r = c.post("/auth/login", json={"staff_id": sid, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def mkuser(c, admin, sid, role, **kw):
    r = c.post("/users", headers=admin, json={"staff_id": sid, "full_name": sid, "password": "password1", "role": role, **kw})
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture()
def world(c):
    admin = login(c, "admin")
    ids = {"pm": mkuser(c, admin, "pm1", "PM"), "pmo": mkuser(c, admin, "pmo1", "PMO"),
           "ccb": mkuser(c, admin, "ccb1", "PM", is_ccb=True)}
    ids["s1"] = mkuser(c, admin, "s1", "STAFF", line_manager_id=ids["pm"])
    ids["s2"] = mkuser(c, admin, "s2", "STAFF")
    h = {k: login(c, k) for k in ("pm1", "pmo1", "ccb1", "s1", "s2")}
    h["admin"] = admin
    # project in planning, baselined with one execution activity
    r = c.post("/projects", headers=h["pm1"], json={"number": "P-001", "name": "Alpha", "state": "planning",
        "planned_start": str(TODAY - timedelta(days=60)), "planned_end": str(TODAY + timedelta(days=60))})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    c.post(f"/projects/{pid}/assignments", headers=h["pm1"], json={"user_id": ids["s1"]})
    a = c.post(f"/projects/{pid}/activities", headers=h["pm1"], json={"code": "DEV", "name": "Development", "planned_hours": 100})
    assert a.status_code == 201, a.text
    r = c.post(f"/projects/{pid}/baseline/lock", headers=h["pm1"])
    assert r.status_code == 200, r.text
    return {"h": h, "ids": ids, "pid": pid, "aid": a.json()["id"]}


def entry(w, **kw):
    d = {"project_id": w["pid"], "activity_id": w["aid"], "entry_date": str(TODAY), "hours": 8}
    d.update(kw)
    return d


def test_auth_required_and_wrong_password(c):
    assert c.get("/projects").status_code == 401
    assert c.post("/auth/login", json={"staff_id": "admin", "password": "nope"}).status_code == 401


def test_only_admin_creates_users_and_cost_hidden_from_pm(c, world):
    h = world["h"]
    r = c.post("/users", headers=h["pm1"], json={"staff_id": "x", "full_name": "x", "password": "password1", "role": "STAFF"})
    assert r.status_code == 403
    assert "rate_grade" not in c.get("/users", headers=h["pm1"]).json()[0]
    assert "rate_grade" in c.get("/users", headers=h["pmo1"]).json()[0]


def test_baseline_lock_moves_state_and_locks_activities(c, world):
    p = c.get(f"/projects/{world['pid']}", headers=world["h"]["pm1"]).json()
    assert p["state"] == "execution" and p["baseline_version"] == 1
    assert all(a["locked"] for a in p["activities"])


def test_staff_visibility_is_row_level(c, world):
    h = world["h"]
    assert len(c.get("/projects", headers=h["s1"]).json()) == 1      # assigned
    assert c.get("/projects", headers=h["s2"]).json() == []          # not assigned
    assert c.get(f"/projects/{world['pid']}", headers=h["s2"]).status_code == 403


def test_timesheet_happy_path_and_approval(c, world):
    h = world["h"]
    r = c.post("/timesheets", headers=h["s1"], json=entry(world))
    assert r.status_code == 201, r.text
    eid = r.json()["id"]
    assert c.get("/timesheets/queue", headers=h["s1"]).json() == []            # cannot approve own
    q = c.get("/timesheets/queue", headers=h["pm1"]).json()
    assert [e["id"] for e in q] == [eid]
    assert c.post(f"/timesheets/{eid}/decision", headers=h["s1"], json={"action": "approve"}).status_code == 403
    r = c.post(f"/timesheets/{eid}/decision", headers=h["pm1"], json={"action": "approve"})
    assert r.status_code == 200 and r.json()["status"] == "approved"
    assert c.post(f"/timesheets/{eid}/decision", headers=h["pm1"], json={"action": "approve"}).status_code == 409


def test_unassigned_staff_blocked_r3(c, world):
    r = c.post("/timesheets", headers=world["h"]["s2"], json=entry(world))
    assert r.status_code == 422
    assert {v["rule"] for v in r.json()["violations"]} == {"R3"}


def test_future_date_blocked_r9(c, world):
    r = c.post("/timesheets", headers=world["h"]["s1"], json=entry(world, entry_date=str(TODAY + timedelta(days=2))))
    assert r.status_code == 422 and "R9" in {v["rule"] for v in r.json()["violations"]}


def test_exact_duplicate_blocked_but_split_day_allowed(c, world):
    h = world["h"]
    assert c.post("/timesheets", headers=h["s1"], json=entry(world, hours=3, description="a")).status_code == 201
    r = c.post("/timesheets", headers=h["s1"], json=entry(world, hours=3, description="a"))
    assert r.status_code == 422 and "R7" in {v["rule"] for v in r.json()["violations"]}
    assert c.post("/timesheets", headers=h["s1"], json=entry(world, hours=3, description="b")).status_code == 201


def test_overtime_flow(c, world):
    h = world["h"]
    past_sun = WEEK - timedelta(days=21)                      # a full past week: deterministic
    for i in range(5):                                        # 5 x 8h = 40h non-project time
        r = c.post("/timesheets", headers=h["s1"], json={"code": "ADMIN", "entry_date": str(past_sun + timedelta(days=i)), "hours": 8})
        assert r.status_code == 201, r.text
    day = str(past_sun + timedelta(days=1))
    over = entry(world, entry_date=day, hours=4)              # 44/40: inside the 125% ceiling
    r = c.post("/timesheets", headers=h["s1"], json=over)
    assert r.status_code == 422 and "Overtime reason" in r.json()["detail"]
    r = c.post("/timesheets", headers=h["s1"], json={**over, "overtime_reason": "release crunch"})
    assert r.status_code == 409                               # R1 is WARN: needs acknowledgment
    r = c.post("/timesheets", headers=h["s1"], json={**over, "overtime_reason": "release crunch", "acknowledge_warnings": True})
    assert r.status_code == 201 and r.json()["overtime_flag"] is True
    r = c.post("/timesheets", headers=h["s1"], json=entry(world, entry_date=day, hours=8, description="more"))
    assert r.status_code == 422 and {v["rule"] for v in r.json()["violations"]} >= {"R1"}   # 52 > 50 ceiling -> BLOCK


def test_period_lock_requires_no_pending_and_blocks_entries(c, world):
    h = world["h"]
    eid = c.post("/timesheets", headers=h["s1"], json=entry(world)).json()["id"]
    assert c.post("/periods/lock", headers=h["pmo1"], json={"locked_through": str(TODAY)}).status_code == 409
    c.post(f"/timesheets/{eid}/decision", headers=h["pm1"], json={"action": "approve"})
    assert c.post("/periods/lock", headers=h["pmo1"], json={"locked_through": str(TODAY)}).status_code == 200
    r = c.post("/timesheets", headers=h["s1"], json=entry(world, hours=1))
    assert r.status_code == 422 and "R8" in {v["rule"] for v in r.json()["violations"]}
    assert c.post("/periods/lock", headers=h["pm1"], json={"locked_through": str(TODAY)}).status_code == 403


def test_reject_needs_reason_and_resubmit_via_edit(c, world):
    h = world["h"]
    eid = c.post("/timesheets", headers=h["s1"], json=entry(world, hours=2)).json()["id"]
    assert c.post(f"/timesheets/{eid}/decision", headers=h["pm1"], json={"action": "reject"}).status_code == 422
    assert c.post(f"/timesheets/{eid}/decision", headers=h["pm1"], json={"action": "reject", "reason": "wrong activity"}).status_code == 200
    r = c.put(f"/timesheets/{eid}", headers=h["s1"], json=entry(world, hours=3))
    assert r.status_code == 201 and r.json()["status"] == "submitted"


def test_adjust_can_only_reduce(c, world):
    h = world["h"]
    eid = c.post("/timesheets", headers=h["s1"], json=entry(world, hours=4)).json()["id"]
    assert c.post(f"/timesheets/{eid}/decision", headers=h["pm1"], json={"action": "adjust", "hours": 6, "reason": "x"}).status_code == 422
    r = c.post(f"/timesheets/{eid}/decision", headers=h["pm1"], json={"action": "adjust", "hours": 3, "reason": "overstated"})
    assert r.json()["hours"] == 3 and r.json()["original_hours"] == 4


def test_nonproject_time_approved_by_line_manager(c, world):
    h = world["h"]
    eid = c.post("/timesheets", headers=h["s1"], json={"code": "TRAINING", "entry_date": str(TODAY), "hours": 2}).json()["id"]
    assert c.post(f"/timesheets/{eid}/decision", headers=h["ccb1"], json={"action": "approve"}).status_code == 403   # not the line manager
    assert c.post(f"/timesheets/{eid}/decision", headers=h["pm1"], json={"action": "approve"}).status_code == 200


def test_rule_severity_configurable_by_admin_only(c, world):
    h = world["h"]
    assert c.put("/admin/rules/R3", headers=h["pm1"], json={"severity": "WARN"}).status_code == 403
    assert c.put("/admin/rules/R3", headers=h["admin"], json={"severity": "WARN"}).status_code == 200
    r = c.post("/timesheets", headers=h["s2"], json=entry(world))
    assert r.status_code == 409                                    # now WARN: needs acknowledgment
    r = c.post("/timesheets", headers=h["s2"], json=entry(world, acknowledge_warnings=True))
    assert r.status_code == 201


def test_change_control_flow_and_activity_addition(c, world):
    h, pid = world["h"], world["pid"]
    assert c.post(f"/projects/{pid}/activities", headers=h["pm1"], json={"code": "NEW", "name": "n", "planned_hours": 10}).status_code == 409
    cid = c.post(f"/projects/{pid}/changes", headers=h["pm1"], json={"change_type": "scope", "description": "add", "impact_hours_delta": 10}).json()["id"]
    assert c.post(f"/projects/{pid}/changes/{cid}/decision", headers=h["pm1"], json={"approve": True}).status_code == 403   # not CCB
    r = c.post(f"/projects/{pid}/changes/{cid}/decision", headers=h["ccb1"], json={"approve": True})
    assert r.json() == {"id": cid, "status": "approved", "baseline_version": 2}
    r = c.post(f"/projects/{pid}/activities", headers=h["pm1"], json={"code": "NEW", "name": "n", "planned_hours": 10, "change_id": cid})
    assert r.status_code == 201 and r.json()["locked"] is True
    assert c.post(f"/projects/{pid}/activities", headers=h["pm1"], json={"code": "N2", "name": "n", "planned_hours": 1, "change_id": cid}).status_code == 409


def test_change_request_needs_impact(c, world):
    r = c.post(f"/projects/{world['pid']}/changes", headers=world["h"]["pm1"], json={"change_type": "scope", "description": "x"})
    assert r.status_code == 422


def test_lifecycle_closure_blocked_by_pending_timesheets(c, world):
    h, pid = world["h"], world["pid"]
    c.post("/timesheets", headers=h["s1"], json=entry(world))
    assert c.post(f"/projects/{pid}/transition", headers=h["pm1"], json={"to_state": "closing"}).status_code == 200
    assert c.post(f"/projects/{pid}/transition", headers=h["pm1"], json={"to_state": "archived"}).status_code == 403
    assert c.post(f"/projects/{pid}/transition", headers=h["pmo1"], json={"to_state": "archived"}).status_code == 409
    eid = c.get("/timesheets/queue", headers=h["pm1"]).json()[0]["id"]
    c.post(f"/timesheets/{eid}/decision", headers=h["pm1"], json={"action": "approve"})
    for it in c.get(f"/projects/{pid}/closure", headers=h["pm1"]).json()["items"]:
        if not it["auto"]:
            assert c.put(f"/projects/{pid}/closure/{it['key']}", headers=h["pm1"], json={"done": True}).status_code == 200
    assert c.post(f"/projects/{pid}/transition", headers=h["pmo1"], json={"to_state": "archived"}).status_code == 200
    r = c.post("/timesheets", headers=h["s1"], json=entry(world, hours=1))
    assert r.status_code == 422                                         # R4: archived


def test_tendering_time_uses_phase_activity(c, world):
    h = world["h"]
    r = c.post("/projects", headers=h["pm1"], json={"number": "B-1", "name": "Bid", "state": "tendering"})
    pid = r.json()["id"]
    c.post(f"/projects/{pid}/assignments", headers=h["pm1"], json={"user_id": world["ids"]["s1"]})
    acts = c.get(f"/projects/{pid}", headers=h["pm1"]).json()["activities"]
    bid = next(a for a in acts if a["code"] == "PRE-BID")
    r = c.post("/timesheets", headers=h["s1"], json={"project_id": pid, "activity_id": bid["id"], "entry_date": str(TODAY), "hours": 2})
    assert r.status_code == 201, r.text
    # planning activity is not valid while tendering (R4)
    plan = next(a for a in acts if a["code"] == "PLAN-GEN")
    r = c.post("/timesheets", headers=h["s1"], json={"project_id": pid, "activity_id": plan["id"], "entry_date": str(TODAY), "hours": 2})
    assert r.status_code == 422 and "R4" in {v["rule"] for v in r.json()["violations"]}


def test_audit_log_append_only_and_outbox_written(app, c, world):
    c.post("/timesheets", headers=world["h"]["s1"], json=entry(world))
    with app.state.Session() as db:
        assert db.query(AuditLog).count() > 0
        assert "timesheet.submitted" in {o.event for o in db.query(Outbox).all()}
        row = db.query(AuditLog).first()
        row.action = "tampered"
        with pytest.raises(RuntimeError):
            db.commit()


def test_anomaly_flag_after_repeated_blocks(c, world, app):
    h = world["h"]
    for _ in range(3):
        c.post("/timesheets", headers=h["s2"], json=entry(world))      # R3 each time
    with app.state.Session() as db:
        assert "anomaly.flag" in {o.event for o in db.query(Outbox).all()}


def test_utilization_view_self_only(c, world):
    h = world["h"]
    c.post("/timesheets", headers=h["s1"], json=entry(world, hours=6))
    u = c.get("/me/utilization", headers=h["s1"]).json()
    assert u["submitted"] == 6 and u["remaining_capacity"] == 34 and u["utilization_pct"] == 15.0
    assert c.get("/me/utilization", headers=h["s2"]).json()["submitted"] == 0
