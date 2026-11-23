"""Scope management: structured charter, assumption log, WBS with acceptance, requirements with traceability."""
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..audit import log
from ..deps import current_user, get_db
from ..models import Activity, Assumption, Deliverable, Project, ProjectCharter, Requirement, User
from ..notify import notify
from ..regkit import project_register, ser
from .projects import can_manage, can_view, get_project, need_manage

router = APIRouter(tags=["scope"])
ACCEPTERS = ("PMO", "ADMIN", "DECISION_MAKER")


def _view(db, user, pid):
    p = get_project(db, pid)
    if not can_view(db, user, p):
        raise HTTPException(403, "No access to this project")
    return p


# ---------------- charter ----------------
CHARTER_FIELDS = ("purpose", "objectives", "success_criteria", "in_scope", "out_of_scope", "key_risks", "approval_requirements")


class CharterIn(BaseModel):
    purpose: str | None = Field(None, max_length=5000)
    objectives: str | None = Field(None, max_length=5000)
    success_criteria: str | None = Field(None, max_length=5000)
    in_scope: str | None = Field(None, max_length=5000)
    out_of_scope: str | None = Field(None, max_length=5000)
    key_risks: str | None = Field(None, max_length=5000)
    approval_requirements: str | None = Field(None, max_length=5000)


def _charter_out(db, p, c):
    d = {k: getattr(c, k, None) if c else None for k in CHARTER_FIELDS}
    d.update({"status": c.status if c else "draft", "approved_by": db.get(User, c.approved_by).full_name if c and c.approved_by else None,
              "approved_on": c.approved_on.isoformat() if c and c.approved_on else None, "sponsor": p.sponsor, "client": p.client,
              "complete": bool(c and all(getattr(c, k) for k in ("purpose", "objectives", "success_criteria", "in_scope")))})
    return d


@router.get("/projects/{pid}/charter")
def get_charter(pid: int, db=Depends(get_db), user: User = Depends(current_user)):
    p = _view(db, user, pid)
    return _charter_out(db, p, db.query(ProjectCharter).filter_by(project_id=pid).first())


@router.put("/projects/{pid}/charter")
def put_charter(pid: int, body: CharterIn, db=Depends(get_db), user: User = Depends(current_user)):
    p = _view(db, user, pid)
    need_manage(db, user, p)
    c = db.query(ProjectCharter).filter_by(project_id=pid).first()
    if c and c.status == "approved":
        raise HTTPException(409, "The charter is approved. Reopen it before editing")
    if not c:
        c = ProjectCharter(project_id=pid)
        db.add(c)
    for k, v in body.model_dump().items():
        setattr(c, k, (v or "").strip() or None)
    c.updated_at = datetime.now(timezone.utc)
    log(db, user.id, "charter.saved", "project", pid, {})
    db.commit()
    return _charter_out(db, p, c)


class CharterDecision(BaseModel):
    action: str = Field(pattern="^(approve|reopen)$")


@router.post("/projects/{pid}/charter/decision")
def charter_decision(pid: int, body: CharterDecision, db=Depends(get_db), user: User = Depends(current_user)):
    p = _view(db, user, pid)
    c = db.query(ProjectCharter).filter_by(project_id=pid).first()
    if not c:
        raise HTTPException(409, "Write the charter first")
    if body.action == "approve":
        if user.role not in ACCEPTERS:
            raise HTTPException(403, "The charter is approved by the PMO, a decision maker or an administrator")
        if not all(getattr(c, k) for k in ("purpose", "objectives", "success_criteria", "in_scope")):
            raise HTTPException(409, "Purpose, objectives, success criteria and in-scope must be filled in before approval")
        c.status, c.approved_by, c.approved_on = "approved", user.id, date.today()
        notify(db, p.pm_id, "charter", f"Charter approved: {p.number}", None, f"#/projects/{pid}")
    else:
        if user.role not in ACCEPTERS and not can_manage(db, user, p):
            raise HTTPException(403, "Not allowed")
        c.status, c.approved_by, c.approved_on = "draft", None, None
    log(db, user.id, f"charter.{body.action}", "project", pid, {})
    db.commit()
    return _charter_out(db, p, c)


# ---------------- assumptions ----------------
def _own_user(db, p, data, row):
    for k in ("owner_id",):
        if data.get(k) and not db.get(User, data[k]):
            raise HTTPException(422, "Unknown user")


