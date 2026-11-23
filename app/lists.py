"""Administrator-maintained lists. Built-in entries can be relabelled or switched off (except protected ones); extra entries can be added."""
from .config import NON_PROJECT_CODES
from .models import ConfigItem

DEFAULTS = {
    "nonproject_code": [(k, v, {}) for k, v in NON_PROJECT_CODES.items()],
    "risk_category": [(c, c, {}) for c in ("Technical", "Schedule", "Cost", "Resource", "External", "Scope", "Quality")],
    "kpi_template": [("ON_TIME", "On-time delivery", {"unit": "%", "higher_is_better": True}), ("DEFECTS", "Defect rate", {"unit": "%", "higher_is_better": False}),
                     ("CSAT", "Customer satisfaction", {"unit": "/5", "higher_is_better": True})],
    "closure_item": [],
    "department": [],
}
PROTECTED = {("nonproject_code", "LEAVE")}          # leave logic (R10 / capacity) depends on this code
LIST_KEYS = tuple(DEFAULTS)


def effective(db, key: str) -> list[dict]:
    rows = {r.code: r for r in db.query(ConfigItem).filter_by(list_key=key)}
    out, seen = [], set()
    for code, label, data in DEFAULTS[key]:
        r = rows.get(code)
        out.append({"code": code, "label": r.label if r else label, "active": (r.active if r else True) or (key, code) in PROTECTED, "default": True,
                    "data": (r.data if r and r.data else data), "protected": (key, code) in PROTECTED})
        seen.add(code)
    for code, r in sorted(rows.items()):
        if code not in seen:
            out.append({"code": code, "label": r.label, "active": r.active, "default": False, "data": r.data or {}, "protected": False})
    return out


def active(db, key: str) -> list[dict]:
    return [x for x in effective(db, key) if x["active"]]


def active_codes(db) -> dict:
    return {x["code"]: x["label"] for x in active(db, "nonproject_code")}


def check_department(db, value) -> None:
    """When the administrator keeps a department list, a user's department must come from it."""
    if not value:
        return
    labels = {x["label"] for x in active(db, "department")}
    if labels and value not in labels:
        from fastapi import HTTPException
        raise HTTPException(422, f"Department must be one of: {', '.join(sorted(labels))}")
