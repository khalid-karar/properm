"""Program management: roadmap, cross-project dependencies, program-level risks."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..alerts import rag_status
from ..audit import log
from ..deps import current_user, get_db
from ..models import Milestone, Program, ProgramRisk, Project, ProjectDependency, User
from .dashboards import EXEC, overall_pct

router = APIRouter(prefix="/programs", tags=["program management"])


def _prog(db, gid, user, manage=False) -> Program:
    if user.role not in EXEC:
        raise HTTPException(403, "Programs require PMO, ADMIN, DECISION_MAKER or PROGRAM_MANAGER")
    g = db.get(Program, gid)
    if not g:
        raise HTTPException(404, "Program not found")
    if manage and not (user.role in ("PMO", "ADMIN") or (user.role == "PROGRAM_MANAGER" and g.manager_id == user.id)):
        raise HTTPException(403, "Only PMO, ADMIN or this program's manager can change it")
    return g


def _dep_out(db, d: ProjectDependency, projects) -> dict:
    succ, pred = projects.get(d.project_id), projects.get(d.predecessor_id)
    m = db.get(Milestone, d.milestone_id) if d.milestone_id else None
    delivers = (m.achieved_on or m.due_date) if m else (pred.planned_end if pred else None)
    met = bool(m and m.achieved_on) or (m is None and pred is not None and pred.state in ("closing", "archived"))
    conflict = (not met) and delivers is not None and delivers > d.needed_by
    late = (not met) and d.needed_by < date.today()
    return {"id": d.id, "project_id": d.project_id, "project": succ.number if succ else None, "predecessor_id": d.predecessor_id,
            "predecessor": pred.number if pred else None, "milestone_id": d.milestone_id, "milestone": m.name if m else None,
            "delivers_on": delivers, "needed_by": d.needed_by, "description": d.description,
            "status": "met" if met else "late" if late else "conflict" if conflict else "on_track", "gap_days": (delivers - d.needed_by).days if conflict else 0}


@router.get("/{gid}/roadmap")
def roadmap(gid: int, db=Depends(get_db), user: User = Depends(current_user)):
    g = _prog(db, gid, user)
    today = date.today()
    projects = {p.id: p for p in db.query(Project).all()}
    rows = []
    for p in sorted((p for p in projects.values() if p.program_id == gid), key=lambda p: (p.planned_start or date.max, p.number)):
        ms = db.query(Milestone).filter_by(project_id=p.id).order_by(Milestone.due_date).all()
        rows.append({"project_id": p.id, "number": p.number, "name": p.name, "state": p.state, "rag": rag_status(db, p),
                     "start": p.planned_start, "end": p.planned_end,
                     "progress_pct": overall_pct(db, p, today) if p.state in ("execution", "closing") else None,
                     "milestones": [{"id": m.id, "name": m.name, "due_date": m.due_date, "achieved_on": m.achieved_on} for m in ms]})
    deps = [_dep_out(db, d, projects) for d in db.query(ProjectDependency).filter_by(program_id=gid).order_by(ProjectDependency.needed_by)]
    can = user.role in ("PMO", "ADMIN") or (user.role == "PROGRAM_MANAGER" and g.manager_id == user.id)
    return {"program": {"id": g.id, "code": g.code, "name": g.name, "description": g.description, "manager_id": g.manager_id},
            "can_manage": can, "projects": rows, "dependencies": deps,
            "conflicts": sum(1 for d in deps if d["status"] in ("conflict", "late"))}


class DepIn(BaseModel):
    project_id: int
    predecessor_id: int
    milestone_id: int | None = None
    needed_by: date
    description: str | None = Field(None, max_length=2000)


@router.post("/{gid}/dependencies", status_code=201)
def add_dep(gid: int, body: DepIn, db=Depends(get_db), user: User = Depends(current_user)):
    _prog(db, gid, user, manage=True)
    succ, pred = db.get(Project, body.project_id), db.get(Project, body.predecessor_id)
    if not succ or not pred:
        raise HTTPException(404, "Project not found")
    if succ.program_id != gid:
        raise HTTPException(422, "The waiting project must be in this program")
    if succ.id == pred.id:
        raise HTTPException(422, "A project cannot depend on itself")
    if body.milestone_id is not None:
        m = db.get(Milestone, body.milestone_id)
        if not m or m.project_id != pred.id:
            raise HTTPException(422, "The milestone must belong to the delivering project")
    # refuse a direct cycle (A waits for B while B waits for A)
    if db.query(ProjectDependency).filter_by(project_id=pred.id, predecessor_id=succ.id).first():
        raise HTTPException(409, f"{pred.number} already waits for {succ.number}; that would be a loop")
    d = ProjectDependency(program_id=gid, **body.model_dump())
    db.add(d)
    db.flush()
    log(db, user.id, "program.dependency_added", "project_dependency", d.id, {"program_id": gid})
    db.commit()
    return _dep_out(db, d, {p.id: p for p in (succ, pred)})


@router.delete("/{gid}/dependencies/{did}", status_code=204)
def del_dep(gid: int, did: int, db=Depends(get_db), user: User = Depends(current_user)):
    _prog(db, gid, user, manage=True)
    d = db.get(ProjectDependency, did)
    if not d or d.program_id != gid:
        raise HTTPException(404, "Dependency not found")
    db.delete(d)
    log(db, user.id, "program.dependency_removed", "project_dependency", did, {"program_id": gid})
    db.commit()


class PRiskIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    probability: int = Field(ge=1, le=5)
    impact: int = Field(ge=1, le=5)
    response: str | None = Field(None, max_length=5000)
    owner_id: int | None = None


class PRiskPatch(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=300)
    probability: int | None = Field(None, ge=1, le=5)
    impact: int | None = Field(None, ge=1, le=5)
    response: str | None = None
    owner_id: int | None = None
    status: str | None = None


def _pr_out(r: ProgramRisk, names) -> dict:
    return {"id": r.id, "title": r.title, "probability": r.probability, "impact": r.impact, "score": r.score, "response": r.response,
            "owner_id": r.owner_id, "owner": names.get(r.owner_id), "status": r.status}


@router.get("/{gid}/risks")
def list_prisks(gid: int, db=Depends(get_db), user: User = Depends(current_user)):
    _prog(db, gid, user)
    names = {u.id: u.full_name for u in db.query(User)}
    rows = db.query(ProgramRisk).filter_by(program_id=gid).all()
    rows.sort(key=lambda r: (r.status in ("closed",), -r.score))
    return [_pr_out(r, names) for r in rows]


@router.post("/{gid}/risks", status_code=201)
def add_prisk(gid: int, body: PRiskIn, db=Depends(get_db), user: User = Depends(current_user)):
    _prog(db, gid, user, manage=True)
    if body.owner_id is not None and not db.get(User, body.owner_id):
        raise HTTPException(422, "owner_id must be an existing user")
    r = ProgramRisk(program_id=gid, **body.model_dump())
    db.add(r)
    db.flush()
    log(db, user.id, "program.risk_added", "program_risk", r.id, {"program_id": gid})
    db.commit()
    return _pr_out(r, {u.id: u.full_name for u in db.query(User)})


@router.patch("/{gid}/risks/{rid}")
def patch_prisk(gid: int, rid: int, body: PRiskPatch, db=Depends(get_db), user: User = Depends(current_user)):
    _prog(db, gid, user, manage=True)
    r = db.get(ProgramRisk, rid)
    if not r or r.program_id != gid:
        raise HTTPException(404, "Risk not found")
    ch = body.model_dump(exclude_unset=True)
    if "status" in ch and ch["status"] not in ("open", "mitigating", "occurred", "closed"):
        raise HTTPException(422, "status must be open, mitigating, occurred or closed")
    if ch.get("owner_id") is not None and not db.get(User, ch["owner_id"]):
        raise HTTPException(422, "owner_id must be an existing user")
    for k, v in ch.items():
        setattr(r, k, v)
    log(db, user.id, "program.risk_updated", "program_risk", rid, ch)
    db.commit()
    return _pr_out(r, {u.id: u.full_name for u in db.query(User)})
