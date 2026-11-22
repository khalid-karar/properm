from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from .models import Base
from .routers import auth_users, projects, timesheets, admin


def create_app(database_url: str = "sqlite:///./properm.db") -> FastAPI:
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
    for r in (auth_users.router, projects.router, timesheets.router, admin.router):
        app.include_router(r)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


def app_from_env() -> FastAPI:
    import os
    return create_app(os.environ.get("DATABASE_URL", "sqlite:///./properm.db"))
