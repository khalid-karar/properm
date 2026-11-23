"""Skills and certifications, matching people to resource requests, development gaps, and the project team charter."""
import re
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..audit import log
from ..deps import current_user, get_db, require_roles
from ..lists import check_skill
from ..models import PlannedAllocation, ResourceRequest, TeamNorm, User, UserCert, UserSkill
from ..regkit import project_register
from ..workcal import effective_capacity
from .portfolio import ws_of

router = APIRouter(tags=["skills and team"])
GENERIC = {"senior", "junior", "lead", "expert", "principal", "and", "the", "with", "for", "of"}


def _ar(w: str) -> str:
    w = w.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ى", "ي").replace("ة", "ه")
    for pre in ("وال", "بال", "لل", "ال", "و"):                    # definite article and conjunction
        if w.startswith(pre) and len(w) - len(pre) >= 3:
            return w[len(pre):]
    return w


def _tokens(text: str) -> set:
    out = set()
    for w in re.findall(r"[a-z0-9]+|[\u0600-\u06ff]+", (text or "").lower()):
        if "\u0600" <= w[0] <= "\u06ff":
            out.add(_ar(w))
            continue
        if w in GENERIC:
            continue
        for suf in ("ing", "ers", "er", "ists", "ist", "s"):       # engineering / engineer / engineers share a stem
            if len(w) > 4 and w.endswith(suf):
                w = w[: -len(suf)]
        out.add(w)
    return out


def _like(a: str, b: str) -> bool:
    x, y = _tokens(a), _tokens(b)
    return bool(x and y and (x <= y or y <= x))


LEVELS = {1: "beginner", 2: "working", 3: "advanced", 4: "expert"}
HR = ("PMO", "ADMIN")


class SkillIn(BaseModel):
    skill: str = Field(min_length=1, max_length=120)
    level: int = Field(2, ge=1, le=4)
    target_level: int | None = Field(None, ge=1, le=4)
    years: float | None = Field(None, ge=0, le=60)


class CertIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    issuer: str | None = Field(None, max_length=200)
    issued_on: date | None = None
    expires_on: date | None = None


def _profile(db, uid):
    today = date.today()
    sk = db.query(UserSkill).filter_by(user_id=uid).order_by(UserSkill.skill).all()
    ce = db.query(UserCert).filter_by(user_id=uid).order_by(UserCert.name).all()
    return {"skills": [{"id": s.id, "skill": s.skill, "level": s.level, "level_name": LEVELS[s.level], "target_level": s.target_level, "years": s.years,
                        "gap": bool(s.target_level and s.target_level > s.level)} for s in sk],
            "certs": [{"id": c.id, "name": c.name, "issuer": c.issuer, "issued_on": c.issued_on.isoformat() if c.issued_on else None,
                       "expires_on": c.expires_on.isoformat() if c.expires_on else None,
                       "expired": bool(c.expires_on and c.expires_on < today), "expires_soon": bool(c.expires_on and today <= c.expires_on <= today + timedelta(days=90))} for c in ce]}


def _add_skill(db, uid, body: SkillIn, actor):
    check_skill(db, body.skill)
    row = db.query(UserSkill).filter_by(user_id=uid, skill=body.skill).first()
    if row:
        row.level, row.target_level, row.years = body.level, body.target_level, body.years
    else:
        db.add(UserSkill(user_id=uid, **body.model_dump()))
    log(db, actor.id, "skill.saved", "user", uid, {"skill": body.skill, "level": body.level})
    db.commit()
    return _profile(db, uid)


def _check_cert(body: CertIn):
    if body.issued_on and body.expires_on and body.expires_on < body.issued_on:
        raise HTTPException(422, "Expiry is before the issue date")


@router.get("/skills/list")
def skill_list(db=Depends(get_db), user: User = Depends(current_user)):
    from ..lists import active
    return [x["label"] for x in active(db, "skill")]


@router.get("/me/skills")
def my_skills(db=Depends(get_db), user: User = Depends(current_user)):
    return _profile(db, user.id)


@router.post("/me/skills", status_code=201)
def add_my_skill(body: SkillIn, db=Depends(get_db), user: User = Depends(current_user)):
    return _add_skill(db, user.id, body, user)


@router.delete("/me/skills/{sid}", status_code=204)
def del_my_skill(sid: int, db=Depends(get_db), user: User = Depends(current_user)):
    r = db.get(UserSkill, sid)
    if not r or r.user_id != user.id:
        raise HTTPException(404, "Not found")
    db.delete(r)
    db.commit()


@router.post("/me/certs", status_code=201)
def add_my_cert(body: CertIn, db=Depends(get_db), user: User = Depends(current_user)):
    _check_cert(body)
    db.add(UserCert(user_id=user.id, **body.model_dump()))
    log(db, user.id, "cert.added", "user", user.id, {"name": body.name})
    db.commit()
    return _profile(db, user.id)


