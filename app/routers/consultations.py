"""Demo / consultation requests from the public landing page.

 * POST /public/consultation: no sign-in. Protected by a hidden honeypot field, a per-address limit and size limits.
 * GET /consultations, PATCH /consultations/{id}: platform owner only (an ADMIN with no tenant).
The platform owner's administrators get an in-app notification (and an e-mail when a mail server is set up)."""
import os
import re
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from ..deps import get_db, require_roles
from ..models import ConsultationRequest, User

router = APIRouter(tags=["consultations"])
SALES_EMAIL = os.environ.get("PROPERM_CONSULTATION_EMAIL", "info@elevantec.sa")   # every request is also e-mailed here (needs the mail server set up in Admin)
_HITS: dict[str, list[float]] = {}
MAX_PER_WINDOW, WINDOW = 5, 3600
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SIZES = {"1-10", "11-50", "51-200", "200+"}
STATUSES = {"new", "contacted", "closed"}


class ConsultationIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    organization: str = Field(min_length=2, max_length=160)
    job_title: str | None = Field(default=None, max_length=120)
    email: str = Field(max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    team_size: str | None = None
    interest: str = "demo"
    message: str | None = Field(default=None, max_length=2000)
    lang: str = "en"
    website: str | None = Field(default=None, max_length=200)    # honeypot: real visitors never see or fill it

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip()
        if not EMAIL.match(v):
            raise ValueError("Enter a valid e-mail address")
        return v

    @field_validator("name", "organization")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Too short")
        return v


def _owner(admin: User = Depends(require_roles("ADMIN"))) -> User:
    if admin.tenant_id is not None:
        raise HTTPException(403, "Only the platform owner can see consultation requests")
    return admin


def _view(r: ConsultationRequest) -> dict:
    return {"id": r.id, "created_at": r.created_at, "name": r.name, "organization": r.organization, "job_title": r.job_title, "email": r.email,
            "phone": r.phone, "team_size": r.team_size, "interest": r.interest, "message": r.message, "lang": r.lang, "status": r.status}


@router.post("/public/consultation", status_code=201)
def request_consultation(body: ConsultationIn, request: Request, db=Depends(get_db)):
    if body.website:                       # a bot filled the hidden field: pretend it worked, store nothing
        return {"ok": True}
    fwd = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    who = fwd or (request.client.host if request.client else "?")
    now = time.time()
    recent = [t for t in _HITS.get(who, []) if now - t < WINDOW]
    if len(recent) >= MAX_PER_WINDOW:
        raise HTTPException(429, "Too many requests from this address. Please try again later.")
    _HITS[who] = recent + [now]
    if len(_HITS) > 5000:
        _HITS.clear()
    row = ConsultationRequest(
        name=body.name, organization=body.organization, job_title=(body.job_title or "").strip() or None, email=body.email,
        phone=(body.phone or "").strip() or None, team_size=body.team_size if body.team_size in SIZES else None,
        interest=body.interest if body.interest in ("consultation", "trial") else "demo", message=(body.message or "").strip() or None,
        lang="ar" if body.lang == "ar" else "en", created_at=datetime.now(timezone.utc))
    db.add(row)
    db.commit()
    try:                                   # best effort: the request is saved either way
        from ..notify import notify
        title = f"New {row.interest} request: {row.name}, {row.organization}"
        body_txt = f"{row.email} · {row.phone or '-'} · team {row.team_size or '-'}\n{row.message or ''}"
        for u in db.query(User).filter(User.role == "ADMIN", User.active.is_(True)).all():
            if u.tenant_id is None:
                notify(db, u.id, "consultation", title, body_txt, "#/admin")
        db.commit()
    except Exception:
        db.rollback()
    try:                                   # e-mail to the sales inbox; best effort, the request is already saved
        from ..notify import deliver, mail_settings
        cfg = mail_settings(db)
        if SALES_EMAIL and cfg.get("host"):
            lines = [f"Type: {row.interest}", f"Name: {row.name}", f"Organisation: {row.organization}", f"Job title: {row.job_title or '-'}",
                     f"E-mail: {row.email}", f"Phone: {row.phone or '-'}", f"Team size: {row.team_size or '-'}", f"Language: {row.lang}", "", row.message or ""]
            deliver(cfg, SALES_EMAIL, f"PROPERM {row.interest} request: {row.name}, {row.organization}", "\n".join(lines))
    except Exception:
        pass
    return {"ok": True}


@router.get("/consultations")
def list_requests(status: str | None = None, db=Depends(get_db), admin: User = Depends(_owner)):
    q = db.query(ConsultationRequest)
    if status in STATUSES:
        q = q.filter(ConsultationRequest.status == status)
    return [_view(r) for r in q.order_by(ConsultationRequest.id.desc()).limit(500).all()]


class StatusIn(BaseModel):
    status: str


@router.patch("/consultations/{rid}")
def set_status(rid: int, body: StatusIn, db=Depends(get_db), admin: User = Depends(_owner)):
    if body.status not in STATUSES:
        raise HTTPException(422, "Status must be new, contacted or closed")
    r = db.get(ConsultationRequest, rid)
    if r is None:
        raise HTTPException(404, "Not found")
    r.status = body.status
    db.commit()
    return _view(r)
