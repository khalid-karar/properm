import base64
from datetime import timedelta

from tests.test_flow import TODAY, app, c, world  # noqa: F401
from tests.test_gates import mk


def b64(x):
    return base64.b64encode(x).decode()


def test_risk_response_and_opportunities(c, world):
    h, pid = world["h"], world["pid"]
    pm, s1 = h["pm1"], h["s1"]
    rk = c.post(f"/projects/{pid}/risks", headers=pm, json={"title": "Vendor insolvency", "probability": 4, "impact": 5}).json()
    rr = c.get(f"/projects/{pid}/risk-responses", headers=pm).json()
    assert rk["id"] in rr["without_response"]
    assert c.put(f"/projects/{pid}/risks/{rk['id']}/response", headers=pm, json={"strategy": "ignore"}).status_code == 422
    assert c.put(f"/projects/{pid}/risks/{rk['id']}/response", headers=pm, json={"strategy": "mitigate"}).status_code == 422
    assert c.put(f"/projects/{pid}/risks/{rk['id']}/response", headers=pm, json={"strategy": "mitigate", "plan": "Dual source", "residual_probability": 2}).status_code == 422
    assert c.put(f"/projects/{pid}/risks/{rk['id']}/response", headers=s1, json={"strategy": "accept"}).status_code == 403
    r = c.put(f"/projects/{pid}/risks/{rk['id']}/response", headers=pm, json={"strategy": "mitigate", "plan": "Dual source", "trigger": "Vendor misses two payments",
                                                                            "contingency_amount": 20000, "residual_probability": 2, "residual_impact": 4}).json()
    assert r["residual_score"] == 8 and r["score"] == 20 and r["needs_response"] is False
    rr = c.get(f"/projects/{pid}/risk-responses", headers=pm).json()
    assert rk["id"] not in rr["without_response"] and rr["residual_exposure"] < rr["exposure"]
    assert c.get(f"/projects/{pid}/risk-responses", headers=s1).json()["risks"][0]["contingency_amount"] is None     # staff do not see amounts
    o = c.post(f"/projects/{pid}/opportunities", headers=pm, json={"title": "Reuse the partner's test suite", "probability": 4, "impact": 3, "strategy": "exploit"}).json()
    assert o["score"] == 12
    assert c.post(f"/projects/{pid}/opportunities", headers=pm, json={"title": "x", "probability": 9}).status_code == 422
    assert c.delete(f"/projects/{pid}/risks/{rk['id']}/response", headers=pm).status_code == 204


def test_reserves(c, world):
    h, pid = world["h"], world["pid"]
    pm, pmo, s1 = h["pm1"], h["pmo1"], h["s1"]
    dm = mk(c, h, "DECISION_MAKER", "dmr")
    assert c.get(f"/projects/{pid}/reserves", headers=s1).status_code == 403
    assert c.put(f"/projects/{pid}/reserves", headers=pm, json={"contingency": 50000}).status_code == 403          # baseline already locked
    assert c.put(f"/projects/{pid}/reserves", headers=pmo, json={"contingency": 50000}).json()["contingency"] == 50000
    assert c.put(f"/projects/{pid}/reserves", headers=pm, json={"management": 100000}).status_code == 403
    assert c.put(f"/projects/{pid}/reserves", headers=dm, json={"management": 100000}).json()["management"] == 100000
    d = c.post(f"/projects/{pid}/reserves/drawdowns", headers=pm, json={"kind": "contingency", "amount": 20000, "reason": "Extra test cycle"}).json()
    assert d["contingency_remaining"] == 30000 and d["drawdowns"][0]["status"] == "approved"
    assert c.post(f"/projects/{pid}/reserves/drawdowns", headers=pm, json={"kind": "contingency", "amount": 40000, "reason": "too much"}).status_code == 409
    m = c.post(f"/projects/{pid}/reserves/drawdowns", headers=pm, json={"kind": "management", "amount": 60000, "reason": "Scope growth"}).json()
    assert m["management_remaining"] == 100000 and m["management_pending"] == 60000
    did = m["drawdowns"][0]["id"]
    assert c.post(f"/projects/{pid}/reserves/drawdowns/{did}/decision", headers=pm, json={"approve": True}).status_code == 403
    done = c.post(f"/projects/{pid}/reserves/drawdowns/{did}/decision", headers=dm, json={"approve": True}).json()
    assert done["management_remaining"] == 40000
    assert c.post(f"/projects/{pid}/reserves/drawdowns/{did}/decision", headers=dm, json={"approve": False}).status_code == 409


