import io
import zipfile
from datetime import date

from tests.test_flow import app, c, world  # noqa: F401
from app.routers.periodic import period_bounds


def test_bounds():
    assert period_bounds("month", date(2026, 2, 10))[:2] == (date(2026, 2, 1), date(2026, 2, 28))
    assert period_bounds("quarter", date(2026, 11, 23))[:2] == (date(2026, 10, 1), date(2026, 12, 31))
    assert period_bounds("year", date(2026, 5, 1))[2] == "2026"


def test_period_reports(c, world):
    h, pid = world["h"], world["pid"]
    pm, pmo, s1 = h["pm1"], h["pmo1"], h["s1"]
    r = c.get(f"/reports/period?scope=project&id={pid}&period=month", headers=pm)
    assert r.status_code == 200
    j = r.json()
    assert j["rows"][0]["project_id"] == pid and "totals" in j and j["period"]["kind"] == "month"
    pf = c.get("/reports/period?scope=portfolio&period=quarter", headers=pmo).json()
    assert len(pf["rows"]) >= 1 and set(pf["totals"]["rag_counts"]) == {"RED", "AMBER", "GREEN", "GREY"}
    assert c.get("/reports/period?scope=portfolio", headers=pm).status_code == 403
    assert c.get("/reports/period?scope=program&id=999", headers=pmo).status_code == 404
    assert c.get("/reports/period?scope=nope", headers=pmo).status_code == 422
    assert c.get("/reports/period?scope=portfolio&period=week", headers=pmo).status_code == 422
    # staff assigned to the project can read the report but get no cost figures
    sj = c.get(f"/reports/period?scope=project&id={pid}&period=year", headers=s1)
    assert sj.status_code == 200 and sj.json()["rows"][0]["cost"] is None and sj.json()["rows"][0]["cpi"] is None
    # formats
    assert c.get("/reports/period?scope=portfolio&format=html", headers=pmo).text.startswith("<!doctype html>")
    csv = c.get("/reports/period?scope=portfolio&format=csv", headers=pmo)
    assert csv.headers["content-type"].startswith("text/csv") and "Hours approved" in csv.text
    x = c.get(f"/reports/period?scope=project&id={pid}&format=xlsx", headers=pm)
    assert x.status_code == 200 and x.content[:2] == b"PK"
    names = zipfile.ZipFile(io.BytesIO(x.content)).namelist()
    assert "xl/worksheets/sheet1.xml" in names and "xl/worksheets/sheet2.xml" in names
    b64 = c.get(f"/reports/period/xlsx-b64?scope=project&id={pid}", headers=pm).json()
    assert b64["filename"].endswith(".xlsx") and b64["content_b64"]
