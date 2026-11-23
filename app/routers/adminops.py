"""Administrator operations: mail server settings and test, full data export, personal start page."""
import base64
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import models
from ..audit import log
from ..deps import current_user, get_db, require_roles
from ..models import Base, MailConfig, User, UserHome
from ..notify import deliver, mail_settings

router = APIRouter(tags=["admin operations"])


# ---------------- mail ----------------
class MailIn(BaseModel):
    host: str | None = Field(None, max_length=200)
    port: int = Field(587, ge=1, le=65535)
    username: str | None = Field(None, max_length=200)
    password: str | None = Field(None, max_length=300)      # omitted or null = keep the stored password
    from_addr: str | None = Field(None, max_length=200)
    starttls: bool = True
    enabled: bool = True


def _mail_out(db) -> dict:
    m = db.query(MailConfig).first()
    cfg = mail_settings(db)
    return {"host": m.host if m else None, "port": m.port if m else 587, "username": m.username if m else None, "from_addr": m.from_addr if m else None,
            "starttls": m.starttls if m else True, "enabled": m.enabled if m else True, "password_set": bool(m and m.password),
            "source": "settings" if m and m.host else ("environment" if cfg.get("host") else "none"), "effective_host": cfg.get("host")}


@router.get("/admin/mail")
def get_mail(db=Depends(get_db), _: User = Depends(require_roles("ADMIN"))):
    return _mail_out(db)


@router.put("/admin/mail")
def put_mail(body: MailIn, db=Depends(get_db), admin: User = Depends(require_roles("ADMIN"))):
    m = db.query(MailConfig).first() or MailConfig()
    m.host, m.port, m.username, m.from_addr, m.starttls, m.enabled = (body.host or None), body.port, (body.username or None), (body.from_addr or None), body.starttls, body.enabled
    if body.password:
        m.password = body.password
    db.add(m)
    log(db, admin.id, "mail.settings_changed", "mail_config", None, {"host": m.host, "port": m.port})   # never the password
    db.commit()
    return _mail_out(db)


class MailTestIn(BaseModel):
    to: str = Field(max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@router.post("/admin/mail/test")
def test_mail(body: MailTestIn, db=Depends(get_db), admin: User = Depends(require_roles("ADMIN"))):
    err = deliver(mail_settings(db), body.to, "PROPERM test message", "If you can read this, PROPERM can send e-mail.")
    log(db, admin.id, "mail.tested", "mail_config", None, {"ok": err is None})
    db.commit()
    return {"ok": err is None, "error": err}


# ---------------- export ----------------
SKIP = {"password_hash", "password"}


def _val(v):
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, bytes):
        return base64.b64encode(v).decode()
    return v


@router.get("/admin/export")
def export_all(include_documents: bool = False, db=Depends(get_db), admin: User = Depends(require_roles("ADMIN"))):
    """Every table as JSON for backup or migration. Password hashes and the mail password are never included;
    document contents only when asked (they can be large)."""
    out = {"exported_at": datetime.now().isoformat(timespec="seconds"), "format": "properm-export-1", "tables": {}}
    for t in Base.metadata.sorted_tables:
        cols = [c.name for c in t.columns if c.name not in SKIP and (include_documents or not (t.name == "documents" and c.name == "content"))]
        rows = db.execute(t.select()).mappings().all()
        out["tables"][t.name] = [{c: _val(r[c]) for c in cols} for r in rows]
    log(db, admin.id, "data.exported", "system", None, {"tables": len(out["tables"]), "documents": include_documents})
    db.commit()
    out["counts"] = {k: len(v) for k, v in out["tables"].items()}
    return out


# ---------------- start page ----------------
class HomeIn(BaseModel):
    page: str | None = Field(None, max_length=40)


@router.put("/me/home")
def set_home(body: HomeIn, db=Depends(get_db), user: User = Depends(current_user)):
    row = db.get(UserHome, user.id)
    if not body.page:
        if row:
            db.delete(row)
    else:
        if not body.page.replace("_", "").isalpha():
            raise HTTPException(422, "Not a page")
        row = row or UserHome(user_id=user.id, page=body.page)
        row.page = body.page
        db.add(row)
    db.commit()
    return {"page": body.page}
