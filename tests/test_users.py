from tests.test_flow import app, c, login, mkuser, world   # noqa: F401


def uid(c, h, staff_id):
    return next(u["id"] for u in c.get("/users", headers=h).json() if u["staff_id"] == staff_id)


def test_admin_updates_user_and_deactivation_blocks_access(c, world):
    adm = login(c, "admin")
    s1 = uid(c, adm, "s1")
    r = c.patch(f"/users/{s1}", headers=adm, json={"full_name": "Renamed", "capacity_hours_week": 30, "is_ccb": True, "rate_grade": "G2"})
    assert r.status_code == 200 and r.json()["full_name"] == "Renamed" and r.json()["capacity_hours_week"] == 30
    tok = login(c, "s1")
    assert c.get("/me", headers=tok).status_code == 200
    assert c.patch(f"/users/{s1}", headers=adm, json={"active": False}).status_code == 200
    assert c.get("/me", headers=tok).status_code == 401                     # existing session dies
    assert c.post("/auth/login", json={"staff_id": "s1", "password": "password1"}).status_code == 401
    assert c.patch(f"/users/{s1}", headers=adm, json={"active": True, "new_password": "brand-new-pw1"}).status_code == 200
    assert c.post("/auth/login", json={"staff_id": "s1", "password": "brand-new-pw1"}).status_code == 200


def test_user_update_guards(c, world):
    adm = login(c, "admin")
    me = uid(c, adm, "admin")
    assert c.patch(f"/users/{me}", headers=adm, json={"active": False}).status_code == 409      # not yourself / last admin
    assert c.patch(f"/users/{me}", headers=adm, json={"role": "PM"}).status_code == 409         # last admin cannot be demoted
    assert c.patch(f"/users/{me}", headers=adm, json={"role": "KING"}).status_code == 422
    assert c.patch(f"/users/{me}", headers=adm, json={"line_manager_id": me}).status_code == 422
    assert c.patch("/users/99999", headers=adm, json={"full_name": "x"}).status_code == 404
    assert c.patch(f"/users/{me}", headers=login(c, "pm1"), json={"full_name": "x"}).status_code == 403