project_register(router, "assumptions", Assumption,
                 {"kind": str, "text": str, "owner_id": int, "validate_by": date, "status": str, "note": str},
                 choices={"kind": ("assumption", "constraint", "dependency", "exclusion"), "status": ("open", "validated", "invalid")},
                 required=("text",), defaults={"kind": "assumption", "status": "open"}, validate=_own_user)


# ---------------- WBS ----------------
def _wbs_validate(db, p, data, row):
    if data.get("kind") and data["kind"] not in ("deliverable", "work_package"):
        raise HTTPException(422, "kind must be deliverable or work_package")
    if "status" in data:
        raise HTTPException(422, "Use the submit and decision actions to change acceptance status")
    if data.get("code"):
        q = db.query(Deliverable).filter_by(project_id=p.id, code=data["code"])
        if q.first() and (row is None or q.first().id != row.id):
            raise HTTPException(409, "Code already used in this project")
    if data.get("parent_id"):
        par = db.get(Deliverable, data["parent_id"])
        if not par or par.project_id != p.id:
            raise HTTPException(422, "Parent not found in this project")
        if row is not None:
            x = par
            while x:
                if x.id == row.id:
                    raise HTTPException(422, "A node cannot sit under itself")
                x = db.get(Deliverable, x.parent_id) if x.parent_id else None
    if data.get("activity_id"):
        a = db.get(Activity, data["activity_id"])
        if not a or a.project_id != p.id:
            raise HTTPException(422, "Activity not found in this project")
    _own_user(db, p, data, row)


def _wbs_enrich(db, p, rows, ds):
    acts = {a.id: f"{a.code} · {a.name}" for a in db.query(Activity).filter_by(project_id=p.id)}
    names = {u.id: u.full_name for u in db.query(User)}
    reqs = {}
    for r in db.query(Requirement).filter_by(project_id=p.id):
        if r.deliverable_id:
            reqs.setdefault(r.deliverable_id, []).append(r.code)
    for d in ds:
        d["activity"] = acts.get(d["activity_id"])
        d["owner"] = names.get(d["owner_id"])
        d["decided_by_name"] = names.get(d["decided_by"])
        d["requirements"] = reqs.get(d["id"], [])


W = project_register(router, "wbs", Deliverable,
                     {"parent_id": int, "code": str, "name": str, "kind": str, "description": str, "acceptance_criteria": str,
                      "activity_id": int, "owner_id": int, "due_date": date},
                     required=("code", "name"), defaults={"kind": "deliverable"}, validate=_wbs_validate, enrich=_wbs_enrich,
                     order=[Deliverable.code])


def _node(db, p, user, pid, did):
    p = _view(db, user, pid)
    d = db.get(Deliverable, did)
    if not d or d.project_id != pid:
        raise HTTPException(404, "Not found")
    return p, d


@router.post("/projects/{pid}/wbs/{did}/submit")
def submit_deliverable(pid: int, did: int, db=Depends(get_db), user: User = Depends(current_user)):
    p, d = _node(db, None, user, pid, did)
    need_manage(db, user, p)
    if d.kind != "deliverable":
        raise HTTPException(409, "Only deliverables are submitted for acceptance")
    if d.status == "accepted":
        raise HTTPException(409, "Already accepted")
    d.status, d.decided_by, d.decided_on, d.decision_note = "submitted", None, None, None
    log(db, user.id, "deliverable.submitted", "deliverable", did, {"project": pid})
    for u in db.query(User).filter(User.role.in_(ACCEPTERS), User.active.is_(True)):
        notify(db, u.id, "deliverable", f"Deliverable awaiting acceptance: {d.code} {d.name}", p.number, f"#/projects/{pid}")
    db.commit()
    return W["out"](db, p, [d])[0]


class AcceptIn(BaseModel):
    accept: bool
    note: str | None = Field(None, max_length=2000)


@router.post("/projects/{pid}/wbs/{did}/decision")
def decide_deliverable(pid: int, did: int, body: AcceptIn, db=Depends(get_db), user: User = Depends(current_user)):
    p, d = _node(db, None, user, pid, did)
    if user.role not in ACCEPTERS:
        raise HTTPException(403, "Acceptance is given by the PMO, a decision maker or an administrator on behalf of the client")
    if d.status != "submitted":
        raise HTTPException(409, "Only submitted deliverables can be accepted or rejected")
    if not body.accept and not (body.note or "").strip():
        raise HTTPException(422, "Give the reason for rejecting")
    d.status = "accepted" if body.accept else "rejected"
    d.decided_by, d.decided_on, d.decision_note = user.id, date.today(), body.note
    log(db, user.id, f"deliverable.{d.status}", "deliverable", did, {"project": pid})
    notify(db, p.pm_id, "deliverable", f"Deliverable {d.status}: {d.code} {d.name}", body.note, f"#/projects/{pid}")
    db.commit()
    return W["out"](db, p, [d])[0]


