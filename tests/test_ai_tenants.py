"""Per-tenant AI settings: default for all tenants, tenant override, permissions, encrypted key, test endpoint."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from tests.test_flow import app, c, login, mkuser  # noqa: F401


class _Fake(BaseHTTPRequestHandler):
    seen = []

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n))
        _Fake.seen.append((body["model"], self.headers.get("Authorization")))
        out = json.dumps({"choices": [{"message": {"content": '{"text": "ok from ' + body["model"] + '"}'}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


def _server():
    srv = HTTPServer(("127.0.0.1", 0), _Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_port}/v1"


def test_default_and_tenant_override(c):
    srv, url = _server()
    try:
        admin = login(c, "admin")
        # tenants
        t1 = c.post("/admin/tenants", headers=admin, json={"name": "Client One", "slug": "one"}).json()["id"]
        t2 = c.post("/admin/tenants", headers=admin, json={"name": "Client Two", "slug": "two"}).json()["id"]
        assert c.post("/admin/tenants", headers=admin, json={"name": "Client One", "slug": "x1"}).status_code == 409
        # default for all tenants
        r = c.put("/admin/ai/settings/global", headers=admin, json={"base_url": url, "model": "default-model", "api_key": "sekret-1"})
        assert r.status_code == 200 and r.json()["has_key"] is True and "sekret" not in r.text
        # tenant 1 gets its own model
        assert c.put(f"/admin/ai/settings/{t1}", headers=admin, json={"base_url": url, "model": "tenant-one-model", "api_key": "sekret-2"}).status_code == 200
        # key never returned, stored encrypted
        s = c.get("/admin/ai/settings", headers=admin)
        assert "sekret" not in s.text
        from app import ai
        from app.models import AiSetting
        with c.app.state.Session() as db:
            raw = db.query(AiSetting).filter_by(scope="global").one().api_key_enc
        assert raw and "sekret-1" not in raw and ai._decrypt_key(raw) == "sekret-1"
        # users in tenants
        assert c.post(f"/admin/tenants/{t1}/admins", headers=admin, json={"staff_id": "t1admin", "full_name": "T1", "password": "password1"}).status_code == 201
        assert c.post(f"/admin/tenants/{t2}/admins", headers=admin, json={"staff_id": "t2admin", "full_name": "T2", "password": "password1"}).status_code == 201
        h1, h2 = login(c, "t1admin"), login(c, "t2admin")
        # effective model per tenant
        _Fake.seen.clear()
        assert c.post("/admin/ai/test-scope", headers=h1, json={"scope": "effective"}).json()["ok"] is True
        assert c.post("/admin/ai/test-scope", headers=h2, json={"scope": "effective"}).json()["ok"] is True
        assert _Fake.seen[0] == ("tenant-one-model", "Bearer sekret-2")
        assert _Fake.seen[1] == ("default-model", "Bearer sekret-1")
        assert c.get("/admin/ai", headers=h1).json()["model"] == "tenant-one-model"       # request-level tenant context
        assert c.get("/admin/ai", headers=h2).json()["source"] == "global"
        # permissions
        assert c.put("/admin/ai/settings/global", headers=h1, json={"base_url": url}).status_code == 403
        assert c.put(f"/admin/ai/settings/{t2}", headers=h1, json={"base_url": url}).status_code == 403
        assert c.post("/admin/tenants", headers=h1, json={"name": "Nope", "slug": "nope"}).status_code == 403
        assert c.put("/admin/ai/settings/mine", headers=h2, json={"base_url": url, "model": "two"}).status_code == 200
        # unsaved form values can be tested; key blank keeps the saved key
        r = c.post("/admin/ai/test-scope", headers=admin, json={"scope": str(t1), "model": "form-model"}).json()
        assert r["ok"] and _Fake.seen[-1] == ("form-model", "Bearer sekret-2")
        # outside the Kingdom is refused on save
        assert c.put("/admin/ai/settings/global", headers=admin, json={"base_url": "https://api.example.com/v1"}).status_code == 422
        # removing the override falls back to the default
        assert c.delete(f"/admin/ai/settings/{t1}", headers=admin).status_code == 200
        assert c.get("/admin/ai", headers=h1).json()["source"] == "global"
        # a switched-off tenant cannot sign in
        c.patch(f"/admin/tenants/{t2}", headers=admin, json={"active": False})
        assert c.post("/auth/login", json={"staff_id": "t2admin", "password": "password1"}).status_code == 403
    finally:
        srv.shutdown()


def test_unreachable_model_reports_failure(c):
    admin = login(c, "admin")
    c.put("/admin/ai/settings/global", headers=admin, json={"base_url": "http://127.0.0.1:9/v1", "model": "x"})
    r = c.post("/admin/ai/test-scope", headers=admin, json={"scope": "global"}).json()
    assert r["ok"] is False and "unreachable" in r["error"]
