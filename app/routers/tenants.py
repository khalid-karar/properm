"""Tenants and AI model settings.
Platform owner = an ADMIN with no tenant: manages tenants, the default model for ALL tenants, and any tenant's override.
A tenant's own ADMIN can set and test only their tenant's override. Keys are stored encrypted and are never returned."""
import os
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import ai
from ..audit import log
from ..deps import get_db, require_roles
from ..models import AiSetting, Tenant, User

router = APIRouter(tags=["tenants"])


def _scope_of(raw: str, admin: User) -> tuple[str, int | None]:
    """Returns (scope key, tenant id) after checking this admin may manage it. 'mine' = the admin's own tenant."""
    if raw == "mine":
        raw = str(admin.tenant_id) if admin.tenant_id else "global"
    if raw == "global":
        if admin.tenant_id:
            raise HTTPException(403, "Only the platform owner can change the default model for all tenants")
        return "global", None
    if not raw.isdigit():
        raise HTTPException(404, "Unknown scope")
    tid = int(raw)
    if admin.tenant_id and admin.tenant_id != tid:
        raise HTTPException(403, "You can only manage your own tenant")
    return f"tenant:{tid}", tid


def _view(row: AiSetting | None) -> dict | None:
    if not row:
        return None
    return {"base_url": row.base_url, "model": row.model, "enabled": bool(row.enabled), "has_key": bool(row.api_key_enc),
            "updated_at": row.updated_at.isoformat() if row.updated_at else None}


@router.get("/admin/ai/settings")
def settings(db=Depends(get_db), admin: User = Depends(require_roles("ADMIN"))):
    owner = admin.tenant_id is None
    db.info["unscoped"] = True          # user counts per tenant: this screen reads across tenants (read-only)
    rows = {r.scope: r for r in db.query(AiSetting).all()}
    out = {"platform_owner": owner, "my_tenant_id": admin.tenant_id, "global": _view(rows.get("global")) if owner else None,
           "env_default": bool(os.environ.get("PROPERM_AI_BASE_URL", "").strip())}
    q = db.query(Tenant).order_by(Tenant.name)
    if not owner:
        q = q.filter(Tenant.id == admin.tenant_id)
    out["tenants"] = [{"id": t.id, "name": t.name, "slug": t.slug, "active": bool(t.active),
                       "users": db.query(User).filter(User.tenant_id == t.id).count(), "override": _view(rows.get(f"tenant:{t.id}"))} for t in q]
    return out


class SettingIn(BaseModel):
    base_url: str = Field(min_length=8, max_length=300)
    model: str = Field(default="qwen", min_length=1, max_length=100)
    api_key: str | None = Field(default=None, max_length=500)    # None or blank = keep the saved key
    enabled: bool = True


def _check_url(url: str) -> str:
    url = url.strip().rstrip("/")
    if not re.match(r"^https?://[^\s/]+", url):
        raise HTTPException(422, "The model address must start with https:// (or http:// for a private network)")
    if not ai.host_in_kingdom(url) and not ai.offsite_demo_allowed():
        raise HTTPException(422, "This host is not inside the Kingdom. Use a .sa address or a private-network address "
                                 "(allowed suffixes are set by PROPERM_AI_ALLOWED_HOSTS).")
    return url


@router.put("/admin/ai/settings/{scope}")
def save_setting(scope: str, body: SettingIn, db=Depends(get_db), admin: User = Depends(require_roles("ADMIN"))):
    key, tid = _scope_of(scope, admin)
    if tid and not db.get(Tenant, tid):
        raise HTTPException(404, "Tenant not found")
    url = _check_url(body.base_url)
    row = db.query(AiSetting).filter(AiSetting.scope == key).first()
    if not row:
        row = AiSetting(scope=key, tenant_id=tid, base_url=url)
        db.add(row)
    row.base_url, row.model, row.enabled, row.updated_by = url, body.model.strip(), body.enabled, admin.id
    if body.api_key and body.api_key.strip():
        row.api_key_enc = ai.encrypt_key(body.api_key.strip())
    from ..models import now
    row.updated_at = now()
    log(db, admin.id, "ai.settings_saved", "ai", tid or 0, {"scope": key, "host": url, "model": row.model, "key_changed": bool(body.api_key)})
    db.commit()
    return {"ok": True, **(_view(row) or {})}


@router.delete("/admin/ai/settings/{scope}")
def delete_setting(scope: str, db=Depends(get_db), admin: User = Depends(require_roles("ADMIN"))):
    key, tid = _scope_of(scope, admin)
    row = db.query(AiSetting).filter(AiSetting.scope == key).first()
    if row:
        db.delete(row)
        log(db, admin.id, "ai.settings_removed", "ai", tid or 0, {"scope": key})
        db.commit()
    return {"ok": True}