@router.post("/projects/{pid}/wbs/{did}/start")
def start_deliverable(pid: int, did: int, db=Depends(get_db), user: User = Depends(current_user)):
    p, d = _node(db, None, user, pid, did)
    need_manage(db, user, p)
    if d.status in ("accepted", "submitted"):
        raise HTTPException(409, f"Cannot restart a {d.status} deliverable")
    d.status = "in_progress"
    log(db, user.id, "deliverable.started", "deliverable", did, {})
    db.commit()
    return W["out"](db, p, [d])[0]


# ---------------- requirements ----------------
def _req_validate(db, p, data, row):
    if data.get("code"):
        q = db.query(Requirement).filter_by(project_id=p.id, code=data["code"]).first()
        if q and (row is None or q.id != row.id):
            raise HTTPException(409, "Code already used in this project")
    if data.get("deliverable_id"):
        d = db.get(Deliverable, data["deliverable_id"])
        if not d or d.project_id != p.id:
            raise HTTPException(422, "Deliverable not found in this project")
    if data.get("status") == "verified" and not (data.get("test_ref") or (row and row.test_ref)):
        raise HTTPException(422, "Give the test or evidence reference before marking a requirement verified")


def _req_enrich(db, p, rows, ds):
    dl = {d.id: f"{d.code} · {d.name}" for d in db.query(Deliverable).filter_by(project_id=p.id)}
    for d in ds:
        d["deliverable"] = dl.get(d["deliverable_id"])


project_register(router, "requirements", Requirement,
                 {"code": str, "title": str, "description": str, "source": str, "priority": str, "status": str,
                  "deliverable_id": int, "test_ref": str},
                 choices={"priority": ("must", "should", "could", "wont"), "status": ("proposed", "approved", "implemented", "verified", "dropped")},
                 required=("code", "title"), defaults={"priority": "must", "status": "proposed"}, validate=_req_validate,
                 enrich=_req_enrich, order=[Requirement.code])


# ---------------- summary / traceability ----------------
@router.get("/projects/{pid}/scope-summary")
def scope_summary(pid: int, db=Depends(get_db), user: User = Depends(current_user)):
    p = _view(db, user, pid)
    c = db.query(ProjectCharter).filter_by(project_id=pid).first()
    dl = db.query(Deliverable).filter_by(project_id=pid).all()
    dv = [d for d in dl if d.kind == "deliverable"]
    rq = [r for r in db.query(Requirement).filter_by(project_id=pid) if r.status != "dropped"]
    traced = {r.deliverable_id for r in rq if r.deliverable_id}
    asm = db.query(Assumption).filter_by(project_id=pid).all()
    today = date.today()
    return {"charter": "approved" if c and c.status == "approved" else ("draft" if c else "missing"),
            "deliverables": {"total": len(dv), **{s: sum(1 for d in dv if d.status == s) for s in ("planned", "in_progress", "submitted", "accepted", "rejected")},
                             "accepted_pct": round(100 * sum(1 for d in dv if d.status == "accepted") / len(dv)) if dv else None},
            "work_packages_without_activity": [d.code for d in dl if d.kind == "work_package" and not d.activity_id],
            "requirements": {"total": len(rq), "must": sum(1 for r in rq if r.priority == "must"),
                             "without_deliverable": [r.code for r in rq if not r.deliverable_id],
                             "verified": sum(1 for r in rq if r.status == "verified"),
                             "verified_pct": round(100 * sum(1 for r in rq if r.status == "verified") / len(rq)) if rq else None},
            "deliverables_without_requirement": [d.code for d in dv if d.id not in traced] if rq else [],
            "assumptions": {"open": sum(1 for a in asm if a.status == "open"), "invalid": sum(1 for a in asm if a.status == "invalid"),
                            "overdue": sum(1 for a in asm if a.status == "open" and a.validate_by and a.validate_by < today)}}
