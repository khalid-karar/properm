from datetime import timedelta

from tests.test_flow import TODAY, app, c, entry, world  # noqa: F401


def post(c, w, who, **kw):
    r = c.post("/timesheets", headers=w["h"][who], json=entry(w, **kw))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_workflow(c, world):
    w, h = world, world["h"]
    pm, s1, s2 = h["pm1"], h["s1"], h["s2"]
    d1, d2, d3 = (str(TODAY - timedelta(days=n)) for n in (1, 2, 3))
    a, b, cc = post(c, w, "s1", entry_date=d1, hours=2), post(c, w, "s1", entry_date=d2, hours=2), post(c, w, "s1", entry_date=d3, hours=2)
    # withdraw: own pending entry yes, someone else's no
    assert c.delete(f"/timesheets/{cc}", headers=s2).status_code == 404
    assert c.delete(f"/timesheets/{cc}", headers=s1).status_code == 204
    # filtered queue
    q = c.get("/timesheets/queue/filtered", headers=pm).json()
    ids = {e["id"] for e in q}
    assert {a, b} <= ids and cc not in ids
    only = c.get(f"/timesheets/queue/filtered?user_id={w['ids']['s1']}", headers=pm).json()
    assert {e["id"] for e in only} <= ids and all(e["user_id"] == w["ids"]["s1"] for e in only)
    # bulk approve: one good, one missing, one own-entry
    r = c.post("/timesheets/bulk-decision", headers=pm, json={"ids": [a, b, 999999], "action": "approve"}).json()
    assert set(r["done"]) == {a, b} and r["failed"][0]["id"] == 999999
    again = c.post("/timesheets/bulk-decision", headers=pm, json={"ids": [a], "action": "approve"}).json()
    assert again["done"] == [] and "already" in again["failed"][0]["error"]
    assert c.post("/timesheets/bulk-decision", headers=pm, json={"ids": [a], "action": "reject"}).status_code == 422
    assert c.post("/timesheets/bulk-decision", headers=pm, json={"ids": [a], "action": "adjust"}).status_code == 422
    # approved entries cannot be withdrawn; history lists them
    assert c.delete(f"/timesheets/{a}", headers=s1).status_code == 409
    hist = c.get("/timesheets/decided", headers=pm).json()
    assert {a, b} <= {e["id"] for e in hist}
    assert c.get("/timesheets/decided?status=rejected", headers=pm).json() == []
    # rejection shows in staff to-do; withdraw a rejected entry works
    e = post(c, w, "s1", entry_date=str(TODAY - timedelta(days=4)), hours=1)
    assert c.post(f"/timesheets/{e}/decision", headers=pm, json={"action": "reject", "reason": "wrong activity"}).status_code == 200
    td = c.get("/me/todo", headers=s1).json()
    assert any(x["id"] == e and x["decision_reason"] == "wrong activity" for x in td["rejected_entries"]) and td["total"] >= 1
    assert c.delete(f"/timesheets/{e}", headers=s1).status_code == 204
    assert c.get("/me/todo", headers=s1).json()["rejected_entries"] == []
    # hints
    hnt = c.get(f"/timesheets/hints?project_id={w['pid']}&activity_id={w['aid']}", headers=s1).json()
    assert hnt["used"] >= 4 and hnt["cap"] is not None and hnt["hard_limit"] >= hnt["cap"]
    assert c.get(f"/timesheets/hints?project_id={w['pid']}&activity_id=99999", headers=s1).status_code == 404
