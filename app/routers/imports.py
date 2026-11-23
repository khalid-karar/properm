"""Bulk import from Excel / CSV (and MS Project XML for plans). Every import has a preview: send commit=false to see what would happen row by row,
then commit=true. Nothing is saved unless every row is fine, or skip_errors is set (then only the good rows are saved)."""
import base64
import binascii
import secrets
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import tabular
from ..audit import log
from ..config import ROLES
from ..deps import get_db, hash_pw, require_roles
from ..models import Activity, PeriodLock, Project, TimesheetEntry, User
from .projects import MANAGE, get_project, need_manage

router = APIRouter(tags=["imports"])
MAX_FILE = 10 * 1024 * 1024


class ImportIn(BaseModel):
    filename: str = Field(max_length=200)
    content_b64: str
    commit: bool = False
    skip_errors: bool = False


def _load(body: ImportIn, required: set[str]):
    try:
        data = base64.b64decode(body.content_b64, validate=False)
    except (binascii.Error, ValueError):
        raise HTTPException(422, "The file could not be read")
    if len(data) > MAX_FILE:
        raise HTTPException(413, "The file is larger than 10 MB. Split it and import in parts.")
    try:
        head, rows = tabular.read_any(body.filename, data)
    except tabular.TableError as e:
        raise HTTPException(422, str(e))
    miss = required - set(head)
    if miss:
        raise HTTPException(422, f"Missing columns: {', '.join(sorted(miss))}. Found: {', '.join(h for h in head if h)}")
    idx = {h: i for i, h in enumerate(head) if h}
    return [{h: (r[i] if i < len(r) else None) for h, i in idx.items()} for r in rows]


def _s(v) -> str:
    return "" if v is None else str(v).strip()


def _verdict(rows_out, body, save):
    bad = [r for r in rows_out if r["status"] == "error"]
    ok = [r for r in rows_out if r["status"] == "ok"]
    dup = [r for r in rows_out if r["status"] == "duplicate"]
    saved = 0
    if body.commit and ok and (not bad or body.skip_errors):
        saved = save([r["_obj"] for r in ok])
    elif body.commit and bad:
        pass
    for r in rows_out:
        r.pop("_obj", None)
    return {"committed": saved > 0, "saved": saved, "ok": len(ok), "errors": len(bad), "duplicates": len(dup), "rows": rows_out[:500],
            "blocked": bool(body.commit and bad and not body.skip_errors)}


# ---------------- staff ----------------
@router.post("/import/staff")
def import_staff(body: ImportIn, db=Depends(get_db), admin: User = Depends(require_roles("ADMIN"))):
    """Columns: staff_id, full_name, role (required); job_title, department, email, capacity_hours_week, password (optional, generated when empty)."""
    from ..acct import password_set, policy_error
    from ..lists import check_department
    rows = _load(body, {"staff_id", "full_name", "role"})
    seen = {r[0] for r in db.query(User.staff_id)}
    out, generated = [], {}
    for n, r in enumerate(rows, start=2):
        sid, name, role = _s(r["staff_id"]), _s(r["full_name"]), _s(r["role"]).upper()
        e = None
        if not sid or not name:
            e = "staff_id and full_name are required"
        elif role not in ROLES:
            e = f"role must be one of {', '.join(ROLES)}"
        elif sid in seen:
            e = "staff_id already exists"
        pw = _s(r.get("password"))
        cap = 40.0
        if not e:
            try:
                cap = tabular.to_float(r.get("capacity_hours_week") or 40)
                if not 0 < cap <= 80:
                    raise ValueError
            except ValueError:
                e = "capacity_hours_week must be 1-80"
        if not e and pw:
            e = policy_error(db, pw)
        if not e:
            try:
                check_department(db, _s(r.get("department")) or None)
            except HTTPException as ex:
                e = str(ex.detail)
        email = _s(r.get("email")) or None
        if not e and email and ("@" not in email or " " in email):
            e = "invalid e-mail"
        if e:
            out.append({"line": n, "key": sid, "status": "error", "message": e})
            continue
        seen.add(sid)
        gen = not pw
        pw = pw or secrets.token_urlsafe(9) + str(secrets.randbelow(10))
        obj = dict(staff_id=sid, full_name=name, role=role, pw=pw, gen=gen, job_title=_s(r.get("job_title")) or None, department=_s(r.get("department")) or None, email=email, cap=cap)
        out.append({"line": n, "key": sid, "status": "ok", "message": f"{name} ({role})", "_obj": obj})

    def save(objs):
        for o in objs:
            u = User(staff_id=o["staff_id"], full_name=o["full_name"], role=o["role"], password_hash=hash_pw(o["pw"]), job_title=o["job_title"], department=o["department"], email=o["email"], capacity_hours_week=o["cap"])
            db.add(u)
            db.flush()
            password_set(db, u, by_admin=True)
            if o["gen"]:
                generated[o["staff_id"]] = o["pw"]
        log(db, admin.id, "import.staff", "user", None, {"count": len(objs)})
        db.commit()
        return len(objs)
    res = _verdict(out, body, save)
    res["generated_passwords"] = generated          # shown once; the user must change it at first sign-in
    return res


