from datetime import timedelta

from tests.test_flow import TODAY, app, c, entry, world  # noqa: F401


def test_profile_password_prefs(c, world):
    w, h = world, world["h"]
    s1 = h["s1"]
    p = c.get("/me/profile", headers=s1).json()
    assert p["prefs"]["email_enabled"] and "timesheet.approved" in p["kinds"]
    r = c.patch("/me/profile", headers=s1, json={"email": "s1@example.com", "delegate_id": w["ids"]["s2"]})
    assert r.status_code == 200 and r.json()["email"] == "s1@example.com" and r.json()["delegate_name"]
    assert c.patch("/me/profile", headers=s1, json={"delegate_id": w["ids"]["s1"]}).status_code == 422
    assert c.post("/me/password", headers=s1, json={"current_password": "wrong-pass", "new_password": "newpassword1"}).status_code == 403
    assert c.put("/me/prefs", headers=s1, json={"muted_kinds": ["bogus"]}).status_code == 422
    # mute "timesheet.approved" and confirm no notification is produced
    assert c.put("/me/prefs", headers=s1, json={"muted_kinds": ["timesheet.approved"], "email_enabled": False}).status_code == 200
    eid = c.post("/timesheets", headers=s1, json=entry(w, entry_date=str(TODAY - timedelta(days=1)), hours=1)).json()["id"]
    assert c.post(f"/timesheets/{eid}/decision", headers=h["pm1"], json={"action": "approve"}).status_code == 200
    c.post("/notifications/dispatch", headers=h["admin"])
    kinds = [n["kind"] for n in c.get("/notifications", headers=s1).json()]
    assert "timesheet.approved" not in kinds


def test_my_projects_and_copy_week(c, world):
    w, h = world, world["h"]
    s1 = h["s1"]
    mp = c.get("/me/projects", headers=s1).json()
    assert mp and mp[0]["activities"] and "remaining" in mp[0]["activities"][0]
    src = TODAY - timedelta(days=14)
    r = c.post("/timesheets", headers=s1, json=entry(w, entry_date=str(src), hours=3))
    assert r.status_code == 201, r.text
    out = c.post("/timesheets/copy-week", headers=s1, json={"from_week_of": str(src), "to_week_of": str(src + timedelta(days=7))}).json()
    assert out["created"] + len(out["skipped"]) >= 1
    again = c.post("/timesheets/copy-week", headers=s1, json={"from_week_of": str(src), "to_week_of": str(src + timedelta(days=7))}).json()
    assert again["created"] == 0
    assert c.post("/timesheets/copy-week", headers=s1, json={"from_week_of": str(src), "to_week_of": str(src)}).status_code == 422
