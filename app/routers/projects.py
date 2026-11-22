from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func

from ..audit import emit, log
from ..config import PHASE_ACTIVITIES
from ..deps import current_user, get_db, require_roles
from ..models import (Activity, ActivityStaffLimit, Assignment, BaselineRate, ChangeRequest, Project,
                      RateCard, TimesheetEntry, User)

router = APIRouter(prefix="/projects", tags=["projects (Layer 1)"])
MANAGE = ("PM", "PMO", "ADMIN")


class ProjectIn(BaseModel):
    number: str
    name: str
    state: str = "planning"          # tendering | planning
    planned_start: date | None = None
    planned_end: date | None = None
    budget_ceiling: float | None = Field(None, ge=0)
    currency: str = Field("SAR", min_length=3, max_length=3)
    project_type: str = "predictive"


class ActivityIn(BaseModel):
    code: str
    name: str
    planned_hours: float = Field(gt=0)
    baseline_cost: float | None = Field(None, ge=0)   # BAC for this activity; needed for EVM
    planned_start: date | None = None                  # needed to phase PV per activity
    planned_end: date | None = None
    change_id: int | None = None     # required once the project is in execution (approved change)


class LimitIn(BaseModel):
    user_id: int
    max_hours: float = Field(gt=0)


class AssignIn(BaseModel):
    user_id: int


class TransitionIn(BaseModel):
    to_state: str


class ChangeIn(BaseModel):
    change_type: str                 # scope | schedule | cost | risk | other
    description: str
    impact_hours_delta: float | None = None
    impact_cost_delta: float | None = None
    impact_schedule_days: int | None = None


class DecisionIn(BaseModel):
    approve: bool
    reason: str | None = None


pending_router = APIRouter(tags=["projects (Layer 1)"])


@pending_router.get("/changes/pending")
def pending_changes(db=Depends(get_db), user: User = Depends(current_user)):
    """Change requests awaiting a decision, for CCB members and PMO/ADMIN (never your own request)."""
    if not (user.is_ccb or user.role in ("PMO", "ADMIN")):
        raise HTTPException(403, "Only CCB members or PMO can decide change requests")
    q = db.query(ChangeRequest).filter_by(status="requested").order_by(ChangeRequest.id)
    return [cr_out(c, True) for c in q if c.requested_by != user.id or user.role == "ADMIN"]


def p_out(p: Project) -> dict:
    return {"id": p.id, "number": p.number, "name": p.name, "state": p.state, "pm_id": p.pm_id,
            "planned_start": p.planned_start, "planned_end": p.planned_end, "budget_ceiling": p.budget_ceiling,
            "currency": p.currency, "project_type": p.project_type, "baseline_version": p.baseline_version,
            "program_id": p.program_id}


def a_out(a: Activity, cost: bool = False) -> dict:
    d = {"id": a.id, "code": a.code, "name": a.name, "phase": a.phase, "planned_hours": a.planned_hours,
         "locked": a.locked, "baseline_version": a.baseline_version}
    d["planned_start"], d["planned_end"] = a.planned_start, a.planned_end
    if cost:
        d["baseline_cost"] = a.baseline_cost    # cost data: cost viewers only (4.1)
    return d


def get_project(db, pid: int) -> Project:
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "Project not found")
    return p


def can_manage(db, user: User, p: Project) -> bool:
    if user.role in ("PMO", "ADMIN"):
        return True
    if user.role == "PM":
        pm = db.get(User, p.pm_id)
        return p.pm_id == user.id or (pm is not None and pm.delegate_id == user.id)
    return False


def need_manage(db, user, p):
    if not can_manage(db, user, p):
        raise HTTPException(403, "Not the project manager of this project")


def can_view_cost(db, user: User, p: Project) -> bool:
    """Cost_view permission: project manager (or delegate), PMO, ADMIN, DECISION_MAKER, PROGRAM_MANAGER."""
    return user.role in ("PMO", "ADMIN", "DECISION_MAKER", "PROGRAM_MANAGER") or can_manage(db, user, p)


