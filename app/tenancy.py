"""Tenant isolation. Every table that mixes in models.Scoped carries tenant_id (NULL = the platform owner's own organisation).

 * Reads: while a request is scoped (a valid bearer token was presented), every ORM SELECT / UPDATE / DELETE on a Scoped
   table gets `tenant_id = <caller's tenant>` added automatically, including lazy loads and Session.get().
 * Writes: new rows are stamped with the caller's tenant before they are flushed. Outside a request (the scheduler, scripts)
   a row inherits the tenant of its project or user.
 * No token (sign-in page, health, public files) = unscoped. The sign-in query must see every user.
 * Raw Core statements (backup / restore) bypass this on purpose; they are restricted by hand in routers/adminops.py and ops.py.
"""
import contextvars

from sqlalchemy import event
from sqlalchemy.orm import Session, with_loader_criteria

from .models import Scoped

UNSCOPED = object()
scope: contextvars.ContextVar = contextvars.ContextVar("properm_scope", default=UNSCOPED)


def set_scope(tid):
    return scope.set(tid)


def reset_scope(token) -> None:
    scope.reset(token)


def _active(session) -> object:
    if session.info.get("unscoped"):
        return UNSCOPED
    if "scope" in session.info:          # set for one request by the API-key check (no bearer token to read the tenant from)
        return session.info["scope"]
    return scope.get()


@event.listens_for(Session, "do_orm_execute")
def _filter(state):
    if state.is_column_load:
        return
    sc = _active(state.session)
    if sc is UNSCOPED or not (state.is_select or state.is_update or state.is_delete):
        return
    if sc is None:
        state.statement = state.statement.options(with_loader_criteria(Scoped, lambda c: c.tenant_id.is_(None), include_aliases=True))
    else:
        state.statement = state.statement.options(with_loader_criteria(Scoped, lambda c: c.tenant_id == sc, include_aliases=True))


@event.listens_for(Session, "before_flush")
def _stamp(session, ctx, instances):
    sc = _active(session)
    for obj in session.new:
        if not isinstance(obj, Scoped) or obj.tenant_id is not None:
            continue
        if sc is not UNSCOPED:
            obj.tenant_id = sc
            continue
        # unscoped writer (scheduler, script): inherit from the parent project or user
        for attr, model in (("project_id", "Project"), ("user_id", "User"), ("activity_id", "Activity")):
            pid = getattr(obj, attr, None)
            if pid:
                from . import models
                parent = session.get(getattr(models, model), pid)
                if parent is not None and parent.tenant_id is not None:
                    obj.tenant_id = parent.tenant_id
                    break
