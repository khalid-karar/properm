from datetime import date, timedelta

from tests.test_flow import TODAY, app, c, entry, login, mkuser, world   # noqa: F401
from tests.test_slice2 import costed                                      # noqa: F401


def test_closure_checklist_gates_archiving(c, world):
    h, pid = world["h"], world["pid"]
    assert c.get(f"/projects/{pid}/closure", headers=h["pm1"]).status_code == 409           # not closing yet
    assert c.post(f"/projects/{pid}/transition", headers=h["pm1"], json={"to_state": "closing"}).status_code == 200
    cl = c.get(f"/projects/{pid}/closure", headers=h["pm1"]).json()
    assert len(cl["items"]) == 8 and cl["ready"] is False
    assert c.post(f"/projects/{pid}/transition", headers=h["pmo1"], json={"to_state": "archived"}).status_code == 409
    assert c.put(f"/projects/{pid}/closure/timesheets_approved", headers=h["pm1"], json={"done": True}).status_code == 409   # system-checked
    assert c.put(f"/projects/{pid}/closure/nonsense", headers=h["pm1"], json={"done": True}).status_code == 404
    assert c.put(f"/projects/{pid}/closure/lessons_learned", headers=h["s1"], json={"done": True}).status_code == 403
    # an open issue blocks the system-checked item
    c.post(f"/projects/{pid}/issues", headers=h["pm1"], json={"title": "Blocker", "severity": "high"})
    for k in ("deliverables_accepted", "costs_reconciled", "risks_reviewed", "lessons_learned", "documents_archived", "benefits_handover"):
        assert c.put(f"/projects/{pid}/closure/{k}", headers=h["pm1"], json={"done": True, "note": "ok"}).status_code == 200
    cl = c.get(f"/projects/{pid}/closure", headers=h["pm1"]).json()
    assert cl["ready"] is False and next(i for i in cl["items"] if i["key"] == "issues_closed")["satisfied"] is False
    r = c.post(f"/projects/{pid}/transition", headers=h["pmo1"], json={"to_state": "archived"})
    assert r.status_code == 409 and "issues_closed" in r.text
    issue = c.get(f"/projects/{pid}/issues", headers=h["pm1"]).json()[0]
    assert c.patch(f"/projects/{pid}/issues/{issue['id']}", headers=h["pm1"], json={"status": "closed"}).status_code == 422      # a bare status flip is refused
    assert c.post(f"/projects/{pid}/issues/{issue['id']}/close", headers=h["pm1"], json={"what_happened": "It happened", "how_handled": "We fixed it", "outcome": "Resolved fully"}).status_code == 200
    assert c.get(f"/projects/{pid}/closure", headers=h["pm1"]).json()["ready"] is True
    assert c.post(f"/projects/{pid}/transition", headers=h["pmo1"], json={"to_state": "archived"}).status_code == 200


def test_benefits_register(c, world):
    h, pid = world["h"], world["pid"]
    r = c.post(f"/projects/{pid}/benefits", headers=h["pm1"], json={"title": "Cut processing time", "metric": "days", "unit": "days", "baseline": 10, "target": 4, "actual": 7, "status": "on_track"})
    assert r.status_code == 201 and r.json()["realization_pct"] == 50.0                       # (7-10)/(4-10)
    bid = r.json()["id"]
    assert c.patch(f"/projects/{pid}/benefits/{bid}", headers=h["pm1"], json={"actual": 4, "status": "realized"}).json()["realization_pct"] == 100.0
    assert c.post(f"/projects/{pid}/benefits", headers=h["pm1"], json={"title": "x", "status": "magic"}).status_code == 422
    assert c.post(f"/projects/{pid}/benefits", headers=h["s1"], json={"title": "x"}).status_code == 403   # assigned staff may read, not write
    assert len(c.get(f"/projects/{pid}/benefits", headers=h["s1"]).json()) == 1
    assert c.get(f"/projects/{pid}/benefits", headers=h["s2"]).status_code == 403                     # unassigned staff
    assert c.patch(f"/projects/{pid}/benefits/9999", headers=h["pm1"], json={"actual": 1}).status_code == 404


