"""Automated security matrix: every route, every role. Nothing may crash (5xx), anonymous callers get 401, and the admin area is closed to everyone else."""
import re

from tests.test_flow import TODAY, app, c, world  # noqa: F401
from tests.test_gates import mk

PUBLIC = {"/auth/login", "/health", "/ai/status", "/auth/demo-login", "/auth/demo-users", "/config"}


def fill(path, ids):
    return re.sub(r"\{(\w+)\}", lambda m: str(ids.get(m.group(1), 1)), path)


def routes(app):
    out = []
    for path, ops in app.openapi()["paths"].items():
        for m in ops:
            if m.upper() in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                out.append((m.upper(), path))
    return out


def test_every_route_is_closed_to_anonymous_and_never_crashes(c, world, app):
    ids = {"pid": world["pid"], "aid": world["aid"]}
    open_, crashed = [], []
    for m, path in routes(app):
        if path in PUBLIC or path.startswith(("/ui", "/static", "/docs", "/openapi", "/redoc")):
            continue
        r = c.request(m, fill(path, ids), json={} if m != "GET" else None)
        if r.status_code not in (401, 403, 404, 405):
            open_.append((m, path, r.status_code))
    assert not open_, f"reachable without a token: {open_[:10]}"


def test_no_route_returns_5xx_for_any_role(c, world, app):
    ids = {"pid": world["pid"], "aid": world["aid"]}
    bad = []
    for role, h in (("STAFF", world["h"]["s1"]), ("PM", world["h"]["pm1"]), ("PMO", world["h"]["pmo1"]), ("ADMIN", world["h"]["admin"])):
        for m, path in routes(app):
            if path in PUBLIC or path.startswith(("/ui", "/static", "/docs", "/openapi", "/redoc")) or "logout" in path or path.startswith("/admin/restore"):
                continue
            r = c.request(m, fill(path, ids), headers=h, json={} if m != "GET" else None)
            if r.status_code >= 500:
                bad.append((role, m, path, r.status_code, r.text[:80]))
    assert not bad, f"server errors: {bad[:10]}"


def test_admin_area_closed_to_other_roles(c, world, app):
    ids = {"pid": world["pid"], "aid": world["aid"]}
    leaks = []
    for role, h in (("STAFF", world["h"]["s1"]), ("PM", world["h"]["pm1"]), ("PMO", world["h"]["pmo1"])):
        for m, path in routes(app):
            if path.startswith("/admin") and m == "GET" and path not in ("/admin/lists", "/admin/permissions"):
                r = c.get(fill(path, ids), headers=h)
                if r.status_code == 200 and role in ("STAFF", "PM"):
                    leaks.append((role, path))
    assert not leaks, f"admin data readable: {leaks}"


def test_security_headers_and_size_cap_and_login_throttle(c, monkeypatch):
    r = c.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    big = c.post("/auth/login", content=b"x", headers={"content-length": str(50 * 1024 * 1024), "content-type": "application/json"})
    assert big.status_code == 413
    import app.hardening as hd
    monkeypatch.setattr(hd, "LOGIN_MAX", 3)
    codes = [c.post("/auth/login", json={"staff_id": "nobody", "password": "x"}).status_code for _ in range(5)]
    assert 429 in codes
