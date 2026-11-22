"""2.6 progress update, 2.7 cost ledger, 2.1b planned allocations."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func

from .. import rules
from ..workcal import effective_capacity
from ..audit import emit, log
from ..config import WEEK_STARTS_ON_SUNDAY
from ..deps import current_user, get_db, get_params, require_roles
from ..evm import latest_progress
from ..models import (Activity, ActivityProgress, Assignment, CostEntry, PlannedAllocation, Project,
                      TimesheetEntry, User)
from .projects import can_view, can_view_cost, get_project, need_manage

router = APIRouter(tags=["progress, cost, allocation"])
MANAGE = ("PM", "PMO", "ADMIN")


def wk(d: date) -> date:
    return rules.week_start(d, WEEK_STARTS_ON_SUNDAY)


# ---------------- 2.6 progress ----------------
class ProgressItem(BaseModel):
    activity_id: int
    pct_complete: float = Field(ge=0, le=100)
    etc_hours: float | None = Field(None, ge=0)
    reason: str | None = None


class ProgressIn(BaseModel):
    week_of: date
    updates: list[ProgressItem] = Field(min_length=1)


@router.put("/projects/{pid}/progress")
def update_progress(pid: int, body: ProgressIn, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p = get_project(db, pid)
    need_manage(db, user, p)
    if p.state not in ("execution", "closing"):
        raise HTTPException(409, "Progress is recorded for projects in execution or closing")
    ws = wk(body.week_of)
    errors, rows = [], []
    for u in body.updates:
        a = db.get(Activity, u.activity_id)
        if not a or a.project_id != pid or a.phase != "execution":
            errors.append(f"Activity {u.activity_id}: not a baseline activity of this project")
            continue
        prev = (db.query(ActivityProgress).filter(ActivityProgress.activity_id == a.id, ActivityProgress.week_start < ws)
                .order_by(ActivityProgress.week_start.desc()).first())
        if prev and u.pct_complete < prev.pct_complete and not u.reason:
            errors.append(f"{a.code}: progress decreased from {prev.pct_complete:g} to {u.pct_complete:g}; a reason is required")
            continue
        rows.append((a, u))
    if errors:
        raise HTTPException(422, {"errors": errors})
    for a, u in rows:
        cur = db.query(ActivityProgress).filter_by(activity_id=a.id, week_start=ws).first()
        if cur:
            cur.pct_complete, cur.etc_hours, cur.reason, cur.updated_by = u.pct_complete, u.etc_hours, u.reason, user.id
        else:
            db.add(ActivityProgress(activity_id=a.id, week_start=ws, pct_complete=u.pct_complete, etc_hours=u.etc_hours,
                                    reason=u.reason, updated_by=user.id))
    log(db, user.id, "progress.updated", "project", pid, {"week_start": str(ws), "activities": len(rows)})
    emit(db, "progress.updated", {"project_id": pid, "week_start": str(ws)})
    db.commit()
    return {"week_start": ws, "updated": len(rows)}


@router.get("/projects/{pid}/progress")
def get_progress(pid: int, as_of: date | None = None, db=Depends(get_db), user: User = Depends(current_user)):
    p = get_project(db, pid)
    if not can_view(db, user, p):
        raise HTTPException(403, "No access to this project")
    as_of = as_of or date.today()
    stale_weeks = int(get_params(db)["stale_progress_weeks"])
    out = []
    for a in db.query(Activity).filter_by(project_id=pid, phase="execution", locked=True).order_by(Activity.id):
        lp = latest_progress(db, a.id, as_of)
        stale = lp is None or (wk(as_of) - lp.week_start).days > 7 * stale_weeks
        out.append({"activity_id": a.id, "code": a.code, "pct_complete": lp.pct_complete if lp else 0.0,
                    "etc_hours": lp.etc_hours if lp else None, "week_start": lp.week_start if lp else None, "stale": stale})
    return out


# ---------------- 2.7 cost ledger ----------------
class CostIn(BaseModel):
    activity_id: int | None = None
    category: str
    vendor: str | None = None
    amount: float = Field(gt=0)
    currency: str = Field("SAR", min_length=3, max_length=3)
    entry_date: date
    doc_ref: str | None = None
    cost_status: str = "invoiced"             # committed | invoiced | paid


def c_out(c: CostEntry) -> dict:
    return {"id": c.id, "project_id": c.project_id, "activity_id": c.activity_id, "category": c.category,
            "vendor": c.vendor, "amount": c.amount, "currency": c.currency, "entry_date": c.entry_date,
            "doc_ref": c.doc_ref, "cost_status": c.cost_status, "approval": c.approval}


@router.post("/projects/{pid}/costs", status_code=201)
def post_cost(pid: int, body: CostIn, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p = get_project(db, pid)
    need_manage(db, user, p)
    if p.state not in ("execution", "closing"):
        raise HTTPException(409, "Costs are posted to projects in execution or closing")
    if body.cost_status not in ("committed", "invoiced", "paid"):
        raise HTTPException(422, "cost_status must be committed, invoiced or paid")
    if body.activity_id:
        a = db.get(Activity, body.activity_id)
        if not a or a.project_id != pid:
            raise HTTPException(404, "Activity not found in this project")
    threshold = get_params(db)["cost_approval_threshold"]
    needs_second = body.amount > threshold and user.role not in ("PMO", "ADMIN")
    c = CostEntry(project_id=pid, created_by=user.id, approval="pending" if needs_second else "approved",
                  approved_by=None if needs_second else user.id, **body.model_dump())
    db.add(c)
    db.flush()
    log(db, user.id, "cost.posted", "cost_entry", c.id, {"amount": c.amount, "approval": c.approval})
    emit(db, "cost.posted", {"project_id": pid, "cost_id": c.id, "approval": c.approval})
    db.commit()
    return c_out(c)


@router.post("/projects/{pid}/costs/{cid}/approve")
def approve_cost(pid: int, cid: int, db=Depends(get_db), user: User = Depends(require_roles("PMO", "ADMIN"))):
    c = db.get(CostEntry, cid)
    if not c or c.project_id != pid:
        raise HTTPException(404, "Cost entry not found")
    if c.approval == "approved":
        raise HTTPException(409, "Already approved")
    c.approval, c.approved_by = "approved", user.id
    log(db, user.id, "cost.approved", "cost_entry", cid, {"amount": c.amount})
    emit(db, "cost.posted", {"project_id": pid, "cost_id": cid, "approval": "approved"})
    db.commit()
    return c_out(c)


@router.get("/projects/{pid}/costs")
def list_costs(pid: int, db=Depends(get_db), user: User = Depends(current_user)):
    p = get_project(db, pid)
    if not can_view_cost(db, user, p):
        raise HTTPException(403, "cost_view permission required")
    return [c_out(c) for c in db.query(CostEntry).filter_by(project_id=pid).order_by(CostEntry.id)]


# ---------------- 2.1b planned allocation ----------------
class AllocIn(BaseModel):
    user_id: int
    week_of: date
    hours: float = Field(ge=0, le=80)


@router.put("/projects/{pid}/allocations")
def set_allocation(pid: int, body: AllocIn, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p = get_project(db, pid)
    need_manage(db, user, p)
    staff = db.get(User, body.user_id)
    if not staff or not db.query(Assignment).filter_by(project_id=pid, user_id=body.user_id).first():
        raise HTTPException(422, "User must be assigned to the project first")
    ws = wk(body.week_of)
    row = db.query(PlannedAllocation).filter_by(project_id=pid, user_id=body.user_id, week_start=ws).first()
    if row:
        row.hours = body.hours
    else:
        db.add(PlannedAllocation(project_id=pid, user_id=body.user_id, week_start=ws, hours=body.hours))
    db.flush()
    total = db.query(func.coalesce(func.sum(PlannedAllocation.hours), 0.0)).filter_by(user_id=body.user_id, week_start=ws).scalar()
    warnings = []
    if total > staff.capacity_hours_week:
        warnings.append(f"Over-allocated: {total:g} planned hours across projects vs capacity {staff.capacity_hours_week:g}")
    log(db, user.id, "allocation.updated", "project", pid, {"user_id": body.user_id, "week_start": str(ws), "hours": body.hours})
    emit(db, "allocation.updated", {"project_id": pid, "user_id": body.user_id, "week_start": str(ws)})
    db.commit()
    return {"project_id": pid, "user_id": body.user_id, "week_start": ws, "hours": body.hours,
            "total_planned_that_week": total, "warnings": warnings}


@router.get("/allocations/load")
def resource_load(week_of: date | None = None, db=Depends(get_db), user: User = Depends(require_roles("PM", "PMO", "ADMIN", "PROGRAM_MANAGER", "DECISION_MAKER"))):
    """Resource load: planned vs capacity vs actual (submitted + approved) hours, per staff for one week."""
    ws = wk(week_of or date.today())
    out = []
    for u in db.query(User).filter(User.role.in_(("STAFF", "PM"))).order_by(User.id):
        planned = db.query(func.coalesce(func.sum(PlannedAllocation.hours), 0.0)).filter_by(user_id=u.id, week_start=ws).scalar()
        actual = db.query(func.coalesce(func.sum(TimesheetEntry.hours), 0.0)).filter(
            TimesheetEntry.user_id == u.id, TimesheetEntry.status.in_(("submitted", "approved")),
            TimesheetEntry.entry_date >= ws, TimesheetEntry.entry_date <= ws + timedelta(days=6)).scalar()
        if planned or actual:
            out.append({"user_id": u.id, "staff_id": u.staff_id, "capacity": effective_capacity(db, u.capacity_hours_week, ws), "planned": planned,
                        "actual": actual, "over_allocated": planned > effective_capacity(db, u.capacity_hours_week, ws)})
    return {"week_start": ws, "staff": out}


@router.get("/projects/{pid}/allocations")
def list_allocations(pid: int, db=Depends(get_db), user: User = Depends(current_user)):
    p = get_project(db, pid)
    if not can_view_cost(db, user, p):
        raise HTTPException(403, "No access to this project's allocations")
    rows = db.query(PlannedAllocation).filter_by(project_id=pid).order_by(PlannedAllocation.week_start, PlannedAllocation.user_id)
    return [{"user_id": r.user_id, "week_start": r.week_start, "hours": r.hours} for r in rows]