class TestIn(BaseModel):
    scope: str = "effective"          # effective | global | <tenant id> | mine
    base_url: str | None = None       # unsaved form values, so the test works before saving
    model: str | None = None
    api_key: str | None = None


@router.post("/admin/ai/test-scope")
def test_scope(body: TestIn, db=Depends(get_db), admin: User = Depends(require_roles("ADMIN"))):
    if body.scope == "effective":
        cfg = ai.resolve(admin.tenant_id)
        label = "effective"
    else:
        key, tid = _scope_of(body.scope, admin)
        saved = ai.resolve(tid, "global" if key == "global" else "tenant")
        cfg = dict(saved)
        label = key
        if body.base_url:
            cfg["url"] = _check_url(body.base_url)
            cfg["source"] = "form"
        if body.model:
            cfg["model"] = body.model.strip()
        if body.api_key and body.api_key.strip():
            cfg["key"] = body.api_key.strip()
        if not cfg["url"]:
            return {"ok": False, "error": "No model address is set for this scope yet.", **ai.status(cfg)}
    try:
        out = ai.run("alert", {"rule": "TEST", "cause": "Connection test from the administration screen", "lang": "en"}, cfg)
    except ai.AiError as e:
        log(db, admin.id, "ai.test_failed", "ai", 0, {"reason": e.msg, "scope": label})
        db.commit()
        return {"ok": False, "error": e.msg, **ai.status(cfg)}
    log(db, admin.id, "ai.test_ok", "ai", 0, {"mode": ai.status(cfg)["mode"], "scope": label})
    db.commit()
    return {"ok": True, "sample": out.get("text", "")[:200], **ai.status(cfg)}


# ---------------- tenants ----------------
class TenantIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    slug: str = Field(min_length=2, max_length=40, pattern=r"^[a-z0-9][a-z0-9-]*$")


def _owner(admin: User = Depends(require_roles("ADMIN"))) -> User:
    if admin.tenant_id:
        raise HTTPException(403, "Only the platform owner can manage tenants")
    return admin


@router.post("/admin/tenants")
def create_tenant(body: TenantIn, db=Depends(get_db), admin: User = Depends(_owner)):
    if db.query(Tenant).filter((Tenant.slug == body.slug) | (Tenant.name == body.name)).first():
        raise HTTPException(409, "A tenant with this name or short code already exists")
    t = Tenant(name=body.name.strip(), slug=body.slug)
    db.add(t)
    db.flush()
    log(db, admin.id, "tenant.created", "tenant", t.id, {"slug": t.slug})
    db.commit()
    return {"id": t.id, "name": t.name, "slug": t.slug, "active": True}


class TenantPatch(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=120)
    active: bool | None = None


@router.patch("/admin/tenants/{tid}")
def patch_tenant(tid: int, body: TenantPatch, db=Depends(get_db), admin: User = Depends(_owner)):
    t = db.get(Tenant, tid)
    if not t:
        raise HTTPException(404, "Tenant not found")
    if body.name:
        t.name = body.name.strip()
    if body.active is not None:
        t.active = body.active
    log(db, admin.id, "tenant.updated", "tenant", t.id, body.model_dump(exclude_none=True))
    db.commit()
    return {"id": t.id, "name": t.name, "slug": t.slug, "active": bool(t.active)}


class TenantAdminIn(BaseModel):
    staff_id: str = Field(min_length=1, max_length=40)
    full_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=128)


@router.post("/admin/tenants/{tid}/admins", status_code=201)
def create_tenant_admin(tid: int, body: TenantAdminIn, db=Depends(get_db), owner: User = Depends(_owner)):
    """Creates the first (or another) administrator inside a tenant. That person then manages their own users."""
    from .. import tenancy
    from .auth_users import UserIn, create_user
    if not db.get(Tenant, tid):
        raise HTTPException(404, "Tenant not found")
    db.info["unscoped"] = True
    if db.query(User).filter_by(staff_id=body.staff_id).first():
        raise HTTPException(409, "staff_id already exists (staff IDs are unique across the whole system)")
    db.info.pop("unscoped", None)
    tok = tenancy.set_scope(tid)                       # everything created below belongs to the tenant
    try:
        out = create_user(UserIn(staff_id=body.staff_id, full_name=body.full_name, password=body.password, role="ADMIN"), db, owner)
    finally:
        tenancy.reset_scope(tok)
    return out