# ---------------- timesheets ----------------
@router.post("/import/timesheets")
def import_timesheets(body: ImportIn, db=Depends(get_db), user: User = Depends(require_roles("ADMIN", "PMO"))):
    """Historic or bulk hours. Columns: staff_id, date, hours, and either project (number) [+ activity (code)] or nonproject_code; description, status optional (default approved).
    Exact duplicates are skipped. Rows inside a locked period are rejected. These rows are loaded as given and do not go through the daily rules."""
    rows = _load(body, {"staff_id", "date", "hours"})
    users = {u.staff_id: u.id for u in db.query(User.id, User.staff_id)}
    projects = {p.number: p.id for p in db.query(Project.id, Project.number)}
    acts = {(a.project_id, a.code): a.id for a in db.query(Activity.id, Activity.project_id, Activity.code)}
    from sqlalchemy import func
    lock = db.query(func.max(PeriodLock.locked_through)).scalar()
    existing = {(e.user_id, e.project_id, e.activity_id, e.nonproject_code, e.entry_date, round(e.hours, 2)) for e in db.query(TimesheetEntry.user_id, TimesheetEntry.project_id, TimesheetEntry.activity_id, TimesheetEntry.nonproject_code, TimesheetEntry.entry_date, TimesheetEntry.hours)}
    out, seen_here = [], set()
    for n, r in enumerate(rows, start=2):
        e, uid, pid, aid, npc = None, users.get(_s(r["staff_id"])), None, None, _s(r.get("nonproject_code")) or None
        try:
            d = tabular.to_date(r["date"])
        except ValueError as ex:
            d, e = None, str(ex)
        try:
            h = round(tabular.to_float(r["hours"]), 2)
            if not e and not 0 < h <= 24:
                e = "hours must be above 0 and at most 24"
        except (ValueError, TypeError):
            h, e = 0, "hours must be a number"
        if not e and uid is None:
            e = f"unknown staff_id '{_s(r['staff_id'])}'"
        pnum = _s(r.get("project"))
        if not e:
            if pnum:
                pid = projects.get(pnum)
                if pid is None:
                    e = f"unknown project '{pnum}'"
                elif _s(r.get("activity")):
                    aid = acts.get((pid, _s(r["activity"])))
                    if aid is None:
                        e = f"project {pnum} has no activity '{_s(r['activity'])}'"
            elif not npc:
                e = "give a project or a nonproject_code"
        if not e and lock and d <= lock:
            e = f"the period up to {lock} is locked"
        status = (_s(r.get("status")) or "approved").lower()
        if not e and status not in ("submitted", "approved"):
            e = "status must be submitted or approved"
        if e:
            out.append({"line": n, "key": _s(r["staff_id"]), "status": "error", "message": e})
            continue
        key = (uid, pid, aid, None if pid else npc, d, h)
        if key in existing or key in seen_here:
            out.append({"line": n, "key": _s(r["staff_id"]), "status": "duplicate", "message": "already exists, skipped"})
            continue
        seen_here.add(key)
        out.append({"line": n, "key": _s(r["staff_id"]), "status": "ok", "message": f"{d} · {h} h", "_obj": (uid, pid, aid, None if pid else npc, d, h, _s(r.get("description")) or None, status)})

    def save(objs):
        now = datetime.now(timezone.utc)
        for i in range(0, len(objs), 2000):
            db.bulk_save_objects([TimesheetEntry(user_id=o[0], project_id=o[1], activity_id=o[2], nonproject_code=o[3], entry_date=o[4], hours=o[5], description=o[6], status=o[7],
                                                 approved_by=user.id if o[7] == "approved" else None, approved_at=now if o[7] == "approved" else None, flags=["imported"]) for o in objs[i:i + 2000]])
        log(db, user.id, "import.timesheets", "timesheet", None, {"count": len(objs), "file": body.filename[:100]})
        db.commit()
        return len(objs)
    return _verdict(out, body, save)


