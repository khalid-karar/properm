from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func

from .. import rules
from ..audit import emit, log
from ..config import NON_PROJECT_CODES, WEEK_STARTS_ON_SUNDAY
from ..deps import current_user, get_db, get_params, get_severities, require_roles
from ..models import (Activity, ActivityStaffLimit, Assignment, PeriodLock, Project, RuleViolation,
                      TimesheetEntry, User)

router = APIRouter(tags=["timesheets (Layer 2)"])


class EntryIn(BaseModel):
    project_id: int | None = None
    activity_id: int | None = None
    code: str | None = None                  # non-project code (LEAVE, ADMIN, TRAINING, PRESALES)
    entry_date: date
    hours: float = Field(gt=0, le=24)
    description: str | None = None
    overtime_reason: str | None = None
    acknowledge_warnings: bool = False

    @model_validator(mode="after")
    def target(self):
        if self.code:
            if self.project_id or self.activity_id:
                raise ValueError("Use either a project activity or a non-project code, not both")
        elif not (self.project_id and self.activity_id):
            raise ValueError("project_id and activity_id are required (or a non-project code)")
        return self


class DecisionIn(BaseModel):
    action: str                              # approve | reject | adjust
    reason: str | None = None
    hours: float | None = Field(None, gt=0, le=24)


class LockIn(BaseModel):
    locked_through: date


def e_out(e: TimesheetEntry) -> dict:
    return {"id": e.id, "user_id": e.user_id, "project_id": e.project_id, "activity_id": e.activity_id,
            "code": e.nonproject_code, "entry_date": e.entry_date, "hours": e.hours, "description": e.description,
            "status": e.status, "overtime_flag": e.overtime_flag, "overtime_reason": e.overtime_reason,
            "flags": e.flags, "original_hours": e.original_hours, "decision_reason": e.decision_reason}


def v_out(vs):
    return [{"rule": v.rule, "severity": v.severity, "message": v.message} for v in vs]


def build_ctx(db, user: User, d: EntryIn, exclude_id: int | None, today: date) -> rules.Ctx:
    sev, params = get_severities(db), get_params(db)
    ctx = rules.Ctx(today=today, entry_date=d.entry_date, hours=d.hours, severities=sev, params=params,
                    capacity=user.capacity_hours_week)
    live = ("submitted", "approved")
    ws = rules.week_start(d.entry_date, WEEK_STARTS_ON_SUNDAY)
    q = db.query(func.coalesce(func.sum(TimesheetEntry.hours), 0.0)).filter(
        TimesheetEntry.user_id == user.id, TimesheetEntry.status.in_(live),
        TimesheetEntry.entry_date >= ws, TimesheetEntry.entry_date <= ws + timedelta(days=6))
    if exclude_id:
        q = q.filter(TimesheetEntry.id != exclude_id)
    ctx.week_hours = float(q.scalar())
    lock = db.query(func.max(PeriodLock.locked_through)).scalar()
    ctx.locked_through = lock

    dup = db.query(TimesheetEntry).filter(
        TimesheetEntry.user_id == user.id, TimesheetEntry.entry_date == d.entry_date, TimesheetEntry.hours == d.hours,
        TimesheetEntry.project_id == d.project_id, TimesheetEntry.activity_id == d.activity_id,
        TimesheetEntry.nonproject_code == d.code, TimesheetEntry.description == d.description,
        TimesheetEntry.status != "rejected")
    if exclude_id:
        dup = dup.filter(TimesheetEntry.id != exclude_id)
    ctx.exact_duplicate = db.query(dup.exists()).scalar()

    if d.code:
        ctx.is_nonproject, ctx.code_valid, ctx.is_leave = True, d.code in NON_PROJECT_CODES, d.code == "LEAVE"
        return ctx
    p = db.get(Project, d.project_id)
    a = db.get(Activity, d.activity_id)
    if not p:
        raise HTTPException(404, "Project not found")
    ctx.project_state, ctx.project_start, ctx.project_end = p.state, p.planned_start, p.planned_end
    ctx.assigned = db.query(Assignment).filter_by(project_id=p.id, user_id=user.id).first() is not None
    ctx.activity_found = bool(a and a.project_id == p.id)
    if ctx.activity_found:
        ctx.activity_phase, ctx.activity_locked = a.phase, a.locked
        lim = db.query(ActivityStaffLimit).filter_by(activity_id=a.id, user_id=user.id).first()
        ctx.activity_cap = lim.max_hours if lim else a.planned_hours   # default cap: planned hours
        used = db.query(func.coalesce(func.sum(TimesheetEntry.hours), 0.0)).filter(
            TimesheetEntry.user_id == user.id, TimesheetEntry.activity_id == a.id, TimesheetEntry.status.in_(live))
        if exclude_id:
            used = used.filter(TimesheetEntry.id != exclude_id)
        ctx.user_activity_hours = float(used.scalar())
    return ctx