def can_view(db, user: User, p: Project) -> bool:
    if user.role in ("PMO", "ADMIN", "DECISION_MAKER", "PROGRAM_MANAGER"):
        return True
    if can_manage(db, user, p):
        return True
    return db.query(Assignment).filter_by(project_id=p.id, user_id=user.id).first() is not None


@router.post("", status_code=201)
def create_project(body: ProjectIn, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    if body.state not in ("tendering", "planning"):
        raise HTTPException(422, "Initial state must be tendering or planning")
    if body.planned_start and body.planned_end and body.planned_end < body.planned_start:
        raise HTTPException(422, "planned_end before planned_start")
    if db.query(Project).filter_by(number=body.number).first():
        raise HTTPException(409, "project_number already exists")
    p = Project(**body.model_dump(), pm_id=user.id)
    db.add(p)
    db.flush()
    for phase, (code, name) in PHASE_ACTIVITIES.items():   # phase activities allow time before a baseline exists
        db.add(Activity(project_id=p.id, code=code, name=name, phase=phase, planned_hours=None, locked=True))
    log(db, user.id, "project.created", "project", p.id, {"number": p.number, "state": p.state})
    emit(db, "project.created", {"project_id": p.id})
    db.commit()
    return p_out(p)


@router.get("")
def list_projects(db=Depends(get_db), user: User = Depends(current_user)):
    out = [p for p in db.query(Project).order_by(Project.id).all() if can_view(db, user, p)]
    return [p_out(p) for p in out]


@router.get("/{pid}")
def get_one(pid: int, db=Depends(get_db), user: User = Depends(current_user)):
    p = get_project(db, pid)
    if not can_view(db, user, p):
        raise HTTPException(403, "No access to this project")
    acts = db.query(Activity).filter_by(project_id=pid).order_by(Activity.id).all()
    cost = can_view_cost(db, user, p)
    out = {**p_out(p), "activities": [a_out(a, cost) for a in acts]}
    if cost:
        out["assigned_user_ids"] = [a.user_id for a in db.query(Assignment).filter_by(project_id=pid)]
    return out


@router.post("/{pid}/assignments", status_code=201)
def assign(pid: int, body: AssignIn, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p = get_project(db, pid)
    need_manage(db, user, p)
    if not db.get(User, body.user_id):
        raise HTTPException(404, "User not found")
    if db.query(Assignment).filter_by(project_id=pid, user_id=body.user_id).first():
        raise HTTPException(409, "Already assigned")
    db.add(Assignment(project_id=pid, user_id=body.user_id))
    log(db, user.id, "staff.assigned", "project", pid, {"user_id": body.user_id})
    emit(db, "staff.assigned", {"project_id": pid, "user_id": body.user_id})
    db.commit()
    return {"project_id": pid, "user_id": body.user_id}


@router.post("/{pid}/activities", status_code=201)
def add_activity(pid: int, body: ActivityIn, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p = get_project(db, pid)
    need_manage(db, user, p)
    cr = None
    if p.state == "planning":
        pass
    elif p.state == "execution":
        cr = db.get(ChangeRequest, body.change_id) if body.change_id else None
        if not cr or cr.project_id != pid or cr.status != "approved":
            raise HTTPException(409, "In execution, activities can only be added through an approved change request (change_id)")
    else:
        raise HTTPException(409, f"Cannot add activities in state {p.state}")
    if db.query(Activity).filter_by(project_id=pid, code=body.code).first():
        raise HTTPException(409, "Activity code already exists")
    if (body.planned_start is None) != (body.planned_end is None):
        raise HTTPException(422, "Give both planned_start and planned_end, or neither")
    if body.planned_start and body.planned_end < body.planned_start:
        raise HTTPException(422, "planned_end before planned_start")
    a = Activity(planned_start=body.planned_start, planned_end=body.planned_end, project_id=pid, code=body.code, name=body.name, phase="execution",
                 planned_hours=body.planned_hours, baseline_cost=body.baseline_cost, locked=cr is not None,
                 baseline_version=cr.new_baseline_version if cr else None)
    db.add(a)
    db.flush()
    if cr:
        cr.status = "applied"
    log(db, user.id, "activity.added", "activity", a.id, {"project_id": pid, "code": a.code, "change_id": body.change_id})
    db.commit()
    return a_out(a, True)


@router.put("/{pid}/activities/{aid}/limits")
def set_limit(pid: int, aid: int, body: LimitIn, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p = get_project(db, pid)
    need_manage(db, user, p)
    a = db.get(Activity, aid)
    if not a or a.project_id != pid:
        raise HTTPException(404, "Activity not found")
    row = db.query(ActivityStaffLimit).filter_by(activity_id=aid, user_id=body.user_id).first()
    if row:
        row.max_hours = body.max_hours
    else:
        db.add(ActivityStaffLimit(activity_id=aid, user_id=body.user_id, max_hours=body.max_hours))
    log(db, user.id, "activity.limit_set", "activity", aid, body.model_dump())
    db.commit()
    return {"activity_id": aid, **body.model_dump()}


@router.post("/{pid}/baseline/lock")
def lock_baseline(pid: int, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    """1.3 baseline lock (manual plan entry in Phase 1): freezes activities as baseline v1.0."""
    p = get_project(db, pid)
    need_manage(db, user, p)
    if p.state != "planning":
        raise HTTPException(409, "Baseline can only be locked in planning state")
    acts = db.query(Activity).filter_by(project_id=pid, phase="execution").all()
    if not acts:
        raise HTTPException(409, "Add at least one execution activity before locking the baseline")
    if not p.planned_start or not p.planned_end:
        raise HTTPException(409, "planned_start and planned_end are required before baselining")
    p.baseline_version = 1
    for a in acts:
        a.locked, a.baseline_version = True, 1
    p.previous_state, p.state = p.state, "execution"
    seen = set()                                   # snapshot the rates in force at lock (latest per grade)
    for r in db.query(RateCard).order_by(RateCard.effective_from.desc()).all():
        if r.grade not in seen and r.effective_from <= date.today():
            seen.add(r.grade)
            db.add(BaselineRate(project_id=pid, baseline_version=1, grade=r.grade, hourly_rate=r.hourly_rate, currency=r.currency))
    log(db, user.id, "baseline.locked", "project", pid, {"version": 1, "activities": len(acts)})
    emit(db, "project.baselined", {"project_id": pid, "version": 1})
    emit(db, "project.state_changed", {"project_id": pid, "from": "planning", "to": "execution"})
    db.commit()
    return {**p_out(p), "activities": [a_out(a, True) for a in acts]}


# 1.0 state machine: (from, to) -> roles allowed. planning -> execution happens only via baseline lock.
TRANSITIONS = {
    ("tendering", "planning"): MANAGE,
    ("tendering", "archived"): MANAGE,
    ("execution", "closing"): MANAGE,
    ("closing", "archived"): ("PMO", "ADMIN"),
    ("planning", "on_hold"): ("PMO", "ADMIN"),
    ("execution", "on_hold"): ("PMO", "ADMIN"),
}


@router.post("/{pid}/transition")
def transition(pid: int, body: TransitionIn, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p = get_project(db, pid)
    to, frm = body.to_state, p.state
    if to == "cancelled" and frm not in ("archived", "cancelled"):
        allowed = ("PMO", "ADMIN")
    elif frm == "on_hold" and to == p.previous_state:
        allowed = ("PMO", "ADMIN")            # resume
    else:
        allowed = TRANSITIONS.get((frm, to))
    if not allowed:
        raise HTTPException(409, f"Transition {frm} -> {to} is not allowed")
    if user.role not in allowed:
        raise HTTPException(403, f"Transition {frm} -> {to} requires role: {', '.join(allowed)}")
    need_manage(db, user, p)
    if to == "closing":
        from .governance import ensure_closure_items
        ensure_closure_items(db, pid)
    if to == "archived" and frm == "closing":   # closure checklist (1.5)
        pending = db.query(func.count(TimesheetEntry.id)).filter_by(project_id=pid, status="submitted").scalar()
        if pending:
            raise HTTPException(409, f"Closure blocked: {pending} timesheet entries still awaiting approval")
        from .governance import closure_status
        open_items = [i["key"] for i in closure_status(db, pid) if not i["satisfied"]]
        if open_items:
            raise HTTPException(409, f"Closure blocked: checklist items not complete: {', '.join(open_items)}")
    if to in ("on_hold",):
        p.previous_state = frm
    p.state = to
    log(db, user.id, "project.state_changed", "project", pid, {"from": frm, "to": to})
    emit(db, "project.state_changed", {"project_id": pid, "from": frm, "to": to})
    db.commit()
    return p_out(p)


# ---- 1.4 change control (Phase 1: manual baseline revision) ----
@router.post("/{pid}/changes", status_code=201)
def request_change(pid: int, body: ChangeIn, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p = get_project(db, pid)
    need_manage(db, user, p)
    if p.state != "execution":
        raise HTTPException(409, "Change control applies to projects in execution")
    if body.change_type not in ("scope", "schedule", "cost", "risk", "other"):
        raise HTTPException(422, "Invalid change_type")
    if body.impact_cost_delta is None and body.impact_schedule_days is None and body.impact_hours_delta is None:
        raise HTTPException(422, "Impact analysis must state at least one of hours, cost or schedule delta")
    cr = ChangeRequest(project_id=pid, requested_by=user.id, **body.model_dump())
    db.add(cr)
    db.flush()
    log(db, user.id, "change.requested", "change_request", cr.id, {"project_id": pid})
    emit(db, "change.requested", {"project_id": pid, "change_id": cr.id})
    db.commit()
    return {"id": cr.id, "status": cr.status}


def cr_out(cr: ChangeRequest, cost_ok: bool) -> dict:
    d = {"id": cr.id, "project_id": cr.project_id, "change_type": cr.change_type, "description": cr.description,
         "impact_hours_delta": cr.impact_hours_delta, "impact_schedule_days": cr.impact_schedule_days,
         "status": cr.status, "requested_by": cr.requested_by, "decided_by": cr.decided_by,
         "decision_reason": cr.decision_reason, "new_baseline_version": cr.new_baseline_version}
    if cost_ok:
        d["impact_cost_delta"] = cr.impact_cost_delta     # cost data: cost viewers only
    return d


@router.get("/{pid}/changes")
def list_changes(pid: int, db=Depends(get_db), user: User = Depends(current_user)):
    p = get_project(db, pid)
    if not can_view(db, user, p):
        raise HTTPException(403, "No access to this project")
    ok = can_view_cost(db, user, p)
    return [cr_out(c, ok) for c in db.query(ChangeRequest).filter_by(project_id=pid).order_by(ChangeRequest.id.desc())]


@router.post("/{pid}/changes/{cid}/decision")
def decide_change(pid: int, cid: int, body: DecisionIn, db=Depends(get_db), user: User = Depends(current_user)):
    cr = db.get(ChangeRequest, cid)
    if not cr or cr.project_id != pid:
        raise HTTPException(404, "Change request not found")
    if not (user.is_ccb or user.role in ("PMO", "ADMIN")):
        raise HTTPException(403, "Only CCB members or PMO can decide change requests")
    if cr.requested_by == user.id and user.role != "ADMIN":
        raise HTTPException(403, "Requester cannot decide own change request")
    if cr.status != "requested":
        raise HTTPException(409, f"Change request already {cr.status}")
    if not body.approve and not body.reason:
        raise HTTPException(422, "A reason is required to reject")
    p = get_project(db, pid)
    cr.decided_by, cr.decision_reason = user.id, body.reason
    if body.approve:
        p.baseline_version += 1
        cr.status, cr.new_baseline_version = "approved", p.baseline_version
        event = "change.approved"
    else:
        cr.status = "rejected"
        event = "change.rejected"
    log(db, user.id, event, "change_request", cid, {"project_id": pid, "baseline_version": p.baseline_version})
    emit(db, event, {"project_id": pid, "change_id": cid})
    if body.approve:
        emit(db, "baseline.revised", {"project_id": pid, "version": p.baseline_version})
    db.commit()
    return {"id": cid, "status": cr.status, "baseline_version": p.baseline_version}
