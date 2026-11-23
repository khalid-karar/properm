from tests.test_flow import TODAY, app, c, world  # noqa: F401


def test_lockout_history_policy_force_change(c, world):
    h, ids = world["h"], world["ids"]
    ad = h["admin"]
    for _ in range(4):
        assert c.post("/auth/login", json={"staff_id": "s2", "password": "wrong-1"}).status_code == 401
    assert c.post("/auth/login", json={"staff_id": "s2", "password": "wrong-1"}).status_code == 401   # 5th locks
    assert c.post("/auth/login", json={"staff_id": "s2", "password": "password1"}).status_code == 423
    hist = c.get("/admin/logins?staff_id=s2", headers=ad).json()
    assert hist["events"][0]["reason"] == "locked" and any(x["user_id"] == ids["s2"] for x in hist["locked"])
    assert c.get("/admin/logins", headers=h["pm1"]).status_code == 403
    assert c.post(f"/admin/users/{ids['s2']}/unlock", headers=ad).status_code == 200
    assert c.post("/auth/login", json={"staff_id": "s2", "password": "password1"}).status_code == 200
    # password policy
    assert c.patch(f"/users/{ids['s2']}", headers=ad, json={"new_password": "onlyletters"}).status_code == 422
    # forced change after an admin reset
    assert c.put("/admin/settings/force_password_change", headers=ad, json={"value": 1}).status_code == 200
    assert c.patch(f"/users/{ids['s2']}", headers=ad, json={"new_password": "temporary-1"}).status_code == 200
    r = c.post("/auth/login", json={"staff_id": "s2", "password": "temporary-1"}).json()
    assert r["must_change_password"]
    s2 = {"Authorization": f"Bearer {r['access_token']}"}
    assert c.get("/me", headers=s2).json()["must_change_password"]
    assert c.get("/projects", headers=s2).status_code == 403
    assert c.post("/me/password", headers=s2, json={"current_password": "temporary-1", "new_password": "my-own-pass-2"}).status_code == 200
    assert c.get("/projects", headers=s2).status_code == 200
    assert c.get("/me/logins", headers=s2).json()[0]["ok"]


def test_handover(c, world):
    h, ids, pid = world["h"], world["ids"], world["pid"]
    ad, pm = h["admin"], h["pm1"]
    c.post(f"/projects/{pid}/risks", headers=pm, json={"title": "R", "probability": 2, "impact": 2, "owner_id": ids["s1"]})
    c.post(f"/projects/{pid}/actions", headers=pm, json={"title": "A", "owner_id": ids["s1"]})
    c.post("/users", headers=ad, json={"staff_id": "pm2", "full_name": "PM Two", "password": "password1", "role": "PM"})
    pm2 = next(u["id"] for u in c.get("/users", headers=ad).json() if u["staff_id"] == "pm2")
    pre = c.get(f"/admin/users/{ids['pm']}/handover", headers=ad).json()
    assert pre["projects_managed"] and pre["total"] >= 1
    assert c.post(f"/admin/users/{ids['pm']}/handover", headers=ad, json={"to_user_id": ids["s2"]}).status_code == 422   # staff can't take projects
    r = c.post(f"/admin/users/{ids['pm']}/handover", headers=ad, json={"to_user_id": pm2}).json()
    assert r["moved"]["projects"] >= 1 and r["deactivated"]
    assert c.get(f"/projects/{pid}", headers=ad).json()["pm_id"] == pm2
    assert c.post("/auth/login", json={"staff_id": "pm1", "password": "password1"}).status_code == 401
    r = c.post(f"/admin/users/{ids['s1']}/handover", headers=ad, json={"to_user_id": ids["s2"], "deactivate": False}).json()
    assert r["moved"]["risks"] >= 1 and r["moved"]["actions"] >= 1 and not r["deactivated"]
