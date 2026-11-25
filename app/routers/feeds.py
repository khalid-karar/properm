"""Read-only data feeds for BI tools and other systems (Power BI, a data warehouse, finance). Sign in with an API key, not a user:

    GET /api/v1/projects | evm | forecast | timesheets | costs | alerts | risks      add ?format=csv for Excel and Power BI

Send the key in the X-API-Key header (or as a Bearer token). A key sees its own organisation's data only, including cost; keep it secret and revoke it in Admin when
it is no longer needed. Feeds never write. The request rate is limited per key."""
import csv
import io
import time
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from ..alerts import LIVE, rag_status
from ..deps import get_db, get_params
from ..evm import compute_evm
from ..forecast import compute_forecast
from ..models import Activity, Alert, ApiKey, CostEntry, Project, Risk, TimesheetEntry, User
from .apikeys import hash_key
from .dashboards import overall_pct
from .exports import _safe

LIMIT, WINDOW = 300, 300                     # requests per key per five minutes
_HITS: dict[int, list[float]] = {}


def api_key_auth(request: Request, db=Depends(get_db)) -> ApiKey:
    raw = request.headers.get("x-api-key") or ""
    if not raw and request.headers.get("authorization", "")[:7].lower() == "bearer ":
        raw = request.headers["authorization"][7:].strip()
    if not raw.startswith("prm_"):
        raise HTTPException(401, "Send your API key in the X-API-Key header")
    db.info["unscoped"] = True                # the key is how we learn which organisation this is
    try:
        k = db.query(ApiKey).filter(ApiKey.key_hash == hash_key(raw)).first()
    finally:
        db.info.pop("unscoped", None)
    if k is None or not k.active:
        raise HTTPException(401, "Unknown or revoked API key")
    now = time.time()
    recent = [t for t in _HITS.get(k.id, []) if now - t < WINDOW]
    if len(recent) >= LIMIT:
        raise HTTPException(429, "Too many requests for this key. Try again in a few minutes.")
    _HITS[k.id] = recent + [now]
    db.info["scope"] = k.tenant_id            # from here on every query sees this organisation only
    stamp = datetime.now(timezone.utc)
    if not k.last_used_at or (stamp - k.last_used_at.replace(tzinfo=k.last_used_at.tzinfo or timezone.utc)).total_seconds() > 60:
        k.last_used_at = stamp
        db.commit()
    return k


router = APIRouter(prefix="/api/v1", tags=["data feeds"], dependencies=[Depends(api_key_auth)])


def _out(fmt: str, name: str, header: list[str], rows: list[list]):
    if fmt == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(header)
        for r in rows:
            w.writerow([_safe(v) for v in r])
        return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'inline; filename="{name}.csv"'})
    if fmt != "json":
        raise HTTPException(422, "format must be json or csv")
    return {"count": len(rows), "data": [dict(zip(header, r)) for r in rows]}


def _running(db):
    return db.query(Project).filter(Project.state.in_(("execution", "closing"))).order_by(Project.id).all()


@router.get("/projects")
def projects(format: str = "json", db=Depends(get_db)):
    today = date.today()
    pm = {u.id: u.staff_id for u in db.query(User.id, User.staff_id)}
    rows = []
    for p in db.query(Project).order_by(Project.id):
        rows.append([p.id, p.number, p.name, p.state, p.project_type, pm.get(p.pm_id), p.client, p.planned_start, p.planned_end, p.budget_ceiling, p.currency, p.baseline_version,
                     rag_status(db, p), overall_pct(db, p, today) if p.state in ("execution", "closing") else None])
    return _out(format, "projects", ["project_id", "number", "name", "state", "type", "manager_staff_id", "client", "planned_start", "planned_end", "budget", "currency", "baseline_version", "rag", "progress_pct"], rows)


