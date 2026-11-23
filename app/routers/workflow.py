"""Daily-work helpers: queue filters, bulk approval, decision history, withdraw an entry, activity cap hints, personal to-do."""
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func

from ..audit import log
from ..deps import current_user, get_db, get_params, require_roles
from ..models import (Activity, ActivityStaffLimit, Alert, Issue, PeriodLock, Project, Risk, TimesheetEntry, User)
from .timesheets import DecisionIn, apply_decision, can_approve, e_out

router = APIRouter(tags=["daily work"])


class BulkIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=200)
    action: str                       # approve | reject
    reason: str | None = None


@router.get("/timesheets/queue/filtered")
def queue_filtered(project_id: int | None = None, user_id: int | None = None, flagged: bool = False, db=Depends(get_db),
                   user: User = Depends(require_roles("PM", "PMO", "ADMIN", "STAFF"))):
    q = db.query(TimesheetEntry).filter_by(status="submitted")
    if project_id:
        q = q.filter(TimesheetEntry.project_id == project_id)
    if user_id:
        q = q.filter(TimesheetEntry.user_id == user_id)
    rows = [e for e in q.order_by(TimesheetEntry.entry_date, TimesheetEntry.id) if e.user_id != user.id and can_approve(db, user, e)]
    if flagged:
        rows = [e for e in rows if e.overtime_flag or e.flags]
    return [e_out(e) for e in rows]


@router.post("/timesheets/bulk-decision")
def bulk_decision(body: BulkIn, db=Depends(get_db), user: User = Depends(require_roles("PM", "PMO", "ADMIN", "STAFF"))):
    if body.action not in ("approve", "reject"):
        raise HTTPException(422, "Bulk action must be approve or reject")
    if body.action == "reject" and not body.reason:
        raise HTTPException(422, "A reason is required to reject")
    done, failed = [], []
    for eid in dict.fromkeys(body.ids):
        e = db.get(TimesheetEntry, eid)
        if not e:
            failed.append({"id": eid, "error": "Entry not found"})
            continue
        try:
            with db.begin_nested():
                apply_decision(db, user, e, DecisionIn(action=body.action, reason=body.reason))
            done.append(eid)
        except HTTPException as ex:
            failed.append({"id": eid, "error": ex.detail})
    db.commit()
    return {"done": done, "failed": failed}


@router.get("/timesheets/decided")
def decided(status: str | None = None, days: int = 60, db=Depends(get_db), user: User = Depends(require_roles("PM", "PMO", "ADMIN", "STAFF"))):
    since = datetime.now(timezone.utc) - timedelta(days=max(1, min(days, 365)))
    q = db.query(TimesheetEntry).filter(TimesheetEntry.approved_by == user.id, TimesheetEntry.approved_at >= since)
    if status in ("approved", "rejected"):
        q = q.filter(TimesheetEntry.status == status)
    return [e_out(e) for e in q.order_by(TimesheetEntry.approved_at.desc()).limit(200)]


@router.delete("/timesheets/{eid}", status_code=204)
def withdraw(eid: int, db=Depends(get_db), user: User = Depends(current_user)):
    """Staff withdraw their own entry while it is still pending or after rejection."""
    e = db.get(TimesheetEntry, eid)
    if not e or e.user_id != user.id:
        raise HTTPException(404, "Entry not found")
    if e.status == "approved":
        raise HTTPException(409, "Approved entries cannot be withdrawn")
    lock = db.query(func.max(PeriodLock.locked_through)).scalar()
    if lock and e.entry_date <= lock:
        raise HTTPException(422, f"Period locked through {lock}")
    log(db, user.id, "timesheet.withdrawn", "timesheet_entry", e.id, {"hours": e.hours, "date": e.entry_date.isoformat(), "status": e.status})
    db.delete(e)
    db.commit()


