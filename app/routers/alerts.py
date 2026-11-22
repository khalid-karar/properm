"""3.3 alert evaluation and 3.5 warning and recommendation loop."""
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..alerts import LIVE, RANK, evaluate_project, sync_alerts
from ..audit import emit, log
from ..deps import current_user, get_db, require_roles
from ..models import Alert, AlertAction, Project, User
from .projects import can_manage, can_view, get_project, need_manage

router = APIRouter(tags=["alerts & triage (3.3, 3.5)"])
VIEWERS = ("PMO", "ADMIN", "DECISION_MAKER", "PROGRAM_MANAGER")
SEVERITIES = ("info", "warning", "critical")


class ActionIn(BaseModel):
    action: str       # acknowledge | assign | escalate | dismiss | resolve | verify | reject_verification
    note: str | None = None
    assignee_id: int | None = None
    due_date: date | None = None


def al_out(a: Alert) -> dict:
    return {"id": a.id, "project_id": a.project_id, "rule": a.rule, "severity": a.severity, "cause": a.cause,
            "suggested_action": a.suggested_action, "status": a.status, "active": a.active, "escalated": a.escalated,
            "assignee_id": a.assignee_id, "due_date": a.due_date, "created_at": a.created_at, "last_seen": a.last_seen}


@router.post("/projects/{pid}/alerts/evaluate")
def evaluate(pid: int, as_of: date | None = None, db=Depends(get_db), user: User = Depends(require_roles("PM", "PMO", "ADMIN"))):
    p = get_project(db, pid)
    need_manage(db, user, p)
    res = sync_alerts(db, p, evaluate_project(db, p, as_of or date.today()))
    log(db, user.id, "alerts.evaluated", "project", pid, res)
    db.commit()
    return res


@router.post("/alerts/evaluate")
def evaluate_all(as_of: date | None = None, db=Depends(get_db), user: User = Depends(require_roles("PMO", "ADMIN"))):
    """Scheduled-job entry point: evaluates every project in delivery. (No scheduler yet; call from cron.)"""
    total = {"projects": 0, "created": 0, "updated": 0, "cleared": 0}
    for p in db.query(Project).filter(Project.state.in_(("execution", "closing"))).all():
        r = sync_alerts(db, p, evaluate_project(db, p, as_of or date.today()))
        total["projects"] += 1
        for k in ("created", "updated", "cleared"):
            total[k] += r[k]
    log(db, user.id, "alerts.evaluated_all", "system", None, total)
    db.commit()
    return total


def _visible(db, user: User, a: Alert) -> bool:
    if user.role in VIEWERS:
        return True
    p = db.get(Project, a.project_id)
    return can_manage(db, user, p) or a.assignee_id == user.id


@router.get("/alerts")
def list_alerts(status: str | None = None, project_id: int | None = None, severity: str | None = None,
                active_only: bool = False, db=Depends(get_db), user: User = Depends(current_user)):
    q = db.query(Alert)
    if status:
        q = q.filter(Alert.status == status)
    if project_id:
        q = q.filter(Alert.project_id == project_id)
    if severity:
        q = q.filter(Alert.severity == severity)
    if active_only:
        q = q.filter(Alert.active.is_(True))
    rows = [a for a in q.all() if _visible(db, user, a)]
    rows.sort(key=lambda a: (-RANK[a.severity], a.id))
    return [al_out(a) for a in rows]


@router.get("/alerts/{aid}/history")
def history(aid: int, db=Depends(get_db), user: User = Depends(current_user)):
    a = db.get(Alert, aid)
    if not a or not _visible(db, user, a):
        raise HTTPException(404, "Alert not found")
    return [{"action": x.action, "actor_id": x.actor_id, "note": x.note, "at": x.created_at}
            for x in db.query(AlertAction).filter_by(alert_id=aid).order_by(AlertAction.id)]


def _can_triage(db, user: User, a: Alert) -> bool:
    return user.role in ("PMO", "ADMIN", "DECISION_MAKER") or can_manage(db, user, db.get(Project, a.project_id))


ALLOWED_FROM = {"acknowledge": ("open",), "assign": ("open", "acknowledged", "assigned"),
                "escalate": ("open", "acknowledged", "assigned"), "dismiss": ("open", "acknowledged", "assigned"),
                "resolve": ("assigned",), "verify": ("resolved",), "reject_verification": ("resolved",)}


@router.post("/alerts/{aid}/actions")
def act(aid: int, body: ActionIn, db=Depends(get_db), user: User = Depends(current_user)):
    a = db.get(Alert, aid)
    if not a or not _visible(db, user, a):
        raise HTTPException(404, "Alert not found")
    if body.action not in ALLOWED_FROM:
        raise HTTPException(422, f"action must be one of {tuple(ALLOWED_FROM)}")
    if a.status not in ALLOWED_FROM[body.action]:
        raise HTTPException(409, f"Cannot {body.action} an alert that is {a.status}")
    triager = _can_triage(db, user, a)
    is_assignee = a.assignee_id == user.id
    if body.action == "resolve":
        if not (triager or is_assignee):
            raise HTTPException(403, "Only the assignee or a triager can resolve")
    elif not triager:
        raise HTTPException(403, "Triage requires the project manager, PMO or a decision maker")

    if body.action == "acknowledge":
        a.status = "acknowledged"
    elif body.action == "assign":
        owner = db.get(User, body.assignee_id) if body.assignee_id else None
        if not owner or not owner.active or not body.due_date:
            raise HTTPException(422, "assignee_id (active user) and due_date are required")
        a.assignee_id, a.due_date, a.status = owner.id, body.due_date, "assigned"
        emit(db, "action.assigned", {"alert_id": a.id, "assignee_id": owner.id, "due_date": str(body.due_date)})
    elif body.action == "escalate":
        a.escalated = True
        a.severity = SEVERITIES[min(RANK[a.severity] + 1, 2)]
    elif body.action == "dismiss":
        if not body.note:
            raise HTTPException(422, "A reason is required to dismiss")
        a.status = "dismissed"
        a.closed_at = datetime.now(timezone.utc)
    elif body.action == "resolve":
        a.status = "resolved"
    elif body.action == "verify":
        if is_assignee and user.role != "ADMIN":
            raise HTTPException(403, "The assignee cannot verify their own closure")
        if a.active:
            raise HTTPException(409, "The condition still holds; the next evaluation must clear it before closure can be verified")
        a.status, a.closed_at = "closed", datetime.now(timezone.utc)
        emit(db, "alert.closed", {"alert_id": a.id, "project_id": a.project_id})
    elif body.action == "reject_verification":
        if not body.note:
            raise HTTPException(422, "A reason is required to reject the resolution")
        a.status = "assigned"
    db.add(AlertAction(alert_id=a.id, actor_id=user.id, action=body.action, note=body.note))
    log(db, user.id, f"alert.{body.action}", "alert", a.id, {"note": body.note})
    db.commit()
    return al_out(a)
