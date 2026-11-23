"""Charts, trends, the executive summary and the decision queue."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func

from ..alerts import LIVE, rag_status
from ..deps import current_user, get_db, require_roles
from ..evm import compute_evm
from ..models import (Activity, Alert, ChangeRequest, CostEntry, Milestone, Project, Risk, Snapshot, TimesheetEntry, User)
from .dashboards import EXEC, _active_alerts, overall_pct
from .projects import can_manage, can_view_cost, get_project

router = APIRouter(prefix="/dashboards", tags=["insights"])


def _access(db, user, p):
    if not (user.role in EXEC or can_manage(db, user, p)):
        raise HTTPException(403, "Charts are for the project manager and portfolio roles")


def take_snapshot(db, p: Project, as_of: date | None = None) -> Snapshot:
    as_of = as_of or date.today()
    e = compute_evm(db, p, as_of) if p.state in ("execution", "closing") else {}
    row = db.query(Snapshot).filter_by(project_id=p.id, snap_date=as_of).first() or Snapshot(project_id=p.id, snap_date=as_of)
    row.rag = rag_status(db, p)
    row.progress_pct = overall_pct(db, p, as_of)
    row.cpi, row.spi = e.get("CPI"), e.get("SPI")
    row.open_risks = db.query(func.count(Risk.id)).filter(Risk.project_id == p.id, Risk.status.in_(("open", "mitigating"))).scalar()
    row.open_alerts = len(_active_alerts(db, p.id))
    db.add(row)
    db.flush()
    return row


@router.post("/snapshots")
def snapshot_all(db=Depends(get_db), _: User = Depends(require_roles("PMO", "ADMIN"))):
    n = 0
    for p in db.query(Project).filter(Project.state != "archived"):
        take_snapshot(db, p)
        n += 1
    db.commit()
    return {"snapshots": n, "date": date.today().isoformat()}


@router.get("/project/{pid}/trend")
def trend(pid: int, days: int = 90, db=Depends(get_db), user: User = Depends(current_user)):
    p = get_project(db, pid)
    _access(db, user, p)
    if p.state != "archived":
        take_snapshot(db, p)
        db.commit()
    since = date.today() - timedelta(days=max(1, min(days, 730)))
    cost = can_view_cost(db, user, p)
    return [{"date": s.snap_date.isoformat(), "rag": s.rag, "progress_pct": s.progress_pct, "open_risks": s.open_risks, "open_alerts": s.open_alerts,
             **({"cpi": s.cpi, "spi": s.spi} if cost else {})}
            for s in db.query(Snapshot).filter(Snapshot.project_id == pid, Snapshot.snap_date >= since).order_by(Snapshot.snap_date)]


@router.get("/project/{pid}/scurve")
def scurve(pid: int, db=Depends(get_db), user: User = Depends(current_user)):
    """Cumulative PV / EV / AC at weekly points from the planned start to today (EV/AC only up to today)."""
    p = get_project(db, pid)
    _access(db, user, p)
    if not can_view_cost(db, user, p):
        raise HTTPException(403, "Cost curves are restricted to cost viewers")
    if not p.planned_start or not p.planned_end:
        return {"available": False, "points": []}
    today = date.today()
    end = max(p.planned_end, today) if p.state in ("execution", "closing") else p.planned_end
    step = max(7, ((end - p.planned_start).days // 60) + 1)
    pts, d, bac = [], p.planned_start, None
    while d <= end + timedelta(days=step - 1) and len(pts) < 90:
        at = min(d, end)
        e = compute_evm(db, p, at)
        if not e.get("available"):
            return {"available": False, "points": [], "reason": e.get("reason")}
        bac = e["BAC"]
        pts.append({"date": at.isoformat(), "PV": e["PV"], "EV": e["EV"] if at <= today else None, "AC": e["AC"] if at <= today else None})
        d += timedelta(days=step)
    if p.planned_start <= today <= end and not any(x["date"] == today.isoformat() for x in pts):
        e = compute_evm(db, p, today)
        pts.append({"date": today.isoformat(), "PV": e["PV"], "EV": e["EV"], "AC": e["AC"]})
        pts.sort(key=lambda x: x["date"])
    return {"available": True, "currency": p.currency, "BAC": bac, "today": today.isoformat(), "points": pts}


@router.get("/project/{pid}/risk-matrix")
def risk_matrix(pid: int, db=Depends(get_db), user: User = Depends(current_user)):
    p = get_project(db, pid)
    _access(db, user, p)
    cells = {}
    for r in db.query(Risk).filter(Risk.project_id == pid, Risk.status.in_(("open", "mitigating"))):
        cells.setdefault(f"{r.probability}-{r.impact}", []).append({"id": r.id, "title": r.title, "score": r.score})
    return {"cells": cells}


@router.get("/project/{pid}/hours-vs-plan")
def hours_vs_plan(pid: int, db=Depends(get_db), user: User = Depends(current_user)):
    p = get_project(db, pid)
    _access(db, user, p)
    used = dict(db.query(TimesheetEntry.activity_id, func.coalesce(func.sum(TimesheetEntry.hours), 0.0)).filter(
        TimesheetEntry.project_id == pid, TimesheetEntry.status == "approved").group_by(TimesheetEntry.activity_id).all())
    return [{"code": a.code, "name": a.name, "planned": a.planned_hours or 0, "approved": round(used.get(a.id, 0.0), 1)}
            for a in db.query(Activity).filter_by(project_id=pid, phase="execution").order_by(Activity.id)]


@router.get("/executive")
def executive(db=Depends(get_db), user: User = Depends(current_user)):
    if user.role not in EXEC:
        raise HTTPException(403, "Executive summary requires PMO, ADMIN, DECISION_MAKER or PROGRAM_MANAGER")
    today = date.today()
    rag = {"RED": 0, "AMBER": 0, "GREEN": 0, "GREY": 0}
    by_state, rows = {}, []
    bac = ev = ac = 0.0
    ccys = set()
    for p in db.query(Project).filter(Project.state != "archived").order_by(Project.id):
        r = rag_status(db, p)
        rag[r] += 1
        by_state[p.state] = by_state.get(p.state, 0) + 1
        if p.state in ("execution", "closing"):
            e = compute_evm(db, p, today)
            if e.get("available") and e.get("currency") == "SAR":
                bac += e["BAC"] or 0
                ev += e["EV"] or 0
                ac += e["AC"] or 0
            elif e.get("available"):
                ccys.add(e.get("currency"))
        if r in ("RED", "AMBER"):
            al = _active_alerts(db, p.id)
            rows.append({"project_id": p.id, "number": p.number, "name": p.name, "rag": r, "top_alert": al[0].cause if al else None})
    rows.sort(key=lambda x: (x["rag"] != "RED", x["project_id"]))
    hist = {}
    for s in db.query(Snapshot).filter(Snapshot.snap_date >= today - timedelta(days=90)).order_by(Snapshot.snap_date):
        hist.setdefault(s.snap_date.isoformat(), {"RED": 0, "AMBER": 0, "GREEN": 0, "GREY": 0})[s.rag] += 1
    risks = sorted(db.query(Risk).filter(Risk.status.in_(("open", "mitigating"))).all(), key=lambda r: (-r.score, r.id))[:5]
    names = {p.id: p.number for p in db.query(Project)}
    overdue = db.query(func.count(Milestone.id)).filter(Milestone.due_date < today, Milestone.achieved_on.is_(None)).scalar()
    return {"as_of": today.isoformat(), "projects": sum(rag.values()), "rag_counts": rag, "by_state": by_state,
            "evm": {"currency": "SAR", "BAC": round(bac, 0), "EV": round(ev, 0), "AC": round(ac, 0), "CPI": round(ev / ac, 2) if ac else None,
                    "excluded_currencies": sorted(c for c in ccys if c)},
            "attention": rows[:8], "rag_history": [{"date": d, **v} for d, v in hist.items()],
            "top_risks": [{"project": names.get(r.project_id), "project_id": r.project_id, "title": r.title, "score": r.score} for r in risks],
            "overdue_milestones": overdue, "pending_decisions": _decisions(db, user)["total"]}


def _decisions(db, user: User) -> dict:
    names = {p.id: f"{p.number} · {p.name}" for p in db.query(Project)}
    changes, costs, alerts = [], [], []
    if user.is_ccb or user.role in ("PMO", "ADMIN"):
        for c in db.query(ChangeRequest).filter_by(status="requested").order_by(ChangeRequest.id):
            if c.requested_by != user.id or user.role == "ADMIN":
                changes.append({"id": c.id, "project_id": c.project_id, "project": names.get(c.project_id), "title": c.description[:140], "type": c.change_type,
                                "cost_delta": c.impact_cost_delta, "schedule_days": c.impact_schedule_days})
    if user.role in ("PMO", "ADMIN"):
        for c in db.query(CostEntry).filter_by(approval="pending").order_by(CostEntry.id):
            costs.append({"id": c.id, "project_id": c.project_id, "project": names.get(c.project_id), "amount": c.amount, "currency": c.currency, "title": f"{c.category}{' · ' + c.vendor if c.vendor else ''}"})
    for a in db.query(Alert).filter(Alert.severity == "critical", Alert.active.is_(True), Alert.status == "open").order_by(Alert.id):
        p = db.get(Project, a.project_id)
        if user.role in EXEC or (p and can_manage(db, user, p)):
            alerts.append({"id": a.id, "project_id": a.project_id, "project": names.get(a.project_id), "title": a.cause})
    return {"changes": changes, "costs": costs, "alerts": alerts, "total": len(changes) + len(costs) + len(alerts)}


@router.get("/decisions")
def decisions(db=Depends(get_db), user: User = Depends(current_user)):
    return _decisions(db, user)


@router.get("/investment")
def investment_vs_return(db=Depends(get_db), user: User = Depends(current_user)):
    """Per project: what it costs (budget, actual, forecast) against what it is meant to return (benefits)."""
    if user.role not in EXEC:
        raise HTTPException(403, "Investment view requires PMO, ADMIN, DECISION_MAKER or PROGRAM_MANAGER")
    from ..models import Benefit
    from .governance import realization_pct
    today, rows = date.today(), []
    for p in db.query(Project).filter(Project.state.notin_(("archived", "cancelled"))).order_by(Project.id):
        e = compute_evm(db, p, today) if p.state in ("execution", "closing") else {}
        bens = db.query(Benefit).filter_by(project_id=p.id).all()
        reals = [x for x in (realization_pct(b) for b in bens) if x is not None]
        rows.append({"project_id": p.id, "number": p.number, "name": p.name, "state": p.state, "rag": rag_status(db, p),
                     "currency": e.get("currency"), "budget": e.get("BAC"), "actual": e.get("AC"), "forecast": e.get("EAC"),
                     "benefits": len(bens), "benefit_realization_pct": round(sum(reals) / len(reals), 1) if reals else None})
    return rows
