from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..audit import log
from ..config import DEFAULT_PARAMS, DEFAULT_SEVERITIES
from ..deps import get_db, get_params, get_severities, require_roles
from ..models import RuleConfig, Setting, User

router = APIRouter(prefix="/admin", tags=["admin / configuration"])


class SeverityIn(BaseModel):
    severity: str


class SettingIn(BaseModel):
    value: float


@router.get("/rules")
def rules(db=Depends(get_db), _: User = Depends(require_roles("ADMIN", "PMO"))):
    return {"severities": get_severities(db), "params": get_params(db)}


@router.put("/rules/{rule}")
def set_severity(rule: str, body: SeverityIn, db=Depends(get_db), admin: User = Depends(require_roles("ADMIN"))):
    if rule not in DEFAULT_SEVERITIES:
        raise HTTPException(404, "Unknown rule")
    if body.severity not in ("BLOCK", "WARN", "FLAG"):
        raise HTTPException(422, "severity must be BLOCK, WARN or FLAG")
    row = db.get(RuleConfig, rule)
    old = row.severity if row else DEFAULT_SEVERITIES[rule]
    if row:
        row.severity = body.severity
    else:
        db.add(RuleConfig(rule=rule, severity=body.severity))
    log(db, admin.id, "rule.severity_changed", "rule_config", None, {"rule": rule, "from": old, "to": body.severity})
    db.commit()
    return {"rule": rule, "severity": body.severity}


@router.put("/settings/{key}")
def set_setting(key: str, body: SettingIn, db=Depends(get_db), admin: User = Depends(require_roles("ADMIN"))):
    if key not in DEFAULT_PARAMS:
        raise HTTPException(404, "Unknown setting")
    row = db.get(Setting, key)
    if row:
        row.value = body.value
    else:
        db.add(Setting(key=key, value=body.value))
    log(db, admin.id, "setting.changed", "setting", None, {"key": key, "value": body.value})
    db.commit()
    return {"key": key, "value": body.value}
