"""Administrator operations, part 2: restore from a backup, retention, and two-factor sign-in (TOTP)."""
import base64
import json
import secrets
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Date, DateTime, LargeBinary, delete

from .. import acct, totp
from ..audit import log
from ..deps import current_user, get_db, hash_pw, require_roles, verify_pw
from ..models import Base, LoginEvent, Notification, Project, TwoFactor, User

router = APIRouter(tags=["restore, retention, 2FA"])

KEEP = {"audit_log"}                       # never wiped or replaced: the audit trail outlives any restore
FORMAT = "properm-export-1"


# ---------------- restore ----------------
class RestoreIn(BaseModel):
    confirm: str
    mode: str = Field("dry_run", pattern="^(dry_run|replace)$")
    backup: dict


def _convert(col, v):
    if v is None:
        return None
    t = col.type
    if isinstance(t, DateTime) and isinstance(v, str):
        d = datetime.fromisoformat(v)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    if isinstance(t, Date) and isinstance(v, str):
        return date.fromisoformat(v[:10])
    if isinstance(t, LargeBinary) and isinstance(v, str):
        return base64.b64decode(v)
    return v


def _plan(db, backup: dict):
    if backup.get("format") != FORMAT or not isinstance(backup.get("tables"), dict):
        raise HTTPException(422, f"Not a PROPERM backup (expected format {FORMAT})")
    tables = backup["tables"]
    known = {t.name for t in Base.metadata.tables.values()}
    unknown = sorted(set(tables) - known)
    users = tables.get("users") or []
    return tables, unknown, users


@router.post("/admin/restore")
def restore(body: RestoreIn, db=Depends(get_db), admin: User = Depends(require_roles("ADMIN"))):
    """Replace the whole database with the contents of a backup made by /admin/export.
    dry_run only reports what would happen. Passwords are never in a backup: people who already exist here keep
    their password; people only in the backup get a temporary one (shown once) and must change it."""
    if body.confirm != "RESTORE":
        raise HTTPException(422, "Type RESTORE to confirm")
    tables, unknown, users = _plan(db, body.backup)
    if not any(u.get("staff_id") == admin.staff_id and u.get("role") == "ADMIN" and u.get("active", True) for u in users):
        raise HTTPException(422, "The backup must contain your own active administrator account, otherwise you would lock yourself out")
    have = {u.staff_id: u.password_hash for u in db.query(User)}
    new_users = [u["staff_id"] for u in users if u.get("staff_id") not in have]
    counts = {n: len(r) for n, r in tables.items() if n not in KEEP and n in Base.metadata.tables}
    skipped_content = [n for n in ("documents", "document_versions") if any(r.get("content") is None for r in tables.get(n, []))]
    report = {"mode": body.mode, "exported_at": body.backup.get("exported_at"), "counts": counts, "unknown_tables": unknown,
              "users_keeping_password": len(users) - len(new_users), "users_needing_temporary_password": new_users,
              "document_content_missing_in": skipped_content, "audit_log": "kept as is"}
    if body.mode == "dry_run":
        return report
    temp: dict[str, str] = {}
    try:
        order = [t for t in Base.metadata.sorted_tables if t.name not in KEEP]
        for t in reversed(order):
            db.execute(delete(t))
        for t in order:
            rows = tables.get(t.name) or []
            if not rows:
                continue
            out = []
            for r in rows:
                rec = {c.name: _convert(c, r[c.name]) for c in t.columns if c.name in r}
                if t.name == "users":
                    h = have.get(rec["staff_id"])
                    if h is None:
                        pw = "Tmp-" + secrets.token_urlsafe(9) + "9"
                        temp[rec["staff_id"]] = pw
                        h = hash_pw(pw)
                    rec["password_hash"] = h
                if t.name in ("documents", "document_versions") and rec.get("content") is None:
                    rec["content"] = b""
                out.append(rec)
            db.execute(t.insert(), out)
        for sid in temp:
            u = db.query(User).filter_by(staff_id=sid).first()
            if u:
                acct.sec(db, u.id).must_change_password = True
        log(db, admin.id, "data.restored", "system", None, {"exported_at": body.backup.get("exported_at"), "tables": len(counts), "rows": sum(counts.values())})
        db.commit()
    except Exception as e:                      # one transaction: any failure leaves the database untouched
        db.rollback()
        raise HTTPException(422, f"Restore failed and nothing was changed: {type(e).__name__}: {str(e)[:200]}")
    report["temporary_passwords"] = temp
    return report


# ---------------- retention ----------------
def _retention(db, years: int, login_days: int, notif_days: int):
    now = datetime.now(timezone.utc)
    logins = db.query(LoginEvent).filter(LoginEvent.at < now - timedelta(days=login_days))
    notes = db.query(Notification).filter(Notification.read_at.isnot(None), Notification.read_at < now - timedelta(days=notif_days))
    cut = date.today() - timedelta(days=365 * years)
    old = [p for p in db.query(Project).filter(Project.state.in_(("closed", "cancelled", "archived"))).all()
           if p.planned_end and p.planned_end < cut]
    return logins, notes, old


