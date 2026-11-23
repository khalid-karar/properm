"""Plan depth: milestones, KPIs, activity dependencies and the staff-limit listing."""
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..audit import log
from ..deps import current_user, get_db, require_roles
from ..models import Activity, ActivityDependency, ActivityStaffLimit, Milestone, ProjectKpi, User
from .projects import MANAGE, can_view, get_project, need_manage

router = APIRouter(prefix="/projects", tags=["plan"])


def _editable(db, user, pid):
    p = get_project(db, pid)
    need_manage(db, user, p)
    if p.state == "archived":
        raise HTTPException(409, "Archived projects are read-only")
    return p


def _view(db, user, pid):
    p = get_project(db, pid)
    if not can_view(db, user, p):
        raise HTTPException(404, "Project not found")
    return p


# ---------- milestones ----------
class MilestoneIn(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    due_date: date
    activity_id: int | None = None


class MilestonePatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=300)
    due_date: date | None = None
    achieved_on: date | None = None
    clear_achieved: bool = False


def ms_out(m: Milestone) -> dict:
    today = date.today()
    status = "achieved" if m.achieved_on else ("missed" if m.due_date < today else "upcoming")
    return {"id": m.id, "name": m.name, "due_date": m.due_date.isoformat(), "achieved_on": m.achieved_on.isoformat() if m.achieved_on else None,
            "activity_id": m.activity_id, "status": status,
            "slip_days": ((m.achieved_on or today) - m.due_date).days if (m.achieved_on or m.due_date < today) else 0}


@router.get("/{pid}/milestones")
def list_milestones(pid: int, db=Depends(get_db), user: User = Depends(current_user)):
    _view(db, user, pid)
    return [ms_out(m) for m in db.query(Milestone).filter_by(project_id=pid).order_by(Milestone.due_date, Milestone.id)]


