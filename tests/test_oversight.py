from datetime import date, timedelta

from tests.test_flow import app, c, world  # noqa: F401


def test_audit_periods_rates(c, world):
    h = world["h"]
    pmo, pm, s1 = h["pmo1"], h["pm1"], h["s1"]
    assert c.get("/admin/audit", headers=s1).status_code == 403
    assert c.get("/admin/audit", headers=pm).status_code == 403
    r = c.get("/admin/audit?limit=5", headers=pmo).json()
    assert r["total"] > 0 and len(r["items"]) <= 5 and r["items"][0]["id"] > r["items"][-1]["id"]
    f = c.get("/admin/audit/facets", headers=pmo).json()
    assert f["actions"] and f["entities"]
    one = f["actions"][0]
    only = c.get(f"/admin/audit?action={one}", headers=pmo).json()
    assert only["items"] and all(i["action"].startswith(one) for i in only["items"])
    assert c.get("/admin/audit?date_from=2999-01-01", headers=pmo).json()["total"] == 0
    assert c.get("/admin/audit?limit=999", headers=pmo).status_code == 422
    # period status
    p = c.get("/timesheets/periods", headers=pmo).json()
    assert "pending_by_date" in p and "history" in p
    assert c.get("/timesheets/periods", headers=s1).status_code == 403
    # future rate can be removed, current cannot
    fut = date.today() + timedelta(days=30)
    rid = c.post("/admin/rates", json={"grade": "ZZ", "hourly_rate": 50, "effective_from": str(fut)}, headers=pmo).json()["id"]
    assert any(x["id"] == rid and x["future"] for x in c.get("/admin/rates", headers=pmo).json())
    assert c.delete(f"/admin/rates/{rid}", headers=pmo).status_code == 204
    cur = c.post("/admin/rates", json={"grade": "ZY", "hourly_rate": 50, "effective_from": str(date.today())}, headers=pmo).json()["id"]
    assert c.delete(f"/admin/rates/{cur}", headers=pmo).status_code == 409
    assert c.delete("/admin/rates/99999", headers=pmo).status_code == 404
