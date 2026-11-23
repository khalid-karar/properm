"""Governance: closure checklist (1.5), benefits register, programs, work calendar."""
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func

from ..alerts import rag_status
from ..audit import emit, log
from ..config import CLOSURE_ITEMS
from ..lists import active as active_list
from ..deps import current_user, get_db, require_roles
from ..evm import compute_evm
from ..models import Benefit, ClosureItem, CostEntry, Holiday, Issue, Program, Project, TimesheetEntry, User
from ..workcal import week_info
from .dashboards import EXEC, overall_pct
from .projects import can_manage, can_view, can_view_cost, get_project, need_manage, p_out

router = APIRouter(tags=["governance"])
MANAGE = ("PM", "PMO", "ADMIN")
BENEFIT_STATUS = ("planned", "on_track", "at_risk", "realized", "missed")


# ---------------- closure checklist ----------------
def ensure_closure_items(db, pid: int) -> None:
    have = {i.key for i in db.query(ClosureItem).filter_by(project_id=pid)}
    for key, _auto in CLOSURE_ITEMS:
        if key not in have:
            db.add(ClosureItem(project_id=pid, key=key))
    for x in active_list(db, "closure_item"):
        if f"x:{x['code']}" not in have:
            db.add(ClosureItem(project_id=pid, key=f"x:{x['code']}"))
    db.flush()


def _has_deliverables(db, pid: int) -> bool:
    from ..models import Deliverable
    return db.query(Deliverable).filter_by(project_id=pid, kind="deliverable").count() > 0


def _auto_check(db, pid: int, key: str) -> tuple[bool, str]:
    if key == "deliverables_accepted":
        from ..models import Deliverable
        n = db.query(func.count(Deliverable.id)).filter(Deliverable.project_id == pid, Deliverable.kind == "deliverable", Deliverable.status != "accepted").scalar()
        return n == 0, f"{n} deliverables not yet accepted" if n else "All deliverables accepted"
    if key == "timesheets_approved":
        n = db.query(func.count(TimesheetEntry.id)).filter_by(project_id=pid, status="submitted").scalar()
        return n == 0, f"{n} timesheet entries awaiting approval" if n else "No entries awaiting approval"
    if key == "issues_closed":
        n = db.query(func.count(Issue.id)).filter(Issue.project_id == pid, Issue.status.in_(("open", "in_progress"))).scalar()
        return n == 0, f"{n} issues still open" if n else "No open issues"
    return True, ""


def closure_status(db, pid: int) -> list[dict]:
    ensure_closure_items(db, pid)
    auto = dict(CLOSURE_ITEMS)
    custom = {f"x:{x['code']}": x["label"] for x in active_list(db, "closure_item")}
    out = []
    for i in db.query(ClosureItem).filter_by(project_id=pid).order_by(ClosureItem.id):
        if i.key.startswith("x:") and i.key not in custom:
            continue                                   # switched off by the administrator
        if i.key == "deliverables_accepted" and _has_deliverables(db, pid):
            ok, detail = _auto_check(db, pid, i.key)
            out.append({"key": i.key, "auto": True, "satisfied": ok, "done": ok, "detail": detail, "note": i.note})
        elif auto.get(i.key):
            ok, detail = _auto_check(db, pid, i.key)
            out.append({"key": i.key, "auto": True, "satisfied": ok, "done": ok, "detail": detail, "note": i.note})
        else:
            out.append({"key": i.key, "auto": False, "satisfied": i.done, "done": i.done, "done_by": i.done_by,
                        "done_at": i.done_at, "note": i.note, **({"label": custom[i.key]} if i.key in custom else {})})
    return out


class ClosureIn(BaseModel):
    done: bool
    note: str | None = None


@router.get("/projects/{pid}/closure")
def get_closure(pid: int, db=Depends(get_db), user: User = Depends(current_user)):
    p = get_project(db, pid)
    if not can_view(db, user, p):
        raise HTTPException(403, "No access to this project")
    if p.state not in ("closing", "archived"):
        raise HTTPException(409, "The closure checklist opens when the project moves to closing")
    items = closure_status(db, pid)
    db.commit()
    return {"project_id": pid, "ready": all(i["satisfied"] for i in items), "items": items}


