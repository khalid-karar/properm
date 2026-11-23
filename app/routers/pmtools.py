"""Project tools: template library, resource requests, RACI matrix, communication plan, critical path."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import rules
from ..audit import emit, log
from ..config import WEEK_STARTS_ON_SUNDAY
from ..deps import current_user, get_db, require_roles
from ..models import (Activity, ActivityDependency, Assignment, CommItem, Milestone, PlannedAllocation, Project, ProjectKpi,
                      ProjectTemplate, RaciEntry, ResourceRequest, Risk, Stakeholder, User)
from .projects import MANAGE, can_manage, can_view, get_project, need_manage

router = APIRouter(tags=["project tools"])


def _view(db, user, pid):
    p = get_project(db, pid)
    if not can_view(db, user, p):
        raise HTTPException(403, "No access to this project")
    return p


def _names(db):
    return {u.id: u.full_name for u in db.query(User)}


# ---------------- templates ----------------
def t_out(x: ProjectTemplate) -> dict:
    d = x.data or {}
    return {"id": x.id, "code": x.code, "name": x.name, "description": x.description, "active": x.active, "data": d,
            "counts": {k: len(d.get(k, [])) for k in ("activities", "milestones", "kpis", "risks")}}


def _validate_data(d: dict) -> dict:
    out = {"activities": [], "milestones": [], "kpis": [], "risks": []}
    try:
        for a in d.get("activities", []):
            out["activities"].append({"code": str(a["code"])[:60], "name": str(a["name"])[:300], "planned_hours": float(a.get("planned_hours") or 0) or None,
                                      "start_offset_days": int(a.get("start_offset_days", 0)), "duration_days": max(1, int(a.get("duration_days", 7))),
                                      "after": a.get("after")})
        for m in d.get("milestones", []):
            out["milestones"].append({"name": str(m["name"])[:300], "offset_days": int(m.get("offset_days", 0))})
        for k in d.get("kpis", []):
            out["kpis"].append({"name": str(k["name"])[:200], "unit": k.get("unit"), "target": float(k["target"]), "higher_is_better": bool(k.get("higher_is_better", True))})
        for r in d.get("risks", []):
            out["risks"].append({"title": str(r["title"])[:300], "category": r.get("category"), "probability": min(5, max(1, int(r.get("probability", 3)))),
                                 "impact": min(5, max(1, int(r.get("impact", 3))))})
    except (KeyError, TypeError, ValueError) as e:
        raise HTTPException(422, f"Template content is not valid: {e}")
    return out


class TemplateIn(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(None, max_length=5000)
    data: dict = {}


class TemplatePatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    active: bool | None = None
    data: dict | None = None


@router.get("/templates")
def list_templates(db=Depends(get_db), user: User = Depends(require_roles("PM", "PMO", "ADMIN", "PROGRAM_MANAGER"))):
    q = db.query(ProjectTemplate).order_by(ProjectTemplate.code)
    if user.role not in ("PMO", "ADMIN"):
        q = q.filter(ProjectTemplate.active.is_(True))
    return [t_out(x) for x in q]


@router.post("/templates", status_code=201)
def create_template(body: TemplateIn, db=Depends(get_db), user: User = Depends(require_roles("PMO", "ADMIN"))):
    if db.query(ProjectTemplate).filter_by(code=body.code).first():
        raise HTTPException(409, "Template code already exists")
    x = ProjectTemplate(code=body.code, name=body.name, description=body.description, data=_validate_data(body.data), created_by=user.id)
    db.add(x)
    db.flush()
    log(db, user.id, "template.created", "project_template", x.id, {"code": x.code})
    db.commit()
    return t_out(x)


@router.patch("/templates/{tid}")
def patch_template(tid: int, body: TemplatePatch, db=Depends(get_db), user: User = Depends(require_roles("PMO", "ADMIN"))):
    x = db.get(ProjectTemplate, tid)
    if not x:
        raise HTTPException(404, "Template not found")
    ch = body.model_dump(exclude_unset=True)
    if "data" in ch:
        ch["data"] = _validate_data(ch["data"] or {})
    for k, v in ch.items():
        setattr(x, k, v)
    log(db, user.id, "template.updated", "project_template", tid, {"fields": sorted(ch)})
    db.commit()
    return t_out(x)


class FromProjectIn(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None


@router.post("/templates/from-project/{pid}", status_code=201)
def template_from_project(pid: int, body: FromProjectIn, db=Depends(get_db), user: User = Depends(require_roles("PMO", "ADMIN"))):
    """Turn a project that went well into a reusable template (dates become offsets from the project start)."""
    p = get_project(db, pid)
    base = p.planned_start or date.today()
    acts = db.query(Activity).filter_by(project_id=pid, phase="execution").order_by(Activity.planned_start, Activity.code).all()
    codes = {a.id: a.code for a in acts}
    after = {}
    for d in db.query(ActivityDependency).filter(ActivityDependency.activity_id.in_(list(codes) or [0])):
        after.setdefault(codes[d.activity_id], codes.get(d.predecessor_id))
    data = {"activities": [{"code": a.code, "name": a.name, "planned_hours": a.planned_hours,
                            "start_offset_days": ((a.planned_start or base) - base).days,
                            "duration_days": max(1, ((a.planned_end or a.planned_start or base) - (a.planned_start or base)).days),
                            "after": after.get(a.code)} for a in acts],
            "milestones": [{"name": m.name, "offset_days": (m.due_date - base).days} for m in db.query(Milestone).filter_by(project_id=pid)],
            "kpis": [{"name": k.name, "unit": k.unit, "target": k.target, "higher_is_better": k.higher_is_better} for k in db.query(ProjectKpi).filter_by(project_id=pid)],
            "risks": [{"title": r.title, "category": r.category, "probability": r.probability, "impact": r.impact} for r in db.query(Risk).filter_by(project_id=pid)]}
    return create_template(TemplateIn(code=body.code, name=body.name, description=body.description, data=data), db, user)


@router.post("/projects/{pid}/apply-template/{tid}")
def apply_template(pid: int, tid: int, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p = get_project(db, pid)
    need_manage(db, user, p)
    if p.state not in ("tendering", "planning"):
        raise HTTPException(409, "Templates can only be applied before the baseline is locked")
    x = db.get(ProjectTemplate, tid)
    if not x or not x.active:
        raise HTTPException(404, "Template not found")
    base = p.planned_start or date.today()
    d = x.data or {}
    have = {a.code for a in db.query(Activity).filter_by(project_id=pid)}
    made, by_code = {"activities": 0, "milestones": 0, "kpis": 0, "risks": 0, "skipped": []}, {}
    for a in d.get("activities", []):
        if a["code"] in have:
            made["skipped"].append(a["code"])
            continue
        s = base + timedelta(days=a.get("start_offset_days", 0))
        act = Activity(project_id=pid, code=a["code"], name=a["name"], phase="execution", planned_hours=a.get("planned_hours"),
                       planned_start=s, planned_end=s + timedelta(days=a.get("duration_days", 7)), locked=False)
        db.add(act)
        db.flush()
        by_code[a["code"]] = act
        made["activities"] += 1
    for a in d.get("activities", []):
        if a.get("after") and a["code"] in by_code and a["after"] in by_code:
            db.add(ActivityDependency(activity_id=by_code[a["code"]].id, predecessor_id=by_code[a["after"]].id))
    for m in d.get("milestones", []):
        db.add(Milestone(project_id=pid, name=m["name"], due_date=base + timedelta(days=m.get("offset_days", 0))))
        made["milestones"] += 1
    for k in d.get("kpis", []):
        db.add(ProjectKpi(project_id=pid, name=k["name"], unit=k.get("unit"), target=k["target"], higher_is_better=k.get("higher_is_better", True)))
        made["kpis"] += 1
    for r in d.get("risks", []):
        db.add(Risk(project_id=pid, title=r["title"], category=r.get("category"), probability=r["probability"], impact=r["impact"]))
        made["risks"] += 1
    log(db, user.id, "template.applied", "project", pid, {"template": x.code, **{k: v for k, v in made.items() if k != "skipped"}})
    db.commit()
    return made


# ---------------- resource requests ----------------
class RRIn(BaseModel):
    skill: str = Field(min_length=1, max_length=200)
    department: str | None = Field(None, max_length=200)
    hours_per_week: float = Field(gt=0, le=80)
    start: date
    end: date
    note: str | None = Field(None, max_length=2000)


class RRDecision(BaseModel):
    approve: bool
    user_id: int | None = None
    reason: str | None = Field(None, max_length=2000)


def rr_out(x: ResourceRequest, names, projects) -> dict:
    p = projects.get(x.project_id)
    return {"id": x.id, "project_id": x.project_id, "project": f"{p.number} · {p.name}" if p else None, "requested_by": names.get(x.requested_by),
            "skill": x.skill, "department": x.department, "hours_per_week": x.hours_per_week, "start": x.start, "end": x.end, "note": x.note,
            "status": x.status, "assigned": names.get(x.assigned_user_id), "decision_reason": x.decision_reason}


@router.post("/projects/{pid}/resource-requests", status_code=201)
def request_resource(pid: int, body: RRIn, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p = get_project(db, pid)
    need_manage(db, user, p)
    if body.end < body.start:
        raise HTTPException(422, "End date is before start date")
    x = ResourceRequest(project_id=pid, requested_by=user.id, **body.model_dump())
    db.add(x)
    db.flush()
    log(db, user.id, "resource.requested", "resource_request", x.id, {"project_id": pid})
    emit(db, "resource.requested", {"project_id": pid, "request_id": x.id, "skill": x.skill})
    db.commit()
    return rr_out(x, _names(db), {p.id: p})


@router.get("/projects/{pid}/resource-requests")
def project_requests(pid: int, db=Depends(get_db), user: User = Depends(current_user)):
    p = _view(db, user, pid)
    return [rr_out(x, _names(db), {p.id: p}) for x in db.query(ResourceRequest).filter_by(project_id=pid).order_by(ResourceRequest.id.desc())]


@router.get("/resource-requests")
def request_queue(status: str = "requested", db=Depends(get_db), user: User = Depends(require_roles("PMO", "ADMIN"))):
    projects = {p.id: p for p in db.query(Project)}
    return [rr_out(x, _names(db), projects) for x in db.query(ResourceRequest).filter_by(status=status).order_by(ResourceRequest.start)]


@router.post("/resource-requests/{rid}/decision")
def decide_request(rid: int, body: RRDecision, db=Depends(get_db), user: User = Depends(require_roles("PMO", "ADMIN"))):
    x = db.get(ResourceRequest, rid)
    if not x:
        raise HTTPException(404, "Request not found")
    if x.status != "requested":
        raise HTTPException(409, f"Request is {x.status}")
    weeks = 0
    if body.approve:
        u = db.get(User, body.user_id) if body.user_id else None
        if not u or not u.active:
            raise HTTPException(422, "Choose an active person to fulfil the request")
        if not db.query(Assignment).filter_by(project_id=x.project_id, user_id=u.id).first():
            db.add(Assignment(project_id=x.project_id, user_id=u.id))
        ws = rules.week_start(x.start, WEEK_STARTS_ON_SUNDAY)
        while ws <= x.end:
            row = db.query(PlannedAllocation).filter_by(project_id=x.project_id, user_id=u.id, week_start=ws).first()
            if row:
                row.hours = x.hours_per_week
            else:
                db.add(PlannedAllocation(project_id=x.project_id, user_id=u.id, week_start=ws, hours=x.hours_per_week))
            weeks += 1
            ws += timedelta(days=7)
        x.status, x.assigned_user_id = "fulfilled", u.id
    else:
        if not (body.reason or "").strip():
            raise HTTPException(422, "A reason is required to reject")
        x.status = "rejected"
    x.decided_by, x.decision_reason = user.id, body.reason
    log(db, user.id, f"resource.{x.status}", "resource_request", rid, {"user_id": x.assigned_user_id, "weeks": weeks})
    emit(db, "resource.decided", {"project_id": x.project_id, "request_id": rid, "status": x.status, "user_id": x.requested_by,
                                  "assigned_id": x.assigned_user_id, "skill": x.skill})
    db.commit()
    projects = {p.id: p for p in db.query(Project).filter_by(id=x.project_id)}
    return {**rr_out(x, _names(db), projects), "weeks_planned": weeks}


@router.delete("/projects/{pid}/resource-requests/{rid}")
def cancel_request(pid: int, rid: int, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p = get_project(db, pid)
    need_manage(db, user, p)
    x = db.get(ResourceRequest, rid)
    if not x or x.project_id != pid or x.status != "requested":
        raise HTTPException(409, "Only waiting requests can be cancelled")
    x.status = "cancelled"
    db.commit()
    return {"id": rid, "status": "cancelled"}


# ---------------- RACI ----------------
class RaciIn(BaseModel):
    item: str = Field(min_length=1, max_length=200)
    person: str = Field(min_length=1, max_length=200)
    letter: str | None = None       # R | A | C | I, or empty to clear


@router.get("/projects/{pid}/raci")
def get_raci(pid: int, db=Depends(get_db), user: User = Depends(current_user)):
    _view(db, user, pid)
    rows = db.query(RaciEntry).filter_by(project_id=pid).all()
    items = list(dict.fromkeys([r.item for r in sorted(rows, key=lambda r: r.id)]))
    people = list(dict.fromkeys([r.person for r in sorted(rows, key=lambda r: r.id)]))
    cells = {f"{r.item}␟{r.person}": r.letter for r in rows}
    warnings = []
    for it in items:
        a = [p for p in people if cells.get(f"{it}␟{p}") == "A"]
        r = [p for p in people if cells.get(f"{it}␟{p}") == "R"]
        if len(a) != 1:
            warnings.append({"item": it, "problem": "no_accountable" if not a else "many_accountable"})
        if not r:
            warnings.append({"item": it, "problem": "no_responsible"})
    return {"items": items, "people": people, "cells": [{"item": r.item, "person": r.person, "letter": r.letter} for r in rows], "warnings": warnings}


@router.put("/projects/{pid}/raci")
def set_raci(pid: int, body: RaciIn, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p = get_project(db, pid)
    need_manage(db, user, p)
    letter = (body.letter or "").strip().upper()
    if letter and letter not in ("R", "A", "C", "I"):
        raise HTTPException(422, "letter must be R, A, C or I")
    row = db.query(RaciEntry).filter_by(project_id=pid, item=body.item.strip(), person=body.person.strip()).first()
    if letter:
        if row:
            row.letter = letter
        else:
            db.add(RaciEntry(project_id=pid, item=body.item.strip(), person=body.person.strip(), letter=letter))
    elif row:
        db.delete(row)
    db.commit()
    return get_raci(pid, db, user)


@router.delete("/projects/{pid}/raci")
def delete_raci_line(pid: int, item: str | None = None, person: str | None = None, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p = get_project(db, pid)
    need_manage(db, user, p)
    q = db.query(RaciEntry).filter_by(project_id=pid)
    if item:
        q = q.filter(RaciEntry.item == item)
    elif person:
        q = q.filter(RaciEntry.person == person)
    else:
        raise HTTPException(422, "Give an item or a person to remove")
    q.delete()
    db.commit()
    return get_raci(pid, db, user)


# ---------------- communication plan ----------------
FREQ_DAYS = {"weekly": 7, "biweekly": 14, "monthly": 30, "quarterly": 91}


class CommIn(BaseModel):
    audience: str = Field(min_length=1, max_length=200)
    information: str = Field(min_length=1, max_length=300)
    method: str = Field(min_length=1, max_length=100)
    frequency: str = "monthly"
    owner_id: int | None = None


def c_out(x: CommItem, names) -> dict:
    n = FREQ_DAYS.get(x.frequency)
    due = (x.last_sent + timedelta(days=n)) if n and x.last_sent else (date.today() if n else None)
    return {"id": x.id, "audience": x.audience, "information": x.information, "method": x.method, "frequency": x.frequency,
            "owner_id": x.owner_id, "owner": names.get(x.owner_id), "last_sent": x.last_sent, "next_due": due,
            "overdue": bool(due and x.last_sent and due < date.today())}


@router.get("/projects/{pid}/comms")
def list_comms(pid: int, db=Depends(get_db), user: User = Depends(current_user)):
    _view(db, user, pid)
    return [c_out(x, _names(db)) for x in db.query(CommItem).filter_by(project_id=pid).order_by(CommItem.id)]


@router.post("/projects/{pid}/comms", status_code=201)
def add_comm(pid: int, body: CommIn, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p = get_project(db, pid)
    need_manage(db, user, p)
    if body.frequency not in (*FREQ_DAYS, "milestone", "ad_hoc"):
        raise HTTPException(422, "frequency must be weekly, biweekly, monthly, quarterly, milestone or ad_hoc")
    x = CommItem(project_id=pid, **body.model_dump())
    db.add(x)
    db.commit()
    return c_out(x, _names(db))


@router.post("/projects/{pid}/comms/{cid}/sent")
def mark_sent(pid: int, cid: int, db=Depends(get_db), user: User = Depends(current_user)):
    p = get_project(db, pid)
    x = db.get(CommItem, cid)
    if not x or x.project_id != pid:
        raise HTTPException(404, "Not found")
    if not (can_manage(db, user, p) or x.owner_id == user.id):
        raise HTTPException(403, "Only the project manager or the owner can record this")
    x.last_sent = date.today()
    db.commit()
    return c_out(x, _names(db))


@router.delete("/projects/{pid}/comms/{cid}", status_code=204)
def del_comm(pid: int, cid: int, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p = get_project(db, pid)
    need_manage(db, user, p)
    x = db.get(CommItem, cid)
    if not x or x.project_id != pid:
        raise HTTPException(404, "Not found")
    db.delete(x)
    db.commit()


# ---------------- critical path ----------------
@router.get("/projects/{pid}/critical-path")
def critical_path(pid: int, db=Depends(get_db), user: User = Depends(current_user)):
    """Finish-to-start network on planned dates: earliest start/finish, slack, and the chain that sets the end date."""
    _view(db, user, pid)
    acts = {a.id: a for a in db.query(Activity).filter_by(project_id=pid, phase="execution") if a.planned_start and a.planned_end}
    if not acts:
        return {"activities": [], "finish": None, "critical": []}
    preds = {i: [] for i in acts}
    succs = {i: [] for i in acts}
    for d in db.query(ActivityDependency).filter(ActivityDependency.activity_id.in_(list(acts))):
        if d.predecessor_id in acts:
            preds[d.activity_id].append(d.predecessor_id)
            succs[d.predecessor_id].append(d.activity_id)
    order, seen = [], set()

    def visit(i):
        if i in seen:
            return
        seen.add(i)
        for p_ in preds[i]:
            visit(p_)
        order.append(i)
    for i in sorted(acts, key=lambda i: acts[i].planned_start):
        visit(i)
    dur = {i: max(1, (acts[i].planned_end - acts[i].planned_start).days) for i in acts}
    es, ef = {}, {}
    for i in order:
        es[i] = max([acts[i].planned_start] + [ef[p_] for p_ in preds[i]])
        ef[i] = es[i] + timedelta(days=dur[i])
    finish = max(ef.values())
    lf, ls = {}, {}
    for i in reversed(order):
        lf[i] = min([finish] + [ls[s] for s in succs[i]])
        ls[i] = lf[i] - timedelta(days=dur[i])
    out = []
    for i in order:
        slack = (lf[i] - ef[i]).days
        out.append({"activity_id": i, "code": acts[i].code, "name": acts[i].name, "early_start": es[i], "early_finish": ef[i],
                    "slack_days": slack, "critical": slack <= 0, "predecessors": [acts[p_].code for p_ in preds[i]],
                    "pushed_days": (es[i] - acts[i].planned_start).days})
    return {"activities": out, "finish": finish, "critical": [x["code"] for x in out if x["critical"]]}
