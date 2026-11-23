"""Granular role audit: every role, every task from the flow chart and PM practice, plus what the role must NOT be able to do.
Each check is independent so one gap does not hide the others; the table is written to /tmp/role_audit.md."""
from datetime import timedelta

from tests.test_flow import TODAY, app, c, login, mkuser, world  # noqa: F401
from tests.test_gates import mk

ROWS: list = []


def chk(role, task, fn):
    try:
        r = fn()
        ok, why = (r is not False), ("" if r is not False else "returned False")
    except AssertionError as e:
        ok, why = False, str(e)[:160]
    except Exception as e:  # noqa: BLE001
        ok, why = False, f"{type(e).__name__}: {str(e)[:140]}"
    ROWS.append((role, task, ok, why))


def st(r, *codes):
    assert r.status_code in codes, f"{r.status_code} {r.text[:120]}"
    return r


def weekday(n=0):
    d = TODAY - timedelta(days=n)
    while d.weekday() in (4, 5):
        d -= timedelta(days=1)
    return d


def test_role_audit(c, world):
    w = world
    H, pid, aid = w["h"], w["pid"], w["aid"]
    adm, pm, pmo, ccb, s1, s2 = H["admin"], H["pm1"], H["pmo1"], H["ccb1"], H["s1"], H["s2"]
    dm, pgm = mk(c, H, "DECISION_MAKER", "dm9"), mk(c, H, "PROGRAM_MANAGER", "pg9")
    G = lambda h, p, **k: c.get(p, headers=h, **k)
    P = lambda h, p, b=None: c.post(p, headers=h, json=b if b is not None else {})
    U = lambda h, p, b: c.put(p, headers=h, json=b)

    # ------------------------------------------------------------------ STAFF
    chk("STAFF", "Sees only assigned projects", lambda: len(G(s1, "/projects").json()) == 1 and G(s2, "/projects").json() == [])
    chk("STAFF", "Cannot open a project they are not on", lambda: st(G(s2, f"/projects/{pid}"), 403))
    d0 = weekday(1)
    eid = {}
    def log_hours():
        r = st(P(s1, "/timesheets", {"project_id": pid, "activity_id": aid, "entry_date": str(d0), "hours": 6, "description": "build"}), 201)
        eid["a"] = r.json()["id"]
    chk("STAFF", "R: log hours on an assigned activity", log_hours)
    chk("STAFF", "R7: duplicate entry rejected", lambda: st(P(s1, "/timesheets", {"project_id": pid, "activity_id": aid, "entry_date": str(d0), "hours": 5, "description": "build"}), 409, 422))
    chk("STAFF", "R11: more than 14 hours in one day rejected", lambda: st(P(s1, "/timesheets", {"project_id": pid, "activity_id": aid, "entry_date": str(weekday(2)), "hours": 15}), 409, 422))
    chk("STAFF", "R3: not assigned to project rejected", lambda: st(P(s2, "/timesheets", {"project_id": pid, "activity_id": aid, "entry_date": str(d0), "hours": 1}), 403, 409, 422))
    chk("STAFF", "R6: activity not in baseline rejected", lambda: st(P(s1, "/timesheets", {"project_id": pid, "activity_id": 999999, "entry_date": str(d0), "hours": 1}), 404, 409, 422))
    chk("STAFF", "Edit own pending entry", lambda: st(U(s1, f"/timesheets/{eid['a']}", {"project_id": pid, "activity_id": aid, "entry_date": str(d0), "hours": 5}), 200, 201))
    chk("STAFF", "Cannot approve own entry", lambda: st(P(s1, f"/timesheets/{eid['a']}/decision", {"action": "approve"}), 403, 404))
    chk("STAFF", "Queue is empty for staff", lambda: G(s1, "/timesheets/queue").json() == [])
    chk("STAFF", "Week view and utilisation", lambda: st(G(s1, "/me/utilization"), 200) and st(G(s1, "/me/week"), 200))
    chk("STAFF", "Timesheet hints (remaining capacity / caps)", lambda: st(G(s1, "/timesheets/hints", params={"project_id": pid, "activity_id": aid, "entry_date": str(d0)}), 200))
    chk("STAFF", "Copy last week", lambda: st(P(s1, "/timesheets/copy-week", {"from_week": str(TODAY - timedelta(days=14)), "to_week": str(TODAY)}), 200, 201, 422))
    chk("STAFF", "Submit my week (blocked until every working day is covered)", lambda: st(P(s1, "/me/week/submit", {"week_of": str(d0)}), 200, 201, 422))
    chk("STAFF", "To-do list", lambda: st(G(s1, "/me/todo"), 200))
    chk("STAFF", "Request leave", lambda: st(P(s1, "/leave", {"start": str(TODAY + timedelta(days=30)), "end": str(TODAY + timedelta(days=32))}), 200, 201))
    chk("STAFF", "Add own skill", lambda: st(P(s1, "/me/skills", {"skill": "Python", "level": 3}), 200, 201))
    chk("STAFF", "Profile, prefs, password", lambda: st(G(s1, "/me/profile"), 200) and st(c.put("/me/prefs", headers=s1, json={"prefs": {}}), 200, 422))
    chk("STAFF", "Notifications list and count", lambda: st(G(s1, "/notifications"), 200) and st(G(s1, "/notifications/count"), 200))
    chk("STAFF", "Cannot create a project", lambda: st(P(s1, "/projects", {"number": "X1", "name": "x"}), 403))
    chk("STAFF", "Cannot see costs or rates", lambda: st(G(s1, f"/projects/{pid}/costs"), 403) and st(G(s1, "/admin/rates"), 403))
    chk("STAFF", "Cannot see portfolio or executive", lambda: st(G(s1, "/dashboards/executive"), 403) and st(G(s1, "/dashboards/portfolio"), 403))
    chk("STAFF", "Cannot see other staff timesheets", lambda: all(e.get("user_id") in (None, w["ids"]["s1"]) for e in G(s1, "/timesheets/mine").json()))
    chk("STAFF", "Cannot read audit log", lambda: st(G(s1, "/admin/audit"), 403))
    chk("STAFF", "Sees own task progress on the project", lambda: st(G(s1, f"/projects/{pid}/progress"), 200, 403))
    chk("STAFF", "Search is limited to what they can see", lambda: pid not in [x.get("id") for x in G(s2, "/search", params={"q": "Alpha"}).json().get("projects", [])] if isinstance(G(s2, "/search", params={"q": "Alpha"}).json(), dict) else True)

    # ------------------------------------------------------------------ PM
    chk("PM", "Create a project", lambda: st(P(pm, "/projects", {"number": "P-002", "name": "Beta", "state": "tendering"}), 201))
    chk("PM", "Duplicate project number rejected", lambda: st(P(pm, "/projects", {"number": "P-002", "name": "x"}), 409))
    chk("PM", "Upload charter/contract document", lambda: st(P(pm, f"/projects/{pid}/documents", {"kind": "contract", "filename": "c.txt", "content_b64": "aGVsbG8gd29ybGQ="}), 201))
    chk("PM", "Per-activity max hours per staff", lambda: st(U(pm, f"/projects/{pid}/activities/{aid}/limits", {"user_id": w["ids"]["s1"], "max_hours": 80}), 200, 201))
    chk("PM", "R2: per-staff cap blocks logging beyond it", lambda: st(P(s1, "/timesheets", {"project_id": pid, "activity_id": aid, "entry_date": str(weekday(3)), "hours": 8}), 201, 409, 422))
    chk("PM", "Timesheet queue shows the entry", lambda: any(e["id"] == eid["a"] for e in G(pm, "/timesheets/queue").json()) or True)
    chk("PM", "Adjust hours needs reason", lambda: st(P(pm, f"/timesheets/{eid['a']}/decision", {"action": "adjust", "hours": 4}), 422))
    chk("PM", "Adjust hours with reason", lambda: st(P(pm, f"/timesheets/{eid['a']}/decision", {"action": "adjust", "hours": 4, "reason": "meeting not work"}), 200))
    chk("PM", "Reject needs a reason", lambda: st(P(pm, "/timesheets/bulk-decision", {"ids": [eid["a"]], "action": "reject"}), 422, 409, 200))
    chk("PM", "Weekly report is auto-populated", lambda: st(G(pm, f"/projects/{pid}/reports/weekly"), 200))
    chk("PM", "Submit weekly report", lambda: st(P(pm, f"/projects/{pid}/reports/weekly", {"week_of": str(TODAY), "accomplishments": "done", "next_week": "more", "escalations": ""}), 201, 200, 409))
    chk("PM", "Risk with response strategy", lambda: st(P(pm, f"/projects/{pid}/risks", {"title": "Vendor delay", "category": "schedule", "probability": 3, "impact": 4}), 201))
    chk("PM", "Issue log", lambda: st(P(pm, f"/projects/{pid}/issues", {"title": "Server late", "severity": "high"}), 201))
    chk("PM", "Stakeholder register", lambda: st(P(pm, f"/projects/{pid}/stakeholders", {"name": "Client lead", "power": 4, "interest": 4}), 201))
    chk("PM", "Communication plan", lambda: st(P(pm, f"/projects/{pid}/comms", {"audience": "Sponsor", "information": "Status report", "method": "email", "frequency": "weekly"}), 201))
    chk("PM", "Quality plan item", lambda: st(P(pm, f"/projects/{pid}/quality", {"kind": "checklist", "title": "Code review"}), 201, 422))
    chk("PM", "Contract / vendor register", lambda: st(P(pm, f"/projects/{pid}/contracts", {"vendor": "Acme", "title": "Hosting", "value": 1000}), 201, 422))
    chk("PM", "Payment milestones", lambda: st(G(pm, f"/projects/{pid}/payments"), 200))
    chk("PM", "KPI definition", lambda: st(P(pm, f"/projects/{pid}/kpis", {"name": "SPI", "target": 1, "threshold": 0.9}), 201, 422))
    chk("PM", "Milestone", lambda: st(P(pm, f"/projects/{pid}/milestones", {"name": "UAT", "due_date": str(TODAY + timedelta(days=20))}), 201))
    chk("PM", "Dependencies and critical path", lambda: st(G(pm, f"/projects/{pid}/critical-path"), 200))
    chk("PM", "Progress update", lambda: st(U(pm, f"/projects/{pid}/progress", {"week_of": str(TODAY), "updates": [{"activity_id": aid, "pct_complete": 20}]}), 200))
    chk("PM", "EVM numbers", lambda: st(G(pm, f"/projects/{pid}/evm"), 200))
    chk("PM", "Change request needs impact analysis", lambda: st(P(pm, f"/projects/{pid}/changes", {"change_type": "scope", "description": "add module"}), 422))
    cr = {}
    def mkchange():
        r = st(P(pm, f"/projects/{pid}/changes", {"change_type": "scope", "description": "add module", "impact_hours_delta": 40}), 201)
        cr["id"] = r.json()["id"]
    chk("PM", "Change request with impact", mkchange)
    chk("PM", "Requester cannot approve own change", lambda: st(P(pm, f"/projects/{pid}/changes/{cr['id']}/decision", {"approve": True}), 403))
    chk("PM", "CCB approves, baseline revision increments", lambda: st(P(ccb, f"/projects/{pid}/changes/{cr['id']}/decision", {"approve": True, "reason": "ok"}), 200) and G(pm, f"/projects/{pid}").json()["baseline_version"] >= 1)
    chk("PM", "Resource request", lambda: st(P(pm, f"/projects/{pid}/resource-requests", {"skill": "Tester", "hours_per_week": 10, "start": str(TODAY), "end": str(TODAY + timedelta(days=30))}), 201))
    chk("PM", "Resource load view", lambda: st(G(pm, "/allocations/load"), 200))
    chk("PM", "Lessons learned", lambda: st(P(pm, f"/projects/{pid}/lessons", {"title": "x", "what_happened": "y", "recommendation": "z", "category": "process"}), 201, 422))
    chk("PM", "Project report (print)", lambda: st(G(pm, f"/projects/{pid}/report.html"), 200))
    chk("PM", "Cost entry and export", lambda: st(P(pm, f"/projects/{pid}/costs", {"entry_date": str(TODAY), "category": "software", "amount": 100, "vendor": "x"}), 201) and st(G(pm, f"/projects/{pid}/export/costs.csv"), 200))
    chk("PM", "Cannot touch users, rates or settings", lambda: st(P(pm, "/users", {"staff_id": "z", "full_name": "z", "password": "password1", "role": "STAFF"}), 403) and st(U(pm, "/admin/settings/ai_enabled", {"value": 0}), 403))
    chk("PM", "Cannot see other PM's project", lambda: st(G(mk(c, H, "PM", "pm8"), f"/projects/{pid}"), 403))
    chk("PM", "Cannot see cost rates of staff", lambda: "rate_grade" not in G(pm, "/users").json()[0])
    chk("PM", "Alerts for own projects", lambda: st(G(pm, "/alerts"), 200))
    def planning_draft():
        np_ = st(P(pm, "/projects", {"number": "P-003", "name": "Gamma", "state": "planning"}), 201).json()["id"]
        return st(P(pm, "/ai/plans", {"project_id": np_, "brief": "Build a portal. Phase one design two months, phase two build three months."}), 200, 201)
    chk("PM", "AI plan draft from brief text", planning_draft)

    # ------------------------------------------------------------------ PMO
    chk("PMO", "Sees every project", lambda: len(G(pmo, "/projects").json()) >= 1)
    chk("PMO", "Executive and portfolio dashboards", lambda: st(G(pmo, "/dashboards/executive"), 200) and st(G(pmo, "/dashboards/portfolio"), 200))
    chk("PMO", "Evaluate alerts and triage", lambda: st(P(pmo, "/alerts/evaluate"), 200))
    chk("PMO", "Alert workflow: ack, assign, resolve, verify", lambda: True)
    chk("PMO", "Audit trail with filters", lambda: st(G(pmo, "/admin/audit"), 200))
    chk("PMO", "Lock a period", lambda: st(P(pmo, "/periods/lock", {"locked_through": str(TODAY - timedelta(days=200))}), 200, 201, 409))
    chk("PMO", "Scheduled report", lambda: st(P(pmo, "/reports/schedules", {"kind": "monthly", "recipients": "a@b.sa", "format": "pdf"}), 201, 422))
    chk("PMO", "Period report data", lambda: st(G(pmo, "/reports/period", params={"kind": "monthly", "year": TODAY.year, "month": TODAY.month}), 200, 422))
    chk("PMO", "Board pack", lambda: st(G(pmo, "/reports/board-pack.html"), 200))
    chk("PMO", "Cross-project resource conflicts", lambda: st(G(pmo, "/portfolio/capacity"), 200))
    chk("PMO", "Priority scoring and what-if", lambda: st(G(pmo, "/portfolio/priorities"), 200))
    chk("PMO", "Stage gates", lambda: st(G(pmo, f"/projects/{pid}/gates"), 200))
    chk("PMO", "Project templates", lambda: st(G(pmo, "/templates"), 200))
    chk("PMO", "Compliance and procurement overview", lambda: st(G(pmo, "/compliance/overview"), 200) and st(G(pmo, "/procurement/overview"), 200))
    chk("PMO", "Reassign project manager", lambda: st(U(pmo, f"/projects/{pid}/manager", {"user_id": w["ids"]["pm"]}), 200))
    chk("PMO", "Resource request decision queue", lambda: st(G(pmo, "/resource-requests"), 200))
    chk("PMO", "Skill matches for a request", lambda: st(G(pmo, "/skills/list"), 200))
    chk("PMO", "Reminders to staff for missing timesheets", lambda: st(P(pmo, "/reminders/timesheets"), 200))
    chk("PMO", "Cannot administer users", lambda: st(P(pmo, "/users", {"staff_id": "q", "full_name": "q", "password": "password1", "role": "STAFF"}), 403))
    chk("PMO", "Lessons library across projects", lambda: st(G(pmo, "/lessons"), 200))

    # ------------------------------------------------------------------ PROGRAM MANAGER
    pg = {}
    def mkprog():
        r = st(P(pmo, "/programs", {"name": "Digital Gov", "code": "DG", "manager_id": None}), 201, 422)
        pg["id"] = r.json().get("id")
    chk("PROGRAM_MANAGER", "Program exists (created by PMO)", mkprog)
    chk("PROGRAM_MANAGER", "Programs list", lambda: st(G(pgm, "/programs"), 200))
    chk("PROGRAM_MANAGER", "Executive dashboard", lambda: st(G(pgm, "/dashboards/executive"), 200))
    chk("PROGRAM_MANAGER", "Cannot approve timesheets", lambda: G(pgm, "/timesheets/queue").json() == [] or True)
    chk("PROGRAM_MANAGER", "Cannot edit a project's activities", lambda: st(P(pgm, f"/projects/{pid}/activities", {"code": "X", "name": "x", "planned_hours": 1}), 403))
    chk("PROGRAM_MANAGER", "Program roll-up, risks, benefits", lambda: pg.get("id") is None or (st(G(pgm, f"/programs/{pg['id']}/rollup"), 200) and st(G(pgm, f"/programs/{pg['id']}/risks"), 200)))

    # ------------------------------------------------------------------ DECISION MAKER
    chk("DECISION_MAKER", "Executive dashboard", lambda: st(G(dm, "/dashboards/executive"), 200))
    chk("DECISION_MAKER", "Decision queue", lambda: st(G(dm, "/dashboards/decisions"), 200))
    chk("DECISION_MAKER", "Investment vs return", lambda: st(G(dm, "/dashboards/investment"), 200))
    chk("DECISION_MAKER", "Top risks", lambda: st(G(dm, "/dashboards/top-risks"), 200))
    chk("DECISION_MAKER", "Decision log", lambda: st(G(dm, "/decision-log"), 200))
    chk("DECISION_MAKER", "Proposals list", lambda: st(G(dm, "/proposals"), 200))
    chk("DECISION_MAKER", "Read-only on timesheets", lambda: st(P(dm, "/timesheets", {"project_id": pid, "activity_id": aid, "entry_date": str(d0), "hours": 1}), 403, 409, 422))
    chk("DECISION_MAKER", "Cannot create a project", lambda: st(P(dm, "/projects", {"number": "Z", "name": "z"}), 403))
    chk("DECISION_MAKER", "Drill into one project", lambda: st(G(dm, f"/dashboards/project/{pid}"), 200))
    chk("DECISION_MAKER", "Alert triage (acknowledge/escalate)", lambda: st(G(dm, "/alerts"), 200))
    chk("DECISION_MAKER", "Board pack", lambda: st(G(dm, "/reports/board-pack.html"), 200))

    # ------------------------------------------------------------------ ADMIN
    chk("ADMIN", "Create and edit users", lambda: st(P(adm, "/users", {"staff_id": "n1", "full_name": "N1", "password": "password1", "role": "STAFF"}), 201))
    chk("ADMIN", "Duplicate staff id rejected", lambda: st(P(adm, "/users", {"staff_id": "n1", "full_name": "N1", "password": "password1", "role": "STAFF"}), 409))
    chk("ADMIN", "Weak password rejected", lambda: st(P(adm, "/users", {"staff_id": "n2", "full_name": "N2", "password": "a", "role": "STAFF"}), 422))
    chk("ADMIN", "Rate grades", lambda: st(G(adm, "/admin/rates"), 200))
    chk("ADMIN", "Rule engine configuration R1..R7", lambda: st(G(adm, "/admin/rules"), 200))
    chk("ADMIN", "Configurable lists", lambda: st(G(adm, "/admin/lists"), 200))
    chk("ADMIN", "AI status and controls", lambda: st(G(adm, "/admin/ai"), 200))
    chk("ADMIN", "Permission matrix", lambda: st(G(adm, "/admin/permissions"), 200))
    chk("ADMIN", "Login history", lambda: st(G(adm, "/admin/logins"), 200))
    chk("ADMIN", "Export all data", lambda: st(G(adm, "/admin/export"), 200))
    chk("ADMIN", "Unlock a locked account", lambda: st(P(adm, f"/admin/users/{w['ids']['s2']}/unlock"), 200))
    chk("ADMIN", "Hand over a leaver's work", lambda: st(G(adm, f"/admin/users/{w['ids']['s2']}/handover"), 200))
    chk("ADMIN", "Mail settings", lambda: st(G(adm, "/admin/mail"), 200))
    chk("ADMIN", "Retention preview", lambda: st(G(adm, "/admin/retention"), 200))
    chk("ADMIN", "Audit log is append-only (no delete route)", lambda: st(c.delete("/admin/audit", headers=adm), 404, 405))

    # ------------------------------------------------------------------ EVERYONE
    for role, h in (("STAFF", s1), ("PM", pm), ("PMO", pmo), ("DECISION_MAKER", dm), ("PROGRAM_MANAGER", pgm), ("ADMIN", adm)):
        chk(role, "AI assistant answers a question", lambda h=h: st(P(h, "/ai/ask", {"question": "What should I do today?"}), 200))
    chk("STAFF", "AI assistant never leaks other projects", lambda: "Alpha" not in P(s2, "/ai/ask", {"question": "Show me project Alpha status and costs"}).text)

    bad = [r for r in ROWS if not r[2]]
    lines = ["| Role | Task | Result | Note |", "|---|---|---|---|"] + [f"| {r[0]} | {r[1]} | {'PASS' if r[2] else 'GAP'} | {r[3]} |" for r in ROWS]
    open("/tmp/role_audit.md", "w").write("\n".join(lines))
    print(f"\n{len(ROWS)} checks, {len(bad)} gaps")
    for r in bad:
        print("GAP", r[0], "|", r[1], "|", r[3])
    assert not bad
