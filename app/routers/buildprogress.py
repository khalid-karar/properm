"""Build progress (the milestones list). Private: sent only when the owner's password is given.
Set PROPERM_BUILD_PASSWORD on the server; when it is not set, the feature is off. The data lives in app/data/milestones.json (not served as a static file)."""
import hmac
import json
import os
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(tags=["build progress"])
_FILE = Path(__file__).resolve().parent.parent / "data" / "milestones.json"
_FAILS: dict[str, list[float]] = {}
MAX_FAILS, WINDOW = 5, 600


class BuildIn(BaseModel):
    password: str = Field(min_length=1, max_length=200)


@router.get("/build-progress/enabled")
def enabled():
    return {"enabled": bool(os.environ.get("PROPERM_BUILD_PASSWORD"))}


@router.post("/build-progress")
def build_progress(body: BuildIn, request: Request):
    secret = os.environ.get("PROPERM_BUILD_PASSWORD", "")
    if not secret:
        raise HTTPException(404, "Not available")
    who = request.client.host if request.client else "?"
    now = time.time()
    recent = [t for t in _FAILS.get(who, []) if now - t < WINDOW]
    if len(recent) >= MAX_FAILS:
        raise HTTPException(429, "Too many wrong passwords. Try again in a few minutes.")
    if not hmac.compare_digest(body.password.encode(), secret.encode()):
        _FAILS[who] = recent + [now]
        raise HTTPException(403, "Wrong password")
    _FAILS.pop(who, None)
    return json.loads(_FILE.read_text(encoding="utf-8"))
