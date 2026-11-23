"""Single sign-on with OpenID Connect (authorization code + PKCE). Works with Microsoft Entra ID, Okta, Keycloak, Google Workspace, ADFS 2019+ and any OIDC provider.
Off unless PROPERM_OIDC_ISSUER is set. Environment:
  PROPERM_OIDC_ISSUER, PROPERM_OIDC_CLIENT_ID, PROPERM_OIDC_CLIENT_SECRET
  PROPERM_OIDC_REDIRECT_URI   the public URL of /auth/sso/callback on this server (register the same one at the provider)
  PROPERM_OIDC_MATCH          'email' (default) or 'staff_id': which user field the claim is matched to
  PROPERM_OIDC_CLAIM          claim holding it (default: email, or preferred_username for staff_id)
  PROPERM_OIDC_AUTO_CREATE    '1' to create a STAFF user the first time an unknown person signs in (default: off, only existing active users can sign in)
  PROPERM_OIDC_LABEL          text on the button (default: Sign in with your company account)
  PROPERM_SSO_ONLY            '1' to turn off password sign-in for everyone except ADMIN (break-glass)
  PROPERM_UI_URL              where to send the browser afterwards (default /ui/)
The person is matched to an existing PROPERM user; roles stay managed in PROPERM. Nothing from the provider is trusted before the ID token signature, issuer, audience, expiry and nonce are checked."""
import base64
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from .. import acct
from ..audit import log
from ..deps import SECRET, get_db, hash_pw, make_token
from ..models import User

router = APIRouter(tags=["sso"])
COOKIE = "properm_sso"


def cfg() -> dict | None:
    iss = os.environ.get("PROPERM_OIDC_ISSUER", "").rstrip("/")
    if not iss:
        return None
    match = os.environ.get("PROPERM_OIDC_MATCH", "email")
    return {"issuer": iss, "client_id": os.environ.get("PROPERM_OIDC_CLIENT_ID", ""), "secret": os.environ.get("PROPERM_OIDC_CLIENT_SECRET", ""),
            "redirect": os.environ.get("PROPERM_OIDC_REDIRECT_URI", ""), "match": match, "claim": os.environ.get("PROPERM_OIDC_CLAIM") or ("preferred_username" if match == "staff_id" else "email"),
            "auto": os.environ.get("PROPERM_OIDC_AUTO_CREATE") == "1", "label": os.environ.get("PROPERM_OIDC_LABEL", "Sign in with your company account"),
            "ui": os.environ.get("PROPERM_UI_URL", "/ui/")}


def sso_only() -> bool:
    return bool(cfg()) and os.environ.get("PROPERM_SSO_ONLY") == "1"


# --- the three calls to the provider; kept small so tests can replace them ---
def _discovery(issuer: str) -> dict:
    import httpx
    r = httpx.get(issuer + "/.well-known/openid-configuration", timeout=10)
    r.raise_for_status()
    d = r.json()
    if d.get("issuer", "").rstrip("/") != issuer:
        raise HTTPException(502, "The sign-in provider's issuer does not match the configuration")
    return d


def _exchange(token_endpoint: str, form: dict) -> dict:
    import httpx
    r = httpx.post(token_endpoint, data=form, timeout=15, headers={"Accept": "application/json"})
    if r.status_code >= 400:
        raise HTTPException(502, "The sign-in provider refused the code")
    return r.json()


def _signing_key(jwks_uri: str, id_token: str):
    return jwt.PyJWKClient(jwks_uri, timeout=10).get_signing_key_from_jwt(id_token).key


@router.get("/auth/sso/config")
def sso_config():
    c = cfg()
    return {"enabled": bool(c), "label": c["label"] if c else None, "sso_only": sso_only()}


@router.get("/auth/sso/login")
def sso_login():
    c = cfg()
    if not c:
        raise HTTPException(404, "Single sign-on is not set up")
    if not (c["client_id"] and c["redirect"]):
        raise HTTPException(500, "PROPERM_OIDC_CLIENT_ID and PROPERM_OIDC_REDIRECT_URI are required")
    d = _discovery(c["issuer"])
    state, nonce, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(24), secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    q = urlencode({"response_type": "code", "client_id": c["client_id"], "redirect_uri": c["redirect"], "scope": "openid email profile", "state": state, "nonce": nonce,
                   "code_challenge": challenge, "code_challenge_method": "S256"})
    resp = RedirectResponse(f"{d['authorization_endpoint']}?{q}", status_code=302)
    pack = jwt.encode({"state": state, "nonce": nonce, "v": verifier, "exp": datetime.now(timezone.utc) + timedelta(minutes=10)}, SECRET, algorithm="HS256")
    resp.set_cookie(COOKIE, pack, max_age=600, httponly=True, samesite="lax", secure=c["redirect"].startswith("https://"), path="/auth/sso")
    return resp


