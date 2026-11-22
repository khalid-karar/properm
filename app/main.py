from pathlib import Path

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from .models import Base
from .routers import auth_users, projects, timesheets, admin, delivery, registers, reports, alerts, dashboards, governance, notifications, exports


def create_app(database_url: str = "sqlite:///./properm.db", serve_ui: bool = True) -> FastAPI:
    kwargs = {}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in database_url:
            kwargs["poolclass"] = StaticPool
    engine = create_engine(database_url, **kwargs)
    Base.metadata.create_all(engine)
    app = FastAPI(title="PROPERM Smart PMO", version="0.1.0")
    app.state.engine = engine
    app.state.Session = sessionmaker(engine, expire_on_commit=False)
    origins = [o.strip() for o in os.environ.get("PROPERM_CORS_ORIGINS", "").split(",") if o.strip()]
    if origins:   # only for a UI hosted on another origin (e.g. Netlify); tokens go in a header, not cookies
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["Authorization", "Content-Type"])
    for r in (auth_users.router, projects.router, projects.pending_router, governance.router, notifications.router, exports.router, timesheets.router, admin.router, delivery.router, registers.router, reports.router, alerts.router, dashboards.router):
        app.include_router(r)

    @app.middleware("http")
    async def dispatch_outbox(request, call_next):
        """After every successful write, turn new outbox events into notifications (best effort)."""
        response = await call_next(request)
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and response.status_code < 400:
            try:
                from .notify import dispatch
                with app.state.Session() as db:
                    dispatch(db)
            except Exception:
                pass
        return response

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
