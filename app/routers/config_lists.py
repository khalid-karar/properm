"""Configurable lists and AI administration."""
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func

from .. import ai
from ..audit import log
from ..deps import current_user, get_db, get_params, require_roles
from ..lists import DEFAULTS, LIST_KEYS, PROTECTED, active, effective
from ..models import AiDraft, AuditLog, ConfigItem, User

router = APIRouter(tags=["configuration"])
CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\- ]{0,39}$")


class ItemIn(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    active: bool = True
    data: dict | None = None


@router.get("/config/lists")
def lists(db=Depends(get_db), _: User = Depends(current_user)):
    return {k: [{"code": x["code"], "label": x["label"], "data": x["data"]} for x in active(db, k)] for k in LIST_KEYS}


@router.get("/admin/lists")
def admin_lists(db=Depends(get_db), _: User = Depends(require_roles("ADMIN", "PMO"))):
    return {k: effective(db, k) for k in LIST_KEYS}


def _data(key: str, d: dict | None) -> dict:
    d = d or {}
    if key == "kpi_template":
        return {"unit": str(d.get("unit") or "")[:30] or None, "higher_is_better": bool(d.get("higher_is_better", True))}
    return {}


@router.put("/admin/lists/{key}/{code}")
def put_item(key: str, code: str, body: ItemIn, db=Depends(get_db), admin: User = Depends(require_roles("ADMIN"))):
    if key not in LIST_KEYS:
        raise HTTPException(404, "Unknown list")
    if not CODE_RE.match(code):
        raise HTTPException(422, "Code must be 1-40 letters, digits, space, dash or underscore")
    if key in ("nonproject_code", "closure_item"):
        code = code.upper()
    if (key, code) in PROTECTED and not body.active:
        raise HTTPException(409, "This entry is required by the system and cannot be switched off")
    row = db.query(ConfigItem).filter_by(list_key=key, code=code).first()
    if row:
        row.label, row.active, row.data = body.label.strip(), body.active, _data(key, body.data)
    else:
        db.add(ConfigItem(list_key=key, code=code, label=body.label.strip(), active=body.active, data=_data(key, body.data)))
    log(db, admin.id, "config.list_item", "config_item", None, {"list": key, "code": code, "active": body.active})
    db.commit()
    return {"list": key, "code": code}


@router.delete("/admin/lists/{key}/{code}", status_code=204)
def delete_item(key: str, code: str, db=Depends(get_db), admin: User = Depends(require_roles("ADMIN"))):
    if key not in LIST_KEYS:
        raise HTTPException(404, "Unknown list")
    if any(c == code for c, _, _ in DEFAULTS[key]):
        raise HTTPException(409, "Built-in entries cannot be deleted; switch them off instead")
    row = db.query(ConfigItem).filter_by(list_key=key, code=code).first()
    if not row:
        raise HTTPException(404, "Entry not found")
    log(db, admin.id, "config.list_item_deleted", "config_item", row.id, {"list": key, "code": code})
    db.delete(row)
    db.commit()


# ---------------- AI administration ----------------
@router.get("/admin/ai")
def ai_admin(db=Depends(get_db), _: User = Depends(require_roles("ADMIN", "PMO"))):
    st = ai.status()
    params = get_params(db)
    since = datetime.now(timezone.utc) - timedelta(days=30)
    by = {}
    for kind, status, mode, n in db.query(AiDraft.kind, AiDraft.status, AiDraft.mode, func.count(AiDraft.id)).filter(AiDraft.created_at >= since).group_by(AiDraft.kind, AiDraft.status, AiDraft.mode):
        by.setdefault(kind, {"total": 0, "applied": 0, "rejected": 0, "draft": 0, "live": 0})
        by[kind]["total"] += n
        by[kind][status] = by[kind].get(status, 0) + n
        by[kind][mode] = by[kind].get(mode, 0) + n
    fails = [{"ts": r.ts.isoformat() if r.ts else None, "reason": (r.detail or {}).get("reason"), "task": (r.detail or {}).get("task")}
             for r in db.query(AuditLog).filter(AuditLog.action == "ai.failed").order_by(AuditLog.id.desc()).limit(10)]
    return {**st, "enabled": bool(params["ai_enabled"]), "hourly_limit": int(params["ai_hourly_limit"]), "allowed_host_suffixes": ai._allowed_suffixes(),
            "usage_30d": by, "recent_failures": fails}


@router.post("/admin/ai/test")
def ai_test(db=Depends(get_db), admin: User = Depends(require_roles("ADMIN"))):
    """One tiny call through the real client path, to check the model URL, key and in-Kingdom guard."""
    try:
        out = ai.run("alert", {"rule": "TEST", "cause": "Connection test from the administration screen", "lang": "en"})
    except ai.AiError as e:
        log(db, admin.id, "ai.test_failed", "ai", 0, {"reason": e.msg})
        db.commit()
        return {"ok": False, "error": e.msg, **ai.status()}
    log(db, admin.id, "ai.test_ok", "ai", 0, {"mode": ai.status()["mode"]})
    db.commit()
    return {"ok": True, "sample": out.get("text", "")[:200], **ai.status()}
