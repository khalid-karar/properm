from datetime import timedelta

from tests.test_flow import TODAY, app, c, world   # noqa: F401
from tests.test_slice2 import approved_hours, costed, progress   # noqa: F401


def test_forecast_dates_and_cost(c, costed):
    h, pid = costed["h"], costed["cpid"]
    approved_hours(c, costed, costed["a"], 14)
    approved_hours(c, costed, costed["a"], 21)
    assert progress(c, costed, 50, 25).status_code == 200           # EV 40000 against PV 50000: 40 of 100 planned days earned after 50 days
    f = c.get(f"/projects/{pid}/forecast", headers=h["pm1"]).json()
    assert f["available"] and f["percent_complete"] == 40.0
    assert f["spi_t"] == 0.8 and f["slip_days"] == 25                   # finishes 75 days from now against 50 planned
    assert f["finish"]["likely"] == str(TODAY + timedelta(days=75))
    assert f["status"] == "AMBER" and f["confidence"] == "high"
    cost = f["cost"]
    assert cost["AC"] == 4000 and cost["EAC"] == 10000 and cost["low"] == 10000 and cost["high"] == 64000 and cost["VAC"] == 90000   # AC 4000, CPI 10


def test_forecast_without_progress_has_no_date(c, costed):
    f = c.get(f"/projects/{costed['cpid']}/forecast", headers=costed["h"]["pm1"]).json()
    assert f["available"] and f["finish"] is None and f["slip_days"] is None and f["confidence"] == "low"
    assert f["cost"]["EAC"] is None


def test_forecast_cost_hidden_from_staff_and_not_for_planning(c, costed):
    h = costed["h"]
    progress(c, costed, 50, 25)
    s = c.get(f"/projects/{costed['cpid']}/forecast", headers=h["s3"])
    assert s.status_code == 200 and "cost" not in s.json() and s.json()["finish"]
    assert c.get(f"/projects/{costed['pid']}/forecast", headers=h["pm1"]).json()["available"] is False   # world project: no priced activities
    assert c.get("/portfolio/forecast", headers=h["s3"]).status_code == 403


def test_portfolio_forecast_lists_running_projects(c, costed):
    progress(c, costed, 50, 25)
    rows = c.get("/portfolio/forecast", headers=costed["h"]["pmo1"]).json()["projects"]
    row = next(r for r in rows if r["project_id"] == costed["cpid"])
    assert row["status"] == "AMBER" and row["slip_days"] == 25 and row["forecast_finish"] == str(TODAY + timedelta(days=75))


def test_completed_work_forecasts_today(c, costed):
    progress(c, costed, 100, 100)
    f = c.get(f"/projects/{costed['cpid']}/forecast", headers=costed["h"]["pm1"]).json()
    assert f["finish"]["likely"] == str(TODAY) and f["slip_days"] == -50
