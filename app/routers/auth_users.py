from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..audit import log
from ..config import ROLES
from ..deps import current_user, get_db, hash_pw, make_token, require_roles, verify_pw
from ..models import User

router = APIRouter(tags=["auth & users"])


class LoginIn(BaseModel):
    staff_id: str
    password: str


class DemoLoginIn(BaseModel):
    staff_id: str


class UserIn(BaseModel):
    staff_id: str
    full_name: str
    password: str = Field(min_length=8)
    role: str
    is_ccb: bool = False
    job_title: str | None = None
    department: str | None = None
    capacity_hours_week: float = Field(40.0, gt=0, le=80)
    rate_grade: str | None = None
    line_manager_id: int | None = None
    delegate_id: int | None = None
    email: str | None = Field(None, max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def user_out(u: User, include_cost: bool = False) -> dict:
    d = {"id": u.id, "staff_id": u.staff_id, "full_name": u.full_name, "role": u.role, "is_ccb": u.is_ccb,
         "job_title": u.job_title, "department": u.department, "capacity_hours_week": u.capacity_hours_week,
         "line_manager_id": u.line_manager_id, "delegate_id": u.delegate_id, "active": u.active}
    if include_cost:
        d["email"] = u.email
    if include_cost:
        d["rate_grade"] = u.rate_grade  # cost data only for ADMIN / PMO (4.1)
    return d


@router.post("/auth/login")
def login(body: LoginIn, db=Depends(get_db)):
    from .. import acct
    u = db.query(User).filter_by(staff_id=body.staff_id).first()
    if u and u.active:
        until = acct.is_locked(db, u)
        if until:
            acct.record(db, body.staff_id, u, False, "locked")
            db.commit()
            raise HTTPException(423, f"Account locked after repeated failed sign-ins. Try again after {until.strftime('%H:%M')} UTC or ask an administrator to unlock it")
    if not u or not u.active or not verify_pw(body.password, u.password_hash):
        locked = acct.on_failure(db, u) if u and u.active else False
        acct.record(db, body.staff_id, u, False, "inactive" if u and not u.active else "locked_now" if locked else "bad_password" if u else "unknown_user")
        db.commit()
        raise HTTPException(401, "Invalid credentials")
    s = acct.on_success(db, u)
    acct.record(db, body.staff_id, u, True)
    db.commit()
    hours = float(acct.params(db).get("session_hours", 8))
    return {"access_token": make_token(u, hours), "token_type": "bearer", "role": u.role, "must_change_password": bool(s.must_change_password)}


def _demo_login_on() -> bool:
    import os
    return os.environ.get("PROPERM_DEMO_LOGIN") == "1"


@router.get("/auth/demo-users")
def demo_users(db=Depends(get_db)):
    """Quick-login list. Exists only when PROPERM_DEMO_LOGIN=1; never enable on a real deployment."""
    if not _demo_login_on():
        raise HTTPException(404, "Not found")
    return [{"staff_id": u.staff_id, "full_name": u.full_name, "role": u.role}
            for u in db.query(User).filter_by(active=True).order_by(User.id)]


@router.post("/auth/demo-login")
def demo_login(body: DemoLoginIn, db=Depends(get_db)):
    if not _demo_login_on():
        raise HTTPException(404, "Not found")
    u = db.query(User).filter_by(staff_id=body.staff_id).first()
    if not u or not u.active:
        raise HTTPException(401, "Invalid credentials")
    return {"access_token": make_token(u), "token_type": "bearer", "role": u.role}


@router.get("/me")
def me(user: User = Depends(current_user), db=Depends(get_db)):
    from ..models import AccountSecurity
    s = db.get(AccountSecurity, user.id)
    return {**user_out(user), "must_change_password": bool(s and s.must_change_password)}


@router.get("/directory")
def directory(db=Depends(get_db), _: User = Depends(current_user)):
    """Names only (no cost data), so any signed-in user can pick an assignee."""
    return [{"id": u.id, "staff_id": u.staff_id, "full_name": u.full_name, "role": u.role}
            for u in db.query(User).filter_by(active=True).order_by(User.full_name)]


@router.get("/config/codes")
def codes(db=Depends(get_db), _: User = Depends(current_user)):
    from ..lists import active_codes
    return active_codes(db)


@router.post("/users", status_code=201)
def create_user(body: UserIn, db=Depends(get_db), admin: User = Depends(require_roles("ADMIN"))):
    if body.role not in ROLES:
        raise HTTPException(422, f"role must be one of {ROLES}")
    if db.query(User).filter_by(staff_id=body.staff_id).first():
        raise HTTPException(409, "staff_id already exists")
    from .. import acct
    acct.enforce_policy(db, body.password)
    u = User(**body.model_dump(exclude={"password"}), password_hash=hash_pw(body.password))
    db.add(u)
    db.flush()
    acct.password_set(db, u, by_admin=True)
    log(db, admin.id, "user.created", "user", u.id, {"role": u.role})
    db.commit()
    return user_out(u, include_cost=True)


class UserPatch(BaseModel):
    full_name: str | None = None
    role: str | None = None
    is_ccb: bool | None = None
    job_title: str | None = None
    department: str | None = None
    capacity_hours_week: float | None = Field(None, gt=0, le=80)
    rate_grade: str | None = None
    line_manager_id: int | None = None
    delegate_id: int | None = None
    active: bool | None = None
    email: str | None = Field(None, max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    new_password: str | None = Field(None, min_length=8)


@router.patch("/users/{uid}")
def update_user(uid: int, body: UserPatch, db=Depends(get_db), admin: User = Depends(require_roles("ADMIN"))):
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "User not found")
    changes = body.model_dump(exclude_unset=True, exclude={"new_password"})
    if "role" in changes and changes["role"] not in ROLES:
        raise HTTPException(422, f"role must be one of {ROLES}")
    if (changes.get("active") is False or ("role" in changes and changes["role"] != "ADMIN")) and u.role == "ADMIN" and u.active:
        others = db.query(User).filter(User.role == "ADMIN", User.active.is_(True), User.id != u.id).count()
        if others == 0:
            raise HTTPException(409, "Cannot remove or demote the last active ADMIN")
    if u.id == admin.id and (changes.get("active") is False):
        raise HTTPException(409, "You cannot deactivate your own account")
    for k in ("line_manager_id", "delegate_id"):
        if changes.get(k) is not None and (changes[k] == u.id or not db.get(User, changes[k])):
            raise HTTPException(422, f"{k} must be another existing user")
    for k, v in changes.items():
        setattr(u, k, v)
    if body.new_password:
        from .. import acct
        acct.enforce_policy(db, body.new_password)
        u.password_hash = hash_pw(body.new_password)
        acct.password_set(db, u, by_admin=True)
    log(db, admin.id, "user.updated", "user", u.id, {"fields": sorted(changes) + (["password"] if body.new_password else [])})
    db.commit()
    return user_out(u, include_cost=True)


@router.get("/users")
def list_users(db=Depends(get_db), user: User = Depends(require_roles("ADMIN", "PMO", "PM"))):
    show_cost = user.role in ("ADMIN", "PMO")
    return [user_out(u, show_cost) for u in db.query(User).order_by(User.id).all()]
