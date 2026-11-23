"""Pure-ASGI hardening (no threads, so it also runs in the browser build): security headers, per-address sign-in throttle, request size cap."""
import os
import time
from collections import defaultdict, deque

MAX_BODY = int(os.environ.get("PROPERM_MAX_BODY_BYTES", str(12 * 1024 * 1024)))
LOGIN_MAX, LOGIN_WINDOW = int(os.environ.get("PROPERM_LOGIN_MAX_PER_WINDOW", "40")), 300
HEADERS = [(b"x-content-type-options", b"nosniff"), (b"x-frame-options", b"DENY"), (b"referrer-policy", b"same-origin"),
           (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"), (b"cross-origin-opener-policy", b"same-origin")]


class Hardening:
    def __init__(self, app):
        self.app, self.hits = app, defaultdict(deque)

    async def _reply(self, send, code, text):
        body = ('{"detail":"%s"}' % text).encode()
        await send({"type": "http.response.start", "status": code, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())] + HEADERS})
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        hdr = dict(scope.get("headers") or [])
        try:
            if int(hdr.get(b"content-length", b"0")) > MAX_BODY:
                return await self._reply(send, 413, "Request too large")
        except ValueError:
            pass
        if scope["method"] == "POST" and scope["path"].endswith("/auth/login"):
            ip = (hdr.get(b"x-forwarded-for", b"").split(b",")[0].strip() or (scope.get("client") or ("local",))[0]) if True else "local"
            q, now = self.hits[ip], time.monotonic()
            while q and now - q[0] > LOGIN_WINDOW:
                q.popleft()
            if len(q) >= LOGIN_MAX:
                return await self._reply(send, 429, "Too many sign-in attempts from this address. Wait a few minutes.")
            q.append(now)
            if len(self.hits) > 5000:
                self.hits.clear()

        async def with_headers(message):
            if message["type"] == "http.response.start":
                have = {k.lower() for k, _ in message.get("headers", [])}
                message["headers"] = list(message.get("headers", [])) + [h for h in HEADERS if h[0] not in have]
                if scope.get("scheme") == "https" and b"strict-transport-security" not in have:
                    message["headers"].append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
            await send(message)
        await self.app(scope, receive, with_headers)