def record_violations(db, user, vs):
    """Persist violations; raise anomaly.flag on repeated BLOCKs (feeds Section 3 later)."""
    for v in vs:
        db.add(RuleViolation(user_id=user.id, rule=v.rule, severity=v.severity, message=v.message))
    db.flush()
    if any(v.severity == "BLOCK" for v in vs):
        since = datetime.now(timezone.utc) - timedelta(days=7)
        n = db.query(func.count(RuleViolation.id)).filter(
            RuleViolation.user_id == user.id, RuleViolation.severity == "BLOCK", RuleViolation.created_at >= since).scalar()
        if n == int(get_params(db)["anomaly_block_count"]):
            log(db, user.id, "anomaly.flag", "user", user.id, {"blocks_7d": n})
            emit(db, "anomaly.flag", {"user_id": user.id, "blocks_7d": n})


def save(db, user: User, d: EntryIn, entry: TimesheetEntry | None):
    today = date.today()
    ctx = build_ctx(db, user, d, entry.id if entry else None, today)
    vs = rules.evaluate(ctx)
    record_violations(db, user, vs)
    blocks, warns = rules.blocking(vs), rules.warnings(vs)
    if blocks:
        db.commit()
        return JSONResponse(status_code=422, content={"detail": "Entry rejected by rule engine", "violations": v_out(vs)})
    overtime = any(v.rule == "R1" for v in vs)
    if overtime and not d.overtime_reason:
        db.commit()
        return JSONResponse(status_code=422, content={"detail": "Overtime reason required", "violations": v_out(vs)})
    if warns and not d.acknowledge_warnings:
        db.commit()
        return JSONResponse(status_code=409, content={"detail": "Warnings must be acknowledged (acknowledge_warnings=true)",
                                                       "violations": v_out(vs)})
    flag_list = [f"{v.rule}: {v.message}" for v in vs if v.severity in (rules.FLAG, rules.WARN)]
    if entry is None:
        entry = TimesheetEntry(user_id=user.id)
        db.add(entry)
    entry.project_id, entry.activity_id, entry.nonproject_code = d.project_id, d.activity_id, d.code
    entry.entry_date, entry.hours, entry.description = d.entry_date, d.hours, d.description
    entry.overtime_flag, entry.overtime_reason = overtime, d.overtime_reason if overtime else None
    entry.flags, entry.status, entry.decision_reason = flag_list, "submitted", None
    db.flush()
    log(db, user.id, "timesheet.submitted", "timesheet_entry", entry.id, {"hours": entry.hours})
    emit(db, "timesheet.submitted", {"entry_id": entry.id, "user_id": user.id})
    db.commit()
    return JSONResponse(status_code=201, content={**_json(e_out(entry)), "violations": v_out(vs)})


def _json(d):
    return {k: (v.isoformat() if isinstance(v, date) else v) for k, v in d.items()}


@router.post("/timesheets")
def create_entry(body: EntryIn, db=Depends(get_db), user: User = Depends(current_user)):
    return save(db, user, body, None)


@router.put("/timesheets/{eid}")
def edit_entry(eid: int, body: EntryIn, db=Depends(get_db), user: User = Depends(current_user)):
    e = db.get(TimesheetEntry, eid)
    if not e or e.user_id != user.id:
        raise HTTPException(404, "Entry not found")
    if e.status == "approved":
        raise HTTPException(409, "Approved entries cannot be edited")
    lock = db.query(func.max(PeriodLock.locked_through)).scalar()
    if lock and e.entry_date <= lock:
        raise HTTPException(422, f"Period locked through {lock}")
    return save(db, user, body, e)


@router.get("/timesheets/mine")
def mine(week_of: date | None = None, db=Depends(get_db), user: User = Depends(current_user)):
    q = db.query(TimesheetEntry).filter_by(user_id=user.id)
    if week_of:
        ws = rules.week_start(week_of, WEEK_STARTS_ON_SUNDAY)
        q = q.filter(TimesheetEntry.entry_date >= ws, TimesheetEntry.entry_date <= ws + timedelta(days=6))
    return [e_out(e) for e in q.order_by(TimesheetEntry.entry_date, TimesheetEntry.id).all()]


