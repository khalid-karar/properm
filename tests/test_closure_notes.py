"""Closing a risk or issue needs a note; it is recorded with who and when; reopening needs a reason."""
from tests.test_flow import TODAY, app, c, entry, login, mkuser, world   # noqa: F401


def test_close_needs_note_and_is_traced(c, world):
    h, pid = world["h"], world["pid"]
    pm = h["pm1"]
    rid = c.post(f"/projects/{pid}/risks", headers=pm, json={"title": "Vendor delay", "probability": 3, "impact": 3}).json()["id"]
    assert c.patch(f"/projects/{pid}/risks/{rid}", headers=pm, json={"status": "closed"}).status_code == 422
    assert c.post(f"/projects/{pid}/risks/{rid}/close", headers=pm, json={"what_happened": "x", "how_handled": "", "outcome": ""}).status_code == 422
    ok = c.post(f"/projects/{pid}/risks/{rid}/close", headers=pm, json={"what_happened": "Vendor was late by 2 weeks", "how_handled": "Moved the test window", "outcome": "No impact on go-live", "lesson": True})
    assert ok.status_code == 200 and ok.json()["status"] == "closed"
    assert c.post(f"/projects/{pid}/risks/{rid}/close", headers=pm, json={"what_happened": "again", "how_handled": "again", "outcome": "again"}).status_code == 409
    assert c.post(f"/projects/{pid}/risks/{rid}/reopen", headers=pm, json={"reason": ""}).status_code == 422
    assert c.post(f"/projects/{pid}/risks/{rid}/reopen", headers=h["s1"], json={"reason": "it came back"}).status_code == 403
    assert c.post(f"/projects/{pid}/risks/{rid}/reopen", headers=pm, json={"reason": "The vendor slipped again"}).status_code == 200
    log = c.get(f"/projects/{pid}/closures", headers=pm).json()
    assert [n["event"] for n in log] == ["closed", "reopened"]
    assert log[0]["lesson"] is True and log[0]["by"] and log[0]["at"] and log[1]["reason"] == "The vendor slipped again"
    assert c.get(f"/projects/{pid}/risks", headers=pm).json()[-1]["status"] == "open"