@router.get("/evm")
def evm(format: str = "json", as_of: date | None = None, db=Depends(get_db)):
    as_of, rows = as_of or date.today(), []
    for p in _running(db):
        e = compute_evm(db, p, as_of)
        if e.get("available"):
            rows.append([p.id, p.number, as_of, e["currency"]] + [e.get(k) for k in ("BAC", "PV", "EV", "AC", "AC_labor", "AC_nonlabor", "CPI", "SPI", "CV", "SV", "TCPI", "EAC", "ETC", "VAC")])
    return _out(format, "evm", ["project_id", "number", "as_of", "currency", "BAC", "PV", "EV", "AC", "AC_labor", "AC_nonlabor", "CPI", "SPI", "CV", "SV", "TCPI", "EAC", "ETC", "VAC"], rows)


@router.get("/forecast")
def forecast(format: str = "json", db=Depends(get_db)):
    params, today, rows = get_params(db), date.today(), []
    for p in _running(db):
        f = compute_forecast(db, p, today, params)
        if f.get("available"):
            fin, c = f.get("finish") or {}, f["cost"]
            rows.append([p.id, p.number, today, f["currency"], f["percent_complete"], f["baseline_finish"], fin.get("likely"), fin.get("earliest"), fin.get("latest"), f.get("slip_days"),
                         c.get("BAC"), c.get("EAC"), c.get("low"), c.get("high"), c.get("VAC"), f["status"], f["confidence"]])
    return _out(format, "forecast", ["project_id", "number", "as_of", "currency", "percent_complete", "baseline_finish", "forecast_finish", "finish_earliest", "finish_latest", "slip_days",
                                     "budget_at_completion", "forecast_cost", "forecast_cost_low", "forecast_cost_high", "variance_at_completion", "status", "confidence"], rows)


@router.get("/timesheets")
def timesheets(format: str = "json", date_from: date | None = None, date_to: date | None = None, status: str | None = None, limit: int = 50000, offset: int = 0, db=Depends(get_db)):
    q = db.query(TimesheetEntry, User.staff_id, Project.number, Activity.code).join(User, User.id == TimesheetEntry.user_id) \
        .outerjoin(Project, Project.id == TimesheetEntry.project_id).outerjoin(Activity, Activity.id == TimesheetEntry.activity_id)
    if date_from:
        q = q.filter(TimesheetEntry.entry_date >= date_from)
    if date_to:
        q = q.filter(TimesheetEntry.entry_date <= date_to)
    if status:
        q = q.filter(TimesheetEntry.status == status)
    rows = [[e.id, sid, pnum, acode, e.nonproject_code, e.entry_date, e.hours, e.status, e.overtime_flag] for e, sid, pnum, acode in
            q.order_by(TimesheetEntry.id).offset(max(0, offset)).limit(max(1, min(limit, 200000))).all()]
    return _out(format, "timesheets", ["entry_id", "staff_id", "project", "activity", "nonproject_code", "date", "hours", "status", "overtime"], rows)


@router.get("/costs")
def costs(format: str = "json", db=Depends(get_db)):
    nums = {p.id: p.number for p in db.query(Project.id, Project.number)}
    rows = [[c.id, nums.get(c.project_id), c.category, c.vendor, c.amount, c.currency, c.entry_date, c.doc_ref, c.cost_status, c.approval] for c in db.query(CostEntry).order_by(CostEntry.id)]
    return _out(format, "costs", ["cost_id", "project", "category", "vendor", "amount", "currency", "date", "reference", "cost_status", "approval"], rows)


@router.get("/alerts")
def alerts(format: str = "json", db=Depends(get_db)):
    nums = {p.id: p.number for p in db.query(Project.id, Project.number)}
    rows = [[a.id, nums.get(a.project_id), a.rule, a.severity, a.status, a.cause, a.suggested_action, a.created_at] for a in db.query(Alert).filter(Alert.status.in_(LIVE), Alert.active.is_(True)).order_by(Alert.id)]
    return _out(format, "alerts", ["alert_id", "project", "rule", "severity", "status", "cause", "suggested_action", "created_at"], rows)


@router.get("/risks")
def risks(format: str = "json", db=Depends(get_db)):
    nums = {p.id: p.number for p in db.query(Project.id, Project.number)}
    rows = [[r.id, nums.get(r.project_id), r.title, r.category, r.probability, r.impact, r.score, r.status] for r in db.query(Risk).order_by(Risk.id)]
    return _out(format, "risks", ["risk_id", "project", "title", "category", "probability", "impact", "score", "status"], rows)
