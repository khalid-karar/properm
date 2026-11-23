"""Strategy alignment (objectives register, coverage view) and compliance (requirement library, per-project evidence)."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..audit import log
from ..deps import current_user, get_db, require_roles
from ..models import (ComplianceRequirement, ObjectiveLink, Project, ProjectCompliance, Proposal, StrategicObjective, User)
from ..regkit import project_register
from .projects import MANAGE, can_manage, can_view, get_project, need_manage

router = APIRouter(tags=["strategy and compliance"])
STRAT = ("PMO", "ADMIN", "DECISION_MAKER")
ACTIVE_STATES = ("tendering", "planning", "execution", "closing", "on_hold")


# ---------------- objectives ----------------
class ObjIn(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=300)
    description: str | None = Field(None, max_length=3000)
    horizon: str | None = Field(None, max_length=40)
    owner_id: int | None = None
    active: bool = True


class ObjPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=300)
    description: str | None = None
    horizon: str | None = None
    owner_id: int | None = None
    active: bool | None = None


def _obj_out(db, o, links):
    prj = [l.project_id for l in links if l.objective_id == o.id and l.project_id]
    props = [l.proposal_id for l in links if l.objective_id == o.id and l.proposal_id]
    for pr in db.query(Proposal).filter(Proposal.id.in_(props or [0])):
        if pr.project_id:
            prj.append(pr.project_id)
    projects = [x for x in db.query(Project).filter(Project.id.in_(set(prj) or [0])) if x.state in ACTIVE_STATES or x.state == "archived"]
    pending = [x for x in db.query(Proposal).filter(Proposal.id.in_(props or [0])) if not x.project_id and x.status in ("submitted", "approved", "under_review")]
    owner = db.get(User, o.owner_id).full_name if o.owner_id else None
    return {"id": o.id, "code": o.code, "name": o.name, "description": o.description, "horizon": o.horizon, "owner_id": o.owner_id, "owner": owner, "active": o.active,
            "projects": [{"id": x.id, "number": x.number, "name": x.name, "state": x.state} for x in projects if x.state != "archived"],
            "delivered": [{"id": x.id, "number": x.number, "name": x.name} for x in projects if x.state == "archived"],
            "proposals": [{"id": x.id, "number": x.number, "name": x.name, "status": x.status} for x in pending]}


@router.get("/objectives")
def list_objectives(db=Depends(get_db), user: User = Depends(current_user)):
    links = db.query(ObjectiveLink).all()
    q = db.query(StrategicObjective).order_by(StrategicObjective.code)
    if user.role not in STRAT:
        q = q.filter(StrategicObjective.active.is_(True))
    return [_obj_out(db, o, links) for o in q]


@router.post("/objectives", status_code=201)
def create_objective(body: ObjIn, db=Depends(get_db), user: User = Depends(require_roles(*STRAT))):
    if db.query(StrategicObjective).filter_by(code=body.code).first():
        raise HTTPException(409, "Objective code already exists")
    if body.owner_id and not db.get(User, body.owner_id):
        raise HTTPException(422, "Unknown owner")
    o = StrategicObjective(**body.model_dump())
    db.add(o)
    db.flush()
    log(db, user.id, "objective.created", "strategic_objectives", o.id, {"code": o.code})
    db.commit()
    return _obj_out(db, o, [])


@router.patch("/objectives/{oid}")
def patch_objective(oid: int, body: ObjPatch, db=Depends(get_db), user: User = Depends(require_roles(*STRAT))):
    o = db.get(StrategicObjective, oid)
    if not o:
        raise HTTPException(404, "Objective not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(o, k, v)
    log(db, user.id, "objective.updated", "strategic_objectives", oid, {})
    db.commit()
    return _obj_out(db, o, db.query(ObjectiveLink).all())


@router.get("/objectives/coverage")
def coverage(db=Depends(get_db), user: User = Depends(require_roles("PM", "PMO", "ADMIN", "DECISION_MAKER", "PROGRAM_MANAGER"))):
    links = db.query(ObjectiveLink).all()
    objs = [_obj_out(db, o, links) for o in db.query(StrategicObjective).filter_by(active=True).order_by(StrategicObjective.code)]
    linked = {l.project_id for l in links if l.project_id}
    for pr in db.query(Proposal).filter(Proposal.id.in_({l.proposal_id for l in links if l.proposal_id} or {0})):
        if pr.project_id:
            linked.add(pr.project_id)
    orphans = [{"id": p.id, "number": p.number, "name": p.name, "state": p.state} for p in db.query(Project).filter(Project.state.in_(ACTIVE_STATES)) if p.id not in linked]
    return {"objectives": objs, "uncovered": [o["id"] for o in objs if not o["projects"] and not o["delivered"] and not o["proposals"]],
            "projects_without_objective": orphans}


class LinkIn(BaseModel):
    objective_ids: list[int]


def _set_links(db, ids, *, project_id=None, proposal_id=None):
    valid = {o.id for o in db.query(StrategicObjective).filter(StrategicObjective.id.in_(ids or [0]), StrategicObjective.active.is_(True))}
    if set(ids) - valid:
        raise HTTPException(422, "Unknown or inactive objective")
    q = db.query(ObjectiveLink).filter_by(project_id=project_id, proposal_id=proposal_id)
    q.delete()
    for i in sorted(set(ids)):
        db.add(ObjectiveLink(objective_id=i, project_id=project_id, proposal_id=proposal_id))


@router.get("/projects/{pid}/objectives")
def project_objectives(pid: int, db=Depends(get_db), user: User = Depends(current_user)):
    p = get_project(db, pid)
    if not can_view(db, user, p):
        raise HTTPException(403, "No access to this project")
    ids = {l.objective_id for l in db.query(ObjectiveLink).filter_by(project_id=pid)}
    for pr in db.query(Proposal).filter_by(project_id=pid):
        ids |= {l.objective_id for l in db.query(ObjectiveLink).filter_by(proposal_id=pr.id)}
    return {"selected": sorted(ids), "available": [{"id": o.id, "code": o.code, "name": o.name} for o in db.query(StrategicObjective).filter_by(active=True).order_by(StrategicObjective.code)]}


@router.put("/projects/{pid}/objectives")
def set_project_objectives(pid: int, body: LinkIn, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p = get_project(db, pid)
    need_manage(db, user, p)
    _set_links(db, body.objective_ids, project_id=pid)
    log(db, user.id, "project.objectives", "project", pid, {"objectives": body.objective_ids})
    db.commit()
    return project_objectives(pid, db, user)


@router.put("/proposals/{xid}/objectives")
def set_proposal_objectives(xid: int, body: LinkIn, db=Depends(get_db), user: User = Depends(current_user)):
    pr = db.get(Proposal, xid)
    if not pr:
        raise HTTPException(404, "Proposal not found")
    if user.id != pr.submitted_by and user.role not in STRAT:
        raise HTTPException(403, "Only the submitter or the PMO can change this")
    _set_links(db, body.objective_ids, proposal_id=xid)
    log(db, user.id, "proposal.objectives", "proposal", xid, {"objectives": body.objective_ids})
    db.commit()
    return {"selected": sorted(set(body.objective_ids))}


@router.get("/proposals/{xid}/objectives")
def get_proposal_objectives(xid: int, db=Depends(get_db), user: User = Depends(current_user)):
    if not db.get(Proposal, xid):
        raise HTTPException(404, "Proposal not found")
    return {"selected": sorted(l.objective_id for l in db.query(ObjectiveLink).filter_by(proposal_id=xid))}


# ---------------- compliance library ----------------
class ReqIn(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    framework: str = Field(min_length=1, max_length=60)
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None


class ReqPatch(BaseModel):
    framework: str | None = Field(None, max_length=60)
    title: str | None = Field(None, max_length=300)
    description: str | None = None
    active: bool | None = None


def _req_out(r):
    return {"id": r.id, "code": r.code, "framework": r.framework, "title": r.title, "description": r.description, "active": r.active}


@router.get("/compliance-library")
def library(db=Depends(get_db), user: User = Depends(require_roles("PM", "PMO", "ADMIN", "DECISION_MAKER", "PROGRAM_MANAGER"))):
    return [_req_out(r) for r in db.query(ComplianceRequirement).order_by(ComplianceRequirement.framework, ComplianceRequirement.code)]


@router.post("/compliance-library", status_code=201)
def add_requirement(body: ReqIn, db=Depends(get_db), user: User = Depends(require_roles("PMO", "ADMIN"))):
    if db.query(ComplianceRequirement).filter_by(code=body.code).first():
        raise HTTPException(409, "Code already exists")
    r = ComplianceRequirement(**body.model_dump())
    db.add(r)
    db.flush()
    log(db, user.id, "compliance.library_added", "compliance_requirements", r.id, {"code": r.code})
    db.commit()
    return _req_out(r)


@router.patch("/compliance-library/{rid}")
def patch_requirement(rid: int, body: ReqPatch, db=Depends(get_db), user: User = Depends(require_roles("PMO", "ADMIN"))):
    r = db.get(ComplianceRequirement, rid)
    if not r:
        raise HTTPException(404, "Not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(r, k, v)
    log(db, user.id, "compliance.library_updated", "compliance_requirements", rid, {})
    db.commit()
    return _req_out(r)


# ---------------- per-project compliance ----------------
def _pc_validate(db, p, data, row):
    if row is None:
        rq = db.get(ComplianceRequirement, data.get("requirement_id") or 0)
        if not rq or not rq.active:
            raise HTTPException(422, "Requirement not found in the library")
        if db.query(ProjectCompliance).filter_by(project_id=p.id, requirement_id=rq.id).first():
            raise HTTPException(409, "Already applied to this project")
    elif "requirement_id" in data:
        if data["requirement_id"] != row.requirement_id:
            raise HTTPException(422, "The requirement cannot be changed")
        data.pop("requirement_id")
    status = data.get("status") or (row.status if row else "not_started")
    evidence = data.get("evidence") if "evidence" in data else (row.evidence if row else None)
    if status in ("compliant", "exception", "n_a") and not (evidence or "").strip():
        raise HTTPException(422, "Give the evidence (or the reason for the exception / not applicable)")
    if status in ("compliant", "exception", "n_a") and "reviewed_on" not in data:
        data["reviewed_on"] = date.today()
    if data.get("owner_id") and not db.get(User, data["owner_id"]):
        raise HTTPException(422, "Unknown user")


def _pc_enrich(db, p, rows, ds):
    lib = {r.id: r for r in db.query(ComplianceRequirement)}
    names = {u.id: u.full_name for u in db.query(User)}
    today = date.today()
    for r, d in zip(rows, ds):
        q = lib.get(r.requirement_id)
        d.update({"code": q.code, "framework": q.framework, "title": q.title, "description": q.description, "owner": names.get(r.owner_id),
                  "overdue": bool(r.due_date and r.due_date < today and r.status in ("not_started", "in_progress"))})


PC = project_register(router, "compliance", ProjectCompliance,
                      {"requirement_id": int, "status": str, "owner_id": int, "due_date": date, "evidence": str, "reviewed_on": date},
                      choices={"status": ("not_started", "in_progress", "compliant", "exception", "n_a")}, required=("requirement_id",),
                      defaults={"status": "not_started"}, validate=_pc_validate, enrich=_pc_enrich, order=[ProjectCompliance.id])


class FrameworkIn(BaseModel):
    framework: str


@router.post("/projects/{pid}/compliance/apply-framework")
def apply_framework(pid: int, body: FrameworkIn, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p = get_project(db, pid)
    need_manage(db, user, p)
    have = {x.requirement_id for x in db.query(ProjectCompliance).filter_by(project_id=pid)}
    added = 0
    for r in db.query(ComplianceRequirement).filter_by(framework=body.framework, active=True):
        if r.id not in have:
            db.add(ProjectCompliance(project_id=pid, requirement_id=r.id))
            added += 1
    if not added and not db.query(ComplianceRequirement).filter_by(framework=body.framework).first():
        raise HTTPException(404, "No such framework in the library")
    log(db, user.id, "compliance.framework_applied", "project", pid, {"framework": body.framework, "added": added})
    db.commit()
    return {"added": added}


@router.get("/compliance/overview")
def overview(db=Depends(get_db), user: User = Depends(require_roles("PMO", "ADMIN", "DECISION_MAKER", "PROGRAM_MANAGER"))):
    lib = {r.id: r for r in db.query(ComplianceRequirement)}
    prj = {p.id: p for p in db.query(Project)}
    fw, by_prj = {}, {}
    today = date.today()
    for x in db.query(ProjectCompliance):
        q = lib.get(x.requirement_id)
        p = prj.get(x.project_id)
        if not q or not p or p.state == "archived":
            continue
        f = fw.setdefault(q.framework, {"framework": q.framework, "total": 0, "compliant": 0, "exception": 0, "n_a": 0, "open": 0, "overdue": 0})
        f["total"] += 1
        f["open" if x.status in ("not_started", "in_progress") else x.status] += 1
        if x.due_date and x.due_date < today and x.status in ("not_started", "in_progress"):
            f["overdue"] += 1
        b = by_prj.setdefault(p.id, {"id": p.id, "number": p.number, "name": p.name, "total": 0, "applicable": 0, "compliant": 0, "open": 0, "exception": 0, "overdue": 0})
        b["total"] += 1
        b["applicable"] += 0 if x.status == "n_a" else 1
        b["compliant"] += x.status == "compliant"
        b["exception"] += x.status == "exception"
        b["open"] += x.status in ("not_started", "in_progress")
        b["overdue"] += bool(x.due_date and x.due_date < today and x.status in ("not_started", "in_progress"))
    for b in by_prj.values():
        b["pct"] = round(100 * b["compliant"] / b["applicable"]) if b["applicable"] else None
    return {"frameworks": sorted(fw.values(), key=lambda f: f["framework"]), "projects": sorted(by_prj.values(), key=lambda b: (b["pct"] is None, b["pct"] or 0)),
            "projects_without_any": [{"id": p.id, "number": p.number, "name": p.name} for p in prj.values() if p.state in ACTIVE_STATES and p.id not in by_prj]}
