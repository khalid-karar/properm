from datetime import timedelta

from app import rules
from tests.test_flow import TODAY, app, c, world  # noqa: F401


def test_priorities_capacity_compliance(c, world):
    w, h = world, world["h"]
    pmo, pid = h["pmo1"], w["pid"]
    assert c.get("/portfolio/priorities", headers=h["s1"]).status_code == 403
    rows = c.get("/portfolio/priorities", headers=pmo).json()
    assert any(r["id"] == pid and r["score"] is None for r in rows)
    assert c.put(f"/portfolio/scores/{pid}", headers=h["pm1"], json={"strategic_fit": 5, "value": 5, "urgency": 5, "risk_level": 1}).status_code == 403
    r = c.put(f"/portfolio/scores/{pid}", headers=pmo, json={"strategic_fit": 5, "value": 5, "urgency": 5, "risk_level": 1}).json()
    assert r["score"] == 100
    rows = c.get("/portfolio/priorities", headers=pmo).json()
    assert rows[0]["id"] == pid and rows[0]["rank"] == 1
    # capacity: plan more than one person can do next week, see it flagged
    nxt = rules.week_start(TODAY, True) + timedelta(days=7)
    assert c.put(f"/projects/{pid}/allocations", headers=h["pm1"], json={"user_id": w["ids"]["s1"], "week_of": str(nxt), "hours": 60}).status_code == 200
    cap = c.get("/portfolio/capacity?group=person&weeks=4", headers=pmo).json()
    assert len(cap["weeks"]) == 4 and cap["groups"]
    assert any(o["week_start"] == str(nxt) and o["demand"] == 60 for o in cap["over_allocated"])
    assert c.get("/portfolio/capacity?group=bogus", headers=pmo).status_code == 422
    comp = c.get("/portfolio/compliance", headers=pmo).json()
    assert comp["managers"] and "rating" in comp["managers"][0]
    assert c.get("/portfolio/compliance", headers=h["pm1"]).status_code == 403
