"""AI usage and cost: each model call is recorded per tenant and person; owner sees all tenants, a tenant admin only their own."""
from app import ai
from tests.test_flow import app, c, login  # noqa: F401


def _call(tid, uid, task, n_in, n_out):
    t1, t2 = ai._tenant.set(tid), ai._actor.set(uid)
    try:
        ai._record_usage(task, {"model": "m"}, n_in, n_out, True, 1200)
    finally:
        ai._tenant.reset(t1)
        ai._actor.reset(t2)


def test_usage_is_per_tenant_and_private(c):
    admin = login(c, "admin")
    t1 = c.post("/admin/tenants", headers=admin, json={"name": "Client One", "slug": "one"}).json()["id"]
    t2 = c.post("/admin/tenants", headers=admin, json={"name": "Client Two", "slug": "two"}).json()["id"]
    for t, s in ((t1, "t1admin"), (t2, "t2admin")):
        assert c.post(f"/admin/tenants/{t}/admins", headers=admin, json={"staff_id": s, "full_name": s, "password": "password1"}).status_code == 201
    h1, h2 = login(c, "t1admin"), login(c, "t2admin")
    _call(t1, None, "brief", 60000, 40000)      # 100,000 chars
    _call(t1, None, "assistant", 5000, 5000)
    _call(t2, None, "brief", 200000, 0)
    owner = c.get("/admin/ai/usage?days=30", headers=admin).json()
    assert owner["owner"] is True and owner["total"]["calls"] == 3
    by = {x["name"]: x for x in owner["by_tenant"]}
    assert by["Client One"]["chars"] == 110000 and by["Client Two"]["chars"] == 200000
    assert round(by["Client One"]["cost"], 4) == round(110000 / 10000 * 0.05850624, 4)
    one = c.get("/admin/ai/usage", headers=h1).json()
    assert one["owner"] is False and one["total"]["calls"] == 2 and "by_tenant" not in one or not one.get("by_tenant")
    two = c.get("/admin/ai/usage", headers=h2).json()
    assert two["total"]["calls"] == 1 and two["total"]["chars"] == 200000
    # a tenant admin cannot look into another tenant
    assert c.get(f"/admin/ai/usage?tenant_id={t2}", headers=h1).json()["total"]["calls"] == 2
    # owner can drill into one tenant
    assert c.get(f"/admin/ai/usage?tenant_id={t2}", headers=admin).json()["total"]["calls"] == 1


def test_only_admins_see_usage(c):
    from tests.test_flow import mkuser
    admin = login(c, "admin")
    mkuser(c, admin, "pm1", "PM")
    assert c.get("/admin/ai/usage", headers=login(c, "pm1")).status_code == 403
    assert c.get("/admin/ai/usage").status_code in (401, 403)
