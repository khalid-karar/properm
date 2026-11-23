"""Staff weekly cycle: week status and submission, reminders, planned leave."""
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func

from .. import rules
from ..audit import emit, log
from ..config import WEEK_STARTS_ON_SUNDAY
from ..deps import current_user, get_db, require_roles
from ..models import Assignment, LeaveRequest, Notification, Project, TimesheetEntry, User, WeekSubmission
from ..notify import notify
from ..workcal import holiday_map, is_weekend, leave_days

router = APIRouter(tags=["weekly cycle"])
ws_of = lambda d: rules.week_start(d, WEEK_STARTS_ON_SUNDAY)
LEAVE_KINDS = ("annual", "sick", "training", "other")


def week_status(db, u: User, ws: date) -> dict:
    end = ws + timedelta(days=6)
    hours = {}
    for e in db.query(TimesheetEntry).filter(TimesheetEntry.user_id == u.id, TimesheetEntry.entry_date >= ws, TimesheetEntry.entry_date <= end,
                                             TimesheetEntry.status != "rejected"):
        hours[e.entry_date] = hours.get(e.entry_date, 0.0) + e.hours
    hol, lv = holiday_map(db, ws, end), leave_days(db, u.id, ws, end)
    today, days, missing = date.today(), [], []
    for i in range(7):
        d = ws + timedelta(days=i)
        reason = "weekend" if is_weekend(d) else ("holiday" if d in hol else ("leave" if d in lv else None))
        h = round(hours.get(d, 0.0), 2)
        if reason is None and h == 0 and d <= today:
            missing.append(d.isoformat())
        days.append({"date": d.isoformat(), "hours": h, "off": reason, "holiday": hol.get(d)})
    sub = db.query(WeekSubmission).filter_by(user_id=u.id, week_start=ws).first()
    rejected = db.query(func.count(TimesheetEntry.id)).filter(TimesheetEntry.user_id == u.id, TimesheetEntry.entry_date >= ws,
                                                             TimesheetEntry.entry_date <= end, TimesheetEntry.status == "rejected").scalar()
    return {"week_start": ws.isoformat(), "days": days, "total": round(sum(hours.values()), 2), "missing_days": missing, "rejected_entries": rejected,
            "submitted": {"at": sub.submitted_at.isoformat() if sub.submitted_at else None, "total": sub.total_hours, "note": sub.note,
                          "missing_days": sub.missing_days} if sub else None,
            "can_submit": ws <= today}


@router.get("/me/week")
def my_week(week_of: date | None = None, db=Depends(get_db), user: User = Depends(current_user)):
    return week_status(db, user, ws_of(week_of or date.today()))


class SubmitWeekIn(BaseModel):
    week_of: date
    note: str | None = Field(None, max_length=2000)


@router.post("/me/week/submit")
def submit_week(body: SubmitWeekIn, db=Depends(get_db), user: User = Depends(current_user)):
    ws = ws_of(body.week_of)
    if ws > date.today():
        raise HTTPException(422, "You cannot submit a week that has not started")
    st = week_status(db, user, ws)
    full_week_over = ws + timedelta(days=6) < date.today()
    if st["missing_days"] and not (body.note or "").strip():
        raise HTTPException(422, f"Days with no hours: {', '.join(st['missing_days'])}. Add the hours, book leave, or explain in a note")
    if st["rejected_entries"]:
        raise HTTPException(422, "Fix or withdraw the rejected entries first")
    sub = db.query(WeekSubmission).filter_by(user_id=user.id, week_start=ws).first() or WeekSubmission(user_id=user.id, week_start=ws)
    sub.total_hours, sub.missing_days, sub.note, sub.submitted_at = st["total"], st["missing_days"], (body.note or "").strip() or None, datetime.now(timezone.utc)
    db.add(sub)
    log(db, user.id, "week.submitted", "week_submission", None, {"week_start": ws.isoformat(), "hours": st["total"], "early": not full_week_over})
    db.commit()
    return week_status(db, user, ws)


