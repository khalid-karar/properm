"""Forecast endpoints (see app/forecast.py). The finish date is visible to anyone who can see the project; cost figures only to cost viewers."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException

from ..deps import current_user, get_db, get_params
from ..forecast import compute_forecast
from ..models import Project, User
from .projects import can_view, can_view_cost, get_project

router = APIRouter(tags=["forecast"])
EXEC = ("PMO", "ADMIN", "DECISION_MAKER", "PROGRAM_MANAGER")


def forecast_for(db, user: User, p: Project, as_of: date, params: dict) -> dict:
    f = compute_forecast(db, p, as_of, params)
    if not can_view_cost(db, user, p):
        f.pop("cost", None)
        f.pop("warnings", None)
        if f.get("status") and not f.get("finish"):
            f.pop("status", None)
    return f


@router.get("/projects/{pid}/forecast")
def project_forecast(pid: int, as_of: date | None = None, db=Depends(get_db), user: User = Depends(current_user)):
    p = get_project(db, pid)
    if not can_view(db, user, p):
        raise HTTPException(403, "No access to this project")
    if p.state not in ("execution", "closing"):
        return {"available": False, "project_id": pid, "reason": "Forecasts are available once the project is in execution"}
    return forecast_for(db, user, p, as_of or date.today(), get_params(db))


@router.get("/portfolio/forecast")
def portfolio_forecast(db=Depends(get_db), user: User = Depends(current_user)):
    if user.role not in EXEC:
        raise HTTPException(403, "Requires PMO, ADMIN, DECISION_MAKER or PROGRAM_MANAGER")
    params, today, rows = get_params(db), date.today(), []
    for p in db.query(Project).filter(Project.state.in_(("execution", "closing"))).order_by(Project.id):
        f = forecast_for(db, user, p, today, params)
        rows.append({"project_id": p.id, "number": p.number, "name": p.name, **{k: f.get(k) for k in ("available", "reason", "status", "confidence", "percent_complete", "baseline_finish", "slip_days", "currency", "cost")},
                     "forecast_finish": (f.get("finish") or {}).get("likely")})
    order = {"RED": 0, "AMBER": 1, "GREEN": 2, None: 3}
    rows.sort(key=lambda r: (order.get(r.get("status"), 3), r["project_id"]))
    return {"as_of": today, "projects": rows}
