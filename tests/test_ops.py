from app import totp
from tests.test_flow import TODAY, app, c, world, login  # noqa: F401
from tests.test_gates import mk


def test_totp_rfc6238_vector():
    # RFC 6238 appendix B, SHA1, secret "12345678901234567890", T=59 -> 94287082 (8 digits); our 6-digit code is its tail
    import base64
    sec = base64.b32encode(b"12345678901234567890").decode()
    assert totp.at(sec, 59) == "287082"
    assert totp.verify(sec, "287082", ts=59) and not totp.verify(sec, "000000", ts=59)
    assert totp.verify(sec, "287082", ts=59 + 30) and not totp.verify(sec, "287082", ts=59 + 120)   # window of one step


def test_two_factor_flow(c, world):
    h = world["h"]
    pm = h["pm1"]
    assert c.get("/me/2fa", headers=pm).json()["enabled"] is False
    st = c.post("/me/2fa/setup", headers=pm).json()
    assert st["uri"].startswith("otpauth://totp/")
    assert c.post("/me/2fa/enable", headers=pm, json={"code": "000000"}).status_code == 422
    codes = c.post("/me/2fa/enable", headers=pm, json={"code": totp.at(st["secret"])}).json()["backup_codes"]
    assert len(codes) == 8
    pw = {"staff_id": "pm1", "password": "password1"}
    r = c.post("/auth/login", json=pw)
    assert r.status_code == 401 and r.json()["detail"] == "otp_required"
    assert c.post("/auth/login", json={**pw, "otp": "123456"}).status_code == 401
    assert c.post("/auth/login", json={**pw, "otp": totp.at(st["secret"])}).status_code == 200
    assert c.post("/auth/login", json={**pw, "otp": codes[0]}).status_code == 200          # backup code works once
    assert c.post("/auth/login", json={**pw, "otp": codes[0]}).status_code == 401
    assert c.get("/me/2fa", headers=pm).json()["backup_codes_left"] == 7
    assert c.post("/me/2fa/disable", headers=pm, json={"password": "password1", "code": "000000"}).status_code == 403
    assert c.post("/admin/users/%d/2fa/reset" % world["ids"]["pm"], headers=h["admin"]).status_code == 200
    assert c.post("/auth/login", json=pw).status_code == 200


def test_two_factor_required_for_privileged(c, world):
    h = world["h"]
    ad, pmo = h["admin"], h["pmo1"]
    assert c.put("/admin/settings/require_2fa_privileged", headers=ad, json={"value": 1}).status_code == 200
    assert c.get("/projects", headers=pmo).status_code == 403                     # PMO must turn it on first
    assert c.get("/projects", headers=h["pm1"]).status_code == 200                # PM is not in the privileged set
    st = c.post("/me/2fa/setup", headers=pmo).json()
    assert c.post("/me/2fa/enable", headers=pmo, json={"code": totp.at(st["secret"])}).status_code == 200
    assert c.get("/projects", headers=pmo).status_code == 200


def test_restore(c, world):
    h = world["h"]
    ad = h["admin"]
    backup = c.get("/admin/export", headers=ad).json()
    # change things after the backup: a new project and a new user
    c.post("/projects", headers=h["pm1"], json={"number": "P-LATER", "name": "Later", "state": "planning"})
    mk(c, h, "STAFF", "later1")
    assert c.post("/admin/restore", headers=h["pm1"], json={"confirm": "RESTORE", "mode": "dry_run", "backup": backup}).status_code == 403
    assert c.post("/admin/restore", headers=ad, json={"confirm": "no", "mode": "dry_run", "backup": backup}).status_code == 422
    assert c.post("/admin/restore", headers=ad, json={"confirm": "RESTORE", "mode": "dry_run", "backup": {"format": "x"}}).status_code == 422
    nobody = {**backup, "tables": {**backup["tables"], "users": [u for u in backup["tables"]["users"] if u["staff_id"] != "admin"]}}
    assert c.post("/admin/restore", headers=ad, json={"confirm": "RESTORE", "mode": "dry_run", "backup": nobody}).status_code == 422
    dry = c.post("/admin/restore", headers=ad, json={"confirm": "RESTORE", "mode": "dry_run", "backup": backup}).json()
    assert dry["counts"]["projects"] == 1 and "temporary_passwords" not in dry
    assert any(p["number"] == "P-LATER" for p in c.get("/projects", headers=ad).json())      # dry run changed nothing
    # make the backup contain a user that does not exist here any more, to get a temporary password
    ghost = {**backup["tables"]["users"][0], "id": 999, "staff_id": "ghost1", "full_name": "Ghost", "role": "STAFF"}
    b2 = {**backup, "tables": {**backup["tables"], "users": backup["tables"]["users"] + [ghost]}}
    audit_before = len(c.get("/audit", headers=ad).json()) if c.get("/audit", headers=ad).status_code == 200 else None
    r = c.post("/admin/restore", headers=ad, json={"confirm": "RESTORE", "mode": "replace", "backup": b2})
    assert r.status_code == 200, r.text
    rep = r.json()
    assert "ghost1" in rep["temporary_passwords"]
    nums = [p["number"] for p in c.get("/projects", headers=ad).json()]
    assert "P-001" in nums and "P-LATER" not in nums
    assert c.post("/auth/login", json={"staff_id": "later1", "password": "password123"}).status_code == 401        # not in the backup
    assert c.post("/auth/login", json={"staff_id": "pm1", "password": "password1"}).status_code == 200          # kept its password
    t = c.post("/auth/login", json={"staff_id": "ghost1", "password": rep["temporary_passwords"]["ghost1"]})
    assert t.status_code == 200 and t.json()["must_change_password"] is True
    assert c.get("/projects", headers=ad).status_code == 200                                                         # admin token still good
    if audit_before is not None:
        assert len(c.get("/audit", headers=ad).json()) >= audit_before                                            # audit never shrinks


def test_retention(c, world):
    h = world["h"]
    ad = h["admin"]
    r = c.get("/admin/retention", headers=ad).json()
    assert r["login_events"] == 0 and r["projects_past_retention"] == []
    assert c.get("/admin/retention", headers=h["pm1"]).status_code == 403
    assert c.post("/admin/retention/apply", headers=ad, json={"login_days": 5}).status_code == 422
    assert c.post("/admin/retention/apply", headers=ad, json={"login_days": 365, "notification_days": 90}).json() == {"login_events_deleted": 0, "read_notifications_deleted": 0}
