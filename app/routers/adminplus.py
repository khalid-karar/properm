"""Administrator extras: bulk user import (CSV) and a read-only permission matrix."""
import csv
import io
import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..audit import log
from ..config import ROLES
from ..deps import get_db, hash_pw, require_roles
from ..models import User

router = APIRouter(tags=["admin extras"])

MATRIX = [  # capability -> roles that have it
    ("Log own time, see own to-do and projects", ["STAFF", "PM", "PMO", "ADMIN"]),
    ("Approve timesheets", ["PM", "PMO", "ADMIN"]),
    ("Create and manage own projects", ["PM", "PMO", "ADMIN"]),
    ("See every project", ["PMO", "ADMIN", "DECISION_MAKER", "PROGRAM_MANAGER"]),
    ("See cost, rates and EVM", ["PMO", "ADMIN", "DECISION_MAKER", "PROGRAM_MANAGER", "PM (own projects)"]),
    ("Executive dashboard and portfolio charts", ["PMO", "ADMIN", "DECISION_MAKER", "PROGRAM_MANAGER"]),
    ("Decide change requests", ["CCB members"]),
    ("Create programs and link any project", ["PMO", "ADMIN"]),
    ("Edit own programs, move projects in and out", ["PROGRAM_MANAGER"]),
    ("Audit trail and period lock", ["PMO", "ADMIN"]),
    ("Users, rate card, configurable lists, AI settings", ["ADMIN"]),
]


@router.get("/admin/permissions")
def permissions(_: User = Depends(require_roles("ADMIN", "PMO"))):
    return {"roles": list(ROLES), "matrix": [{"capability": c, "roles": r} for c, r in MATRIX]}


class ImportIn(BaseModel):
    csv_text: str = Field(min_length=1, max_length=500_000)


@router.post("/admin/users/import")
def import_users(body: ImportIn, db=Depends(get_db), admin: User = Depends(require_roles("ADMIN"))):
    """Columns: staff_id, full_name, role (required); job_title, department, email, capacity_hours_week, password (optional).
    A missing password is generated and returned once."""
    rows = list(csv.DictReader(io.StringIO(body.csv_text.lstrip("﻿"))))
    if not rows or not {"staff_id", "full_name", "role"} <= set(rows[0].keys()):
        raise HTTPException(422, "CSV needs the columns staff_id, full_name, role")
    created, errors = [], []
    seen = {r[0] for r in db.query(User.staff_id)}
    for n, r in enumerate(rows, start=2):
        sid, name, role = (r.get("staff_id") or "").strip(), (r.get("full_name") or "").strip(), (r.get("role") or "").strip().upper()
        if not sid or not name:
            errors.append({"line": n, "error": "staff_id and full_name are required"}); continue
        if role not in ROLES:
            errors.append({"line": n, "staff_id": sid, "error": f"role must be one of {', '.join(ROLES)}"}); continue
        if sid in seen:
            errors.append({"line": n, "staff_id": sid, "error": "staff_id already exists"}); continue
        pw = (r.get("password") or "").strip()
        generated = not pw
        if generated:
            pw = secrets.token_urlsafe(9) + str(secrets.randbelow(10))
        else:
            from ..acct import policy_error
            pe = policy_error(db, pw)
            if pe:
                errors.append({"line": n, "staff_id": sid, "error": pe}); continue
        try:
            cap = float(r.get("capacity_hours_week") or 40)
            if not 0 < cap <= 80:
                raise ValueError
        except ValueError:
            errors.append({"line": n, "staff_id": sid, "error": "capacity_hours_week must be 1-80"}); continue
        email = (r.get("email") or "").strip() or None
        if email and ("@" not in email or " " in email):
            errors.append({"line": n, "staff_id": sid, "error": "invalid e-mail"}); continue
        db.add(User(staff_id=sid, full_name=name, role=role, password_hash=hash_pw(pw), job_title=(r.get("job_title") or "").strip() or None,
                    department=(r.get("department") or "").strip() or None, email=email, capacity_hours_week=cap))
        db.flush()
        from ..acct import password_set
        password_set(db, db.query(User).filter_by(staff_id=sid).first(), by_admin=True)
        seen.add(sid)
        created.append({"staff_id": sid, "full_name": name, "role": role, **({"password": pw} if generated else {})})
    if created:
        log(db, admin.id, "user.bulk_imported", "user", None, {"count": len(created)})
    db.commit()
    return {"created": created, "errors": errors}
