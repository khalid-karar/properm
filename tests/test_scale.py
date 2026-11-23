from datetime import date, timedelta

from app.models import TimesheetEntry
from tests.test_flow import TODAY, app, c, world  # noqa: F401


def test_lists_are_capped_and_windowed(app, c, world):
    h, ids, pid = world["h"], world["ids"], world["pid"]
    old = TODAY - timedelta(days=400)
    with app.state.Session() as db:
        db.bulk_save_objects([TimesheetEntry(user_id=ids["s1"], project_id=pid, entry_date=old - timedelta(days=i), hours=4, status="submitted", flags=[]) for i in range(350)]
                             + [TimesheetEntry(user_id=ids["s1"], project_id=pid, entry_date=TODAY - timedelta(days=1), hours=2, status="approved", flags=[])])
        db.commit()
    mine = c.get("/timesheets/mine", headers=h["s1"]).json()
    assert all(e["entry_date"] >= str(TODAY - timedelta(days=91)) for e in mine)                  # default window: last 90 days, not every entry ever
    assert len(c.get("/timesheets/mine", params={"start": str(old - timedelta(days=400)), "limit": 50}, headers=h["s1"]).json()) == 50
    q = c.get("/timesheets/queue", headers=h["pmo1"]).json()
    assert len(q) == 300                                                                          # capped; the rest show up as these are decided
    assert len(c.get("/timesheets/queue", params={"limit": 20}, headers=h["pmo1"]).json()) == 20
    assert len(c.get("/timesheets/queue/filtered", headers=h["pmo1"]).json()) == 300
    assert q[0]["entry_date"] <= q[-1]["entry_date"]                                              # oldest first
