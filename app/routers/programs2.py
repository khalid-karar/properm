"""Program management: roadmap, cross-project dependencies, program-level risks."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..alerts import rag_status
from ..audit import log
from ..deps import current_user, get_db
from ..models import Benefit, Milestone, Program, ProgramBudget, ProgramIssue, ProgramRisk, Project, ProjectDependency, User
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


# ---------------- program issues ----------------
class PIssueIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    severity: str = "medium"
    owner_id: int | None = None
    due_date: date | None = None


class PIssuePatch(BaseModel):
    severity: str | None = None
    owner_id: int | None = None
    due_date: date | None = None
    status: str | None = None


def _pi_out(x: ProgramIssue, names) -> dict:
    return {"id": x.id, "title": x.title, "severity": x.severity, "owner_id": x.owner_id, "owner": names.get(x.owner_id), "due_date": x.due_date,
            "status": x.status, "overdue": x.status in ("open", "in_progress") and x.due_date is not None and x.due_date < date.today()}


@router.get("/{gid}/issues")
def list_pissues(gid: int, db=Depends(get_db), user: User = Depends(current_user)):
    _prog(db, gid, user)
    names = {u.id: u.full_name for u in db.query(User)}
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    rows = sorted(db.query(ProgramIssue).filter_by(program_id=gid), key=lambda x: (x.status in ("resolved", "closed"), order.get(x.severity, 9)))
    return [_pi_out(x, names) for x in rows]


@router.post("/{gid}/issues", status_code=201)
def add_pissue(gid: int, body: PIssueIn, db=Depends(get_db), user: User = Depends(current_user)):
    _prog(db, gid, user, manage=True)
    if body.severity not in ("low", "medium", "high", "critical"):
        raise HTTPException(422, "severity must be low, medium, high or critical")
    x = ProgramIssue(program_id=gid, **body.model_dump())
    db.add(x)
    db.flush()
    log(db, user.id, "program.issue_added", "program_issue", x.id, {"program_id": gid})
    db.commit()
    return _pi_out(x, {u.id: u.full_name for u in db.query(User)})


@router.patch("/{gid}/issues/{iid}")
def patch_pissue(gid: int, iid: int, body: PIssuePatch, db=Depends(get_db), user: User = Depends(current_user)):
    _prog(db, gid, user, manage=True)
    x = db.get(ProgramIssue, iid)
    if not x or x.program_id != gid:
        raise HTTPException(404, "Issue not found")
    ch = body.model_dump(exclude_unset=True)
    if "status" in ch and ch["status"] not in ("open", "in_progress", "resolved", "closed"):
        raise HTTPException(422, "status must be open, in_progress, resolved or closed")
    if "severity" in ch and ch["severity"] not in ("low", "medium", "high", "critical"):
        raise HTTPException(422, "severity must be low, medium, high or critical")
    for k, v in ch.items():
        setattr(x, k, v)
    log(db, user.id, "program.issue_updated", "program_issue", iid, {k: str(v) for k, v in ch.items()})
    db.commit()
    return _pi_out(x, {u.id: u.full_name for u in db.query(User)})


# ---------------- budget envelope and benefits plan ----------------
class EnvelopeIn(BaseModel):
    envelope: float = Field(ge=0)
    currency: str = Field("SAR", min_length=3, max_length=3)


@router.put("/{gid}/budget")
def set_envelope(gid: int, body: EnvelopeIn, db=Depends(get_db), user: User = Depends(current_user)):
    if user.role not in ("PMO", "ADMIN", "DECISION_MAKER"):
        raise HTTPException(403, "The funding envelope is set by PMO, ADMIN or a decision maker")
    _prog(db, gid, user)
    b = db.get(ProgramBudget, gid) or ProgramBudget(program_id=gid, envelope=0)
    b.envelope, b.currency = body.envelope, body.currency.upper()
    db.add(b)
    log(db, user.id, "program.envelope_set", "program", gid, body.model_dump())
    db.commit()
    return budget(gid, db, user)


@router.get("/{gid}/budget")
def budget(gid: int, db=Depends(get_db), user: User = Depends(current_user)):
    _prog(db, gid, user)
    from ..evm import compute_evm
    b = db.get(ProgramBudget, gid)
    ccy = b.currency if b else "SAR"
    rows, other = [], []
    for p in db.query(Project).filter_by(program_id=gid).order_by(Project.number):
        e = compute_evm(db, p, date.today()) if p.state in ("execution", "closing") else {}
        if p.currency != ccy:
            other.append(p.number)
            continue
        rows.append({"project_id": p.id, "number": p.number, "budget": p.budget_ceiling or 0, "spent": (e.get("AC") or 0) if e.get("available") else 0,
                     "forecast": (e.get("EAC") or p.budget_ceiling or 0) if e.get("available") else (p.budget_ceiling or 0)})
    tot = {k: round(sum(r[k] for r in rows), 0) for k in ("budget", "spent", "forecast")}
    env = b.envelope if b else None
    return {"envelope": env, "currency": ccy, "projects": rows, "totals": tot, "excluded_other_currency": other,
            "allocated_pct": round(100 * tot["budget"] / env, 1) if env else None,
            "headroom": round(env - tot["forecast"], 0) if env is not None else None}


@router.get("/{gid}/benefits-plan")
def benefits_plan(gid: int, db=Depends(get_db), user: User = Depends(current_user)):
    """All benefits of the program's projects in date order, with owners, grouped by quarter."""
    _prog(db, gid, user)
    from .governance import b_out
    names = {u.id: u.full_name for u in db.query(User)}
    projs = {p.id: p for p in db.query(Project).filter_by(program_id=gid)}
    rows = []
    for b in db.query(Benefit).filter(Benefit.project_id.in_(list(projs) or [0])):
        d = b_out(b)
        d["project"] = projs[b.project_id].number
        d["owner"] = names.get(b.owner_id)
        d["quarter"] = f"{b.due_date.year}-Q{(b.due_date.month - 1) // 3 + 1}" if b.due_date else "No date"
        d["overdue"] = b.due_date is not None and b.due_date < date.today() and b.status not in ("realized", "missed")
        rows.append(d)
    rows.sort(key=lambda r: (r["due_date"] is None, r["due_date"] or date.max))
    return {"benefits": rows, "by_status": {s: sum(1 for r in rows if r["status"] == s) for s in ("planned", "on_track", "at_risk", "realized", "missed")},
            "no_owner": sum(1 for r in rows if not r["owner_id"])}
