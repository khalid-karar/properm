"""Administrator security: sign-in history, locked accounts, unlock; off-boarding a user with a handover of open work."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import acct
from ..audit import log
from ..deps import current_user, get_db, require_roles
from ..models import (AccountSecurity, Alert, Issue, LoginEvent, Program, ProgramRisk, Project, ProjectAction, Risk, User,
                      LeaveRequest, TimesheetEntry)

router = APIRouter(tags=["security"])


def ev_out(e: LoginEvent, names) -> dict:
    return {"id": e.id, "staff_id": e.staff_id, "user": names.get(e.user_id), "ok": e.ok, "reason": e.reason,
            "at": acct._utc(e.at).isoformat() if e.at else None}


@router.get("/admin/logins")
def logins(staff_id: str | None = None, failed_only: bool = False, limit: int = 200, db=Depends(get_db), _: User = Depends(require_roles("ADMIN"))):
    q = db.query(LoginEvent)
    if staff_id:
        q = q.filter(LoginEvent.staff_id == staff_id)
    if failed_only:
        q = q.filter(LoginEvent.ok.is_(False))
    names = {u.id: u.full_name for u in db.query(User)}
    locked = []
    for s in db.query(AccountSecurity).filter(AccountSecurity.locked_until.isnot(None)):
        lu = acct._utc(s.locked_until)
        if lu > datetime.now(timezone.utc):
            locked.append({"user_id": s.user_id, "user": names.get(s.user_id), "locked_until": lu.isoformat()})
    must = [{"user_id": s.user_id, "user": names.get(s.user_id)} for s in db.query(AccountSecurity).filter(AccountSecurity.must_change_password.is_(True))]
    return {"events": [ev_out(e, names) for e in q.order_by(LoginEvent.id.desc()).limit(min(limit, 1000))], "locked": locked, "must_change": must}


@router.get("/me/logins")
def my_logins(db=Depends(get_db), user: User = Depends(current_user)):
    names = {user.id: user.full_name}
    return [ev_out(e, names) for e in db.query(LoginEvent).filter_by(user_id=user.id).order_by(LoginEvent.id.desc()).limit(10)]


@router.post("/admin/users/{uid}/unlock")
def unlock(uid: int, db=Depends(get_db), admin: User = Depends(require_roles("ADMIN"))):
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "User not found")
    s = acct.sec(db, uid)
    s.locked_until, s.failed_count = None, 0
    log(db, admin.id, "user.unlocked", "user", uid, {})
    db.commit()
    return {"user_id": uid, "locked": False}


# ---------------- off-boarding ----------------
def open_work(db, uid: int) -> dict:
    live = ("tendering", "planning", "execution", "closing", "on_hold")
    return {
        "projects_managed": [p.number for p in db.query(Project).filter(Project.pm_id == uid, Project.state.in_(live))],
        "programs_managed": [g.code for g in db.query(Program).filter_by(manager_id=uid)],
        "risks_owned": db.query(Risk).filter(Risk.owner_id == uid, Risk.status.in_(("open", "mitigating"))).count()
                       + db.query(ProgramRisk).filter(ProgramRisk.owner_id == uid, ProgramRisk.status.in_(("open", "mitigating"))).count(),
        "issues_owned": db.query(Issue).filter(Issue.owner_id == uid, Issue.status.in_(("open", "in_progress"))).count(),
        "actions_owned": db.query(ProjectAction).filter(ProjectAction.owner_id == uid, ProjectAction.status == "open").count(),
        "alerts_assigned": db.query(Alert).filter(Alert.assignee_id == uid, Alert.active.is_(True), Alert.status == "assigned").count(),
        "line_reports": [u.full_name for u in db.query(User).filter(User.line_manager_id == uid, User.active.is_(True))],
        "delegate_for": [u.full_name for u in db.query(User).filter(User.delegate_id == uid, User.active.is_(True))],
        "own_entries_pending": db.query(TimesheetEntry).filter(TimesheetEntry.user_id == uid, TimesheetEntry.status == "submitted").count(),
    }


@router.get("/admin/users/{uid}/handover")
def handover_preview(uid: int, db=Depends(get_db), _: User = Depends(require_roles("ADMIN"))):
    if not db.get(User, uid):
        raise HTTPException(404, "User not found")
    w = open_work(db, uid)
    w["total"] = sum(len(v) if isinstance(v, list) else v for k, v in w.items() if k != "own_entries_pending")
    return w


class HandoverIn(BaseModel):
    to_user_id: int
    deactivate: bool = True


@router.post("/admin/users/{uid}/handover")
def handover(uid: int, body: HandoverIn, db=Depends(get_db), admin: User = Depends(require_roles("ADMIN"))):
    u, to = db.get(User, uid), db.get(User, body.to_user_id)
    if not u or not to:
        raise HTTPException(404, "User not found")
    if to.id == u.id or not to.active:
        raise HTTPException(422, "Hand over to another active user")
    if body.deactivate and u.id == admin.id:
        raise HTTPException(409, "You cannot deactivate your own account")
    live = ("tendering", "planning", "execution", "closing", "on_hold")
    pms = db.query(Project).filter(Project.pm_id == uid, Project.state.in_(live)).all()
    if pms and to.role not in ("PM", "PMO", "ADMIN"):
        raise HTTPException(422, f"{to.full_name} cannot take over projects (role {to.role}); choose a PM, PMO or ADMIN")
    if body.deactivate and u.role == "ADMIN" and db.query(User).filter(User.role == "ADMIN", User.active.is_(True), User.id != uid).count() == 0:
        raise HTTPException(409, "Cannot remove the last active ADMIN")
    moved = {"projects": 0, "programs": 0, "risks": 0, "issues": 0, "actions": 0, "alerts": 0, "line_reports": 0, "delegations": 0}
    for p in pms:
        p.pm_id = to.id
        moved["projects"] += 1
    for g in db.query(Program).filter_by(manager_id=uid):
        g.manager_id = to.id if to.role in ("PROGRAM_MANAGER", "PMO", "ADMIN") else None
        moved["programs"] += 1
    for M, st in ((Risk, ("open", "mitigating")), (ProgramRisk, ("open", "mitigating")), (Issue, ("open", "in_progress"))):
        for r in db.query(M).filter(M.owner_id == uid, M.status.in_(st)):
            r.owner_id = to.id
            moved["issues" if M is Issue else "risks"] += 1
    for a in db.query(ProjectAction).filter(ProjectAction.owner_id == uid, ProjectAction.status == "open"):
        a.owner_id = to.id
        moved["actions"] += 1
    for a in db.query(Alert).filter(Alert.assignee_id == uid, Alert.active.is_(True), Alert.status == "assigned"):
        a.assignee_id = to.id
        moved["alerts"] += 1
    for x in db.query(User).filter(User.line_manager_id == uid):
        x.line_manager_id = to.id if x.id != to.id else None
        moved["line_reports"] += 1
    for x in db.query(User).filter(User.delegate_id == uid):
        x.delegate_id = to.id if x.id != to.id else None
        moved["delegations"] += 1
    for lv in db.query(LeaveRequest).filter(LeaveRequest.user_id == uid, LeaveRequest.status == "requested"):
        lv.status = "cancelled"
    if body.deactivate:
        u.active = False
        u.delegate_id = None
    log(db, admin.id, "user.handed_over", "user", uid, {"to": to.id, "deactivated": body.deactivate, **moved})
    db.commit()
    return {"user_id": uid, "to_user_id": to.id, "deactivated": body.deactivate, "moved": moved}