@router.get("/timesheets/hints")
def hints(project_id: int, activity_id: int, db=Depends(get_db), user: User = Depends(current_user)):
    """How much of an activity's cap this person has used (drives the hint beside the hours box)."""
    a = db.get(Activity, activity_id)
    if not a or a.project_id != project_id:
        raise HTTPException(404, "Activity not found")
    lim = db.query(ActivityStaffLimit).filter_by(activity_id=a.id, user_id=user.id).first()
    cap = lim.max_hours if lim else a.planned_hours
    used = float(db.query(func.coalesce(func.sum(TimesheetEntry.hours), 0.0)).filter(
        TimesheetEntry.user_id == user.id, TimesheetEntry.activity_id == a.id, TimesheetEntry.status.in_(("submitted", "approved"))).scalar())
    tol = get_params(db)["activity_cap_tolerance"]
    return {"cap": cap, "used": round(used, 2), "remaining": None if cap is None else round(cap - used, 2),
            "hard_limit": None if cap is None else round(cap * (1 + tol), 2), "personal_limit": lim is not None}


@router.get("/me/todo")
def todo(db=Depends(get_db), user: User = Depends(current_user)):
    rejected = [e_out(e) for e in db.query(TimesheetEntry).filter_by(user_id=user.id, status="rejected").order_by(TimesheetEntry.entry_date.desc()).limit(30)]
    waiting = 0
    if user.role in ("PM", "PMO", "ADMIN", "STAFF"):
        waiting = sum(1 for e in db.query(TimesheetEntry).filter_by(status="submitted") if e.user_id != user.id and can_approve(db, user, e))
    names = {p.id: f"{p.number} · {p.name}" for p in db.query(Project)}
    alerts = [{"id": a.id, "project_id": a.project_id, "project": names.get(a.project_id), "title": a.cause, "severity": a.severity}
              for a in db.query(Alert).filter(Alert.assignee_id == user.id, Alert.status == "assigned", Alert.active.is_(True))]
    risks = [{"id": r.id, "project_id": r.project_id, "project": names.get(r.project_id), "title": r.title, "score": r.score}
             for r in db.query(Risk).filter(Risk.owner_id == user.id, Risk.status.in_(("open", "mitigating"))).order_by(Risk.id)]
    issues = [{"id": i.id, "project_id": i.project_id, "project": names.get(i.project_id), "title": i.title, "severity": i.severity}
              for i in db.query(Issue).filter(Issue.owner_id == user.id, Issue.status.in_(("open", "in_progress"))).order_by(Issue.id)]
    from ..models import ProjectAction
    actions = [{"id": x.id, "project_id": x.project_id, "project": names.get(x.project_id), "title": x.title, "due_date": x.due_date,
                "overdue": x.due_date is not None and x.due_date < date.today()}
               for x in db.query(ProjectAction).filter(ProjectAction.owner_id == user.id, ProjectAction.status == "open").order_by(ProjectAction.due_date)]
    from .weekly import can_decide_leave, week_status, ws_of
    from ..models import LeaveRequest, WeekSubmission
    last = ws_of(date.today()) - timedelta(days=7)
    week_due = None
    if user.role in ("STAFF", "PM") and not db.query(WeekSubmission).filter_by(user_id=user.id, week_start=last).first():
        s = week_status(db, user, last)
        week_due = {"week_start": last.isoformat(), "missing_days": len(s["missing_days"]), "total": s["total"]}
    leave_waiting = sum(1 for x in db.query(LeaveRequest).filter_by(status="requested") if can_decide_leave(db, user, x))
    return {"rejected_entries": rejected, "approvals_waiting": waiting, "alerts": alerts, "risks": risks, "issues": issues, "actions": actions,
            "week_due": week_due, "leave_waiting": leave_waiting,
            "total": len(rejected) + (1 if waiting else 0) + len(alerts) + len(risks) + len(issues) + len(actions) + (1 if week_due else 0) + (1 if leave_waiting else 0)}