def test_quality_docs_engagement(c, world):
    h, pid = world["h"], world["pid"]
    pm, s1 = h["pm1"], h["s1"]
    q = c.post(f"/projects/{pid}/quality", headers=pm, json={"title": "Totals wrong on invoice", "severity": "high"}).json()
    c.post(f"/projects/{pid}/quality", headers=pm, json={"kind": "inspection", "title": "Peer review of design", "status": "closed"})
    assert c.patch(f"/projects/{pid}/quality/{q['id']}", headers=pm, json={"status": "verified"}).status_code == 409
    assert c.get(f"/projects/{pid}/quality-summary", headers=s1).json()["open_by_severity"]["high"] == 1
    assert c.patch(f"/projects/{pid}/quality/{q['id']}", headers=pm, json={"status": "fixed"}).status_code == 200
    assert c.patch(f"/projects/{pid}/quality/{q['id']}", headers=pm, json={"status": "closed"}).json()["closed_on"] == str(TODAY)
    assert c.get(f"/projects/{pid}/quality-summary", headers=pm).json()["closure_rate_pct"] == 100
    # document versions
    d = c.post(f"/projects/{pid}/documents", headers=pm, json={"kind": "other", "filename": "plan.txt", "content_b64": b64(b"v1")}).json()
    assert c.post(f"/projects/{pid}/documents/{d['id']}/versions", headers=s1, json={"filename": "plan.txt", "content_b64": b64(b"x")}).status_code == 403
    assert c.post(f"/projects/{pid}/documents/{d['id']}/versions", headers=pm, json={"filename": "plan.exe", "content_b64": b64(b"x")}).status_code == 422
    assert c.post(f"/projects/{pid}/documents/{d['id']}/versions", headers=pm, json={"filename": "plan.txt", "content_b64": b64(b"v2"), "note": "rev"}).json()["version"] == 2
    vs = c.get(f"/projects/{pid}/documents/{d['id']}/versions", headers=s1).json()
    assert [v["version"] for v in vs] == [2, 1] and vs[0]["current"]
    assert base64.b64decode(c.get(f"/projects/{pid}/documents/{d['id']}/versions/{vs[1]['id']}/content", headers=pm).json()["content_b64"]) == b"v1"
    assert base64.b64decode(c.get(f"/projects/{pid}/documents/{d['id']}/content", headers=pm).json()["content_b64"]) == b"v2"
    assert next(x for x in c.get(f"/projects/{pid}/documents", headers=pm).json() if x["id"] == d["id"])["version"] == 2
    # stakeholder engagement
    st = c.post(f"/projects/{pid}/stakeholders", headers=pm, json={"name": "Dr. Salem", "power": 5, "interest": 4}).json()
    sid = st["id"]
    assert c.put(f"/projects/{pid}/stakeholders/{sid}/engagement", headers=pm, json={"current": "resistant", "desired": "supportive"}).status_code == 422
    e = c.put(f"/projects/{pid}/stakeholders/{sid}/engagement", headers=pm, json={"current": "resistant", "desired": "supportive", "plan": "Monthly 1:1 with the sponsor"}).json()
    assert e["gap"] == 2
    assert c.put(f"/projects/{pid}/stakeholders/{sid}/engagement", headers=pm, json={"current": "fan", "desired": "supportive"}).status_code == 422
    assert c.get(f"/projects/{pid}/engagement", headers=s1).json()[0]["gap"] == 2