def test_programs_group_and_roll_up(c, costed):
    h, pid, cpid = costed["h"], costed["pid"], costed["cpid"]
    assert c.post("/programs", headers=h["pm1"], json={"code": "PG1", "name": "Digital"}).status_code == 403
    g = c.post("/programs", headers=h["pmo1"], json={"code": "PG1", "name": "Digital"})
    assert g.status_code == 201
    gid = g.json()["id"]
    assert c.post("/programs", headers=h["pmo1"], json={"code": "PG1", "name": "dup"}).status_code == 409
    assert c.put(f"/projects/{cpid}/program", headers=h["pm1"], json={"program_id": gid}).status_code == 403
    assert c.put(f"/projects/{cpid}/program", headers=h["pmo1"], json={"program_id": gid}).status_code == 200
    assert c.put(f"/projects/{pid}/program", headers=h["pmo1"], json={"program_id": gid}).status_code == 200
    assert c.put(f"/projects/{pid}/program", headers=h["pmo1"], json={"program_id": 999}).status_code == 404
    c.post(f"/projects/{cpid}/benefits", headers=h["pm1"], json={"title": "B", "baseline": 0, "target": 10, "actual": 5})
    d = c.get(f"/programs/{gid}/dashboard", headers=h["pmo1"]).json()
    assert len(d["projects"]) == 2 and sum(d["rag_counts"].values()) == 2
    assert d["benefits"]["count"] == 1 and d["benefits"]["avg_realization_pct"] == 50.0
    assert d["evm"]["available"] is True and d["evm"]["BAC"] == 100000.0
    assert c.get(f"/programs/{gid}/dashboard", headers=h["pm1"]).status_code == 403
    assert c.get("/programs", headers=h["s1"]).status_code == 403
    assert c.get(f"/projects/{cpid}", headers=h["pm1"]).json()["program_id"] == gid


def test_work_calendar_holidays_weekend_and_capacity(c, world):
    h = world["h"]
    ws = TODAY - timedelta(days=(TODAY.weekday() + 1) % 7 + 14)           # a Sunday two weeks ago
    hol = ws + timedelta(days=1)                                          # Monday
    assert c.post("/calendar/holidays", headers=h["pm1"], json={"day": str(hol), "name": "Founding Day"}).status_code == 403
    r = c.post("/calendar/holidays", headers=h["pmo1"], json={"day": str(hol), "name": "Founding Day"})
    assert r.status_code == 201
    assert c.post("/calendar/holidays", headers=h["pmo1"], json={"day": str(hol), "name": "again"}).status_code == 409
    wk = c.get(f"/calendar/week?week_of={ws}", headers=h["s1"]).json()
    assert wk["working_days"] == 4 and abs(wk["factor"] - 0.8) < 1e-9 and str(hol) in wk["holidays"]
    # capacity for that week is 32h: 33h is over capacity (warning), 32h is not
    for d in (0, 2, 3, 4):                                                # Sun, Tue, Wed, Thu: 4 x 8h = 32h
        assert c.post("/timesheets", headers=h["s1"], json=entry(world, entry_date=str(ws + timedelta(days=d)), hours=8)).status_code == 201
    over = c.post("/timesheets", headers=h["s1"], json=entry(world, entry_date=str(ws), hours=1))
    assert over.status_code == 422 and "33/32" in over.text              # 33h > 32h capacity in a holiday week
    # an entry on the holiday itself is recorded with an R10 flag but not blocked
    ws2 = ws - timedelta(days=7)                                          # another week, so capacity is not the issue
    hol2 = ws2 + timedelta(days=1)
    assert c.post("/calendar/holidays", headers=h["pmo1"], json={"day": str(hol2), "name": "Eid"}).status_code == 201
    on_hol = c.post("/timesheets", headers=h["s1"], json=entry(world, entry_date=str(hol2), hours=4))
    assert on_hol.status_code == 201 and "R10" in str(on_hol.json())
    # weekend work is flagged the same way
    fri = ws2 + timedelta(days=5)
    wkd = c.post("/timesheets", headers=h["s1"], json=entry(world, entry_date=str(fri), hours=2))
    assert wkd.status_code == 201 and "R10" in str(wkd.json())
    assert c.delete(f"/calendar/holidays/{r.json()['id']}", headers=h["pmo1"]).status_code == 204
    assert c.get(f"/calendar/week?week_of={ws}", headers=h["s1"]).json()["working_days"] == 5
