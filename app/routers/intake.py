"""Project intake and editing: details, manager reassignment, documents, stakeholders, activity edit/delete, unassign."""
import base64
import binascii
import os
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..audit import emit, log
from ..deps import current_user, get_db, require_roles
from ..models import (Activity, ActivityDependency, ActivityStaffLimit, Milestone, Assignment, Document, Project, Stakeholder, TimesheetEntry, User)
from .projects import MANAGE, a_out, can_view, get_project, need_manage, p_out

router = APIRouter(prefix="/projects", tags=["project intake"])
LOCKED_AFTER_BASELINE = ("planned_start", "planned_end", "budget_ceiling", "currency", "project_type")
MAX_DOC_BYTES = 3 * 1024 * 1024
DOC_EXT = {".pdf", ".docx", ".doc", ".txt", ".png", ".jpg", ".jpeg", ".xlsx", ".md"}
DOC_KINDS = ("contract", "charter", "scope", "other")


class ProjectPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=300)
    planned_start: date | None = None
    planned_end: date | None = None
    budget_ceiling: float | None = Field(None, ge=0)
    currency: str | None = Field(None, min_length=3, max_length=3)
    project_type: str | None = None
    client: str | None = Field(None, max_length=200)
    sponsor: str | None = Field(None, max_length=200)
    scope_statement: str | None = Field(None, max_length=10000)


