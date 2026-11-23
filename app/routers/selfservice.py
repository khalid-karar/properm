"""Self-service: profile, password, notification choices, my projects, copy last week."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func

from ..audit import log
from ..config import WEEK_STARTS_ON_SUNDAY
from ..deps import current_user, get_db, hash_pw, verify_pw
from ..models import Activity, ActivityStaffLimit, Assignment, Project, TimesheetEntry, User, UserPref
from .. import rules
from .auth_users import user_out

router = APIRouter(tags=["self-service"])

KINDS = ["timesheet.submitted", "timesheet.approved", "timesheet.rejected", "alert.raised", "action.assigned",
         "change.requested", "change.approved", "change.rejected", "project.manager_changed", "project.state_changed",
         "cost.posted", "anomaly.flag", "proposal.submitted", "proposal.decided", "gate.requested", "gate.decided", "change.returned", "leave.requested", "leave.decided", "timesheet.reminder"]


def _prefs(db, uid):
    p = db.get(UserPref, uid)
    return {"muted_kinds": list(p.muted_kinds or []) if p else [], "email_enabled": p.email_enabled if p else True}


@router.get("/me/profile")
def profile(db=Depends(get_db), user: User = Depends(current_user)):
    d = user_out(user)
    d["email"] = user.email
    d["delegate_name"] = db.get(User, user.delegate_id).full_name if user.delegate_id else None
    d["line_manager_name"] = db.get(User, user.line_manager_id).full_name if user.line_manager_id else None
    return {**d, "prefs": _prefs(db, user.id), "kinds": KINDS}


class ProfilePatch(BaseModel):
    email: str | None = Field(None, max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    delegate_id: int | None = None


@router.patch("/me/profile")
def patch_profile(body: ProfilePatch, db=Depends(get_db), user: User = Depends(current_user)):
    ch = body.model_dump(exclude_unset=True)
    if ch.get("delegate_id") is not None:
        t = db.get(User, ch["delegate_id"])
        if ch["delegate_id"] == user.id or not t or not t.active:
            raise HTTPException(422, "Delegate must be another active user")
    for k, v in ch.items():
        setattr(user, k, v)
    log(db, user.id, "profile.updated", "user", user.id, {"fields": sorted(ch)})
    db.commit()
    return profile(db, user)


class PasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


@router.post("/me/password")
def change_password(body: PasswordIn, db=Depends(get_db), user: User = Depends(current_user)):
    if not verify_pw(body.current_password, user.password_hash):
        raise HTTPException(403, "Current password is incorrect")
    if body.new_password == body.current_password:
        raise HTTPException(422, "New password must differ from the current one")
    from .. import acct
    acct.enforce_policy(db, body.new_password)
    user.password_hash = hash_pw(body.new_password)
    acct.password_set(db, user, by_admin=False)
    log(db, user.id, "user.password_changed", "user", user.id, {})
    db.commit()
    return {"ok": True}


class PrefsIn(BaseModel):
    muted_kinds: list[str] = []
    email_enabled: bool = True


@router.put("/me/prefs")
def set_prefs(body: PrefsIn, db=Depends(get_db), user: User = Depends(current_user)):
    bad = [k for k in body.muted_kinds if k not in KINDS]
    if bad:
        raise HTTPException(422, f"Unknown notification kinds: {bad}")
    p = db.get(UserPref, user.id) or UserPref(user_id=user.id)
    p.muted_kinds, p.email_enabled = sorted(set(body.muted_kinds)), body.email_enabled
    db.add(p)
    db.commit()
    return _prefs(db, user.id)


@router.get("/me/projects")
def my_projects(db=Depends(get_db), user: User = Depends(current_user)):
    ids = {a.project_id for a in db.query(Assignment).filter_by(user_id=user.id)}
    ids |= {p.id for p in db.query(Project).filter_by(pm_id=user.id)}
    out = []
    live = ("submitted", "approved")
    for p in db.query(Project).filter(Project.id.in_(ids)).order_by(Project.number) if ids else []:
        acts = []
        for a in db.query(Activity).filter_by(project_id=p.id).order_by(Activity.code):
            lim = db.query(ActivityStaffLimit).filter_by(activity_id=a.id, user_id=user.id).first()
            cap = lim.max_hours if lim else a.planned_hours
            used = float(db.query(func.coalesce(func.sum(TimesheetEntry.hours), 0.0)).filter(
                TimesheetEntry.user_id == user.id, TimesheetEntry.activity_id == a.id, TimesheetEntry.status.in_(live)).scalar())
            acts.append({"id": a.id, "code": a.code, "name": a.name, "planned_hours": a.planned_hours, "cap": cap,
                         "my_hours": used, "remaining": max(0.0, (cap or 0) - used)})
        mine = sum(x["my_hours"] for x in acts)
        out.append({"id": p.id, "number": p.number, "name": p.name, "state": p.state, "is_pm": p.pm_id == user.id,
                    "my_hours": mine, "activities": acts})
    return out


class CopyIn(BaseModel):
    from_week_of: date
    to_week_of: date


@router.post("/timesheets/copy-week")
def copy_week(body: CopyIn, db=Depends(get_db), user: User = Depends(current_user)):
    from .timesheets import EntryIn, save
    a = rules.week_start(body.from_week_of, WEEK_STARTS_ON_SUNDAY)
    b = rules.week_start(body.to_week_of, WEEK_STARTS_ON_SUNDAY)
    if a == b:
        raise HTTPException(422, "Source and target weeks must differ")
    src = db.query(TimesheetEntry).filter(TimesheetEntry.user_id == user.id, TimesheetEntry.entry_date >= a,
                                          TimesheetEntry.entry_date <= a + timedelta(days=6),
                                          TimesheetEntry.status != "rejected").order_by(TimesheetEntry.entry_date).all()
    created, skipped = 0, []
    for e in src:
        nd = b + (e.entry_date - a)
        dup = db.query(TimesheetEntry).filter(
            TimesheetEntry.user_id == user.id, TimesheetEntry.entry_date == nd, TimesheetEntry.project_id == e.project_id,
            TimesheetEntry.activity_id == e.activity_id, TimesheetEntry.nonproject_code == e.nonproject_code,
            TimesheetEntry.status != "rejected").first()
        if dup:
            skipped.append({"date": nd.isoformat(), "reason": "already exists"})
            continue
        r = save(db, user, EntryIn(project_id=e.project_id, activity_id=e.activity_id, code=e.nonproject_code,
                                   entry_date=nd, hours=e.hours, description=e.description), None)
        if r.status_code == 201:
            created += 1
        else:
            import json
            try:
                msg = json.loads(r.body).get("detail", "rejected")
            except Exception:
                msg = "rejected"
            skipped.append({"date": nd.isoformat(), "reason": msg})
    return {"created": created, "skipped": skipped}
