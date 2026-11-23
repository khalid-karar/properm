"""Account protection helpers: password policy, lockout, sign-in history, forced password change."""
import re
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from .models import AccountSecurity, LoginEvent, User


def _utc(d):
    return d.replace(tzinfo=timezone.utc) if d is not None and d.tzinfo is None else d


def params(db):
    from .deps import get_params
    return get_params(db)


def policy_error(db, pw: str) -> str | None:
    n = int(params(db).get("password_min_length", 8))
    if len(pw) < n:
        return f"Password must be at least {n} characters"
    if not re.search(r"[A-Za-z؀-ۿ]", pw) or not re.search(r"\d", pw):
        return "Password must contain at least one letter and one digit"
    return None


def enforce_policy(db, pw: str) -> None:
    err = policy_error(db, pw)
    if err:
        raise HTTPException(422, err)


def sec(db, uid: int) -> AccountSecurity:
    s = db.get(AccountSecurity, uid)
    if s is None:
        s = AccountSecurity(user_id=uid, failed_count=0, must_change_password=False)
        db.add(s)
    return s


def is_locked(db, u: User) -> datetime | None:
    s = db.get(AccountSecurity, u.id)
    lu = _utc(s.locked_until) if s else None
    return lu if lu and lu > datetime.now(timezone.utc) else None


def record(db, staff_id: str, user: User | None, ok: bool, reason: str | None = None) -> None:
    db.add(LoginEvent(staff_id=staff_id[:40], user_id=user.id if user else None, ok=ok, reason=reason))


def on_failure(db, user: User) -> bool:
    """Count a failed sign-in; returns True when this failure locks the account."""
    prm = params(db)
    s = sec(db, user.id)
    s.failed_count = (s.failed_count or 0) + 1
    if s.failed_count >= int(prm.get("lockout_attempts", 5)):
        s.locked_until = datetime.now(timezone.utc) + timedelta(minutes=float(prm.get("lockout_minutes", 15)))
        s.failed_count = 0
        return True
    return False


def on_success(db, user: User) -> AccountSecurity:
    s = sec(db, user.id)
    s.failed_count, s.locked_until = 0, None
    return s


def password_set(db, user: User, by_admin: bool) -> None:
    """Call whenever a password is set. Admin-set passwords may require a change at next sign-in."""
    s = sec(db, user.id)
    s.password_changed_at = datetime.now(timezone.utc)
    s.must_change_password = bool(by_admin and params(db).get("force_password_change"))
