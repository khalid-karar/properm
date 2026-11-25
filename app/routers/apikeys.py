"""API keys for the read-only data feeds (/api/v1). Administrators create and revoke them; the key is shown once."""
import hashlib
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..audit import log
from ..deps import get_db, require_roles
from ..models import ApiKey, User

router = APIRouter(prefix="/admin/api-keys", tags=["api keys"])


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _view(k: ApiKey) -> dict:
    return {"id": k.id, "name": k.name, "prefix": k.prefix, "active": k.active, "created_at": k.created_at, "last_used_at": k.last_used_at, "revoked_at": k.revoked_at}


class KeyIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)


@router.get("")
def list_keys(db=Depends(get_db), admin: User = Depends(require_roles("ADMIN"))):
    return [_view(k) for k in db.query(ApiKey).order_by(ApiKey.id.desc()).all()]


@router.post("", status_code=201)
def create_key(body: KeyIn, db=Depends(get_db), admin: User = Depends(require_roles("ADMIN"))):
    key = "prm_" + secrets.token_urlsafe(32)
    k = ApiKey(name=body.name.strip(), prefix=key[:8], key_hash=hash_key(key), created_by=admin.id)
    db.add(k)
    db.flush()
    log(db, admin.id, "apikey.create", "api_key", k.id, {"name": k.name})
    db.commit()
    return {**_view(k), "key": key, "note": "Copy the key now. It is not shown again."}


@router.delete("/{kid}")
def revoke_key(kid: int, db=Depends(get_db), admin: User = Depends(require_roles("ADMIN"))):
    k = db.get(ApiKey, kid)
    if k is None:
        raise HTTPException(404, "Not found")
    k.active, k.revoked_at = False, datetime.now(timezone.utc)
    log(db, admin.id, "apikey.revoke", "api_key", k.id, {"name": k.name})
    db.commit()
    return _view(k)