def _back(c, **kw):
    r = RedirectResponse(c["ui"].rstrip("/") + "/#/" + ("sso/" + kw["code"] if "code" in kw else "login?sso_error=" + kw.get("error", "failed")), status_code=302)
    r.delete_cookie(COOKIE, path="/auth/sso")
    return r


@router.get("/auth/sso/callback")
def sso_callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None, db=Depends(get_db)):
    c = cfg()
    if not c:
        raise HTTPException(404, "Single sign-on is not set up")
    if error or not code or not state:
        return _back(c, error="provider_refused")
    try:
        pack = jwt.decode(request.cookies.get(COOKIE, ""), SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        return _back(c, error="expired")
    if not secrets.compare_digest(pack["state"], state):
        return _back(c, error="state")
    d = _discovery(c["issuer"])
    tok = _exchange(d["token_endpoint"], {"grant_type": "authorization_code", "code": code, "redirect_uri": c["redirect"], "client_id": c["client_id"],
                                          "client_secret": c["secret"], "code_verifier": pack["v"]})
    try:
        claims = jwt.decode(tok["id_token"], _signing_key(d["jwks_uri"], tok["id_token"]), algorithms=["RS256", "ES256", "PS256"], audience=c["client_id"], issuer=c["issuer"],
                            options={"require": ["exp", "iss", "aud"]})
    except (jwt.PyJWTError, KeyError):
        acct.record(db, "sso", None, False, "sso_bad_token")
        db.commit()
        return _back(c, error="bad_token")
    if not secrets.compare_digest(str(claims.get("nonce", "")), pack["nonce"]):
        return _back(c, error="nonce")
    val = str(claims.get(c["claim"]) or "").strip()
    if not val:
        return _back(c, error="no_claim")
    if c["match"] == "email" and claims.get("email_verified") is False:
        return _back(c, error="unverified_email")
    q = db.query(User)
    u = q.filter(User.email.ilike(val)).first() if c["match"] == "email" else q.filter_by(staff_id=val).first()
    if not u and c["auto"]:
        sid = (val.split("@")[0] if c["match"] == "email" else val)[:40]
        if db.query(User).filter_by(staff_id=sid).first():
            sid = f"{sid[:30]}-{secrets.token_hex(3)}"
        u = User(staff_id=sid, full_name=str(claims.get("name") or sid)[:200], role="STAFF", password_hash=hash_pw(secrets.token_urlsafe(24)), email=val if c["match"] == "email" else None)
        db.add(u)
        db.flush()
        log(db, u.id, "user.sso_created", "user", u.id, {"issuer": c["issuer"]})
    if not u or not u.active:
        acct.record(db, val[:40], u, False, "sso_no_user" if not u else "inactive")
        db.commit()
        return _back(c, error="no_account")
    acct.record(db, u.staff_id, u, True, "sso")
    log(db, u.id, "auth.sso_login", "user", u.id, {"issuer": c["issuer"]})
    db.commit()
    once = jwt.encode({"sub": str(u.id), "typ": "sso", "jti": secrets.token_hex(8), "exp": datetime.now(timezone.utc) + timedelta(seconds=60)}, SECRET, algorithm="HS256")
    return _back(c, code=once)


class ExchangeIn(BaseModel):
    code: str


@router.post("/auth/sso/exchange")
def sso_exchange(body: ExchangeIn, db=Depends(get_db)):
    try:
        data = jwt.decode(body.code, SECRET, algorithms=["HS256"])
        assert data.get("typ") == "sso"
    except (jwt.PyJWTError, AssertionError):
        raise HTTPException(401, "The sign-in link expired. Try again.")
    u = db.get(User, int(data["sub"]))
    if not u or not u.active:
        raise HTTPException(401, "Invalid credentials")
    hours = float(acct.params(db).get("session_hours", 8))
    return {"access_token": make_token(u, hours), "token_type": "bearer", "role": u.role, "must_change_password": False}
