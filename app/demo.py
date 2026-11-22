"""Fill an EMPTY database with demo users and projects so the UI has something to show.
   PROPERM_DEMO=1 PROPERM_DEMO_PASSWORD='<8+ chars>' python -m app.demo
Never run this against real data: it refuses unless the database has no users."""
import os
from datetime import date, timedelta

from fastapi.testclient import TestClient

from .deps import hash_pw
from .main import app_from_env
from .models import User


def main():
    if os.environ.get("PROPERM_DEMO") != "1":
        raise SystemExit("Set PROPERM_DEMO=1 to confirm this is a throwaway demo database")
    pw = os.environ.get("PROPERM_DEMO_PASSWORD", "")
    if len(pw) < 8:
        raise SystemExit("Set PROPERM_DEMO_PASSWORD (min 8 chars)")
    app = app_from_env()
    with app.state.Session() as db:
        if db.query(User).count():
            raise SystemExit("Database is not empty; refusing to add demo data")
        db.add(User(staff_id="admin", full_name="Admin User", role="ADMIN", password_hash=hash_pw(pw)))
        db.commit()
    c = TestClient(app)
    tok = lambda sid: {"Authorization": "Bearer " + c.post("/auth/login", json={"staff_id": sid, "password": pw}).json()["access_token"]}
    ok = lambda r: (r.raise_for_status(), r.json())[1]
    admin = tok("admin")
    ok(c.post("/admin/rates", headers=admin, json={"grade": "G1", "hourly_rate": 180, "currency": "SAR", "effective_from": "2024-01-01"}))
    ok(c.post("/admin/rates", headers=admin, json={"grade": "G2", "hourly_rate": 320, "currency": "SAR", "effective_from": "2024-01-01"}))
    ids = {}
    for sid, name, role, kw in [("pm1", "Sara Al-Harbi", "PM", {"rate_grade": "G2", "is_ccb": True}), ("pmo1", "Omar Al-Qahtani", "PMO", {}),
                                ("dm1", "Layla Al-Otaibi", "DECISION_MAKER", {}), ("s1", "Faisal Nasser", "STAFF", {"rate_grade": "G1"}),
                                ("s2", "Huda Saleh", "STAFF", {"rate_grade": "G1"}), ("s3", "Khaled Mansour", "STAFF", {"rate_grade": "G2"})]:
        ids[sid] = ok(c.post("/users", headers=admin, json={"staff_id": sid, "full_name": name, "password": pw, "role": role, **kw}))["id"]
    pm, pmo = tok("pm1"), tok("pmo1")
    T = date.today()
    d = lambda n: str(T + timedelta(days=n))

    def project(number, name, start, end, acts, state="planning"):
        pid = ok(c.post("/projects", headers=pm, json={"number": number, "name": name, "state": state, "planned_start": d(start), "planned_end": d(end), "budget_ceiling": sum(a[3] for a in acts) if acts else None}))["id"]
        for s in ("s1", "s2", "s3"):
            c.post(f"/projects/{pid}/assignments", headers=pm, json={"user_id": ids[s]})
        aids = []
        for code, nm, hrs, cost, a0, a1 in acts:
            aids.append(ok(c.post(f"/projects/{pid}/activities", headers=pm, json={"code": code, "name": nm, "planned_hours": hrs, "baseline_cost": cost, "planned_start": d(a0), "planned_end": d(a1)}))["id"])
        if acts:
            ok(c.post(f"/projects/{pid}/baseline/lock", headers=pm))
        return pid, aids

    # Healthy project
    a_pid, a_acts = project("ALPHA-01", "ERP Rollout", -60, 60, [("DES", "Design", 160, 60000, -60, -20), ("BLD", "Build", 400, 150000, -20, 30), ("TST", "Testing", 120, 40000, 30, 60)])
    # Struggling project: late and over budget
    b_pid, b_acts = project("BETA-02", "Data Platform", -90, 20, [("ARC", "Architecture", 120, 50000, -90, -50), ("ETL", "Data pipelines", 300, 120000, -50, -5)])
    project("TENDER-03", "Smart City Bid", 0, 0, [], state="tendering")

    def log(sid, pid, aid, days_ago, hrs):
        r = c.post("/timesheets", headers=tok(sid), json={"project_id": pid, "activity_id": aid, "entry_date": d(-days_ago), "hours": hrs, "description": "Demo work"})
        r.raise_for_status()
        return r.json()["id"]

    for i, (sid, n) in enumerate([("s1", 14), ("s2", 13), ("s3", 12), ("s1", 8), ("s2", 7)]):
        c.post(f"/timesheets/{log(sid, a_pid, a_acts[1], n, 8)}/decision", headers=pm, json={"action": "approve"})
    for sid, n in (("s1", 21), ("s2", 20), ("s3", 19)):
        c.post(f"/timesheets/{log(sid, b_pid, b_acts[1], n, 8)}/decision", headers=pm, json={"action": "approve"})
    log("s1", a_pid, a_acts[1], 2, 6)                                   # pending approvals for the queue
    log("s2", a_pid, a_acts[1], 1, 7.5)
    ok(c.post("/timesheets", headers=tok("s3"), json={"code": "TRAINING", "entry_date": d(-3), "hours": 4}))

    for pid, acts, pcts in ((a_pid, a_acts, (100, 45, 0)), (b_pid, b_acts, (70, 15))):
        c.put(f"/projects/{pid}/progress", headers=pm, json={"week_of": d(0), "updates": [{"activity_id": a, "pct_complete": p} for a, p in zip(acts, pcts)]}).raise_for_status()
    ok(c.post(f"/projects/{a_pid}/costs", headers=pm, json={"category": "Licences", "vendor": "Acme", "amount": 30000, "entry_date": d(-30), "currency": "SAR"}))
    ok(c.post(f"/projects/{b_pid}/costs", headers=pm, json={"category": "Cloud hosting", "vendor": "HostCo", "amount": 90000, "entry_date": d(-10), "currency": "SAR"}))   # above threshold: pending approval
    ok(c.post(f"/projects/{b_pid}/costs", headers=pm, json={"category": "Contractors", "vendor": "Build Ltd", "amount": 45000, "entry_date": d(-12), "currency": "SAR"}))
    ok(c.post(f"/projects/{a_pid}/risks", headers=pm, json={"title": "Key vendor delay", "probability": 3, "impact": 3}))
    ok(c.post(f"/projects/{b_pid}/risks", headers=pm, json={"title": "Source data quality", "probability": 5, "impact": 4}))
    ok(c.post(f"/projects/{b_pid}/issues", headers=pm, json={"title": "Production access not granted", "severity": "critical", "due_date": d(-3)}))
    ok(c.post("/alerts/evaluate", headers=pmo))
    print("Demo data ready. Users: admin, pm1, pmo1, dm1, s1, s2, s3 (all with the demo password).")


if __name__ == "__main__":
    main()
