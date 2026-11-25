"""Self-serve sandbox trial: a visitor gets a private, empty-of-real-data organisation filled with sample data, for 14 days.

Off unless PROPERM_TRIALS=1. Limits: a hidden honeypot field, 3 sign-ups per address per hour, one live trial per e-mail address, and a cap on live trials
(PROPERM_TRIAL_MAX, default 30). The visitor sees the sign-in details once on screen; nothing is e-mailed to them. Each signup also lands in the consultation list
so sales can follow up. After 14 days sign-in is refused (a token already issued may work for up to 8 more hours). Trial data is not deleted automatically."""
import os
import re
import secrets
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from ..deps import get_db, hash_pw, make_token
from ..models import Tenant, User
from .consultations import EMAIL, ConsultationIn, request_consultation

router = APIRouter(tags=["trial"])
DAYS = 14
_HITS: dict[str, list[float]] = {}


def enabled() -> bool:
    return os.environ.get("PROPERM_TRIALS") == "1"


def _cap() -> int:
    try:
        return max(1, int(os.environ.get("PROPERM_TRIAL_MAX", "30")))
    except ValueError:
        return 30


class TrialIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    organization: str = Field(min_length=2, max_length=120)
    email: str = Field(max_length=200)
    lang: str = "en"
    website: str | None = Field(default=None, max_length=200)      # honeypot

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if not EMAIL.match(v):
            raise ValueError("Enter a valid e-mail address")
        return v

    @field_validator("name", "organization")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = re.sub(r"\s+", " ", v).strip()
        if len(v) < 2:
            raise ValueError("Too short")
        return v


def _live(db):
    return db.query(Tenant).filter(Tenant.trial_until.isnot(None), Tenant.trial_until > datetime.now(timezone.utc))


@router.get("/public/trial/config")
def config(db=Depends(get_db)):
    return {"enabled": enabled() and _live(db).count() < _cap(), "days": DAYS}


@router.get("/public/trial/status")
def status(slug: str, db=Depends(get_db)):
    t = db.query(Tenant).filter(Tenant.slug == slug, Tenant.trial_until.isnot(None)).first()
    return {"state": (t.seed_state if t else None) or "unknown"}


def _seed(app, tenant_id: int, prefix: str, pw: str, admin_id: int):
    from fastapi.testclient import TestClient
    from ..demo import seed

    def tokfn(sid):
        with app.state.Session() as s:
            s.info["unscoped"] = True
            u = s.query(User).filter_by(staff_id=sid).first()
            return {"Authorization": "Bearer " + make_token(u)}
    state = "failed"
    try:
        seed(app, pw, TestClient(app), prefix=prefix, tokfn=tokfn, admin_token=tokfn(prefix + "admin"))
        state = "ready"
    except BaseException:
        import logging
        logging.getLogger("uvicorn.error").exception("Sample data for %s failed", prefix)
        state = "failed"
    finally:
        with app.state.Session() as s:
            t = s.get(Tenant, tenant_id)
            if t:
                t.seed_state = state
                s.commit()


@router.post("/public/trial", status_code=201)
def start_trial(body: TrialIn, request: Request, tasks: BackgroundTasks, db=Depends(get_db)):
    if not enabled():
        raise HTTPException(404, "Not found")
    if body.website:                                               # a bot filled the hidden field: pretend it worked
        return {"ok": True, "login": None}
    fwd = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    who = fwd or (request.client.host if request.client else "?")
    now = time.time()
    recent = [t for t in _HITS.get(who, []) if now - t < 3600]
    if len(recent) >= 3:
        raise HTTPException(429, "Too many requests from this address. Please try again later.")
    _HITS[who] = recent + [now]
    if len(_HITS) > 5000:
        _HITS.clear()
    if _live(db).count() >= _cap():
        raise HTTPException(503, "All sandbox places are taken right now. Request a demo and we will set one up for you.")
    if _live(db).filter(Tenant.trial_email == body.email).first():
        raise HTTPException(409, "This e-mail address already has a live trial. Sign in with the details you were given, or request a demo.")
    slug = "trial-" + secrets.token_hex(3)
    pw = secrets.token_urlsafe(9) + "-Aa1"
    until = datetime.now(timezone.utc) + timedelta(days=DAYS)
    t = Tenant(name=f"{body.organization} (trial {slug[-6:]})"[:120], slug=slug, trial_until=until, trial_email=body.email, seed_state="loading")
    db.add(t)
    db.flush()
    prefix = slug + "-"
    admin = User(staff_id=prefix + "admin", full_name=body.name, role="ADMIN", password_hash=hash_pw(pw), tenant_id=t.id, email=body.email)
    db.add(admin)
    db.commit()
    try:                                                          # lead for sales (also e-mailed to the sales inbox when mail is set up)
        request_consultation(ConsultationIn(name=body.name, organization=body.organization, email=body.email, interest="trial", lang=body.lang,
                                            message=f"14-day sandbox started: {slug}"), request, db)
    except HTTPException:
        pass
    tasks.add_task(_seed, request.app, t.id, prefix, pw, admin.id)
    accounts = [{"staff_id": prefix + "admin", "role": "ADMIN"}] + [{"staff_id": prefix + s, "role": r} for s, r in (("pm1", "PM"), ("pmo1", "PMO"), ("s1", "STAFF"))]
    return {"ok": True, "slug": slug, "password": pw, "accounts": accounts, "expires": until.date().isoformat(), "days": DAYS}
