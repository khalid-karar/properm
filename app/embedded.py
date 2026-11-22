"""In-browser runtime (Pyodide). Runs the same FastAPI app inside a Web Worker with an in-memory SQLite
database seeded with demo data. No threads and no network: requests are driven synchronously."""
import json as _json
import os
import secrets
from urllib.parse import urlsplit

_client = None


def _patch_anyio():
    """Pyodide has no threads: run 'threadpool' work inline."""
    import anyio.to_thread

    async def run_sync(func, *args, **kwargs):
        return func(*args)
    anyio.to_thread.run_sync = run_sync


def _drive(coro):
    """Run a coroutine to completion without an event loop (nothing here waits on real I/O)."""
    while True:
        try:
            coro.send(None)
        except StopIteration as stop:
            return stop.value


class Response:
    def __init__(self, status, body):
        self.status_code, self.content = status, body
        self.text = body.decode("utf-8")

    def json(self):
        return _json.loads(self.text)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"{self.status_code}: {self.text}")


class SyncClient:
    def __init__(self, app):
        self.app = app

    def request(self, method, url, headers=None, json=None, body=None):
        parts = urlsplit(url)
        data = _json.dumps(json).encode() if json is not None else (body or b"")
        hdrs = {"content-type": "application/json", **{k.lower(): v for k, v in (headers or {}).items()}}
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method.upper(),
                 "scheme": "http", "path": parts.path, "raw_path": parts.path.encode(), "root_path": "",
                 "query_string": parts.query.encode(), "server": ("demo", 80), "client": ("127.0.0.1", 0),
                 "headers": [(k.encode(), str(v).encode()) for k, v in hdrs.items()] + [(b"content-length", str(len(data)).encode())]}
        out = {"status": 500, "body": b""}
        sent = False

        async def receive():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": data, "more_body": False}
            return {"type": "http.disconnect"}

        async def send(msg):
            if msg["type"] == "http.response.start":
                out["status"] = msg["status"]
            elif msg["type"] == "http.response.body":
                out["body"] += msg.get("body", b"")

        _drive(self.app(scope, receive, send))
        return Response(out["status"], out["body"])

    def get(self, url, headers=None): return self.request("GET", url, headers)
    def post(self, url, headers=None, json=None): return self.request("POST", url, headers, json)
    def put(self, url, headers=None, json=None): return self.request("PUT", url, headers, json)
    def patch(self, url, headers=None, json=None): return self.request("PATCH", url, headers, json)
    def delete(self, url, headers=None): return self.request("DELETE", url, headers)


def boot():
    """Create the app and seed demo data. Called once when the worker starts."""
    global _client
    os.environ["PROPERM_SECRET"] = secrets.token_hex(32)     # fresh per page load: sessions end on reload
    os.environ["PROPERM_BCRYPT_ROUNDS"] = "4"                # fast hashing: demo data only
    os.environ["PROPERM_DEMO_LOGIN"] = "1"                   # one-click role buttons
    _patch_anyio()
    from . import demo
    from .main import create_app
    app = create_app("sqlite:///:memory:", serve_ui=False)
    pw = secrets.token_urlsafe(16)
    demo.seed(app, pw, SyncClient(app))
    _client = SyncClient(app)


def handle(method, path, headers_json, body):
    r = _client.request(method, path, _json.loads(headers_json or "{}"), body=(body or "").encode())
    return _json.dumps({"status": r.status_code, "body": r.text})