def _team(db, user: User):
    if user.role in ("PMO", "ADMIN"):
        return db.query(User).filter(User.active.is_(True), User.role.in_(("STAFF", "PM"))).order_by(User.full_name).all()
    ids = {u.id for u in db.query(User).filter(User.line_manager_id == user.id)}
    pids = [p.id for p in db.query(Project).filter_by(pm_id=user.id)]
    if pids:
        ids |= {a.user_id for a in db.query(Assignment).filter(Assignment.project_id.in_(pids))}
    ids.discard(user.id)
    return db.query(User).filter(User.id.in_(ids), User.active.is_(True)).order_by(User.full_name).all() if ids else []


@router.get("/timesheets/weeks")
def team_weeks(week_of: date | None = None, db=Depends(get_db), user: User = Depends(require_roles("PM", "PMO", "ADMIN"))):
    ws = ws_of(week_of or (date.today() - timedelta(days=7)))
    rows = []
    for u in _team(db, user):
        s = week_status(db, u, ws)
        rows.append({"user_id": u.id, "full_name": u.full_name, "total": s["total"], "missing_days": len(s["missing_days"]),
                     "submitted": bool(s["submitted"]), "submitted_at": s["submitted"]["at"] if s["submitted"] else None, "note": s["submitted"]["note"] if s["submitted"] else None})
    return {"week_start": ws.isoformat(), "staff": rows, "not_submitted": sum(1 for r in rows if not r["submitted"])}


@router.post("/reminders/timesheets")
def send_reminders(week_of: date | None = None, db=Depends(get_db), user: User = Depends(require_roles("PMO", "ADMIN"))):
    """Remind everyone who has not submitted the week (default: last week). Call from a cron or the Approvals page."""
    ws = ws_of(week_of or (date.today() - timedelta(days=7)))
    sent = 0
    for u in db.query(User).filter(User.active.is_(True), User.role.in_(("STAFF", "PM"))):
        if db.query(WeekSubmission).filter_by(user_id=u.id, week_start=ws).first():
            continue
        s = week_status(db, u, ws)
        detail = f"{len(s['missing_days'])} day(s) without hours" if s["missing_days"] else "Hours entered but the week is not submitted"
        if notify(db, u.id, "timesheet.reminder", f"Timesheet for week of {ws} not submitted", detail, "#/timesheet"):
            sent += 1
    log(db, user.id, "reminders.sent", "week_submission", None, {"week_start": ws.isoformat(), "sent": sent})
    db.commit()
    return {"week_start": ws.isoformat(), "sent": sent}


# ---------------- leave ----------------
class LeaveIn(BaseModel):
    start: date
    end: date
    kind: str = "annual"
    note: str | None = Field(None, max_length=2000)


class LeaveDecisionIn(BaseModel):
    approve: bool
    reason: str | None = Field(None, max_length=2000)


def lv_out(x: LeaveRequest, names, db=None) -> dict:
    d = {"id": x.id, "user_id": x.user_id, "user": names.get(x.user_id), "start": x.start, "end": x.end, "kind": x.kind, "note": x.note,
         "status": x.status, "decided_by": names.get(x.decided_by), "decision_reason": x.decision_reason}
    if db is not None:
        d["working_days"] = len(leave_days_any(db, x))
    return d


def leave_days_any(db, x: LeaveRequest) -> list:
    hol = holiday_map(db, x.start, x.end)
    out, d = [], x.start
    while d <= x.end:
        if not is_weekend(d) and d not in hol:
            out.append(d)
        d += timedelta(days=1)
    return out


def _names(db):
    return {u.id: u.full_name for u in db.query(User)}


def can_decide_leave(db, approver: User, x: LeaveRequest) -> bool:
    if approver.id == x.user_id:
        return False
    if approver.role in ("PMO", "ADMIN"):
        return True
    owner = db.get(User, x.user_id)
    if owner and owner.line_manager_id:
        lm = db.get(User, owner.line_manager_id)
        return approver.id == lm.id or approver.id == lm.delegate_id
    return False