# ---------------- plan ----------------
@router.post("/projects/{pid}/import/plan")
def import_plan(pid: int, body: ImportIn, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    """Tasks from Excel/CSV (columns code, name, planned_hours; planned_start, planned_end optional) or an MS Project XML export. Project must be in planning."""
    p = get_project(db, pid)
    need_manage(db, user, p)
    if p.state != "planning":
        raise HTTPException(409, "Plans can be imported while the project is in planning")
    rows = _load(body, {"code", "name", "planned_hours"})
    have = {a.code for a in db.query(Activity).filter_by(project_id=pid)}
    out = []
    for n, r in enumerate(rows, start=2):
        code, name, e = _s(r["code"])[:40], _s(r["name"])[:300], None
        try:
            hrs = tabular.to_float(r["planned_hours"])
        except (ValueError, TypeError):
            hrs, e = 0, "planned_hours must be a number"
        s_ = f_ = None
        if not e:
            try:
                s_ = tabular.to_date(r["planned_start"]) if _s(r.get("planned_start")) else None
                f_ = tabular.to_date(r["planned_end"]) if _s(r.get("planned_end")) else None
            except ValueError as ex:
                e = str(ex)
        if not e and (not code or not name):
            e = "code and name are required"
        elif not e and hrs <= 0:
            e = "planned_hours must be above 0"
        elif not e and code in have:
            e = "code already exists in this project"
        elif not e and (s_ is None) != (f_ is None):
            e = "give both start and end, or neither"
        elif not e and s_ and f_ < s_:
            e = "end is before start"
        if e:
            out.append({"line": n, "key": code, "status": "error", "message": e})
            continue
        have.add(code)
        out.append({"line": n, "key": code, "status": "ok", "message": f"{name} · {hrs:g} h", "_obj": (code, name, hrs, s_, f_)})

    def save(objs):
        for o in objs:
            db.add(Activity(project_id=pid, code=o[0], name=o[1], phase="execution", planned_hours=o[2], planned_start=o[3], planned_end=o[4]))
        log(db, user.id, "import.plan", "project", pid, {"count": len(objs), "file": body.filename[:100]})
        db.commit()
        return len(objs)
    return _verdict(out, body, save)


@router.get("/import/templates")
def templates(user: User = Depends(require_roles("ADMIN", "PMO", "PM"))):
    return {"staff": ["staff_id", "full_name", "role", "job_title", "department", "email", "capacity_hours_week", "password"],
            "timesheets": ["staff_id", "date", "hours", "project", "activity", "nonproject_code", "description", "status"],
            "plan": ["code", "name", "planned_hours", "planned_start", "planned_end"]}
