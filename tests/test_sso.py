import time
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.routers import sso
from tests.test_flow import app, c, world  # noqa: F401

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
ISS, CID = "https://idp.example", "properm-client"


@pytest.fixture
def idp(monkeypatch):
    env = {"PROPERM_OIDC_ISSUER": ISS, "PROPERM_OIDC_CLIENT_ID": CID, "PROPERM_OIDC_CLIENT_SECRET": "s", "PROPERM_OIDC_REDIRECT_URI": "http://testserver/auth/sso/callback"}
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    state = {"claims": {}}
    monkeypatch.setattr(sso, "_discovery", lambda iss: {"issuer": iss, "authorization_endpoint": ISS + "/auth", "token_endpoint": ISS + "/token", "jwks_uri": ISS + "/jwks"})
    monkeypatch.setattr(sso, "_signing_key", lambda uri, tok: KEY.public_key())

    def exchange(url, form):
        assert form["code_verifier"] and form["code"] == "abc"
        claims = {"iss": ISS, "aud": CID, "exp": int(time.time()) + 300, "nonce": state["nonce"], **state["claims"]}
        return {"id_token": jwt.encode(claims, KEY, algorithm="RS256")}
    monkeypatch.setattr(sso, "_exchange", exchange)
    return state


def start(c, idp):
    r = c.get("/auth/sso/login", follow_redirects=False)
    assert r.status_code == 302
    q = parse_qs(urlparse(r.headers["location"]).query)
    assert q["code_challenge_method"] == ["S256"] and q["client_id"] == [CID]
    idp["nonce"] = q["nonce"][0]
    return q["state"][0]


def test_sso_off_by_default(c, world):
    assert c.get("/auth/sso/config").json()["enabled"] is False
    assert c.get("/auth/sso/login", follow_redirects=False).status_code == 404


def test_sso_sign_in_matches_existing_user_only(c, world, idp):
    h = world["h"]
    assert c.get("/auth/sso/config").json()["enabled"] is True
    from app.models import User
    with c.app.state.Session() as db:
        db.query(User).filter_by(staff_id="s1").one().email = "faisal@corp.sa"
        db.commit()
    idp["claims"] = {"email": "Faisal@Corp.sa", "email_verified": True}
    st = start(c, idp)
    r = c.get("/auth/sso/callback", params={"code": "abc", "state": st}, follow_redirects=False)
    loc = r.headers["location"]
    assert "#/sso/" in loc
    code = loc.split("#/sso/")[1]
    tok = c.post("/auth/sso/exchange", json={"code": code}).json()
    me = c.get("/me", headers={"Authorization": "Bearer " + tok["access_token"]}).json()
    assert me["staff_id"] == "s1"
    assert c.post("/auth/sso/exchange", json={"code": "junk"}).status_code == 401
    # a person with no PROPERM account is refused, not created
    idp["claims"] = {"email": "stranger@corp.sa", "email_verified": True}
    st = start(c, idp)
    assert "sso_error=no_account" in c.get("/auth/sso/callback", params={"code": "abc", "state": st}, follow_redirects=False).headers["location"]


def test_sso_rejects_forgeries(c, world, idp, monkeypatch):
    idp["claims"] = {"email": "x@corp.sa"}
    st = start(c, idp)
    assert "error=state" in c.get("/auth/sso/callback", params={"code": "abc", "state": "wrong"}, follow_redirects=False).headers["location"]
    c.cookies.clear()
    assert "error=expired" in c.get("/auth/sso/callback", params={"code": "abc", "state": st}, follow_redirects=False).headers["location"]     # no cookie: not this browser
    st = start(c, idp)
    idp["nonce"] = "someone-elses-nonce"
    assert "error=nonce" in c.get("/auth/sso/callback", params={"code": "abc", "state": st}, follow_redirects=False).headers["location"]
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)                          # token signed by a different key
    monkeypatch.setattr(sso, "_signing_key", lambda uri, tok: other.public_key())
    st = start(c, idp)
    assert "error=bad_token" in c.get("/auth/sso/callback", params={"code": "abc", "state": st}, follow_redirects=False).headers["location"]


def test_sso_auto_create_and_sso_only(c, world, idp, monkeypatch):
    h = world["h"]
    monkeypatch.setenv("PROPERM_OIDC_AUTO_CREATE", "1")
    idp["claims"] = {"email": "newbie@corp.sa", "name": "New Bie", "email_verified": True}
    st = start(c, idp)
    code = c.get("/auth/sso/callback", params={"code": "abc", "state": st}, follow_redirects=False).headers["location"].split("#/sso/")[1]
    tok = c.post("/auth/sso/exchange", json={"code": code}).json()
    assert c.get("/me", headers={"Authorization": "Bearer " + tok["access_token"]}).json()["role"] == "STAFF"
    monkeypatch.setenv("PROPERM_SSO_ONLY", "1")
    assert c.post("/auth/login", json={"staff_id": "s1", "password": "password1"}).status_code == 403      # passwords off for staff
    assert c.post("/auth/login", json={"staff_id": "admin", "password": "password1"}).status_code == 200    # admin break-glass stays
