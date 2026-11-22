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
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()


def verify_pw(p: str, h: str) -> bool:
    return bcrypt.checkpw(p.encode(), h.encode())


def make_token(user: User) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=8)
    return jwt.encode({"sub": str(user.id), "role": user.role, "exp": exp}, SECRET, algorithm="HS256")


def get_db(request: Request):
    db = request.app.state.Session()
    try:
        yield db
    finally:
        db.close()


def current_user(creds: HTTPAuthorizationCredentials = Depends(bearer), db=Depends(get_db)) -> User:
    if not creds:
        raise HTTPException(401, "Not authenticated")
    try:
        data = jwt.decode(creds.credentials, SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired token")
    user = db.get(User, int(data["sub"]))
    if not user or not user.active:
        raise HTTPException(401, "Unknown or inactive user")
    return user


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