@router.patch("/{pid}")
def edit_project(pid: int, body: ProjectPatch, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p = get_project(db, pid)
    need_manage(db, user, p)
    if p.state == "archived":
        raise HTTPException(409, "Archived projects are read-only")
    data = body.model_dump(exclude_unset=True)
    if p.baseline_version > 0:
        blocked = [k for k in LOCKED_AFTER_BASELINE if k in data and data[k] != getattr(p, k)]
        if blocked:
            raise HTTPException(409, f"After the baseline is locked, {', '.join(blocked)} can only change through change control")
    if "project_type" in data and data["project_type"] not in ("predictive", "hybrid", "adaptive"):
        raise HTTPException(422, "project_type must be predictive, hybrid or adaptive")
    s, e = data.get("planned_start", p.planned_start), data.get("planned_end", p.planned_end)
    if s and e and e < s:
        raise HTTPException(422, "planned_end before planned_start")
    for k, v in data.items():
        setattr(p, k, v)
    log(db, user.id, "project.edited", "project", p.id, {k: str(v) for k, v in data.items() if k != "scope_statement"})
    db.commit()
    return p_out(p)


class ManagerIn(BaseModel):
    user_id: int


@router.put("/{pid}/manager")
def reassign_manager(pid: int, body: ManagerIn, db=Depends(get_db), user: User = Depends(require_roles("PMO", "ADMIN"))):
    p = get_project(db, pid)
    u = db.get(User, body.user_id)
    if not u or not u.active or u.role not in ("PM", "PMO", "ADMIN"):
        raise HTTPException(422, "The new project manager must be an active PM, PMO or ADMIN user")
    old = p.pm_id
    p.pm_id = u.id
    if not db.query(Assignment).filter_by(project_id=pid, user_id=u.id).first():
        db.add(Assignment(project_id=pid, user_id=u.id))
    log(db, user.id, "project.manager_changed", "project", pid, {"from": old, "to": u.id})
    emit(db, "project.manager_changed", {"project_id": pid, "user_id": u.id})
    db.commit()
    return p_out(p)


# ---------------- documents ----------------
class DocIn(BaseModel):
    kind: str
    filename: str = Field(min_length=1, max_length=200)
    content_b64: str


def doc_out(d: Document) -> dict:
    return {"id": d.id, "kind": d.kind, "filename": d.filename, "size": d.size, "uploaded_by": d.uploaded_by, "uploaded_at": d.uploaded_at}


@router.get("/{pid}/documents")
def list_documents(pid: int, db=Depends(get_db), user: User = Depends(current_user)):
    p = get_project(db, pid)
    if not can_view(db, user, p):
        raise HTTPException(403, "No access to this project")
    from ..models import DocumentVersion
    return [{**doc_out(d), "version": db.query(DocumentVersion).filter_by(document_id=d.id).count() + 1} for d in db.query(Document).filter_by(project_id=pid).order_by(Document.id)]


@router.post("/{pid}/documents", status_code=201)
def upload_document(pid: int, body: DocIn, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p = get_project(db, pid)
    need_manage(db, user, p)
    if body.kind not in DOC_KINDS:
        raise HTTPException(422, f"kind must be one of {', '.join(DOC_KINDS)}")
    name = os.path.basename(body.filename.replace("\\", "/"))
    if os.path.splitext(name)[1].lower() not in DOC_EXT:
        raise HTTPException(422, "File type not allowed (pdf, docx, doc, txt, md, png, jpg, xlsx)")
    try:
        raw = base64.b64decode(body.content_b64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(422, "content_b64 is not valid base64")
    if not raw or len(raw) > MAX_DOC_BYTES:
        raise HTTPException(422, f"File must be between 1 byte and {MAX_DOC_BYTES // 1024 // 1024} MB")
    d = Document(project_id=pid, kind=body.kind, filename=name, size=len(raw), content=raw, uploaded_by=user.id)
    db.add(d)
    db.flush()
    log(db, user.id, "document.uploaded", "project", pid, {"document_id": d.id, "filename": name, "kind": body.kind})
    db.commit()
    return doc_out(d)


@router.get("/{pid}/documents/{did}/download")
def download_document(pid: int, did: int, db=Depends(get_db), user: User = Depends(current_user)):
    p = get_project(db, pid)
    d = db.get(Document, did)
    if not can_view(db, user, p) or not d or d.project_id != pid:
        raise HTTPException(404, "Document not found")
    safe = d.filename.replace('"', "")
    return Response(d.content, media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{safe}"', "X-Content-Type-Options": "nosniff"})


@router.get("/{pid}/documents/{did}/content")
def document_content(pid: int, did: int, db=Depends(get_db), user: User = Depends(current_user)):
    """JSON form of the download (base64) so the browser build, which only carries text, can save the file too."""
    p = get_project(db, pid)
    d = db.get(Document, did)
    if not can_view(db, user, p) or not d or d.project_id != pid:
        raise HTTPException(404, "Document not found")
    return {"filename": d.filename, "content_b64": base64.b64encode(d.content).decode()}


@router.delete("/{pid}/documents/{did}", status_code=204)
def delete_document(pid: int, did: int, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p = get_project(db, pid)
    need_manage(db, user, p)
    d = db.get(Document, did)
    if not d or d.project_id != pid:
        raise HTTPException(404, "Document not found")
    db.delete(d)
    log(db, user.id, "document.deleted", "project", pid, {"document_id": did, "filename": d.filename})
    db.commit()


# ---------------- stakeholders ----------------
class StakeIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    organisation: str | None = Field(None, max_length=200)
    role: str | None = Field(None, max_length=200)
    power: int = Field(3, ge=1, le=5)
    interest: int = Field(3, ge=1, le=5)
    engagement: str | None = Field(None, max_length=2000)


def sh_out(x: Stakeholder) -> dict:
    return {"id": x.id, "name": x.name, "organisation": x.organisation, "role": x.role, "power": x.power, "interest": x.interest, "engagement": x.engagement}


@router.get("/{pid}/stakeholders")
def list_stakeholders(pid: int, db=Depends(get_db), user: User = Depends(current_user)):
    p = get_project(db, pid)
    if not can_view(db, user, p):
        raise HTTPException(403, "No access to this project")
    return [sh_out(x) for x in db.query(Stakeholder).filter_by(project_id=pid).order_by(Stakeholder.id)]


@router.post("/{pid}/stakeholders", status_code=201)
def add_stakeholder(pid: int, body: StakeIn, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p = get_project(db, pid)
    need_manage(db, user, p)
    x = Stakeholder(project_id=pid, **body.model_dump())
    db.add(x)
    db.flush()
    log(db, user.id, "stakeholder.added", "project", pid, {"stakeholder_id": x.id})
    db.commit()
    return sh_out(x)


@router.delete("/{pid}/stakeholders/{sid}", status_code=204)
def delete_stakeholder(pid: int, sid: int, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p = get_project(db, pid)
    need_manage(db, user, p)
    x = db.get(Stakeholder, sid)
    if not x or x.project_id != pid:
        raise HTTPException(404, "Stakeholder not found")
    db.delete(x)
    log(db, user.id, "stakeholder.deleted", "project", pid, {"stakeholder_id": sid})
    db.commit()


# ---------------- activity edit / delete (planning only) and unassign ----------------
class ActivityPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=300)
    planned_hours: float | None = Field(None, gt=0)
    baseline_cost: float | None = Field(None, ge=0)
    planned_start: date | None = None
    planned_end: date | None = None


def _planning_activity(db, p, aid):
    if p.state != "planning":
        raise HTTPException(409, "Activities can only be edited or deleted in planning; after the baseline use change control")
    a = db.get(Activity, aid)
    if not a or a.project_id != p.id or a.phase != "execution" or a.locked:
        raise HTTPException(404, "Editable activity not found")
    return a


@router.patch("/{pid}/activities/{aid}")
def edit_activity(pid: int, aid: int, body: ActivityPatch, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p = get_project(db, pid)
    need_manage(db, user, p)
    a = _planning_activity(db, p, aid)
    data = body.model_dump(exclude_unset=True)
    s, e = data.get("planned_start", a.planned_start), data.get("planned_end", a.planned_end)
    if (s is None) != (e is None):
        raise HTTPException(422, "Give both planned_start and planned_end, or neither")
    if s and e < s:
        raise HTTPException(422, "planned_end before planned_start")
    for k, v in data.items():
        setattr(a, k, v)
    log(db, user.id, "activity.edited", "activity", a.id, {k: str(v) for k, v in data.items()})
    db.commit()
    return a_out(a, True)


@router.delete("/{pid}/activities/{aid}", status_code=204)
def delete_activity(pid: int, aid: int, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p = get_project(db, pid)
    need_manage(db, user, p)
    a = _planning_activity(db, p, aid)
    if db.query(TimesheetEntry).filter_by(activity_id=aid).first():
        raise HTTPException(409, "This activity already has timesheet entries")
    db.query(ActivityStaffLimit).filter_by(activity_id=aid).delete()
    db.query(ActivityDependency).filter((ActivityDependency.activity_id == aid) | (ActivityDependency.predecessor_id == aid)).delete(synchronize_session=False)
    db.query(Milestone).filter_by(activity_id=aid).update({"activity_id": None})
    db.delete(a)
    log(db, user.id, "activity.deleted", "activity", aid, {"project_id": pid, "code": a.code})
    db.commit()


@router.delete("/{pid}/assignments/{uid}", status_code=204)
def unassign(pid: int, uid: int, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p = get_project(db, pid)
    need_manage(db, user, p)
    if uid == p.pm_id:
        raise HTTPException(409, "The project manager cannot be unassigned; reassign the project first")
    row = db.query(Assignment).filter_by(project_id=pid, user_id=uid).first()
    if not row:
        raise HTTPException(404, "Not assigned")
    if db.query(TimesheetEntry).filter(TimesheetEntry.project_id == pid, TimesheetEntry.user_id == uid, TimesheetEntry.status.in_(("submitted", "draft"))).first():
        raise HTTPException(409, "This person has entries awaiting approval on the project; decide them first")
    db.delete(row)
    log(db, user.id, "staff.unassigned", "project", pid, {"user_id": uid})
    db.commit()
