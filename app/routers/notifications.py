"""In-app notifications and scheduled report delivery."""
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..audit import log
from ..deps import current_user, get_db, require_roles
from ..models import Notification, Project, ReportSchedule, User
from ..notify import dispatch, notify
from .projects import can_manage, can_view, get_project

router = APIRouter(tags=["notifications"])


def n_out(n: Notification) -> dict:
    return {"id": n.id, "kind": n.kind, "title": n.title, "body": n.body, "link": n.link, "created_at": n.created_at,
            "read": n.read_at is not None}


@router.get("/notifications")
def list_notifications(unread: bool = False, db=Depends(get_db), user: User = Depends(current_user)):
    dispatch(db)
    q = db.query(Notification).filter_by(user_id=user.id)
    if unread:
        q = q.filter(Notification.read_at.is_(None))
    return [n_out(n) for n in q.order_by(Notification.id.desc()).limit(100)]


@router.get("/notifications/count")
def unread_count(db=Depends(get_db), user: User = Depends(current_user)):
    dispatch(db)
    return {"unread": db.query(Notification).filter_by(user_id=user.id).filter(Notification.read_at.is_(None)).count()}


@router.post("/notifications/read-all")
def read_all(db=Depends(get_db), user: User = Depends(current_user)):
    now = datetime.now(timezone.utc)
    for n in db.query(Notification).filter_by(user_id=user.id).filter(Notification.read_at.is_(None)):
        n.read_at = now
    db.commit()
    return {"ok": True}


@router.post("/notifications/{nid}/read")
def read_one(nid: int, db=Depends(get_db), user: User = Depends(current_user)):
    n = db.get(Notification, nid)
    if not n or n.user_id != user.id:
        raise HTTPException(404, "Notification not found")
    n.read_at = n.read_at or datetime.now(timezone.utc)
    db.commit()
    return n_out(n)


# ---------------- scheduled reports ----------------
class ScheduleIn(BaseModel):
    kind: str
    project_id: int | None = None
    frequency: str


def s_out(s: ReportSchedule) -> dict:
    return {"id": s.id, "owner_id": s.owner_id, "kind": s.kind, "project_id": s.project_id, "frequency": s.frequency,
            "active": s.active, "last_run_on": s.last_run_on}


@router.get("/reports/schedules")
def list_schedules(db=Depends(get_db), user: User = Depends(require_roles("PM", "PMO", "ADMIN", "DECISION_MAKER", "PROGRAM_MANAGER"))):
    q = db.query(ReportSchedule)
    if user.role != "ADMIN":
        q = q.filter_by(owner_id=user.id)
    return [s_out(s) for s in q.order_by(ReportSchedule.id)]


@router.post("/reports/schedules", status_code=201)
def create_schedule(body: ScheduleIn, db=Depends(get_db), user: User = Depends(require_roles("PM", "PMO", "ADMIN", "DECISION_MAKER", "PROGRAM_MANAGER"))):
    if body.frequency not in ("weekly", "monthly"):
        raise HTTPException(422, "frequency must be weekly or monthly")
    if body.kind == "portfolio":
        if user.role == "PM":
            raise HTTPException(403, "Portfolio reports are for PMO, ADMIN, DECISION_MAKER or PROGRAM_MANAGER")
        pid = None
    elif body.kind == "project":
        if body.project_id is None:
            raise HTTPException(422, "project_id is required for a project report")
        p = get_project(db, body.project_id)
        if not can_view(db, user, p):
            raise HTTPException(403, "No access to this project")
        pid = p.id
    else:
        raise HTTPException(422, "kind must be portfolio or project")
    s = ReportSchedule(owner_id=user.id, kind=body.kind, project_id=pid, frequency=body.frequency)
    db.add(s)
    db.flush()
    log(db, user.id, "report_schedule.created", "report_schedule", s.id, {"kind": body.kind, "project_id": pid})
    db.commit()
    return s_out(s)


@router.delete("/reports/schedules/{sid}", status_code=204)
def delete_schedule(sid: int, db=Depends(get_db), user: User = Depends(current_user)):
    s = db.get(ReportSchedule, sid)
    if not s or (s.owner_id != user.id and user.role != "ADMIN"):
        raise HTTPException(404, "Schedule not found")
    db.delete(s)
    log(db, user.id, "report_schedule.deleted", "report_schedule", sid, {})
    db.commit()


def is_due(s: ReportSchedule, today: date) -> bool:
    if not s.active:
        return False
    if s.last_run_on is None:
        return True
    if s.frequency == "weekly":
        return (today - s.last_run_on).days >= 7
    return (today.year, today.month) != (s.last_run_on.year, s.last_run_on.month)


@router.post("/reports/run-due")
def run_due(today: date | None = None, db=Depends(get_db), user: User = Depends(require_roles("ADMIN", "PMO"))):
    """Delivers every due scheduled report. Call it from a cron (e.g. a GitHub Actions schedule) or press the button."""
    from .exports import portfolio_summary, project_summary
    today = today or date.today()
    sent = 0
    for s in db.query(ReportSchedule).order_by(ReportSchedule.id):
        if not is_due(s, today):
            continue
        if s.kind == "portfolio":
            title, body, link = f"{s.frequency.title()} portfolio report", portfolio_summary(db, today), "#/dashboard"
        else:
            p = db.get(Project, s.project_id)
            if not p:
                continue
            title, body, link = f"{s.frequency.title()} report: {p.number}", project_summary(db, p, today), f"#/projects/{p.id}"
        if notify(db, s.owner_id, "report.scheduled", title, body, link):
            sent += 1
        s.last_run_on = today
    log(db, user.id, "report_schedule.run", "report_schedule", 0, {"sent": sent})
    db.commit()
    return {"sent": sent}
