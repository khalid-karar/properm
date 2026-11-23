"""1.6 risk and issue registers."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..audit import emit, log
from ..deps import current_user, get_db, require_roles
from ..models import ClosureNote, Issue, Risk, User
from .projects import can_view, get_project, need_manage

router = APIRouter(tags=["risks & issues"])
MANAGE = ("PM", "PMO", "ADMIN")
RISK_STATUS = ("open", "mitigating", "occurred", "closed")
ISSUE_STATUS = ("open", "in_progress", "resolved", "closed")
SEVERITY = ("low", "medium", "high", "critical")


class RiskIn(BaseModel):
    title: str
    category: str | None = None
    probability: int = Field(ge=1, le=5)
    impact: int = Field(ge=1, le=5)
    response: str | None = None
    owner_id: int | None = None


class RiskPatch(BaseModel):
    title: str | None = Field(None, min_length=1)
    category: str | None = None
    probability: int | None = Field(None, ge=1, le=5)
    impact: int | None = Field(None, ge=1, le=5)
    response: str | None = None
    owner_id: int | None = None
    status: str | None = None


class IssueIn(BaseModel):
    title: str
    description: str | None = None
    severity: str
    owner_id: int | None = None
    due_date: date | None = None


class IssuePatch(BaseModel):
    title: str | None = Field(None, min_length=1)
    description: str | None = None
    severity: str | None = None
    owner_id: int | None = None
    due_date: date | None = None
    status: str | None = None


def r_out(r: Risk) -> dict:
    return {"id": r.id, "title": r.title, "category": r.category, "probability": r.probability, "impact": r.impact,
            "score": r.score, "response": r.response, "owner_id": r.owner_id, "status": r.status, "last_reviewed": r.last_reviewed}


def i_out(i: Issue) -> dict:
    return {"id": i.id, "title": i.title, "description": i.description, "severity": i.severity, "owner_id": i.owner_id,
            "due_date": i.due_date, "status": i.status, "linked_risk_id": i.linked_risk_id}


def _view(db, user, pid):
    p = get_project(db, pid)
    if not can_view(db, user, p):
        raise HTTPException(403, "No access to this project")
    return p


@router.post("/projects/{pid}/risks", status_code=201)
def add_risk(pid: int, body: RiskIn, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p = get_project(db, pid)
    need_manage(db, user, p)
    r = Risk(project_id=pid, last_reviewed=date.today(), **body.model_dump())
    db.add(r)
    db.flush()
    log(db, user.id, "risk.created", "risk", r.id, {"score": r.score})
    emit(db, "risk.updated", {"project_id": pid, "risk_id": r.id})
    db.commit()
    return r_out(r)


@router.patch("/projects/{pid}/risks/{rid}")
def patch_risk(pid: int, rid: int, body: RiskPatch, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p = get_project(db, pid)
    need_manage(db, user, p)
    r = db.get(Risk, rid)
    if not r or r.project_id != pid:
        raise HTTPException(404, "Risk not found")
    data = body.model_dump(exclude_unset=True)
    if "status" in data and data["status"] not in RISK_STATUS:
        raise HTTPException(422, f"status must be one of {RISK_STATUS}")
    if data.get("owner_id") is not None and not db.get(User, data["owner_id"]):
        raise HTTPException(422, "owner_id must be an existing user")
    was = r.status
    if data.get("status") == "closed" and was != "closed":
        raise HTTPException(422, "Closing a risk needs a closure note: say what happened, how it was handled and the outcome")
    for k, v in data.items():
        setattr(r, k, v)
    r.last_reviewed = date.today()
    issue = None
    if r.status == "occurred" and was != "occurred":           # occurred risk converts to an issue (1.6.1)
        issue = Issue(project_id=pid, title=f"Risk occurred: {r.title}", severity="high" if r.score >= 15 else "medium",
                      owner_id=r.owner_id, linked_risk_id=r.id)
        db.add(issue)
        db.flush()
        emit(db, "issue.raised", {"project_id": pid, "issue_id": issue.id})
    log(db, user.id, "risk.updated", "risk", r.id, data)
    emit(db, "risk.updated", {"project_id": pid, "risk_id": r.id})
    db.commit()
    return {**r_out(r), "created_issue_id": issue.id if issue else None}


@router.get("/projects/{pid}/risks")
def list_risks(pid: int, db=Depends(get_db), user: User = Depends(current_user)):
    _view(db, user, pid)
    return [r_out(r) for r in db.query(Risk).filter_by(project_id=pid).order_by(Risk.id)]


@router.post("/projects/{pid}/issues", status_code=201)
def add_issue(pid: int, body: IssueIn, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p = get_project(db, pid)
    need_manage(db, user, p)
    if body.severity not in SEVERITY:
        raise HTTPException(422, f"severity must be one of {SEVERITY}")
    i = Issue(project_id=pid, **body.model_dump())
    db.add(i)
    db.flush()
    log(db, user.id, "issue.raised", "issue", i.id, {"severity": i.severity})
    emit(db, "issue.raised", {"project_id": pid, "issue_id": i.id})
    db.commit()
    return i_out(i)


@router.patch("/projects/{pid}/issues/{iid}")
def patch_issue(pid: int, iid: int, body: IssuePatch, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p = get_project(db, pid)
    need_manage(db, user, p)
    i = db.get(Issue, iid)
    if not i or i.project_id != pid:
        raise HTTPException(404, "Issue not found")
    data = body.model_dump(exclude_unset=True)
    if "status" in data and data["status"] not in ISSUE_STATUS:
        raise HTTPException(422, f"status must be one of {ISSUE_STATUS}")
    if "severity" in data and data["severity"] not in SEVERITY:
        raise HTTPException(422, f"severity must be one of {SEVERITY}")
    if data.get("owner_id") is not None and not db.get(User, data["owner_id"]):
        raise HTTPException(422, "owner_id must be an existing user")
    if data.get("status") in ("closed", "resolved") and i.status not in ("closed", "resolved"):
        raise HTTPException(422, "Closing an issue needs a closure note: say what happened, how it was handled and the outcome")
    for k, v in data.items():
        setattr(i, k, v)
    log(db, user.id, "issue.updated", "issue", i.id, data)
    emit(db, "issue.raised", {"project_id": pid, "issue_id": i.id})
    db.commit()
    return i_out(i)


@router.get("/projects/{pid}/issues")
def list_issues(pid: int, db=Depends(get_db), user: User = Depends(current_user)):
    _view(db, user, pid)
    return [i_out(i) for i in db.query(Issue).filter_by(project_id=pid).order_by(Issue.id)]


# ---- closure notes -------------------------------------------------------------------------------------------

class CloseIn(BaseModel):
    what_happened: str = Field(min_length=3)
    how_handled: str = Field(min_length=3)
    outcome: str = Field(min_length=3)
    lesson: bool = False
    status: str = "closed"             # issues may be "resolved" or "closed"


class ReopenIn(BaseModel):
    reason: str = Field(min_length=3)


def _note_out(n: ClosureNote, names: dict) -> dict:
    return {"id": n.id, "kind": n.kind, "item_id": n.item_id, "event": n.event, "what_happened": n.what_happened, "how_handled": n.how_handled,
            "outcome": n.outcome, "reason": n.reason, "lesson": bool(n.lesson), "by_id": n.by_id, "by": names.get(n.by_id), "at": n.at}


def _item(db, pid, kind, iid):
    row = db.get(Risk if kind == "risks" else Issue, iid)
    if not row or row.project_id != pid:
        raise HTTPException(404, "Not found")
    return row


@router.post("/projects/{pid}/{kind}/{iid}/close")
def close_item(pid: int, kind: str, iid: int, body: CloseIn, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    if kind not in ("risks", "issues"):
        raise HTTPException(404, "Not found")
    p = get_project(db, pid)
    need_manage(db, user, p)
    row = _item(db, pid, kind, iid)
    done = ("closed",) if kind == "risks" else ("closed", "resolved")
    if row.status in done:
        raise HTTPException(409, "Already closed; reopen it first")
    if body.status not in done:
        raise HTTPException(422, f"status must be one of {done}")
    row.status = body.status
    if kind == "risks":
        row.last_reviewed = date.today()
    n = ClosureNote(project_id=pid, kind=kind[:-1], item_id=iid, event="closed", what_happened=body.what_happened.strip(), how_handled=body.how_handled.strip(),
                    outcome=body.outcome.strip(), lesson=body.lesson, by_id=user.id)
    db.add(n)
    log(db, user.id, f"{kind[:-1]}.closed", kind[:-1], iid, {"lesson": body.lesson})
    emit(db, "risk.updated" if kind == "risks" else "issue.raised", {"project_id": pid, f"{kind[:-1]}_id": iid})
    db.commit()
    return {"status": row.status, "note_id": n.id}


@router.post("/projects/{pid}/{kind}/{iid}/reopen")
def reopen_item(pid: int, kind: str, iid: int, body: ReopenIn, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    if kind not in ("risks", "issues"):
        raise HTTPException(404, "Not found")
    p = get_project(db, pid)
    need_manage(db, user, p)
    row = _item(db, pid, kind, iid)
    if row.status not in ("closed", "resolved"):
        raise HTTPException(409, "Only a closed item can be reopened")
    row.status = "open"
    db.add(ClosureNote(project_id=pid, kind=kind[:-1], item_id=iid, event="reopened", reason=body.reason.strip(), by_id=user.id))
    log(db, user.id, f"{kind[:-1]}.reopened", kind[:-1], iid, {})
    db.commit()
    return {"status": "open"}


@router.get("/projects/{pid}/closures")
def closures(pid: int, db=Depends(get_db), user: User = Depends(current_user)):
    _view(db, user, pid)
    rows = db.query(ClosureNote).filter_by(project_id=pid).order_by(ClosureNote.id).all()
    names = {u.id: u.full_name for u in db.query(User).filter(User.id.in_({n.by_id for n in rows} or {0}))}
    return [_note_out(n, names) for n in rows]