@router.post("/leave", status_code=201)
def request_leave(body: LeaveIn, db=Depends(get_db), user: User = Depends(current_user)):
    if body.end < body.start:
        raise HTTPException(422, "End date is before start date")
    if (body.end - body.start).days > 90:
        raise HTTPException(422, "Leave longer than 90 days must be arranged with HR")
    if body.kind not in LEAVE_KINDS:
        raise HTTPException(422, f"kind must be one of {', '.join(LEAVE_KINDS)}")
    clash = db.query(LeaveRequest).filter(LeaveRequest.user_id == user.id, LeaveRequest.status.in_(("requested", "approved")),
                                          LeaveRequest.start <= body.end, LeaveRequest.end >= body.start).first()
    if clash:
        raise HTTPException(409, f"Overlaps your leave {clash.start} – {clash.end}")
    x = LeaveRequest(user_id=user.id, **body.model_dump())
    db.add(x)
    db.flush()
    log(db, user.id, "leave.requested", "leave_request", x.id, {"start": str(x.start), "end": str(x.end)})
    emit(db, "leave.requested", {"leave_id": x.id, "user_id": user.id, "name": user.full_name, "start": str(x.start), "end": str(x.end)})
    db.commit()
    return lv_out(x, _names(db), db)


@router.get("/me/leave")
def my_leave(db=Depends(get_db), user: User = Depends(current_user)):
    names = _names(db)
    return [lv_out(x, names, db) for x in db.query(LeaveRequest).filter_by(user_id=user.id).order_by(LeaveRequest.start.desc())]


@router.get("/leave/queue")
def leave_queue(db=Depends(get_db), user: User = Depends(current_user)):
    names = _names(db)
    return [lv_out(x, names, db) for x in db.query(LeaveRequest).filter_by(status="requested").order_by(LeaveRequest.start) if can_decide_leave(db, user, x)]


@router.get("/leave/calendar")
def leave_calendar(start: date | None = None, days: int = 42, db=Depends(get_db), user: User = Depends(require_roles("PM", "PMO", "ADMIN", "PROGRAM_MANAGER", "DECISION_MAKER"))):
    """Approved and requested leave in a window, so managers can see who is away."""
    s = start or date.today()
    e = s + timedelta(days=min(max(days, 1), 180))
    names = _names(db)
    return [lv_out(x, names, db) for x in db.query(LeaveRequest).filter(LeaveRequest.status.in_(("requested", "approved")),
                                                                         LeaveRequest.start <= e, LeaveRequest.end >= s).order_by(LeaveRequest.start)]


@router.post("/leave/{lid}/decision")
def decide_leave(lid: int, body: LeaveDecisionIn, db=Depends(get_db), user: User = Depends(current_user)):
    x = db.get(LeaveRequest, lid)
    if not x:
        raise HTTPException(404, "Leave request not found")
    if not can_decide_leave(db, user, x):
        raise HTTPException(403, "Only the line manager, their delegate, PMO or ADMIN can decide this leave")
    if x.status != "requested":
        raise HTTPException(409, f"Leave request is {x.status}")
    if not body.approve and not (body.reason or "").strip():
        raise HTTPException(422, "A reason is required to reject")
    x.status, x.decided_by, x.decision_reason = ("approved" if body.approve else "rejected"), user.id, body.reason
    log(db, user.id, f"leave.{x.status}", "leave_request", x.id, {"user_id": x.user_id})
    emit(db, "leave.decided", {"leave_id": x.id, "user_id": x.user_id, "status": x.status, "start": str(x.start), "end": str(x.end)})
    db.commit()
    return lv_out(x, _names(db), db)


@router.delete("/leave/{lid}")
def cancel_leave(lid: int, db=Depends(get_db), user: User = Depends(current_user)):
    x = db.get(LeaveRequest, lid)
    if not x or x.user_id != user.id:
        raise HTTPException(404, "Leave request not found")
    if x.status not in ("requested", "approved") or x.start <= date.today() and x.status == "approved":
        raise HTTPException(409, "Only pending leave, or approved leave that has not started, can be cancelled")
    x.status = "cancelled"
    log(db, user.id, "leave.cancelled", "leave_request", x.id, {})
    db.commit()
    return lv_out(x, _names(db), db)
