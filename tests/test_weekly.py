from datetime import timedelta

from app import rules
from tests.test_flow import TODAY, app, c, entry, world  # noqa: F401


def test_week_submit_reminders_leave(c, world):
    w, h = world, world["h"]
    s1, pmo, pm = h["s1"], h["pmo1"], h["pm1"]
    last = rules.week_start(TODAY, True) - timedelta(days=7)
    wk = c.get(f"/me/week?week_of={last}", headers=s1).json()
    assert len(wk["missing_days"]) == 5 and not wk["submitted"]
    assert c.post("/me/week/submit", headers=s1, json={"week_of": str(last)}).status_code == 422
    assert c.post("/me/week/submit", headers=s1, json={"week_of": str(last + timedelta(days=21))}).status_code == 422
    todo = c.get("/me/todo", headers=s1).json()
    assert todo["week_due"]["week_start"] == str(last)
    # reminders: PMO only; s1 gets one
    assert c.post("/reminders/timesheets", headers=s1).status_code == 403
    assert c.post("/reminders/timesheets", headers=pmo).json()["sent"] >= 1
    assert any(n["kind"] == "timesheet.reminder" for n in c.get("/notifications", headers=s1).json())
    team = c.get("/timesheets/weeks", headers=pm).json()
    assert any(r["user_id"] == w["ids"]["s1"] and not r["submitted"] for r in team["staff"])
    # submit with a note explaining gaps
    r = c.post("/me/week/submit", headers=s1, json={"week_of": str(last), "note": "Was at a workshop"})
    assert r.status_code == 200 and r.json()["submitted"]["note"] == "Was at a workshop"
    assert c.get("/me/todo", headers=s1).json()["week_due"] is None
    # leave: request, overlap refused, PMO approves, capacity drops
    nxt = rules.week_start(TODAY, True) + timedelta(days=14)
    lv = c.post("/leave", headers=s1, json={"start": str(nxt), "end": str(nxt + timedelta(days=1)), "kind": "annual"})
    assert lv.status_code == 201 and lv.json()["working_days"] == 2
    assert c.post("/leave", headers=s1, json={"start": str(nxt + timedelta(days=1)), "end": str(nxt + timedelta(days=2))}).status_code == 409
    assert c.post(f"/leave/{lv.json()['id']}/decision", headers=s1, json={"approve": True}).status_code == 403
    assert c.post(f"/leave/{lv.json()['id']}/decision", headers=pmo, json={"approve": False}).status_code == 422
    assert any(x["id"] == lv.json()["id"] for x in c.get("/leave/queue", headers=pmo).json())
    assert c.post(f"/leave/{lv.json()['id']}/decision", headers=pmo, json={"approve": True}).json()["status"] == "approved"
    cal = c.get(f"/leave/calendar?start={nxt}", headers=pm).json()
    assert cal and cal[0]["status"] == "approved"
    # the planned leave days count as covered in that week
    c.post("/timesheets", headers=s1, json=entry(w, entry_date=str(TODAY - timedelta(days=1)), hours=1))
    wk2 = c.get(f"/me/week?week_of={nxt}", headers=s1).json()
    assert [d["off"] for d in wk2["days"]].count("leave") == 2
    assert c.delete(f"/leave/{lv.json()['id']}", headers=s1).json()["status"] == "cancelled"
