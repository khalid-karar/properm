"""3.2 weekly PM report and 3.1 EVM view."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func

from .. import rules
from ..audit import emit, log
from ..config import WEEK_STARTS_ON_SUNDAY
from ..deps import current_user, get_db, require_roles
from ..evm import compute_evm
from ..models import Activity, ActivityProgress, Issue, Risk, TimesheetEntry, User, WeeklyReport
from .projects import can_view, can_view_cost, get_project, need_manage

router = APIRouter(tags=["reports & EVM"])


class ReportIn(BaseModel):
    week_of: date
    accomplishments: str
    next_week: str
    escalations: str | None = None


@router.get("/projects/{pid}/evm")
def evm(pid: int, as_of: date | None = None, db=Depends(get_db), user: User = Depends(current_user)):
    p = get_project(db, pid)
    if not can_view_cost(db, user, p):
        raise HTTPException(403, "cost_view permission required")
    return compute_evm(db, p, as_of or date.today())


def snapshot(db, p, ws: date) -> dict:
    """Auto-populated figures stored with the report so it stays reproducible."""
    we = ws + timedelta(days=6)
    hrs = dict(db.query(TimesheetEntry.status, func.coalesce(func.sum(TimesheetEntry.hours), 0.0)).filter(
        TimesheetEntry.project_id == p.id, TimesheetEntry.entry_date >= ws, TimesheetEntry.entry_date <= we
    ).group_by(TimesheetEntry.status).all())
    risks = db.query(Risk).filter(Risk.project_id == p.id, Risk.status.in_(("open", "mitigating"))).all()
    issues = db.query(Issue).filter(Issue.project_id == p.id, Issue.status.in_(("open", "in_progress"))).all()
    acts = db.query(Activity).filter_by(project_id=p.id, phase="execution", locked=True).all()
    pcts = []
    for a in acts:
        lp = (db.query(ActivityProgress).filter(ActivityProgress.activity_id == a.id, ActivityProgress.week_start <= ws)
              .order_by(ActivityProgress.week_start.desc()).first())
        pcts.append((a.planned_hours or 0.0, lp.pct_complete if lp else 0.0))
    tot = sum(h for h, _ in pcts)
    overall = round(sum(h * x for h, x in pcts) / tot, 1) if tot else None   # hours-weighted percent complete
    evm_data = compute_evm(db, p, we)
    return {"hours": {"approved": hrs.get("approved", 0.0), "submitted": hrs.get("submitted", 0.0)},
            "overall_pct_complete": overall,
            "open_risks": len(risks), "top_risk_score": max((r.score for r in risks), default=None),
            "open_issues": len(issues), "critical_issues": sum(1 for i in issues if i.severity == "critical"),
            "evm": {k: evm_data.get(k) for k in ("BAC", "PV", "EV", "AC", "CPI", "SPI", "EAC")} if evm_data.get("available") else None}


@router.post("/projects/{pid}/reports/weekly", status_code=201)
def submit_weekly(pid: int, body: ReportIn, db=Depends(get_db), user: User = Depends(require_roles("PM", "PMO", "ADMIN"))):
    p = get_project(db, pid)
    need_manage(db, user, p)
    if p.state not in ("execution", "closing"):
        raise HTTPException(409, "Weekly reports apply to projects in execution or closing")
    ws = rules.week_start(body.week_of, WEEK_STARTS_ON_SUNDAY)
    if db.query(WeeklyReport).filter_by(project_id=pid, week_start=ws).first():
        raise HTTPException(409, "A report for this week was already submitted")
    # submission requires the weekly progress update (2.6) for every baselined activity
    acts = db.query(Activity).filter_by(project_id=pid, phase="execution", locked=True).all()
    missing = [a.code for a in acts if not db.query(ActivityProgress).filter_by(activity_id=a.id, week_start=ws).first()]
    if missing:
        raise HTTPException(409, f"Progress update missing for week {ws}: {', '.join(missing)}")
    snap = snapshot(db, p, ws)
    rep = WeeklyReport(project_id=pid, week_start=ws, pm_id=user.id, snapshot=_plain(snap),
                       narrative={"accomplishments": body.accomplishments, "next_week": body.next_week, "escalations": body.escalations})
    db.add(rep)
    db.flush()
    log(db, user.id, "pm_report.submitted", "weekly_report", rep.id, {"project_id": pid, "week_start": str(ws)})
    emit(db, "pm_report.submitted", {"project_id": pid, "report_id": rep.id})
    db.commit()
    return {"id": rep.id, "week_start": ws, "snapshot": rep.snapshot, "narrative": rep.narrative}


def _plain(d):
    if isinstance(d, dict):
        return {k: _plain(v) for k, v in d.items()}
    return d.isoformat() if isinstance(d, date) else d


@router.get("/projects/{pid}/reports/weekly")
def list_reports(pid: int, db=Depends(get_db), user: User = Depends(current_user)):
    p = get_project(db, pid)
    if not can_view(db, user, p):
        raise HTTPException(403, "No access to this project")
    cost_ok = can_view_cost(db, user, p)
    out = []
    for r in db.query(WeeklyReport).filter_by(project_id=pid).order_by(WeeklyReport.week_start.desc()):
        snap = dict(r.snapshot)
        if not cost_ok:
            snap.pop("evm", None)                 # EVM figures are cost data
        out.append({"id": r.id, "week_start": r.week_start, "pm_id": r.pm_id, "narrative": r.narrative, "snapshot": snap})
    return out
