"""Tendering stage: scorecard, estimate, capacity gap, checklist, submit, win / lose."""
import base64

from tests.test_brief import AR_BOOK
from tests.test_flow import TODAY, app, c, entry, login, mkuser, world   # noqa: F401


def mk(c, h, number):
    body = {"filename": "book.txt", "content_b64": base64.b64encode(AR_BOOK.encode()).decode()}
    pv = c.post("/project-intake/book/preview", headers=h["pm1"], json=body).json()
    r = c.post("/project-intake/book/confirm", headers=h["pm1"], json={**body, "number": number, "name": "Bid " + number, "planned_start": pv["planned_start"], "planned_end": pv["planned_end"], "state": "tendering"})
    assert r.status_code == 201, r.text
    return r.json()["project_id"]


def test_tender_flow_win(c, world):
    h = world["h"]
    pid = mk(c, h, "TND-W")
    u = f"/projects/{pid}/tender"
    t = c.get(u, headers=h["pm1"]).json()
    assert t["estimate"]["available"] and t["estimate"]["hours"] > 0 and t["capacity"]["available"] and t["review"]["available"] and t["scorecard"]["pct"] is None
    assert t["checklist_total"] == 8 and t["decision"] == "open"
    # decision needs a complete scorecard and the right role
    assert c.post(u + "/decision", headers=h["pmo1"], json={"decision": "go"}).status_code == 422
    assert c.post(u + "/decision", headers=h["pm1"], json={"decision": "go"}).status_code == 403
    scores = {k: {"score": 4, "note": "ok"} for k in ("strategic_fit", "capability", "capacity", "margin", "client", "competition", "delivery_risk")}
    assert c.patch(u, headers=h["pm1"], json={"scores": {"bogus": {"score": 3}}}).status_code == 422
    assert c.patch(u, headers=h["pm1"], json={"scores": {"margin": {"score": 9}}}).status_code == 422
    t = c.patch(u, headers=h["pm1"], json={"scores": scores, "deadline": str(TODAY), "margin_pct": 25}).json()
    assert t["scorecard"]["pct"] == 80.0 and t["scorecard"]["recommendation"] == "go" and t["days_to_deadline"] == 0 and t["estimate"]["margin_pct"] == 25
    # cannot submit before go or without the checklist
    assert c.post(u + "/submit", headers=h["pm1"]).status_code == 409
    assert c.post(u + "/decision", headers=h["pmo1"], json={"decision": "go"}).status_code == 200
    assert c.post(u + "/submit", headers=h["pm1"]).status_code == 409
    assert c.post(u + "/outcome", headers=h["pm1"], json={"outcome": "won"}).status_code == 409           # not submitted
    keys = [i["key"] for i in t["checklist"]]
    c.patch(u, headers=h["pm1"], json={"checklist": {k: {"done": True} for k in keys}})
    assert c.post(u + "/submit", headers=h["pm1"]).json()["submitted_at"]
    out = c.post(u + "/outcome", headers=h["pm1"], json={"outcome": "won", "note": "Awarded"})
    assert out.status_code == 200 and out.json()["outcome"] == "won"
    assert [p for p in c.get("/projects", headers=h["pm1"]).json() if p["id"] == pid][0]["state"] == "planning"


def test_tender_lost_and_no_go(c, world):
    h = world["h"]
    pid = mk(c, h, "TND-L")
    u = f"/projects/{pid}/tender"
    c.patch(u, headers=h["pm1"], json={"scores": {k: {"score": 1} for k in ("strategic_fit", "capability", "capacity", "margin", "client", "competition", "delivery_risk")}})
    assert c.get(u, headers=h["pm1"]).json()["scorecard"]["recommendation"] == "no_go"
    assert c.post(u + "/decision", headers=h["pmo1"], json={"decision": "go"}).status_code == 422            # going against the scorecard needs a reason
    assert c.post(u + "/decision", headers=h["pmo1"], json={"decision": "no_go"}).status_code == 422
    assert c.post(u + "/decision", headers=h["pmo1"], json={"decision": "no_go", "note": "Too thin on skills"}).json()["decision"] == "no_go"
    assert c.post(u + "/outcome", headers=h["pm1"], json={"outcome": "lost"}).status_code == 422
    r = c.post(u + "/outcome", headers=h["pm1"], json={"outcome": "lost", "note": "Not pursued: price too high"})
    assert r.status_code == 200
    assert [p for p in c.get("/projects", headers=h["pm1"]).json() if p["id"] == pid][0]["state"] == "archived"