@router.put("/projects/{pid}/closure/{key}")
def set_closure(pid: int, key: str, body: ClosureIn, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p = get_project(db, pid)
    need_manage(db, user, p)
    if p.state != "closing":
        raise HTTPException(409, "Closure items can be changed while the project is closing")
    auto = dict(CLOSURE_ITEMS)
    if key not in auto and not (key.startswith("x:") and key[2:] in {x["code"] for x in active_list(db, "closure_item")}):
        raise HTTPException(404, "Unknown closure item")
    if auto.get(key):
        raise HTTPException(409, "This item is checked by the system, not ticked by hand")
    ensure_closure_items(db, pid)
    it = db.query(ClosureItem).filter_by(project_id=pid, key=key).one()
    it.done, it.note = body.done, body.note
    it.done_by, it.done_at = (user.id, datetime.now(timezone.utc)) if body.done else (None, None)
    log(db, user.id, "closure.item", "project", pid, {"key": key, "done": body.done})
    db.commit()
    return get_closure(pid, db, user)


# ---------------- benefits register ----------------
class BenefitIn(BaseModel):
    title: str = Field(min_length=1)
    metric: str | None = None
    unit: str | None = None
    baseline: float | None = None
    target: float | None = None
    actual: float | None = None
    due_date: date | None = None
    owner_id: int | None = None
    status: str = "planned"
    notes: str | None = None


class BenefitPatch(BaseModel):
    title: str | None = None
    metric: str | None = None
    unit: str | None = None
    baseline: float | None = None
    target: float | None = None
    actual: float | None = None
    due_date: date | None = None
    owner_id: int | None = None
    status: str | None = None
    notes: str | None = None


def realization_pct(b: Benefit):
    if b.baseline is None or b.target is None or b.actual is None or b.target == b.baseline:
        return None
    return round(max(0.0, min(150.0, 100 * (b.actual - b.baseline) / (b.target - b.baseline))), 1)


def b_out(b: Benefit) -> dict:
    return {"id": b.id, "project_id": b.project_id, "title": b.title, "metric": b.metric, "unit": b.unit,
            "baseline": b.baseline, "target": b.target, "actual": b.actual, "due_date": b.due_date,
            "owner_id": b.owner_id, "status": b.status, "notes": b.notes, "realization_pct": realization_pct(b)}


@router.get("/projects/{pid}/benefits")
def list_benefits(pid: int, db=Depends(get_db), user: User = Depends(current_user)):
    p = get_project(db, pid)
    if not can_view(db, user, p):
        raise HTTPException(403, "No access to this project")
    return [b_out(b) for b in db.query(Benefit).filter_by(project_id=pid).order_by(Benefit.id)]


def _check_benefit(db, status, owner_id):
    if status is not None and status not in BENEFIT_STATUS:
        raise HTTPException(422, f"status must be one of {BENEFIT_STATUS}")
    if owner_id is not None and not db.get(User, owner_id):
        raise HTTPException(422, "owner_id is not a user")


@router.post("/projects/{pid}/benefits", status_code=201)
def add_benefit(pid: int, body: BenefitIn, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p = get_project(db, pid)
    need_manage(db, user, p)
    _check_benefit(db, body.status, body.owner_id)
    b = Benefit(project_id=pid, **body.model_dump())
    db.add(b)
    db.flush()
    log(db, user.id, "benefit.created", "benefit", b.id, {"project_id": pid})
    emit(db, "benefit.updated", {"project_id": pid, "benefit_id": b.id})
    db.commit()
    return b_out(b)


@router.patch("/projects/{pid}/benefits/{bid}")
def update_benefit(pid: int, bid: int, body: BenefitPatch, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p = get_project(db, pid)
    need_manage(db, user, p)
    b = db.get(Benefit, bid)
    if not b or b.project_id != pid:
        raise HTTPException(404, "Benefit not found")
    ch = body.model_dump(exclude_unset=True)
    _check_benefit(db, ch.get("status"), ch.get("owner_id"))
    for k, v in ch.items():
        setattr(b, k, v)
    log(db, user.id, "benefit.updated", "benefit", b.id, {"fields": sorted(ch)})
    emit(db, "benefit.updated", {"project_id": pid, "benefit_id": b.id})
    db.commit()
    return b_out(b)


# ---------------- programs ----------------
class ProgramIn(BaseModel):
    code: str = Field(min_length=1)
    name: str = Field(min_length=1)
    manager_id: int | None = None
    description: str | None = None


class ProgramPatch(BaseModel):
    name: str | None = None
    manager_id: int | None = None
    description: str | None = None


def prog_out(g: Program) -> dict:
    return {"id": g.id, "code": g.code, "name": g.name, "manager_id": g.manager_id, "description": g.description}


@router.get("/programs")
def list_programs(mine: bool = False, db=Depends(get_db), user: User = Depends(current_user)):
    if user.role == "STAFF":
        raise HTTPException(403, "Programs are for managers and portfolio roles")
    q = db.query(Program).order_by(Program.code)
    if mine:
        q = q.filter(Program.manager_id == user.id)
    return [prog_out(g) for g in q]


@router.post("/programs", status_code=201)
def create_program(body: ProgramIn, db=Depends(get_db), user: User = Depends(require_roles("PMO", "ADMIN"))):
    if db.query(Program).filter_by(code=body.code).first():
        raise HTTPException(409, "Program code already exists")
    if body.manager_id is not None and not db.get(User, body.manager_id):
        raise HTTPException(422, "manager_id is not a user")
    g = Program(**body.model_dump())
    db.add(g)
    db.flush()
    log(db, user.id, "program.created", "program", g.id, {"code": g.code})
    db.commit()
    return prog_out(g)


@router.patch("/programs/{gid}")
def update_program(gid: int, body: ProgramPatch, db=Depends(get_db), user: User = Depends(require_roles("PMO", "ADMIN", "PROGRAM_MANAGER"))):
    g = db.get(Program, gid)
    if not g:
        raise HTTPException(404, "Program not found")
    ch = body.model_dump(exclude_unset=True)
    if user.role == "PROGRAM_MANAGER":
        if g.manager_id != user.id:
            raise HTTPException(403, "You can only edit programs you manage")
        ch.pop("manager_id", None)
    if ch.get("manager_id") is not None and not db.get(User, ch["manager_id"]):
        raise HTTPException(422, "manager_id is not a user")
    for k, v in ch.items():
        setattr(g, k, v)
    log(db, user.id, "program.updated", "program", gid, {"fields": sorted(ch)})
    db.commit()
    return prog_out(g)


class ProgramLink(BaseModel):
    program_id: int | None


@router.put("/projects/{pid}/program")
def set_project_program(pid: int, body: ProgramLink, db=Depends(get_db), user: User = Depends(require_roles("PMO", "ADMIN", "PROGRAM_MANAGER"))):
    p = get_project(db, pid)
    if body.program_id is not None and not db.get(Program, body.program_id):
        raise HTTPException(404, "Program not found")
    if user.role == "PROGRAM_MANAGER":
        mine = {g.id for g in db.query(Program).filter_by(manager_id=user.id)}
        if (body.program_id is not None and body.program_id not in mine) or (p.program_id is not None and p.program_id not in mine):
            raise HTTPException(403, "You can only move projects into or out of programs you manage")
    p.program_id = body.program_id
    log(db, user.id, "project.program_set", "project", pid, {"program_id": body.program_id})
    db.commit()
    return p_out(p)


@router.get("/programs/{gid}/dashboard")
def program_dashboard(gid: int, as_of: date | None = None, db=Depends(get_db), user: User = Depends(current_user)):
    if user.role not in EXEC:
        raise HTTPException(403, "Program dashboards require PMO, ADMIN, DECISION_MAKER or PROGRAM_MANAGER")
    g = db.get(Program, gid)
    if not g:
        raise HTTPException(404, "Program not found")
    as_of = as_of or date.today()
    projects, counts = [], {"RED": 0, "AMBER": 0, "GREEN": 0, "GREY": 0}
    tot = {"BAC": 0.0, "PV": 0.0, "EV": 0.0, "AC": 0.0}
    currencies = set()
    for p in db.query(Project).filter_by(program_id=gid).order_by(Project.id):
        r = rag_status(db, p)
        counts[r] += 1
        e = compute_evm(db, p, as_of) if p.state in ("execution", "closing") else {"available": False}
        if e.get("available"):
            currencies.add(e["currency"])
            for k in tot:
                tot[k] += e[k] or 0.0
        projects.append({"project_id": p.id, "number": p.number, "name": p.name, "state": p.state, "rag": r,
                         "progress_pct": overall_pct(db, p, as_of), "cpi": e.get("CPI"), "spi": e.get("SPI")})
    ids = [x["project_id"] for x in projects]
    bens = db.query(Benefit).filter(Benefit.project_id.in_(ids)).all() if ids else []
    by_status = {s: sum(1 for b in bens if b.status == s) for s in BENEFIT_STATUS}
    reals = [realization_pct(b) for b in bens if realization_pct(b) is not None]
    out = {"program": prog_out(g), "as_of": as_of, "rag_counts": counts, "projects": projects,
           "benefits": {"count": len(bens), "by_status": by_status,
                        "avg_realization_pct": round(sum(reals) / len(reals), 1) if reals else None}}
    if len(currencies) > 1:
        out["evm"] = {"available": False, "reason": f"Projects use several currencies ({', '.join(sorted(currencies))}); totals not summed"}
    elif tot["AC"] or tot["EV"] or tot["PV"]:
        out["evm"] = {"available": True, "currency": next(iter(currencies), None), **{k: round(v, 2) for k, v in tot.items()},
                      "CPI": round(tot["EV"] / tot["AC"], 3) if tot["AC"] else None, "SPI": round(tot["EV"] / tot["PV"], 3) if tot["PV"] else None}
    else:
        out["evm"] = {"available": False, "reason": "No executing projects with a cost baseline"}
    return out


# ---------------- work calendar ----------------
class HolidayIn(BaseModel):
    day: date
    name: str = Field(min_length=1)


@router.get("/calendar/holidays")
def list_holidays(year: int | None = None, db=Depends(get_db), user: User = Depends(current_user)):
    q = db.query(Holiday)
    if year:
        q = q.filter(Holiday.day >= date(year, 1, 1), Holiday.day <= date(year, 12, 31))
    return [{"id": h.id, "day": h.day, "name": h.name} for h in q.order_by(Holiday.day)]


@router.post("/calendar/holidays", status_code=201)
def add_holiday(body: HolidayIn, db=Depends(get_db), user: User = Depends(require_roles("PMO", "ADMIN"))):
    if db.query(Holiday).filter_by(day=body.day).first():
        raise HTTPException(409, "A holiday already exists on that date")
    h = Holiday(day=body.day, name=body.name)
    db.add(h)
    db.flush()
    log(db, user.id, "holiday.added", "holiday", h.id, {"day": str(body.day)})
    db.commit()
    return {"id": h.id, "day": h.day, "name": h.name}


@router.delete("/calendar/holidays/{hid}", status_code=204)
def delete_holiday(hid: int, db=Depends(get_db), user: User = Depends(require_roles("PMO", "ADMIN"))):
    h = db.get(Holiday, hid)
    if not h:
        raise HTTPException(404, "Holiday not found")
    log(db, user.id, "holiday.removed", "holiday", hid, {"day": str(h.day)})
    db.delete(h)
    db.commit()


@router.get("/calendar/week")
def calendar_week(week_of: date | None = None, db=Depends(get_db), user: User = Depends(current_user)):
    from ..rules import week_start
    from ..config import WEEK_STARTS_ON_SUNDAY
    return week_info(db, week_start(week_of or date.today(), WEEK_STARTS_ON_SUNDAY))


@router.get("/programs/{gid}/rollup")
def program_rollup(gid: int, db=Depends(get_db), user: User = Depends(current_user)):
    """Open risks and all benefits across the program's projects."""
    if user.role not in EXEC:
        raise HTTPException(403, "Program roll-up requires PMO, ADMIN, DECISION_MAKER or PROGRAM_MANAGER")
    if not db.get(Program, gid):
        raise HTTPException(404, "Program not found")
    from ..models import Risk
    projs = {p.id: p for p in db.query(Project).filter_by(program_id=gid)}
    risks = db.query(Risk).filter(Risk.project_id.in_(list(projs)), Risk.status.in_(("open", "mitigating"))).all() if projs else []
    risks.sort(key=lambda r: -r.score)
    bens = db.query(Benefit).filter(Benefit.project_id.in_(list(projs))).all() if projs else []
    from ..models import ProgramRisk
    prisks = [{"id": r.id, "project_id": None, "project": "PROGRAM", "title": r.title, "score": r.score, "status": r.status}
              for r in db.query(ProgramRisk).filter(ProgramRisk.program_id == gid, ProgramRisk.status.in_(("open", "mitigating")))]
    allr = sorted(prisks + [{"id": r.id, "project_id": r.project_id, "project": projs[r.project_id].number, "title": r.title, "score": r.score,
                             "status": r.status} for r in risks], key=lambda x: -x["score"])
    return {"risks": allr[:50],
            "benefits": [{**b_out(b), "project": projs[b.project_id].number} for b in bens]}