@router.delete("/me/certs/{cid}", status_code=204)
def del_my_cert(cid: int, db=Depends(get_db), user: User = Depends(current_user)):
    r = db.get(UserCert, cid)
    if not r or r.user_id != user.id:
        raise HTTPException(404, "Not found")
    db.delete(r)
    db.commit()


@router.post("/people/{uid}/skills", status_code=201)
def set_skill_for(uid: int, body: SkillIn, db=Depends(get_db), user: User = Depends(require_roles(*HR))):
    if not db.get(User, uid):
        raise HTTPException(404, "User not found")
    return _add_skill(db, uid, body, user)


@router.get("/people/skills")
def people_skills(skill: str | None = None, db=Depends(get_db), user: User = Depends(require_roles("PM", "PMO", "ADMIN", "PROGRAM_MANAGER"))):
    """Skills directory. A search term matches skill names and certification names."""
    out = []
    q = (skill or "").strip().lower()
    for u in db.query(User).filter(User.active.is_(True), User.role.in_(("STAFF", "PM"))).order_by(User.full_name):
        pr = _profile(db, u.id)
        if q and not any(q in s["skill"].lower() for s in pr["skills"]) and not any(q in c["name"].lower() for c in pr["certs"]):
            continue
        out.append({"id": u.id, "name": u.full_name, "department": u.department, "grade": u.rate_grade, **pr})
    return out


@router.get("/people/development-gaps")
def gaps(db=Depends(get_db), user: User = Depends(require_roles(*HR))):
    names = {u.id: u for u in db.query(User)}
    today = date.today()
    g = [{"user": names[s.user_id].full_name, "skill": s.skill, "level": s.level, "target_level": s.target_level}
         for s in db.query(UserSkill).filter(UserSkill.target_level.isnot(None)) if s.target_level > s.level and names[s.user_id].active]
    c = [{"user": names[x.user_id].full_name, "name": x.name, "expires_on": x.expires_on.isoformat(), "expired": x.expires_on < today}
         for x in db.query(UserCert).filter(UserCert.expires_on.isnot(None), UserCert.expires_on <= today + timedelta(days=90)).order_by(UserCert.expires_on) if names[x.user_id].active]
    return {"skill_gaps": g, "certs_expiring": c}


@router.get("/resource-requests/{rid}/matches")
def matches(rid: int, db=Depends(get_db), user: User = Depends(require_roles(*HR))):
    """Rank people for a resource request by skill level, with the hours they actually have free in the requested window."""
    rr = db.get(ResourceRequest, rid)
    if not rr:
        raise HTTPException(404, "Request not found")
    term = rr.skill
    weeks, w = [], ws_of(rr.start)
    while w <= rr.end:
        weeks.append(w)
        w += timedelta(days=7)
    alloc = {}
    for a in db.query(PlannedAllocation).filter(PlannedAllocation.week_start.in_(weeks or [date.today()])):
        alloc[(a.user_id, a.week_start)] = alloc.get((a.user_id, a.week_start), 0.0) + a.hours
    out = []
    for u in db.query(User).filter(User.active.is_(True), User.role.in_(("STAFF", "PM"))):
        sk = [s for s in db.query(UserSkill).filter_by(user_id=u.id) if _like(term, s.skill)]
        ce = [c for c in db.query(UserCert).filter_by(user_id=u.id) if _like(term, c.name) and not (c.expires_on and c.expires_on < date.today())]
        if rr.department and u.department and u.department != rr.department and not sk:
            continue
        if not sk and not ce:
            continue
        free = [effective_capacity(db, u.capacity_hours_week, wk, u.id) - alloc.get((u.id, wk), 0.0) for wk in weeks] or [0.0]
        best = max(sk, key=lambda s: s.level) if sk else None
        out.append({"id": u.id, "name": u.full_name, "department": u.department, "skill": best.skill if best else None, "level": best.level if best else None,
                    "years": best.years if best else None, "certs": [c.name for c in ce], "min_free_hours": round(min(free), 1), "avg_free_hours": round(sum(free) / len(free), 1),
                    "weeks_short": sum(1 for f in free if f < rr.hours_per_week), "fits": min(free) >= rr.hours_per_week})
    out.sort(key=lambda x: (not x["fits"], x["weeks_short"], -(x["level"] or 0), -len(x["certs"])))
    return {"request": {"id": rr.id, "skill": rr.skill, "hours_per_week": rr.hours_per_week, "start": rr.start.isoformat(), "end": rr.end.isoformat()}, "candidates": out[:12]}


project_register(router, "team-norms", TeamNorm, {"category": str, "text": str},
                 choices={"category": ("communication", "meetings", "decisions", "conflict", "quality", "other")}, required=("text",), defaults={"category": "communication"},
                 order=[TeamNorm.category, TeamNorm.id])
