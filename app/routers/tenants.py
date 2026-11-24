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
from ..models import AiSetting, AiUsage, Tenant, User

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


# ---------------- model usage and cost ----------------
RATE_SAR_PER_10K = 0.05850624      # Oracle "Large Cohere" (Command A), SAR per 10,000 characters (prompt + reply). Override: PROPERM_AI_RATE_SAR_PER_10K


def _rate() -> float:
    try:
        return float(os.environ.get("PROPERM_AI_RATE_SAR_PER_10K", RATE_SAR_PER_10K))
    except ValueError:
        return RATE_SAR_PER_10K


@router.get("/admin/ai/usage")
def ai_usage(days: int = 30, tenant_id: int | None = None, db=Depends(get_db), admin: User = Depends(require_roles("ADMIN"))):
    """Model calls and what they cost. The platform owner sees every tenant (and can look into one); a tenant administrator sees only their own tenant."""
    from datetime import datetime, timedelta, timezone
    days = max(1, min(int(days), 366))
    owner = admin.tenant_id is None
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    rate = _rate()
    cost = lambda chars: round(chars / 10000 * rate, 4)
    if owner:
        db.info["unscoped"] = True
    q = db.query(AiUsage.at, AiUsage.tenant_id, AiUsage.user_id, AiUsage.task, AiUsage.chars_in, AiUsage.chars_out, AiUsage.ok, AiUsage.ms).filter(AiUsage.at >= since)
    if owner and tenant_id is not None:
        q = q.filter(AiUsage.tenant_id == tenant_id)
    rows = q.limit(200000).all()
    names = {t.id: t.name for t in db.query(Tenant).all()} if owner else {}
    users = {u.id: u for u in db.query(User).all()}
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    def agg(items, key):
        out = {}
        for r in items:
            k = key(r)
            a = out.setdefault(k, {"calls": 0, "chars": 0, "failed": 0})
            a["calls"] += 1
            a["chars"] += (r.chars_in or 0) + (r.chars_out or 0)
            a["failed"] += 0 if r.ok else 1
        return out

    def view(d, name):
        return {**name, "calls": d["calls"], "failed": d["failed"], "chars": d["chars"], "cost": cost(d["chars"])}

    tot = agg(rows, lambda r: "all").get("all", {"calls": 0, "chars": 0, "failed": 0})
    mrows = [r for r in rows if r.at.replace(tzinfo=r.at.tzinfo or timezone.utc) >= month_start]
    mtot = agg(mrows, lambda r: "m").get("m", {"calls": 0, "chars": 0, "failed": 0})
    elapsed = max(1.0, (now - month_start).total_seconds() / 86400)
    dim = (month_start.replace(month=month_start.month % 12 + 1, year=month_start.year + (month_start.month == 12)) - month_start).days
    out = {"currency": "SAR", "rate_per_10k_chars": rate, "days": days, "owner": owner,
           "total": {"calls": tot["calls"], "failed": tot["failed"], "chars": tot["chars"], "cost": cost(tot["chars"]),
                     "avg_seconds": round(sum(r.ms or 0 for r in rows) / max(1, len(rows)) / 1000, 1)},
           "month": {"calls": mtot["calls"], "chars": mtot["chars"], "cost": cost(mtot["chars"]), "forecast": cost(mtot["chars"] / elapsed * dim)},
           "by_task": sorted((view(d, {"task": k}) for k, d in agg(rows, lambda r: r.task).items()), key=lambda x: -x["chars"]),
           "by_user": sorted((view(d, {"user_id": k, "name": users[k].full_name if k in users else "(system)", "staff_id": users[k].staff_id if k in users else "",
                                       "tenant": names.get(users[k].tenant_id, "Owner organisation") if (owner and k in users) else None})
                             for k, d in agg(rows, lambda r: r.user_id).items()), key=lambda x: -x["chars"])[:50],
           "by_day": [{"day": k, "calls": d["calls"], "cost": cost(d["chars"])} for k, d in sorted(agg(rows, lambda r: r.at.strftime("%Y-%m-%d")).items())]}
    if owner:
        out["by_tenant"] = sorted((view(d, {"tenant_id": k, "name": names.get(k, "Owner organisation")}) for k, d in agg(rows, lambda r: r.tenant_id).items()), key=lambda x: -x["chars"])
    return out
