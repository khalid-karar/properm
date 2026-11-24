from pathlib import Path

import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from .models import Base
from .routers import auth_users, projects, timesheets, admin, delivery, registers, reports, alerts, dashboards, governance, notifications, exports, ai as ai_router, intake, plan, oversight, insights, workflow, periodic, config_lists, selfservice, adminplus, gates, control, weekly, portfolio, programs2, security, pmtools, insight2, adminops, scope, agile, strategy, procurement, skills, depth, ops, jobs, imports, sso, tender, brief as brief_router


class OutboxDispatch:
    """Pure ASGI middleware (no threads or task groups, so it also runs in the browser build): after a successful
    write request, turn new outbox events into notifications. Best effort; never affects the response."""

    def __init__(self, app, session_factory):
        self.app, self.sessions = app, session_factory

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in ("POST", "PUT", "PATCH", "DELETE"):
            return await self.app(scope, receive, send)
        status = {}

        async def watch(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        await self.app(scope, receive, watch)
        if status.get("code", 500) < 400:
            try:
                from .notify import dispatch
                with self.sessions() as db:
                    dispatch(db)
            except Exception:
                pass


@asynccontextmanager
async def _lifespan(app):
    task = None
    if os.environ.get("PROPERM_SCHEDULER") == "1" and sys.platform != "emscripten":
        async def loop():
            from . import scheduler
            while True:
                try:
                    def once():
                        with app.state.Session() as db:
                            scheduler.run_due(db)
                    await asyncio.to_thread(once)
                except Exception:
                    pass
                await asyncio.sleep(int(os.environ.get("PROPERM_SCHEDULER_MINUTES", "15")) * 60)
        task = asyncio.create_task(loop())
    yield
    if task:
        task.cancel()


def _dump_json(obj):
    from decimal import Decimal

    def default(o):
        if isinstance(o, Decimal):
            return int(o) if o == o.to_integral_value() else float(o)
        raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")
    return json.dumps(obj, default=default)


def create_app(database_url: str = "sqlite:///./properm.db", serve_ui: bool = True) -> FastAPI:
    kwargs = {}
    test_db = os.environ.get("PROPERM_TEST_DATABASE_URL", "")
    redirect = bool(test_db) and ":memory:" in database_url and "PYTEST_CURRENT_TEST" in os.environ
    if redirect:   # run the test-suite against another database (scripts/test_oracle.sh); the schema is rebuilt for every test
        database_url = test_db
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in database_url:
            kwargs["poolclass"] = StaticPool
    kwargs["json_serializer"] = _dump_json
    kwargs["json_deserializer"] = json.loads   # Oracle hands JSON numbers back as Decimal unless told otherwise
    engine = create_engine(database_url, **kwargs)
    if redirect:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    app = FastAPI(title="PROPERM Smart PMO", version="0.1.0", lifespan=_lifespan)
    app.state.engine = engine
    app.state.Session = sessionmaker(engine, expire_on_commit=False)
    origins = [o.strip() for o in os.environ.get("PROPERM_CORS_ORIGINS", "").split(",") if o.strip()]
    if origins:   # only for a UI hosted on another origin (e.g. Netlify); tokens go in a header, not cookies
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["Authorization", "Content-Type"])
    for r in (auth_users.router, projects.router, projects.pending_router, governance.router, notifications.router, exports.router, ai_router.router, intake.router, plan.router, oversight.router, insights.router, workflow.router, periodic.router, config_lists.router, selfservice.router, adminplus.router, gates.router, control.router, weekly.router, portfolio.router, programs2.router, security.router, pmtools.router, insight2.router, adminops.router, scope.router, agile.router, strategy.router, procurement.router, skills.router, depth.router, ops.router, jobs.router, imports.router, sso.router, brief_router.router, tender.router, timesheets.router, admin.router, delivery.router, registers.router, reports.router, alerts.router, dashboards.router):
        app.include_router(r)

    app.add_middleware(OutboxDispatch, session_factory=app.state.Session)
    from .hardening import Hardening
    app.add_middleware(Hardening)

    if serve_ui:
        app.mount("/ui", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="ui")

        @app.get("/", include_in_schema=False)
        def root():
            return RedirectResponse("/ui/")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


def app_from_env() -> FastAPI:
    import os
    return create_app(os.environ.get("DATABASE_URL", "sqlite:///./properm.db"))
