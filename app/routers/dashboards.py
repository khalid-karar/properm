"""3.4 role-based dashboards: project health (PM) and portfolio (executive) with drill-down to the project."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func

from ..alerts import LIVE, RANK, rag_status
from ..deps import current_user, get_db
from ..evm import compute_evm, latest_progress
from ..models import Activity, Alert, Issue, Milestone, Project, ProjectAction, Risk, TimesheetEntry, User
from .projects import can_manage, can_view, can_view_cost, get_project, p_out

router = APIRouter(prefix="/dashboards", tags=["dashboards (3.4)"])
EXEC = ("PMO", "ADMIN", "DECISION_MAKER", "PROGRAM_MANAGER")


def overall_pct(db, p: Project, as_of: date):
    acts = db.query(Activity).filter_by(project_id=p.id, phase="execution", locked=True).all()
    tot = sum(a.planned_hours or 0 for a in acts)
    if not tot:
        return None
    s = 0.0
    for a in acts:
        lp = latest_progress(db, a.id, as_of)
        s += (a.planned_hours or 0) * (lp.pct_complete if lp else 0.0)
    return round(s / tot, 1)


def _active_alerts(db, pid):
    rows = db.query(Alert).filter(Alert.project_id == pid, Alert.status.in_(LIVE), Alert.active.is_(True)).all()
    return sorted(rows, key=lambda a: (-RANK[a.severity], a.id))


@router.get("/project/{pid}")
def project_dashboard(pid: int, as_of: date | None = None, db=Depends(get_db), user: User = Depends(current_user)):
    p = get_project(db, pid)
    if not (user.role in EXEC or can_manage(db, user, p)):
        raise HTTPException(403, "Project dashboards are for the project manager and portfolio roles")
    as_of = as_of or date.today()
    alerts = _active_alerts(db, pid)
    acts = db.query(Activity).filter_by(project_id=pid, phase="execution", locked=True).all()
    hrs = dict(db.query(TimesheetEntry.status, func.coalesce(func.sum(TimesheetEntry.hours), 0.0)).filter(
        TimesheetEntry.project_id == pid, TimesheetEntry.entry_date <= as_of).group_by(TimesheetEntry.status).all())
    risks = db.query(Risk).filter(Risk.project_id == pid, Risk.status.in_(("open", "mitigating"))).all()
    issues = db.query(Issue).filter(Issue.project_id == pid, Issue.status.in_(("open", "in_progress"))).all()
    late = []
    for a in acts:
        lp = latest_progress(db, a.id, as_of)
        if a.planned_end and a.planned_end < as_of and not (lp and lp.pct_complete >= 100):
            late.append({"code": a.code, "planned_end": a.planned_end, "days_late": (as_of - a.planned_end).days})
    out = {"project": p_out(p), "rag": rag_status(db, p),
           "health_reasons": [{"severity": a.severity, "cause": a.cause} for a in alerts if a.severity != "info"],
           "progress_pct": overall_pct(db, p, as_of),
           "hours": {"planned": sum(a.planned_hours or 0 for a in acts), "approved": hrs.get("approved", 0.0),
                     "pending_approval": hrs.get("submitted", 0.0)},
           "overdue_activities": late,
           "risks": {"open": len(risks), "top_score": max((r.score for r in risks), default=None)},
           "issues": {"open": len(issues), "critical": sum(1 for i in issues if i.severity == "critical")},
           "alerts": [{"id": a.id, "severity": a.severity, "cause": a.cause, "status": a.status} for a in alerts]}
    if can_view_cost(db, user, p):
        out["evm"] = compute_evm(db, p, as_of)
    return out


@router.get("/portfolio")
def portfolio(state: str | None = None, rag: str | None = None, as_of: date | None = None, db=Depends(get_db),
              user: User = Depends(current_user)):
    if user.role not in EXEC:
        raise HTTPException(403, "Portfolio dashboard requires PMO, ADMIN, DECISION_MAKER or PROGRAM_MANAGER")
    as_of = as_of or date.today()
    rows, counts = [], {"RED": 0, "AMBER": 0, "GREEN": 0, "GREY": 0}
    q = db.query(Project)
    if state:
        q = q.filter(Project.state == state)
    for p in q.order_by(Project.id):
        r = rag_status(db, p)
        counts[r] += 1
        if rag and r != rag.upper():
            continue
        alerts = _active_alerts(db, p.id)
        e = compute_evm(db, p, as_of) if p.state in ("execution", "closing") else {"available": False}
        rows.append({"project_id": p.id, "number": p.number, "name": p.name, "state": p.state, "rag": r,
                     "progress_pct": overall_pct(db, p, as_of),
                     "cpi": e.get("CPI"), "spi": e.get("SPI"),
                     "open_alerts": {s: sum(1 for a in alerts if a.severity == s) for s in ("critical", "warning", "info")},
                     "top_alert": alerts[0].cause if alerts else None})
    order = {"RED": 0, "AMBER": 1, "GREEN": 2, "GREY": 3}
    rows.sort(key=lambda r: (order[r["rag"]], r["project_id"]))
    return {"as_of": as_of, "rag_counts": counts, "projects": rows}


@router.get("/top-risks")
def top_risks(limit: int = 10, db=Depends(get_db), user: User = Depends(current_user)):
    if user.role not in EXEC:
        raise HTTPException(403, "Requires PMO, ADMIN, DECISION_MAKER or PROGRAM_MANAGER")
    rs = db.query(Risk).filter(Risk.status.in_(("open", "mitigating"))).all()
    rs.sort(key=lambda r: (-r.score, r.id))
    return [{"project_id": r.project_id, "risk_id": r.id, "title": r.title, "score": r.score, "status": r.status} for r in rs[:max(1, min(limit, 50))]]


@router.get("/project/{pid}/summary")
def project_summary(pid: int, db=Depends(get_db), user: User = Depends(current_user)):
    """One-screen view for the project Overview tab: anyone who can see the project may read it; cost only for those allowed to see cost."""
    p = get_project(db, pid)
    if not can_view(db, user, p):
        raise HTTPException(403, "No access to this project")
    today = date.today()
    acts = db.query(Activity).filter_by(project_id=pid, phase="execution").all()
    approved = float(db.query(func.coalesce(func.sum(TimesheetEntry.hours), 0.0)).filter(TimesheetEntry.project_id == pid, TimesheetEntry.status == "approved").scalar() or 0)
    planned = sum(a.planned_hours or 0 for a in acts)
    ms = db.query(Milestone).filter(Milestone.project_id == pid, Milestone.achieved_on.is_(None)).order_by(Milestone.due_date).limit(4).all()
    rs = db.query(Risk).filter(Risk.project_id == pid, Risk.status.in_(("open", "mitigating", "occurred"))).all()
    rs.sort(key=lambda r: -r.score)
    acts_open = db.query(ProjectAction).filter(ProjectAction.project_id == pid, ProjectAction.status == "open").order_by(ProjectAction.due_date.is_(None), ProjectAction.due_date).all()
    issues = db.query(Issue).filter(Issue.project_id == pid, Issue.status.in_(("open", "in_progress"))).all()
    out = {"project": p_out(p), "rag": rag_status(db, p), "progress_pct": overall_pct(db, p, today) if acts else 0.0,
           "hours": {"planned": round(planned, 1), "approved": round(approved, 1), "pct": round(100 * approved / planned, 1) if planned else None},
           "milestones": [{"name": m.name, "due_date": m.due_date, "days": (m.due_date - today).days} for m in ms],
           "risks": [{"title": r.title, "score": r.score, "status": r.status} for r in rs[:3]], "risks_open": len(rs),
           "issues_open": len(issues), "issues_critical": sum(1 for i in issues if i.severity == "critical"),
           "actions": [{"title": a.title, "due_date": a.due_date, "overdue": bool(a.due_date and a.due_date < today)} for a in acts_open[:5]],
           "actions_open": len(acts_open), "actions_overdue": sum(1 for a in acts_open if a.due_date and a.due_date < today),
           "overdue_activities": sum(1 for a in acts if a.planned_end and a.planned_end < today and a.locked and (latest_progress(db, a.id, today) is None or latest_progress(db, a.id, today).pct_complete < 100))}
    if can_view_cost(db, user, p):
        e = compute_evm(db, p, today)
        out["cost"] = {k: e.get(k) for k in ("available", "currency", "BAC", "PV", "EV", "AC", "CPI", "SPI", "EAC") if k in e}
    return out
