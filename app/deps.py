import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .models import User, RuleConfig, Setting
from .config import DEFAULT_SEVERITIES, DEFAULT_PARAMS

SECRET = os.environ.get("PROPERM_SECRET", "dev-secret-change-me-in-production-0123456789")
bearer = HTTPBearer(auto_error=False)


def hash_pw(p: str) -> str:
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt(int(os.environ.get("PROPERM_BCRYPT_ROUNDS", "12")))).decode()


def verify_pw(p: str, h: str) -> bool:
    return bcrypt.checkpw(p.encode(), h.encode())


def make_token(user: User, hours: float = 8) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=hours)
    return jwt.encode({"sub": str(user.id), "role": user.role, "tid": user.tenant_id, "exp": exp}, SECRET, algorithm="HS256")


def get_db(request: Request):
    db = request.app.state.Session()
    try:
        yield db
    finally:
        db.close()


def current_user(request: Request, creds: HTTPAuthorizationCredentials = Depends(bearer), db=Depends(get_db)) -> User:
    if not creds:
        raise HTTPException(401, "Not authenticated")
    try:
        data = jwt.decode(creds.credentials, SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired token")
    user = db.get(User, int(data["sub"]))
    if not user or not user.active:
        raise HTTPException(401, "Unknown or inactive user")
    if request.url.path not in MUST_CHANGE_ALLOWED:
        from .models import AccountSecurity
        s = db.get(AccountSecurity, user.id)
        if s and s.must_change_password:
            raise HTTPException(403, "Change your password first (My profile)")
        if user.role in ("ADMIN", "PMO", "DECISION_MAKER") and get_params(db).get("require_2fa_privileged"):
            from .models import TwoFactor
            tf = db.get(TwoFactor, user.id)
            if not (tf and tf.enabled):
                raise HTTPException(403, "Turn on two-factor sign-in first (My profile)")
    return user


MUST_CHANGE_ALLOWED = {"/me", "/me/password", "/me/profile", "/directory", "/notifications/count", "/config/governance", "/me/2fa", "/me/2fa/setup", "/me/2fa/enable"}


def require_roles(*roles):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, f"Requires role: {', '.join(roles)}")
        return user
    return dep


def get_severities(db) -> dict:
    s = dict(DEFAULT_SEVERITIES)
    for r in db.query(RuleConfig).all():
        s[r.rule] = r.severity
    return s


def get_params(db) -> dict:
    p = dict(DEFAULT_PARAMS)
    for r in db.query(Setting).all():
        if r.key in p:
            p[r.key] = r.value
    return p