@router.post("/{pid}/milestones", status_code=201)
def add_milestone(pid: int, body: MilestoneIn, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    _editable(db, user, pid)
    if body.activity_id is not None:
        a = db.get(Activity, body.activity_id)
        if not a or a.project_id != pid:
            raise HTTPException(422, "Activity is not in this project")
    m = Milestone(project_id=pid, name=body.name.strip(), due_date=body.due_date, activity_id=body.activity_id)
    db.add(m)
    db.flush()
    log(db, user.id, "milestone.added", "milestone", m.id, {"project_id": pid, "name": m.name, "due": m.due_date.isoformat()})
    db.commit()
    return ms_out(m)


@router.patch("/{pid}/milestones/{mid}")
def edit_milestone(pid: int, mid: int, body: MilestonePatch, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    _editable(db, user, pid)
    m = db.get(Milestone, mid)
    if not m or m.project_id != pid:
        raise HTTPException(404, "Milestone not found")
    if body.name:
        m.name = body.name.strip()
    if body.due_date:
        m.due_date = body.due_date
    if body.clear_achieved:
        m.achieved_on = None
    elif body.achieved_on:
        if body.achieved_on > date.today():
            raise HTTPException(422, "Achieved date cannot be in the future")
        m.achieved_on = body.achieved_on
    log(db, user.id, "milestone.edited", "milestone", m.id, body.model_dump(mode="json", exclude_none=True))
    db.commit()
    return ms_out(m)


@router.delete("/{pid}/milestones/{mid}", status_code=204)
def delete_milestone(pid: int, mid: int, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    _editable(db, user, pid)
    m = db.get(Milestone, mid)
    if not m or m.project_id != pid:
        raise HTTPException(404, "Milestone not found")
    log(db, user.id, "milestone.deleted", "milestone", mid, {"project_id": pid, "name": m.name})
    db.delete(m)
    db.commit()


# ---------- KPIs ----------
class KpiIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    unit: str | None = Field(None, max_length=30)
    target: float
    higher_is_better: bool = True


class KpiActual(BaseModel):
    actual: float


def kpi_out(k: ProjectKpi) -> dict:
    rag = None
    ratio = None
    if k.actual is not None and k.target:
        ratio = k.actual / k.target if k.higher_is_better else k.target / k.actual if k.actual else None
        if ratio is not None:
            rag = "green" if ratio >= 1 else "amber" if ratio >= 0.9 else "red"
    return {"id": k.id, "name": k.name, "unit": k.unit, "target": k.target, "actual": k.actual, "higher_is_better": k.higher_is_better,
            "rag": rag, "achievement_pct": round(ratio * 100, 1) if ratio is not None else None,
            "updated_at": k.updated_at.isoformat() if k.updated_at else None}


@router.get("/{pid}/kpis")
def list_kpis(pid: int, db=Depends(get_db), user: User = Depends(current_user)):
    _view(db, user, pid)
    return [kpi_out(k) for k in db.query(ProjectKpi).filter_by(project_id=pid).order_by(ProjectKpi.id)]


@router.post("/{pid}/kpis", status_code=201)
def add_kpi(pid: int, body: KpiIn, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    _editable(db, user, pid)
    if body.target == 0:
        raise HTTPException(422, "Target cannot be zero")
    k = ProjectKpi(project_id=pid, name=body.name.strip(), unit=body.unit, target=body.target, higher_is_better=body.higher_is_better)
    db.add(k)
    db.flush()
    log(db, user.id, "kpi.added", "kpi", k.id, {"project_id": pid, "name": k.name, "target": k.target})
    db.commit()
    return kpi_out(k)


@router.put("/{pid}/kpis/{kid}/actual")
def set_kpi_actual(pid: int, kid: int, body: KpiActual, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    _editable(db, user, pid)
    k = db.get(ProjectKpi, kid)
    if not k or k.project_id != pid:
        raise HTTPException(404, "KPI not found")
    k.actual = body.actual
    k.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    log(db, user.id, "kpi.updated", "kpi", k.id, {"actual": body.actual})
    db.commit()
    return kpi_out(k)


@router.delete("/{pid}/kpis/{kid}", status_code=204)
def delete_kpi(pid: int, kid: int, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    _editable(db, user, pid)
    k = db.get(ProjectKpi, kid)
    if not k or k.project_id != pid:
        raise HTTPException(404, "KPI not found")
    log(db, user.id, "kpi.deleted", "kpi", kid, {"project_id": pid, "name": k.name})
    db.delete(k)
    db.commit()


# ---------- dependencies ----------
class DepIn(BaseModel):
    activity_id: int
    predecessor_id: int


def _reaches(db, start: int, goal: int) -> bool:
    """True if `goal` is reachable from `start` following successor links (cycle test)."""
    seen, stack = set(), [start]
    while stack:
        cur = stack.pop()
        if cur == goal:
            return True
        if cur in seen:
            continue
        seen.add(cur)
        stack += [d.activity_id for d in db.query(ActivityDependency).filter_by(predecessor_id=cur)]
    return False


@router.get("/{pid}/dependencies")
def list_dependencies(pid: int, db=Depends(get_db), user: User = Depends(current_user)):
    _view(db, user, pid)
    acts = {a.id: a for a in db.query(Activity).filter_by(project_id=pid)}
    out = []
    for d in db.query(ActivityDependency).filter(ActivityDependency.activity_id.in_(list(acts) or [0])).order_by(ActivityDependency.id):
        a, pr = acts[d.activity_id], acts.get(d.predecessor_id)
        if not pr:
            continue
        conflict = bool(a.planned_start and pr.planned_end and a.planned_start <= pr.planned_end)
        out.append({"id": d.id, "activity_id": a.id, "activity_code": a.code, "predecessor_id": pr.id, "predecessor_code": pr.code, "date_conflict": conflict})
    return out


@router.post("/{pid}/dependencies", status_code=201)
def add_dependency(pid: int, body: DepIn, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    _editable(db, user, pid)
    a, pr = db.get(Activity, body.activity_id), db.get(Activity, body.predecessor_id)
    if not a or not pr or a.project_id != pid or pr.project_id != pid:
        raise HTTPException(422, "Both activities must belong to this project")
    if a.id == pr.id:
        raise HTTPException(422, "An activity cannot depend on itself")
    if db.query(ActivityDependency).filter_by(activity_id=a.id, predecessor_id=pr.id).first():
        raise HTTPException(409, "Dependency already exists")
    if _reaches(db, a.id, pr.id):
        raise HTTPException(422, "This link would create a circular dependency")
    d = ActivityDependency(activity_id=a.id, predecessor_id=pr.id)
    db.add(d)
    db.flush()
    log(db, user.id, "dependency.added", "activity", a.id, {"project_id": pid, "predecessor": pr.code})
    db.commit()
    return {"id": d.id, "activity_id": a.id, "predecessor_id": pr.id}


@router.delete("/{pid}/dependencies/{did}", status_code=204)
def delete_dependency(pid: int, did: int, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    _editable(db, user, pid)
    d = db.get(ActivityDependency, did)
    a = db.get(Activity, d.activity_id) if d else None
    if not d or not a or a.project_id != pid:
        raise HTTPException(404, "Dependency not found")
    log(db, user.id, "dependency.deleted", "activity", a.id, {"project_id": pid})
    db.delete(d)
    db.commit()


# ---------- staff limits listing ----------
@router.get("/{pid}/limits")
def list_limits(pid: int, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p = get_project(db, pid)
    need_manage(db, user, p)
    acts = {a.id: a for a in db.query(Activity).filter_by(project_id=pid)}
    return [{"activity_id": l.activity_id, "activity_code": acts[l.activity_id].code, "user_id": l.user_id, "max_hours": l.max_hours}
            for l in db.query(ActivityStaffLimit).filter(ActivityStaffLimit.activity_id.in_(list(acts) or [0]))]


@router.delete("/{pid}/activities/{aid}/limits/{uid}", status_code=204)
def clear_limit(pid: int, aid: int, uid: int, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    _editable(db, user, pid)
    a = db.get(Activity, aid)
    row = db.query(ActivityStaffLimit).filter_by(activity_id=aid, user_id=uid).first()
    if not a or a.project_id != pid or not row:
        raise HTTPException(404, "Limit not found")
    log(db, user.id, "activity.limit_cleared", "activity", aid, {"user_id": uid})
    db.delete(row)
    db.commit()
