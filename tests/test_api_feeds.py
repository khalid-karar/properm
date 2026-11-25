import base64

from tests.test_flow import TODAY, app, c, world   # noqa: F401
from tests.test_slice2 import approved_hours, costed, progress   # noqa: F401


def _key(c, h, name="Power BI"):
    r = c.post("/admin/api-keys", headers=h["admin"], json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()


def _csv(text):
    return {"filename": "export.csv", "content_b64": base64.b64encode(text.encode()).decode()}


def test_key_created_once_listed_without_secret_and_revoked(c, costed):
    h = costed["h"]
    k = _key(c, h)
    assert k["key"].startswith("prm_") and k["prefix"] == k["key"][:8]
    listed = c.get("/admin/api-keys", headers=h["admin"]).json()
    assert listed and "key" not in listed[0] and "key_hash" not in listed[0]
    assert c.post("/admin/api-keys", headers=h["pm1"], json={"name": "nope"}).status_code == 403
    assert c.get("/api/v1/projects", headers={"X-API-Key": k["key"]}).status_code == 200
    assert c.delete(f"/admin/api-keys/{k['id']}", headers=h["admin"]).status_code == 200
    assert c.get("/api/v1/projects", headers={"X-API-Key": k["key"]}).status_code == 401


def test_feeds_need_a_key_and_a_user_token_is_not_enough(c, costed):
    h = costed["h"]
    assert c.get("/api/v1/projects").status_code == 401
    assert c.get("/api/v1/projects", headers=h["admin"]).status_code == 401
    assert c.get("/api/v1/projects", headers={"X-API-Key": "prm_wrong"}).status_code == 401


def test_feeds_return_data_json_and_csv(c, costed):
    h = costed["h"]
    approved_hours(c, costed, costed["a"], 14)
    progress(c, costed, 50, 25)
    k = {"X-API-Key": _key(c, h)["key"]}
    p = c.get("/api/v1/projects", headers=k).json()
    assert p["count"] >= 1 and any(r["number"] == "P-COST" for r in p["data"])
    e = c.get("/api/v1/evm", headers=k).json()["data"]
    assert any(r["number"] == "P-COST" and r["BAC"] == 100000 for r in e)
    f = c.get("/api/v1/forecast", headers=k).json()["data"]
    row = next(r for r in f if r["number"] == "P-COST")
    assert row["slip_days"] == 25 and row["forecast_cost"] is not None
    t = c.get("/api/v1/timesheets", headers=k, params={"date_from": str(TODAY.replace(year=TODAY.year - 1))}).json()
    assert t["count"] >= 1
    csv = c.get("/api/v1/evm?format=csv", headers=k)
    assert csv.headers["content-type"].startswith("text/csv") and csv.text.startswith("﻿project_id,number")
    assert c.get("/api/v1/evm?format=xml", headers=k).status_code == 422
    for name in ("costs", "alerts", "risks"):
        assert c.get(f"/api/v1/{name}", headers=k).status_code == 200


def test_key_sees_only_its_own_organisation(c, costed):
    h = costed["h"]
    t = c.post("/admin/tenants", headers=h["admin"], json={"name": "Other Org", "slug": "other"}).json()["id"]
    assert c.post(f"/admin/tenants/{t}/admins", headers=h["admin"], json={"staff_id": "oadmin", "full_name": "O", "password": "password1"}).status_code == 201
    tok = c.post("/auth/login", json={"staff_id": "oadmin", "password": "password1"}).json()["access_token"]
    oh = {"Authorization": f"Bearer {tok}"}
    ok = c.post("/admin/api-keys", headers=oh, json={"name": "other"}).json()["key"]
    other = c.get("/api/v1/projects", headers={"X-API-Key": ok}).json()
    assert other["count"] == 0
    mine = c.get("/api/v1/projects", headers={"X-API-Key": _key(c, h)["key"]}).json()
    assert mine["count"] >= 1


def test_cost_import_presets_preview_commit_and_duplicates(c, costed):
    h = costed["h"]
    sap = "WBS Element,Posting Date,Amount in Local Currency,Cost Element,Vendor,Document Number\nP-COST-01,2026-11-01,1500.50,Hardware,Acme,4900001\nP-COST,2026-11-02,200,Travel,,4900002\nNOPE,2026-11-02,5,x,,1\n"
    r = c.post("/import/costs?source=sap", headers=h["pmo1"], json=_csv(sap)).json()
    assert r["ok"] == 2 and r["errors"] == 1 and not r["committed"]
    assert r["matched_columns"]["amount"] == "amount_in_local_currency"
    blocked = c.post("/import/costs?source=sap", headers=h["pmo1"], json={**_csv(sap), "commit": True}).json()
    assert blocked["blocked"] and blocked["saved"] == 0
    done = c.post("/import/costs?source=sap", headers=h["pmo1"], json={**_csv(sap), "commit": True, "skip_errors": True}).json()
    assert done["saved"] == 2
    again = c.post("/import/costs?source=sap", headers=h["pmo1"], json={**_csv(sap), "commit": True, "skip_errors": True}).json()
    assert again["saved"] == 0 and again["duplicates"] == 2
    odoo = "Analytic Account,Date,Amount,Account,Partner,Journal Entry\nP-COST,2026-11-03,90,Services,Beta,BILL/1\n"
    assert c.post("/import/costs?source=odoo", headers=h["pmo1"], json={**_csv(odoo), "commit": True}).json()["saved"] == 1
    assert c.post("/import/costs", headers=h["pmo1"], json=_csv("a,b\n1,2\n")).status_code == 422
    assert c.post("/import/costs?source=sap", headers=h["s3"], json=_csv(sap)).status_code == 403
