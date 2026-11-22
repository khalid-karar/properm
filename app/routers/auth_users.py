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


def user_out(u: User, include_cost: bool = False) -> dict:
    d = {"id": u.id, "staff_id": u.staff_id, "full_name": u.full_name, "role": u.role, "is_ccb": u.is_ccb,
         "job_title": u.job_title, "department": u.department, "capacity_hours_week": u.capacity_hours_week,
         "line_manager_id": u.line_manager_id, "delegate_id": u.delegate_id, "active": u.active}
    if include_cost:
        d["rate_grade"] = u.rate_grade  # cost data only for ADMIN / PMO (4.1)
    return d


@router.post("/auth/login")
def login(body: LoginIn, db=Depends(get_db)):
    u = db.query(User).filter_by(staff_id=body.staff_id).first()
    if not u or not u.active or not verify_pw(body.password, u.password_hash):
        raise HTTPException(401, "Invalid credentials")
    return {"access_token": make_token(u), "token_type": "bearer", "role": u.role}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return user_out(user)


@router.get("/directory")
def directory(db=Depends(get_db), _: User = Depends(current_user)):
    """Names only (no cost data), so any signed-in user can pick an assignee."""
    return [{"id": u.id, "staff_id": u.staff_id, "full_name": u.full_name, "role": u.role}
            for u in db.query(User).filter_by(active=True).order_by(User.full_name)]


@router.get("/config/codes")
def codes(_: User = Depends(current_user)):
    from ..config import NON_PROJECT_CODES
    return NON_PROJECT_CODES


@router.post("/users", status_code=201)
def create_user(body: UserIn, db=Depends(get_db), admin: User = Depends(require_roles("ADMIN"))):
    if body.role not in ROLES:
        raise HTTPException(422, f"role must be one of {ROLES}")
    if db.query(User).filter_by(staff_id=body.staff_id).first():
        raise HTTPException(409, "staff_id already exists")
    u = User(**body.model_dump(exclude={"password"}), password_hash=hash_pw(body.password))
    db.add(u)
    db.flush()
    log(db, admin.id, "user.created", "user", u.id, {"role": u.role})
    db.commit()
    return user_out(u, include_cost=True)


@router.get("/users")
def list_users(db=Depends(get_db), user: User = Depends(require_roles("ADMIN", "PMO", "PM"))):
    show_cost = user.role in ("ADMIN", "PMO")
    return [user_out(u, show_cost) for u in db.query(User).order_by(User.id).all()]
