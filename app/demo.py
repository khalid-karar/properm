"""Fill an EMPTY database with demo users and projects so the UI has something to show.
   PROPERM_DEMO=1 PROPERM_DEMO_PASSWORD='<8+ chars>' python -m app.demo
Never run this against real data: it refuses unless the database has no users."""
import os
from datetime import date, timedelta

from .deps import hash_pw
from .main import app_from_env
from .models import User


def main():
    if os.environ.get("PROPERM_DEMO") != "1":
        raise SystemExit("Set PROPERM_DEMO=1 to confirm this is a throwaway demo database")
    pw = os.environ.get("PROPERM_DEMO_PASSWORD", "")
    if len(pw) < 8:
        raise SystemExit("Set PROPERM_DEMO_PASSWORD (min 8 chars)")
    from fastapi.testclient import TestClient
    app = app_from_env()
    seed(app, pw, TestClient(app))


def seed(app, pw, c):
    """Fill an empty database. `c` is any client with TestClient's post/get/put API (the browser build passes its own)."""
    with app.state.Session() as db:
        if db.query(User).count():
            raise SystemExit("Database is not empty; refusing to add demo data")
        db.add(User(staff_id="admin", full_name="Admin User", role="ADMIN", password_hash=hash_pw(pw)))
        db.commit()
    tok = lambda sid: {"Authorization": "Bearer " + c.post("/auth/login", json={"staff_id": sid, "password": pw}).json()["access_token"]}
    ok = lambda r: (r.raise_for_status(), r.json())[1]
    admin = tok("admin")
    ok(c.post("/admin/rates", headers=admin, json={"grade": "G1", "hourly_rate": 180, "currency": "SAR", "effective_from": "2024-01-01"}))
    ok(c.post("/admin/rates", headers=admin, json={"grade": "G2", "hourly_rate": 320, "currency": "SAR", "effective_from": "2024-01-01"}))
    ids = {}
    for sid, name, role, kw in [("pm1", "Sara Al-Harbi", "PM", {"rate_grade": "G2", "is_ccb": True}), ("pmo1", "Omar Al-Qahtani", "PMO", {}),
                                ("dm1", "Layla Al-Otaibi", "DECISION_MAKER", {}), ("pg1", "Nasser Al-Dosari", "PROGRAM_MANAGER", {}), ("s1", "Faisal Nasser", "STAFF", {"rate_grade": "G1"}),
                                ("s2", "Huda Saleh", "STAFF", {"rate_grade": "G1"}), ("s3", "Khaled Mansour", "STAFF", {"rate_grade": "G2"})]:
        ids[sid] = ok(c.post("/users", headers=admin, json={"staff_id": sid, "full_name": name, "password": pw, "role": role, **kw}))["id"]
    pm, pmo = tok("pm1"), tok("pmo1")
    T = date.today()
    d = lambda n: str(T + timedelta(days=n))

    def project(number, name, start, end, acts, state="planning", ptype=None):
        pid = ok(c.post("/projects", headers=pm, json={"number": number, "name": name, "state": state, "planned_start": d(start), "planned_end": d(end), "budget_ceiling": sum(a[3] for a in acts) if acts else None, **({"project_type": ptype} if ptype else {})}))["id"]
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
    g = ok(c.post("/programs", headers=pmo, json={"code": "DX-2026", "name": "Digital Transformation", "manager_id": ids["pg1"]}))["id"]
    for pid in (a_pid, b_pid):
        ok(c.put(f"/projects/{pid}/program", headers=pmo, json={"program_id": g}))
    ok(c.post(f"/projects/{a_pid}/benefits", headers=pm, json={"title": "Faster month-end close", "metric": "Days to close", "unit": "days", "baseline": 10, "target": 5, "actual": 8, "due_date": d(120), "status": "on_track"}))
    ok(c.post(f"/projects/{b_pid}/benefits", headers=pm, json={"title": "Single source of truth for reporting", "metric": "Manual reports per month", "unit": "reports", "baseline": 40, "target": 10, "due_date": d(150)}))
    ok(c.post("/calendar/holidays", headers=pmo, json={"day": d(30), "name": "Demo public holiday"}))
    ok(c.post("/alerts/evaluate", headers=pmo))
    # plan depth and intake examples on ALPHA-01
    ok(c.patch(f"/projects/{a_pid}", headers=pm, json={"client": "Ministry of Digital Services", "sponsor": "Dr. Salem Al-Otaibi", "scope_statement": "Replace the legacy finance system with the new ERP across all departments."}))
    ok(c.post(f"/projects/{a_pid}/stakeholders", headers=pm, json={"name": "Dr. Salem Al-Otaibi", "organisation": "Ministry", "role": "Sponsor", "power": 5, "interest": 4, "engagement": "Monthly steering meeting"}))
    ok(c.post(f"/projects/{a_pid}/milestones", headers=pm, json={"name": "Design sign-off", "due_date": d(-20)}))
    ok(c.post(f"/projects/{a_pid}/milestones", headers=pm, json={"name": "Go-live", "due_date": d(55)}))
    ms = c.get(f"/projects/{a_pid}/milestones", headers=pm).json()
    ok(c.patch(f"/projects/{a_pid}/milestones/{ms[0]['id']}", headers=pm, json={"achieved_on": d(-18)}))
    k = ok(c.post(f"/projects/{a_pid}/kpis", headers=pm, json={"name": "On-time delivery", "unit": "%", "target": 95}))
    ok(c.put(f"/projects/{a_pid}/kpis/{k['id']}/actual", headers=pm, json={"actual": 88}))
    # project tools: template library, RACI, communication plan, dependencies (critical path), a waiting resource request
    ok(c.post(f"/templates/from-project/{a_pid}", headers=pmo, json={"code": "ERP-STD", "name": "Standard ERP implementation"}))
    ok(c.post("/templates", headers=pmo, json={"code": "DIGI-SVC", "name": "Digital service (agile delivery)", "description": "Discovery, alpha, beta and live, as used for citizen-facing services",
        "data": {"activities": [{"code": "DISC", "name": "Discovery", "planned_hours": 120, "start_offset_days": 0, "duration_days": 28},
                                {"code": "ALPHA", "name": "Alpha prototype", "planned_hours": 240, "start_offset_days": 28, "duration_days": 42, "after": "DISC"},
                                {"code": "BETA", "name": "Private and public beta", "planned_hours": 480, "start_offset_days": 70, "duration_days": 84, "after": "ALPHA"},
                                {"code": "LIVE", "name": "Go live and handover", "planned_hours": 80, "start_offset_days": 154, "duration_days": 21, "after": "BETA"}],
                 "milestones": [{"name": "Discovery report approved", "offset_days": 28}, {"name": "Public beta launched", "offset_days": 112}],
                 "kpis": [{"name": "User satisfaction", "unit": "%", "target": 85, "higher_is_better": True}, {"name": "Digital take-up", "unit": "%", "target": 60, "higher_is_better": True}],
                 "risks": [{"title": "Low user research participation", "category": "stakeholders", "probability": 3, "impact": 3},
                           {"title": "Legacy integration harder than expected", "category": "technical", "probability": 3, "impact": 4}]}}))
    for i in (1, 2):
        c.post(f"/projects/{a_pid}/dependencies", headers=pm, json={"activity_id": a_acts[i], "predecessor_id": a_acts[i - 1]})
    for item, cells in (("Solution design", {"Sara Al-Harbi": "A", "Faisal Nasser": "R", "Dr. Salem Al-Otaibi": "C", "Omar Al-Qahtani": "I"}),
                        ("Data migration", {"Sara Al-Harbi": "A", "Khaled Mansour": "R", "Huda Saleh": "C"}),
                        ("Go-live decision", {"Dr. Salem Al-Otaibi": "A", "Sara Al-Harbi": "R", "Omar Al-Qahtani": "C", "Faisal Nasser": "I"})):
        for person, letter in cells.items():
            ok(c.put(f"/projects/{a_pid}/raci", headers=pm, json={"item": item, "person": person, "letter": letter}))
    cm = ok(c.post(f"/projects/{a_pid}/comms", headers=pm, json={"audience": "Steering committee", "information": "Status, risks and decisions needed", "method": "Meeting", "frequency": "monthly", "owner_id": ids["pm1"]}))
    ok(c.post(f"/projects/{a_pid}/comms", headers=pm, json={"audience": "Finance users", "information": "What changes next month", "method": "E-mail newsletter", "frequency": "biweekly", "owner_id": ids["s1"]}))
    ok(c.post(f"/projects/{a_pid}/comms/{cm['id']}/sent", headers=pm))
    ok(c.post(f"/projects/{b_pid}/resource-requests", headers=pm, json={"skill": "Senior data engineer", "department": "Data", "hours_per_week": 24, "start": d(7), "end": d(49), "note": "Pipelines are behind; need a second engineer"}))
    # scope: charter, WBS, requirements, assumptions
    ok(c.put(f"/projects/{a_pid}/charter", headers=pm, json={"purpose": "Replace the legacy finance system with a single ERP so month-end close is faster and auditable.",
        "objectives": "Cut month-end close from 10 days to 4. One ledger for all entities.", "success_criteria": "Close in 4 working days for three consecutive months; zero manual journal uploads.",
        "in_scope": "GL, AP, AR, fixed assets, reporting.", "out_of_scope": "HR and payroll, procurement portal.", "key_risks": "Legacy integration; data quality; user adoption."}))
    ok(c.post(f"/projects/{a_pid}/charter/decision", headers=pmo, json={"action": "approve"}))
    w1 = ok(c.post(f"/projects/{a_pid}/wbs", headers=pm, json={"code": "1", "name": "Finance core configured", "acceptance_criteria": "UAT scripts passed with finance sign-off", "owner_id": ids["pm1"], "due_date": d(30)}))
    ok(c.post(f"/projects/{a_pid}/wbs", headers=pm, json={"code": "1.1", "name": "General ledger set-up", "kind": "work_package", "parent_id": w1["id"], "activity_id": a_acts[0]}))
    w2 = ok(c.post(f"/projects/{a_pid}/wbs", headers=pm, json={"code": "2", "name": "Data migrated and reconciled", "acceptance_criteria": "Balances match to the riyal", "due_date": d(45)}))
    ok(c.post(f"/projects/{a_pid}/wbs", headers=pm, json={"code": "3", "name": "Training delivered", "due_date": d(60)}))
    ok(c.post(f"/projects/{a_pid}/wbs/{w1['id']}/start", headers=pm))
    ok(c.post(f"/projects/{a_pid}/wbs/{w1['id']}/submit", headers=pm))
    ok(c.post(f"/projects/{a_pid}/requirements", headers=pm, json={"code": "R-01", "title": "Automatic bank reconciliation", "priority": "must", "status": "approved", "source": "Finance director", "deliverable_id": w1["id"]}))
    ok(c.post(f"/projects/{a_pid}/requirements", headers=pm, json={"code": "R-02", "title": "Opening balances migrated with audit trail", "priority": "must", "deliverable_id": w2["id"]}))
    ok(c.post(f"/projects/{a_pid}/requirements", headers=pm, json={"code": "R-03", "title": "Arabic statutory reports", "priority": "should"}))
    ok(c.post(f"/projects/{a_pid}/assumptions", headers=pm, json={"kind": "assumption", "text": "Legacy vendor provides a data export by week 3", "validate_by": d(10)}))
    ok(c.post(f"/projects/{a_pid}/assumptions", headers=pm, json={"kind": "constraint", "text": "Go-live must avoid the fiscal year-end freeze"}))
    ok(c.post(f"/projects/{a_pid}/assumptions", headers=pm, json={"kind": "exclusion", "text": "Payroll integration is not part of this release"}))
    # strategy alignment and compliance
    o1 = ok(c.post("/objectives", headers=pmo, json={"code": "SO-1", "name": "Digitise government services", "horizon": "2030", "owner_id": ids["dm1"]}))
    o2 = ok(c.post("/objectives", headers=pmo, json={"code": "SO-2", "name": "Build national data capability", "horizon": "2030", "owner_id": ids["dm1"]}))
    ok(c.post("/objectives", headers=pmo, json={"code": "SO-3", "name": "Localise critical supply chains", "horizon": "2030"}))
    ok(c.put(f"/projects/{a_pid}/objectives", headers=pm, json={"objective_ids": [o1["id"]]}))
    ok(c.put(f"/projects/{b_pid}/objectives", headers=pm, json={"objective_ids": [o2["id"]]}))
    for code, fw, title in [("PDPL-01", "PDPL", "Lawful basis and consent recorded for each data category"), ("PDPL-02", "PDPL", "Data subject request process in place"), ("PDPL-03", "PDPL", "Data protection impact assessment completed"),
                            ("ECC-01", "NCA-ECC", "Role-based access control and periodic access review"), ("ECC-02", "NCA-ECC", "Vulnerability assessment before go-live"), ("POL-01", "Internal policy", "Data hosted inside the Kingdom")]:
        ok(c.post("/compliance-library", headers=pmo, json={"code": code, "framework": fw, "title": title}))
    ok(c.post(f"/projects/{a_pid}/compliance/apply-framework", headers=pm, json={"framework": "PDPL"}))
    ok(c.post(f"/projects/{a_pid}/compliance/apply-framework", headers=pm, json={"framework": "NCA-ECC"}))
    rows = ok(c.get(f"/projects/{a_pid}/compliance", headers=pm))
    ok(c.patch(f"/projects/{a_pid}/compliance/{rows[0]['id']}", headers=pm, json={"status": "compliant", "evidence": "Consent register v3, approved by DPO"}))
    ok(c.patch(f"/projects/{a_pid}/compliance/{rows[1]['id']}", headers=pm, json={"status": "in_progress", "due_date": d(-5), "owner_id": ids["s1"]}))
    ok(c.patch(f"/projects/{a_pid}/compliance/{rows[3]['id']}", headers=pm, json={"status": "compliant", "evidence": "Access matrix signed off by security"}))
    # procurement
    k1 = ok(c.post(f"/projects/{a_pid}/contracts", headers=pm, json={"number": "CT-101", "title": "ERP licences and implementation partner", "vendor": "Najd Systems", "value": 240000, "status": "active",
                                                                    "start_date": d(-60), "end_date": d(50), "owner_id": ids["pm1"]}))
    for nm, amt, due, st in [("Mobilisation", 48000, -55, "paid"), ("Design sign-off", 72000, -15, "invoiced"), ("Build complete", 72000, 10, "planned"), ("Go-live and handover", 48000, 45, "planned")]:
        pay = ok(c.post(f"/projects/{a_pid}/payments", headers=pm, json={"contract_id": k1["id"], "name": nm, "amount": amt, "due_date": d(due)}))
        if st in ("invoiced", "paid"):
            ok(c.patch(f"/projects/{a_pid}/payments/{pay['id']}", headers=pm, json={"status": "invoiced", "invoice_no": f"INV-{pay['id']:03d}"}))
        if st == "paid":
            ok(c.patch(f"/projects/{a_pid}/payments/{pay['id']}", headers=pm, json={"status": "paid"}))
    ok(c.post(f"/projects/{a_pid}/vendor-reviews", headers=pm, json={"contract_id": k1["id"], "review_date": d(-20), "quality": 4, "schedule": 3, "communication": 4, "note": "Design delivered four days late"}))
    k2 = ok(c.post(f"/projects/{b_pid}/contracts", headers=pm, json={"number": "CT-207", "title": "Cloud hosting (Saudi region)", "vendor": "Hosting Co", "value": 90000, "status": "active", "start_date": d(-80), "end_date": d(25)}))
    ok(c.post(f"/projects/{b_pid}/payments", headers=pm, json={"contract_id": k2["id"], "name": "Quarterly fee", "amount": 30000, "due_date": d(-4)}))
    # a couple of failed sign-ins so the security history has something to show
    for _ in range(2):
        c.post("/auth/login", json={"staff_id": "s3", "password": "wrong-password-1"})
    c.post("/auth/login", json={"staff_id": "unknown.user", "password": "x"})
    # program roadmap: BETA's data platform feeds ALPHA's reporting (late), a program-level risk
    bm = ok(c.post(f"/projects/{b_pid}/milestones", headers=pm, json={"name": "Data platform live", "due_date": d(25)}))
    ok(c.post(f"/programs/{g}/dependencies", headers=pmo, json={"project_id": a_pid, "predecessor_id": b_pid, "milestone_id": bm["id"], "needed_by": d(15), "description": "ERP reports read from the data platform"}))
    ok(c.post(f"/programs/{g}/risks", headers=pmo, json={"title": "Same integration vendor on both projects", "probability": 4, "impact": 4, "owner_id": ids["pg1"], "response": "Agree a shared delivery plan with the vendor"}))
    ok(c.post(f"/programs/{g}/issues", headers=pmo, json={"title": "Shared test environment unavailable two days a week", "severity": "high", "owner_id": ids["pg1"], "due_date": d(7)}))
    ok(c.put(f"/programs/{g}/budget", headers=pmo, json={"envelope": 450000, "currency": "SAR"}))
    # portfolio: departments, planned hours for the coming weeks, strategic scores
    for sid, dep in (("s1", "Delivery"), ("s2", "Data"), ("s3", "Delivery"), ("pm1", "PMO Office")):
        ok(c.patch(f"/users/{ids[sid]}", headers=admin, json={"department": dep}))
    ws0 = T - timedelta(days=(T.weekday() + 1) % 7)
    for wk in range(8):
        for sid, pid_, hrs in (("s1", a_pid, 32), ("s2", b_pid, 36 + (12 if wk in (2, 3) else 0)), ("s3", a_pid, 20), ("s3", b_pid, 16)):
            ok(c.put(f"/projects/{pid_}/allocations", headers=pm, json={"user_id": ids[sid], "week_of": str(ws0 + timedelta(days=7 * wk)), "hours": hrs}))
    ok(c.put(f"/portfolio/scores/{a_pid}", headers=pmo, json={"strategic_fit": 5, "value": 4, "urgency": 4, "risk_level": 2}))
    ok(c.put(f"/portfolio/scores/{b_pid}", headers=pmo, json={"strategic_fit": 3, "value": 4, "urgency": 3, "risk_level": 4}))
    for code, label in (("DEL", "Delivery"), ("DATA", "Data"), ("PMO", "PMO Office")):
        ok(c.put(f"/admin/lists/department/{code}", headers=admin, json={"label": label}))
    # weekly cycle: one submitted week, leave requests (one approved, one waiting)
    lw = T - timedelta(days=((T.weekday() + 1) % 7) + 7)
    ok(c.post("/me/week/submit", headers=tok("s1"), json={"week_of": str(lw), "note": "Two days at the vendor workshop"}))
    lv = ok(c.post("/leave", headers=tok("s3"), json={"start": d(21), "end": d(25), "kind": "annual", "note": "Family trip"}))
    ok(c.post(f"/leave/{lv['id']}/decision", headers=pmo, json={"approve": True}))
    ok(c.post("/leave", headers=tok("s2"), json={"start": d(10), "end": d(11), "kind": "training", "note": "PMP exam"}))
    # PM control: forecasts, actions, lessons
    ok(c.put(f"/projects/{b_pid}/activities/{b_acts[1]}/forecast", headers=pm, json={"forecast_end": d(40), "note": "Source system access arrived three weeks late"}))
    ok(c.post(f"/projects/{a_pid}/actions", headers=pm, json={"title": "Circulate steering committee minutes", "owner_id": ids["s1"], "due_date": d(2), "source": "Steering meeting"}))
    ok(c.post(f"/projects/{b_pid}/actions", headers=pm, json={"title": "Escalate production access to IT director", "owner_id": ids["pm1"], "due_date": d(-2), "source": "Issue review"}))
    ok(c.post(f"/projects/{b_pid}/lessons", headers=pm, json={"category": "stakeholders", "impact": "negative", "what_happened": "Production access took six weeks because no owner was named in IT.",
                                                             "recommendation": "Name an IT access owner at kick-off and request access in week one."}))
    ok(c.post(f"/projects/{a_pid}/lessons", headers=pm, json={"category": "quality", "impact": "positive", "what_happened": "Weekly design walkthroughs with finance users caught gaps early.",
                                                             "recommendation": "Keep a fixed weekly walkthrough with the business owner during design."}))
    # governance: a planning project waiting at its stage gate, proposals waiting for a decision, one decided proposal
    g_pid = ok(c.post("/projects", headers=pm, json={"number": "GAMMA-04", "name": "Citizen Portal", "planned_start": d(14), "planned_end": d(200), "budget_ceiling": 300000, "sponsor": "Eng. Hind Al-Shehri"}))["id"]
    ok(c.post(f"/projects/{g_pid}/activities", headers=pm, json={"code": "UX", "name": "User research and design", "planned_hours": 200, "baseline_cost": 70000, "planned_start": d(14), "planned_end": d(70)}))
    ok(c.post(f"/projects/{g_pid}/milestones", headers=pm, json={"name": "Design approved", "due_date": d(70)}))
    ok(c.put("/admin/settings/intake_required", headers=admin, json={"value": 1}))
    ok(c.put("/admin/settings/stage_gates", headers=admin, json={"value": 1}))
    ok(c.post(f"/projects/{g_pid}/gates", headers=pm, json={"note": "Design team ready to start; risks to be logged in week one."}))
    case = "Ministry staff spend about 3,000 hours a month answering status questions by phone. A self-service tracker cuts this and supports Vision 2030 digital targets."
    ok(c.post("/proposals", headers=pm, json={"number": "DELTA-05", "name": "Case Status Tracker", "business_case": case, "expected_benefits": "50% fewer status calls within 6 months",
                                               "sponsor": "Dr. Salem Al-Otaibi", "est_cost": 420000, "est_start": d(45), "est_end": d(240), "strategic_fit": 5, "value": 4, "urgency": 4, "risk_level": 2}))
    ok(c.post("/proposals", headers=pm, json={"number": "EPS-06", "name": "Intranet Refresh", "business_case": "The intranet is dated and staff rarely use it; a refresh would improve internal communication.",
                                               "est_cost": 180000, "strategic_fit": 2, "value": 2, "urgency": 2, "risk_level": 2}))
    z = ok(c.post("/proposals", headers=pmo, json={"number": "ZETA-07", "name": "Records Digitisation", "business_case": "Scan and index 2 million paper records so they can be searched online.",
                                                    "est_cost": 900000, "strategic_fit": 4, "value": 4, "urgency": 2, "risk_level": 4}))
    ok(c.post(f"/proposals/{z['id']}/decision", headers=tok("dm1"), json={"outcome": "defer", "rationale": "Good idea; revisit in next budget cycle when funding is confirmed."}))
    # a few weeks of history so the trend charts have something to show
    with app.state.Session() as db:
        from datetime import date as _d, timedelta as _td
        from .models import Snapshot
        for w in range(8, 0, -1):
            db.add(Snapshot(project_id=a_pid, snap_date=_d.today() - _td(days=7 * w), rag="GREEN" if w > 3 else "AMBER", progress_pct=round(45 - 5 * w, 1) if w < 8 else 0.0,
                            cpi=round(1.1 - 0.02 * w, 2), spi=round(0.85 + 0.02 * w, 2), open_risks=1, open_alerts=0 if w > 3 else 1))
        db.commit()
    # skills
    for sid, items in {"s1": [("Data engineering", 4, 4, 6), ("Python", 4, None, 7)], "s2": [("Data engineering", 2, 4, 2), ("Business analysis", 3, None, 4)], "s3": [("Solution architecture", 3, 4, 5), ("Data engineering", 3, None, 3)]}.items():
        for sk, lv, tg, yr in items:
            ok(c.post("/me/skills", headers=tok(sid), json={"skill": sk, "level": lv, "target_level": tg, "years": yr}))
    ok(c.post("/me/certs", headers=tok("s3"), json={"name": "TOGAF 9 Certified", "issuer": "The Open Group", "expires_on": d(45)}))
    ok(c.post("/me/certs", headers=tok("s1"), json={"name": "AWS Data Analytics Specialty", "issuer": "AWS", "expires_on": d(400)}))
    ok(c.post(f"/projects/{a_pid}/team-norms", headers=pm, json={"category": "meetings", "text": "Weekly stand-up on Sundays at 9:30, 15 minutes, camera optional"}))
    ok(c.post(f"/projects/{a_pid}/team-norms", headers=pm, json={"category": "decisions", "text": "Scope or date changes only through change control; everything else the team lead decides"}))
    # depth: risk responses, opportunities, reserves, quality, stakeholder engagement, document versions
    rks = ok(c.get(f"/projects/{a_pid}/risks", headers=pm))
    if rks:
        ok(c.put(f"/projects/{a_pid}/risks/{rks[0]['id']}/response", headers=pm, json={"strategy": "mitigate", "plan": "Run the legacy integration as a two-week spike before build and keep the old interface alive for one more quarter.",
            "trigger": "Spike shows more than 5 undocumented interfaces", "contingency_amount": 40000, "residual_probability": 2, "residual_impact": 3, "owner_id": ids["pm1"]}))
    ok(c.post(f"/projects/{a_pid}/opportunities", headers=pm, json={"title": "Partner can reuse its reconciliation module", "probability": 4, "impact": 3, "strategy": "exploit", "owner_id": ids["pm1"]}))
    ok(c.put(f"/projects/{a_pid}/reserves", headers=pmo, json={"contingency": 60000}))
    ok(c.put(f"/projects/{a_pid}/reserves", headers=tok("dm1"), json={"management": 120000}))
    ok(c.post(f"/projects/{a_pid}/reserves/drawdowns", headers=pm, json={"kind": "contingency", "amount": 15000, "reason": "Extra data-migration test cycle"}))
    ok(c.post(f"/projects/{a_pid}/reserves/drawdowns", headers=pm, json={"kind": "management", "amount": 50000, "reason": "Regulator asked for extra reports not in scope"}))
    for kind, title, sev_, st in [("defect", "Trial balance does not agree after migration", "high", "open"), ("defect", "Arabic labels truncated on invoice screen", "low", "fixed"), ("inspection", "Peer review of data model", "medium", "closed")]:
        ok(c.post(f"/projects/{a_pid}/quality", headers=pm, json={"kind": kind, "title": title, "severity": sev_, "status": st, "found_on": d(-6)}))
    sks = ok(c.get(f"/projects/{a_pid}/stakeholders", headers=pm))
    for sk, cur, des, plan in list(zip(sks, ["resistant", "neutral"], ["supportive", "neutral"], ["Monthly walk-through of savings with the finance director", None])):
        ok(c.put(f"/projects/{a_pid}/stakeholders/{sk['id']}/engagement", headers=pm, json={"current": cur, "desired": des, "plan": plan}))
    import base64 as _b
    dd_ = ok(c.post(f"/projects/{a_pid}/documents", headers=pm, json={"kind": "scope", "filename": "scope-statement.txt", "content_b64": _b.b64encode(b"Scope statement v1: GL, AP, AR, assets.").decode()}))
    ok(c.post(f"/projects/{a_pid}/documents/{dd_['id']}/versions", headers=pm, json={"filename": "scope-statement.txt", "content_b64": _b.b64encode(b"Scope statement v2: adds statutory reports.").decode(), "note": "Change CR-1"}))
    # the agile project is created last so earlier projects keep their order; governance switches are paused while it is set up
    for k in ("intake_required", "stage_gates"):
        ok(c.put(f"/admin/settings/{k}", headers=admin, json={"value": 0}))
    # agile project with a running sprint
    ag_pid, _ = project("AGILE-01", "Citizen services app", -14, 70, [("SPR", "Delivery sprints", 600, 200000, -14, 70)], ptype="adaptive")
    s1_ = ok(c.post(f"/projects/{ag_pid}/sprints", headers=pm, json={"name": "Sprint 1", "goal": "Sign-in and profile", "start_date": d(-9), "end_date": d(4)}))
    ok(c.post(f"/projects/{ag_pid}/sprints", headers=pm, json={"name": "Sprint 2", "goal": "Payments", "start_date": d(5), "end_date": d(18)}))
    bl = [("Sign in with national ID", 5, 1, "done"), ("Profile page", 3, 2, "done"), ("Arabic and English UI", 5, 3, "review"), ("Notification preferences", 3, 4, "in_progress"), ("Accessibility audit fixes", 2, 5, "ready")]
    bids = [ok(c.post(f"/projects/{ag_pid}/backlog", headers=pm, json={"title": t_, "points": pt, "rank": rk, "sprint_id": s1_["id"], "kind": "story"}))["id"] for t_, pt, rk, _ in bl]
    ok(c.post(f"/projects/{ag_pid}/sprints/{s1_['id']}/start", headers=pm))
    for bid, (_, _, _, st) in zip(bids, bl):
        if st != "ready":
            ok(c.post(f"/projects/{ag_pid}/backlog/{bid}/move", headers=pm, json={"status": st}))
    ok(c.post(f"/projects/{ag_pid}/backlog", headers=pm, json={"title": "Online payment of fees", "points": 8, "rank": 10}))
    ok(c.post(f"/projects/{ag_pid}/backlog", headers=pm, json={"title": "Appointment booking", "rank": 11}))
    ok(c.put(f"/projects/{ag_pid}/objectives", headers=pm, json={"objective_ids": [o1["id"]]}))
    ok(c.post(f"/projects/{ag_pid}/compliance/apply-framework", headers=pm, json={"framework": "PDPL"}))
    for k in ("intake_required", "stage_gates"):
        ok(c.put(f"/admin/settings/{k}", headers=admin, json={"value": 1}))
    print("Demo data ready. Users: admin, pm1, pmo1, dm1, pg1, s1, s2, s3 (all with the demo password).")


if __name__ == "__main__":
    main()
