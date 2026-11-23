from datetime import timedelta

from tests.test_flow import TODAY, app, c, world  # noqa: F401
from tests.test_gates import mk


def test_contracts_payments_reviews(c, world):
    h, pid = world["h"], world["pid"]
    pm, pmo, s1 = h["pm1"], h["pmo1"], h["s1"]
    dm = mk(c, h, "DECISION_MAKER", "dmp")
    assert c.post(f"/projects/{pid}/contracts", headers=s1, json={"number": "C1", "title": "x", "vendor": "v"}).status_code == 403
    assert c.get(f"/projects/{pid}/contracts", headers=s1).status_code == 403          # staff do not see contract values
    assert c.post(f"/projects/{pid}/contracts", headers=pm, json={"number": "C1", "title": "Licences", "vendor": "Acme", "status": "active"}).status_code == 422
    k = c.post(f"/projects/{pid}/contracts", headers=pm, json={"number": "C1", "title": "Licences", "vendor": "Acme", "value": 100000, "status": "active",
                                                                "end_date": str(TODAY + timedelta(days=30))}).json()
    assert c.post(f"/projects/{pid}/contracts", headers=pm, json={"number": "C1", "title": "dup", "vendor": "v"}).status_code == 409
    p1 = c.post(f"/projects/{pid}/payments", headers=pm, json={"contract_id": k["id"], "name": "Kick-off", "amount": 30000, "due_date": str(TODAY - timedelta(days=3))}).json()
    assert p1["overdue"] is True
    assert c.post(f"/projects/{pid}/payments", headers=pm, json={"contract_id": k["id"], "name": "Too much", "amount": 80000}).status_code == 409
    p2 = c.post(f"/projects/{pid}/payments", headers=pm, json={"contract_id": k["id"], "name": "Go-live", "amount": 70000, "due_date": str(TODAY + timedelta(days=20))}).json()
    assert c.patch(f"/projects/{pid}/payments/{p1['id']}", headers=pm, json={"status": "invoiced"}).status_code == 422         # needs invoice no
    assert c.patch(f"/projects/{pid}/payments/{p1['id']}", headers=pm, json={"status": "paid", "invoice_no": "INV-1"}).status_code == 409   # invoiced first
    r = c.patch(f"/projects/{pid}/payments/{p1['id']}", headers=pm, json={"status": "invoiced", "invoice_no": "INV-1"}).json()
    assert r["invoiced_on"] == str(TODAY)
    assert c.patch(f"/projects/{pid}/payments/{p1['id']}", headers=pm, json={"status": "paid"}).json()["paid_on"] == str(TODAY)
    ks = c.get(f"/projects/{pid}/contracts", headers=pm).json()[0]
    assert ks["invoiced"] == 30000 and ks["paid"] == 30000 and ks["remaining"] == 70000 and ks["pct_invoiced"] == 30 and ks["unscheduled"] == 0 and ks["expires_in"] == 30
    assert c.patch(f"/projects/{pid}/contracts/{k['id']}", headers=pm, json={"value": 50000}).status_code == 409          # below scheduled milestones
    assert c.patch(f"/projects/{pid}/contracts/{k['id']}", headers=pm, json={"status": "completed"}).status_code == 409
    assert c.post(f"/projects/{pid}/vendor-reviews", headers=pm, json={"contract_id": k["id"], "review_date": str(TODAY), "quality": 6, "schedule": 3, "communication": 3}).status_code == 422
    c.post(f"/projects/{pid}/vendor-reviews", headers=pm, json={"contract_id": k["id"], "review_date": str(TODAY), "quality": 4, "schedule": 3, "communication": 5})
    assert c.get(f"/projects/{pid}/contracts", headers=pm).json()[0]["rating"] == 4.0
    ov = c.get("/procurement/overview", headers=dm).json()
    assert ov["total_value"] == 100000 and ov["expiring_soon"][0]["number"] == "C1" and ov["vendors"][0]["rating"] == 4.0
    assert c.get("/procurement/overview", headers=pm).status_code == 403
    assert c.delete(f"/projects/{pid}/payments/{p2['id']}", headers=pm).status_code == 204
    assert c.delete(f"/projects/{pid}/contracts/{k['id']}", headers=pm).status_code == 409
    k2 = c.post(f"/projects/{pid}/contracts", headers=pm, json={"number": "C2", "title": "Spare", "vendor": "Zed", "value": 10}).json()
    c.post(f"/projects/{pid}/payments", headers=pm, json={"contract_id": k2["id"], "name": "x", "amount": 5})
    assert c.delete(f"/projects/{pid}/contracts/{k2['id']}", headers=pm).status_code == 204
