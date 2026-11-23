"""Small factory for project-scoped registers (list, create, edit, delete) with the usual access rules and audit trail."""
from datetime import date, datetime

from fastapi import Depends, HTTPException
from pydantic import Field, create_model

from .audit import log
from .deps import current_user, get_db
from .models import User
from .routers.projects import can_manage, can_view, get_project, need_manage


def ser(row, cols=None) -> dict:
    out = {}
    for c in row.__table__.columns:
        v = getattr(row, c.name)
        out[c.name] = v.isoformat() if isinstance(v, (date, datetime)) else v
    return out


def project_register(router, slug, Model, fields, *, choices=None, required=(), validate=None, enrich=None, order=None,
                     writer=None, defaults=None, reader=None, on_delete=None):
    """fields: {name: python type}. choices: {name: tuple of allowed values}. validate(db, project, data, row|None) may raise.
    enrich(db, project, rows, dicts) may add computed keys. writer(db, user, project) -> bool overrides the manager rule."""
    choices = choices or {}
    kw_in = {k: ((tp if k in required else tp | None), ... if k in required else (defaults or {}).get(k)) for k, tp in fields.items()}
    In = create_model(f"{Model.__name__}In", **kw_in)
    Patch = create_model(f"{Model.__name__}Patch", **{k: (tp | None, None) for k, tp in fields.items()})

    def check(data):
        for k, allowed in choices.items():
            if data.get(k) is not None and data[k] not in allowed:
                raise HTTPException(422, f"{k} must be one of: {', '.join(allowed)}")

    def can_write(db, user, p):
        if writer:
            if not writer(db, user, p):
                raise HTTPException(403, "Not allowed")
        else:
            need_manage(db, user, p)

    def view(db, user, pid):
        p = get_project(db, pid)
        if not (reader(db, user, p) if reader else can_view(db, user, p)):
            raise HTTPException(403, "No access to this project")
        return p

    def one(db, p, rid):
        r = db.get(Model, rid)
        if not r or r.project_id != p.id:
            raise HTTPException(404, "Not found")
        return r

    def out(db, p, rows):
        ds = [ser(r) for r in rows]
        if enrich:
            enrich(db, p, rows, ds)
        return ds

    @router.get(f"/projects/{{pid}}/{slug}", name=f"list_{slug}")
    def list_(pid: int, db=Depends(get_db), user: User = Depends(current_user)):
        p = view(db, user, pid)
        q = db.query(Model).filter_by(project_id=pid)
        q = q.order_by(*(order or [Model.id]))
        return out(db, p, q.all())

    @router.post(f"/projects/{{pid}}/{slug}", status_code=201, name=f"create_{slug}")
    def create_(pid: int, body: In, db=Depends(get_db), user: User = Depends(current_user)):
        p = view(db, user, pid)
        can_write(db, user, p)
        data = body.model_dump()
        check(data)
        if validate:
            validate(db, p, data, None)
        r = Model(project_id=pid, **data)
        db.add(r)
        db.flush()
        log(db, user.id, f"{slug}.created", Model.__tablename__, r.id, {"project": pid})
        db.commit()
        return out(db, p, [r])[0]

    @router.patch(f"/projects/{{pid}}/{slug}/{{rid}}", name=f"patch_{slug}")
    def patch_(pid: int, rid: int, body: Patch, db=Depends(get_db), user: User = Depends(current_user)):
        p = view(db, user, pid)
        can_write(db, user, p)
        r = one(db, p, rid)
        data = body.model_dump(exclude_unset=True)
        check(data)
        for k in required:
            if k in data and data[k] in (None, ""):
                raise HTTPException(422, f"{k} is required")
        if validate:
            validate(db, p, data, r)
        for k, v in data.items():
            setattr(r, k, v)
        log(db, user.id, f"{slug}.updated", Model.__tablename__, rid, {"fields": sorted(data)})
        db.commit()
        return out(db, p, [r])[0]

    @router.delete(f"/projects/{{pid}}/{slug}/{{rid}}", status_code=204, name=f"delete_{slug}")
    def delete_(pid: int, rid: int, db=Depends(get_db), user: User = Depends(current_user)):
        p = view(db, user, pid)
        can_write(db, user, p)
        r = one(db, p, rid)
        if on_delete:
            on_delete(db, p, r)
        db.delete(r)
        log(db, user.id, f"{slug}.deleted", Model.__tablename__, rid, {"project": pid})
        db.commit()

    return {"one": one, "view": view, "out": out, "check": check}