@router.get("/admin/retention")
def retention(years: int = 7, login_days: int = 365, notification_days: int = 90, db=Depends(get_db), _: User = Depends(require_roles("ADMIN"))):
    logins, notes, old = _retention(db, years, login_days, notification_days)
    return {"years": years, "login_days": login_days, "notification_days": notification_days,
            "login_events": logins.count(), "read_notifications": notes.count(),
            "projects_past_retention": [{"id": p.id, "number": p.number, "name": p.name, "planned_end": p.planned_end} for p in old],
            "note": "Only sign-in history and read notifications are removed by Apply. Closed projects past the retention period are listed for the administrator to export and decide; the audit log is never deleted."}


class RetentionIn(BaseModel):
    login_days: int = Field(365, ge=30)
    notification_days: int = Field(90, ge=7)


@router.post("/admin/retention/apply")
def retention_apply(body: RetentionIn, db=Depends(get_db), admin: User = Depends(require_roles("ADMIN"))):
    logins, notes, _ = _retention(db, 7, body.login_days, body.notification_days)
    a, b = logins.delete(synchronize_session=False), notes.delete(synchronize_session=False)
    log(db, admin.id, "retention.applied", "system", None, {"login_events": a, "read_notifications": b, "login_days": body.login_days, "notification_days": body.notification_days})
    db.commit()
    return {"login_events_deleted": a, "read_notifications_deleted": b}


# ---------------- two-factor (TOTP) ----------------
def _tf(db, uid):
    return db.get(TwoFactor, uid)


def two_factor_on(db, user) -> bool:
    r = _tf(db, user.id)
    return bool(r and r.enabled)


def check_otp(db, user, code: str) -> bool:
    """True for a valid TOTP or an unused backup code (which is then spent)."""
    r = _tf(db, user.id)
    if not r or not r.enabled or not code:
        return False
    if totp.verify(r.secret, code):
        return True
    hashes = json.loads(r.backup_hashes or "[]")
    h = totp.hash_code(code.strip().replace(" ", "").replace("-", ""))
    if h in hashes:
        hashes.remove(h)
        r.backup_hashes = json.dumps(hashes)
        return True
    return False


@router.get("/me/2fa")
def tf_status(db=Depends(get_db), user: User = Depends(current_user)):
    r = _tf(db, user.id)
    return {"enabled": bool(r and r.enabled), "backup_codes_left": len(json.loads(r.backup_hashes or "[]")) if r and r.enabled else 0,
            "required_for_role": user.role in ("ADMIN", "PMO", "DECISION_MAKER") and bool(acct.params(db).get("require_2fa_privileged", 0))}


@router.post("/me/2fa/setup")
def tf_setup(db=Depends(get_db), user: User = Depends(current_user)):
    r = _tf(db, user.id)
    if r and r.enabled:
        raise HTTPException(409, "Two-factor sign-in is already on. Turn it off first to set it up again")
    secret = totp.new_secret()
    if r:
        r.secret = secret
    else:
        db.add(TwoFactor(user_id=user.id, secret=secret, enabled=False))
    db.commit()
    return {"secret": secret, "uri": totp.uri(secret, user.staff_id)}


class CodeIn(BaseModel):
    code: str = Field(max_length=20)


@router.post("/me/2fa/enable")
def tf_enable(body: CodeIn, db=Depends(get_db), user: User = Depends(current_user)):
    r = _tf(db, user.id)
    if not r or r.enabled:
        raise HTTPException(409, "Start the setup first")
    if not totp.verify(r.secret, body.code):
        raise HTTPException(422, "That code is not right. Check the clock on your phone and try again")
    codes = totp.new_backup_codes()
    r.backup_hashes = json.dumps([totp.hash_code(c) for c in codes])
    r.enabled, r.enabled_at = True, datetime.now(timezone.utc)
    log(db, user.id, "2fa.enabled", "user", user.id, {})
    db.commit()
    return {"enabled": True, "backup_codes": codes}


class DisableIn(BaseModel):
    password: str
    code: str = Field(max_length=20)


@router.post("/me/2fa/disable")
def tf_disable(body: DisableIn, db=Depends(get_db), user: User = Depends(current_user)):
    r = _tf(db, user.id)
    if not r or not r.enabled:
        raise HTTPException(409, "Two-factor sign-in is not on")
    if not verify_pw(body.password, user.password_hash) or not check_otp(db, user, body.code):
        raise HTTPException(403, "Password or code is not right")
    db.delete(r)
    log(db, user.id, "2fa.disabled", "user", user.id, {})
    db.commit()
    return {"enabled": False}


@router.post("/admin/users/{uid}/2fa/reset")
def tf_reset(uid: int, db=Depends(get_db), admin: User = Depends(require_roles("ADMIN"))):
    r = _tf(db, uid)
    if not r:
        raise HTTPException(404, "That user has no two-factor setup")
    db.delete(r)
    log(db, admin.id, "2fa.reset", "user", uid, {})
    db.commit()
    return {"enabled": False}


@router.get("/admin/2fa")
def tf_list(db=Depends(get_db), _: User = Depends(require_roles("ADMIN"))):
    return [{"user_id": r.user_id, "enabled_at": r.enabled_at} for r in db.query(TwoFactor).filter_by(enabled=True)]