@router.get("/me/utilization")
def utilization(week_of: date | None = None, db=Depends(get_db), user: User = Depends(current_user)):
    """2.5 staff self-view: own data only."""
    ws = rules.week_start(week_of or date.today(), WEEK_STARTS_ON_SUNDAY)
    rows = db.query(TimesheetEntry).filter(
        TimesheetEntry.user_id == user.id, TimesheetEntry.entry_date >= ws,
        TimesheetEntry.entry_date <= ws + timedelta(days=6)).all()
    by_status = {"submitted": 0.0, "approved": 0.0, "rejected": 0.0}
    per_project: dict = {}
    for e in rows:
        by_status[e.status] += e.hours
        if e.status != "rejected":
            k = e.project_id if e.project_id else (e.nonproject_code or "non-project")
            per_project[k] = per_project.get(k, 0.0) + e.hours
    live = by_status["submitted"] + by_status["approved"]
    return {"week_start": ws, "capacity": user.capacity_hours_week, **by_status,
            "utilization_pct": round(100 * live / user.capacity_hours_week, 1),
            "remaining_capacity": max(0.0, user.capacity_hours_week - live), "per_project": per_project,
            "overtime_entries": sum(1 for e in rows if e.overtime_flag and e.status != "rejected")}


# ---- 2.4 approval ----
def can_approve(db, approver: User, e: TimesheetEntry) -> bool:
    if approver.role in ("PMO", "ADMIN"):
        return True
    if e.project_id:
        p = db.get(Project, e.project_id)
        pm = db.get(User, p.pm_id)
        return p.pm_id == approver.id or (pm.delegate_id == approver.id)
    owner = db.get(User, e.user_id)                        # non-project time: line manager (or delegate)
    if not owner.line_manager_id:
        return False
    lm = db.get(User, owner.line_manager_id)
    return lm.id == approver.id or lm.delegate_id == approver.id


@router.get("/timesheets/queue")
def queue(db=Depends(get_db), user: User = Depends(require_roles("PM", "PMO", "ADMIN", "STAFF"))):
    rows = db.query(TimesheetEntry).filter_by(status="submitted").order_by(TimesheetEntry.entry_date).all()
    return [e_out(e) for e in rows if e.user_id != user.id and can_approve(db, user, e)]


@router.post("/timesheets/{eid}/decision")
def decide(eid: int, body: DecisionIn, db=Depends(get_db), user: User = Depends(current_user)):
    e = db.get(TimesheetEntry, eid)
    if not e:
        raise HTTPException(404, "Entry not found")
    if e.user_id == user.id:
        raise HTTPException(403, "Cannot approve your own timesheet")
    if not can_approve(db, user, e):
        raise HTTPException(403, "Not an approver for this entry")
    if e.status != "submitted":
        raise HTTPException(409, f"Entry is already {e.status}")
    lock = db.query(func.max(PeriodLock.locked_through)).scalar()
    if lock and e.entry_date <= lock:
        raise HTTPException(422, f"Period locked through {lock}")
    if body.action == "approve":
        e.status, event = "approved", "timesheet.approved"
    elif body.action == "reject":
        if not body.reason:
            raise HTTPException(422, "A reason is required to reject")
        e.status, event = "rejected", "timesheet.rejected"
    elif body.action == "adjust":
        if not body.reason or body.hours is None:
            raise HTTPException(422, "hours and reason are required to adjust")
        if body.hours > e.hours:
            raise HTTPException(422, "Adjustment can only reduce hours; ask the staff member to resubmit for more")
        e.original_hours, e.hours, e.status, event = e.hours, body.hours, "approved", "timesheet.approved"
    else:
        raise HTTPException(422, "action must be approve, reject or adjust")
    e.approved_by, e.approved_at, e.decision_reason = user.id, datetime.now(timezone.utc), body.reason
    log(db, user.id, event, "timesheet_entry", e.id, {"action": body.action, "reason": body.reason, "hours": e.hours})
    emit(db, event, {"entry_id": e.id, "user_id": e.user_id, "project_id": e.project_id})
    db.commit()
    return e_out(e)


@router.post("/periods/lock")
def lock_period(body: LockIn, db=Depends(get_db), user: User = Depends(require_roles("PMO", "ADMIN"))):
    """PMO closes a period (R8). Refused while entries in it still await approval."""
    pending = db.query(func.count(TimesheetEntry.id)).filter(
        TimesheetEntry.status == "submitted", TimesheetEntry.entry_date <= body.locked_through).scalar()
    if pending:
        raise HTTPException(409, f"{pending} entries up to {body.locked_through} are still awaiting approval")
    cur = db.query(func.max(PeriodLock.locked_through)).scalar()
    if cur and body.locked_through <= cur:
        raise HTTPException(409, f"Already locked through {cur}")
    db.add(PeriodLock(locked_through=body.locked_through, locked_by=user.id))
    log(db, user.id, "period.locked", "period", None, {"locked_through": str(body.locked_through)})
    emit(db, "period.locked", {"locked_through": str(body.locked_through)})
    db.commit()
    return {"locked_through": body.locked_through}
