"""Portfolio planning: ranked priorities, a 12-week capacity plan, and a governance compliance view per project manager."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func

from .. import rules
from ..alerts import rag_status
from ..config import WEEK_STARTS_ON_SUNDAY
from ..deps import current_user, get_db, get_params, require_roles
from ..evm import compute_evm, latest_progress
from ..models import (Activity, PlannedAllocation, Project, ProjectAction, ProjectScore, Proposal, Risk, TimesheetEntry, User,
                      WeekSubmission, WeeklyReport, Assignment)
from ..workcal import effective_capacity
from .dashboards import EXEC, overall_pct
from .gates import score
from .projects import get_project

router = APIRouter(prefix="/portfolio", tags=["portfolio"])
ws_of = lambda d: rules.week_start(d, WEEK_STARTS_ON_SUNDAY)
LIVE_STATES = ("tendering", "planning", "execution", "closing", "on_hold")


def _exec(user: User):
    if user.role not in EXEC:
        raise HTTPException(403, "Portfolio views require PMO, ADMIN, DECISION_MAKER or PROGRAM_MANAGER")


# ---------------- priorities ----------------
class ScoreIn(BaseModel):
    strategic_fit: int = Field(ge=1, le=5)
    value: int = Field(ge=1, le=5)
    urgency: int = Field(ge=1, le=5)
    risk_level: int = Field(ge=1, le=5)


@router.put("/scores/{pid}")
def set_score(pid: int, body: ScoreIn, db=Depends(get_db), user: User = Depends(require_roles("PMO", "ADMIN", "DECISION_MAKER"))):
    get_project(db, pid)
    s = db.get(ProjectScore, pid) or ProjectScore(project_id=pid, updated_by=user.id)
    for k, v in body.model_dump().items():
        setattr(s, k, v)
    s.updated_by = user.id
    db.add(s)
    from ..audit import log
    log(db, user.id, "project.scored", "project", pid, body.model_dump())
    db.commit()
    return {"project_id": pid, **body.model_dump(), "score": score(s)}


@router.get("/priorities")
def priorities(db=Depends(get_db), user: User = Depends(current_user)):
    """Running projects and open proposals on one ranked list."""
    _exec(user)
    today, rows = date.today(), []
    for p in db.query(Project).filter(Project.state.in_(LIVE_STATES)):
        s = db.get(ProjectScore, p.id)
        e = compute_evm(db, p, today) if p.state in ("execution", "closing") else {}
        rows.append({"kind": "project", "id": p.id, "number": p.number, "name": p.name, "state": p.state, "rag": rag_status(db, p),
                     "scored": s is not None, "score": score(s) if s else None,
                     **({k: getattr(s, k) for k in ("strategic_fit", "value", "urgency", "risk_level")} if s else {}),
                     "budget": p.budget_ceiling, "currency": p.currency, "cpi": e.get("CPI"), "spi": e.get("SPI"),
                     "progress_pct": overall_pct(db, p, today) if p.state in ("execution", "closing") else None})
    for x in db.query(Proposal).filter(Proposal.status.in_(("submitted", "deferred", "info_requested"))):
        rows.append({"kind": "proposal", "id": x.id, "number": x.number, "name": x.name, "state": x.status, "rag": None, "scored": True,
                     "score": score(x), "strategic_fit": x.strategic_fit, "value": x.value, "urgency": x.urgency, "risk_level": x.risk_level,
                     "budget": x.est_cost, "currency": x.currency})
    rows.sort(key=lambda r: (r["score"] is None, -(r["score"] or 0), r["number"]))
    for i, r in enumerate(rows, start=1):
        r["rank"] = i if r["score"] is not None else None
    return rows


# ---------------- capacity ----------------
@router.get("/capacity")
def capacity(weeks: int = 12, group: str = "department", db=Depends(get_db), user: User = Depends(current_user)):
    """Supply (capacity after holidays and approved leave) against demand (planned allocations), week by week."""
    _exec(user)
    if group not in ("department", "grade", "person"):
        raise HTTPException(422, "group must be department, grade or person")
    weeks = max(1, min(weeks, 26))
    start = ws_of(date.today())
    wks = [start + timedelta(days=7 * i) for i in range(weeks)]
    people = db.query(User).filter(User.active.is_(True), User.role.in_(("STAFF", "PM"))).all()
    key = {"department": lambda u: u.department or "—", "grade": lambda u: u.rate_grade or "—", "person": lambda u: u.full_name}[group]
    alloc = {}
    for a in db.query(PlannedAllocation).filter(PlannedAllocation.week_start >= wks[0], PlannedAllocation.week_start <= wks[-1]):
        alloc[(a.user_id, a.week_start)] = alloc.get((a.user_id, a.week_start), 0.0) + a.hours
    groups, over = {}, []
    for u in people:
        g = groups.setdefault(key(u), {"group": key(u), "people": 0, "weeks": [{"week_start": w.isoformat(), "supply": 0.0, "demand": 0.0} for w in wks]})
        g["people"] += 1
        for i, w in enumerate(wks):
            sup = effective_capacity(db, u.capacity_hours_week, w, u.id)
            dem = alloc.get((u.id, w), 0.0)
            g["weeks"][i]["supply"] += sup
            g["weeks"][i]["demand"] += dem
            if dem > sup + 0.01:
                over.append({"user": u.full_name, "week_start": w.isoformat(), "supply": sup, "demand": dem})
    out = []
    for g in sorted(groups.values(), key=lambda g: g["group"]):
        for x in g["weeks"]:
            x["supply"], x["demand"] = round(x["supply"], 1), round(x["demand"], 1)
            x["load_pct"] = round(100 * x["demand"] / x["supply"], 0) if x["supply"] else None
        out.append(g)
    totals = [{"week_start": w.isoformat(), "supply": round(sum(g["weeks"][i]["supply"] for g in out), 1),
               "demand": round(sum(g["weeks"][i]["demand"] for g in out), 1)} for i, w in enumerate(wks)]
    return {"weeks": [w.isoformat() for w in wks], "group_by": group, "groups": out, "totals": totals, "over_allocated": over[:100]}


# ---------------- compliance ----------------
@router.get("/compliance")
def compliance(db=Depends(get_db), user: User = Depends(require_roles("PMO", "ADMIN", "PROGRAM_MANAGER"))):
    """Per project manager: governance duties that are late."""
    today = date.today()
    last = ws_of(today) - timedelta(days=7)
    stale_weeks = int(get_params(db)["stale_progress_weeks"])
    pms = {}
    for p in db.query(Project).filter(Project.state.in_(("planning", "execution", "closing"))):
        row = pms.setdefault(p.pm_id, {"pm_id": p.pm_id, "projects": 0, "missing_reports": [], "stale_progress": 0, "risks_unreviewed": 0,
                                       "overdue_actions": 0, "approvals_waiting_3d": 0, "team_weeks_missing": 0})
        row["projects"] += 1
        if p.state == "execution":
            if not db.query(WeeklyReport).filter_by(project_id=p.id, week_start=last).first():
                row["missing_reports"].append(p.number)
            for a in db.query(Activity).filter_by(project_id=p.id, phase="execution", locked=True):
                lp = latest_progress(db, a.id, today)
                if lp is None or (ws_of(today) - lp.week_start).days > 7 * stale_weeks:
                    row["stale_progress"] += 1
        row["risks_unreviewed"] += db.query(func.count(Risk.id)).filter(
            Risk.project_id == p.id, Risk.status.in_(("open", "mitigating")),
            (Risk.last_reviewed.is_(None)) | (Risk.last_reviewed < today - timedelta(days=30))).scalar()
        row["overdue_actions"] += db.query(func.count(ProjectAction.id)).filter(
            ProjectAction.project_id == p.id, ProjectAction.status == "open", ProjectAction.due_date < today).scalar()
        row["approvals_waiting_3d"] += db.query(func.count(TimesheetEntry.id)).filter(
            TimesheetEntry.project_id == p.id, TimesheetEntry.status == "submitted", TimesheetEntry.entry_date < today - timedelta(days=3)).scalar()
        team = {a.user_id for a in db.query(Assignment).filter_by(project_id=p.id)}
        row.setdefault("_team", set()).update(team)
    names = {u.id: u.full_name for u in db.query(User)}
    out = []
    for pm_id, r in pms.items():
        team = r.pop("_team", set())
        r["team_weeks_missing"] = sum(1 for uid in team if not db.query(WeekSubmission).filter_by(user_id=uid, week_start=last).first())
        r["pm"] = names.get(pm_id)
        r["issues"] = len(r["missing_reports"]) + r["stale_progress"] + r["risks_unreviewed"] + r["overdue_actions"] + r["approvals_waiting_3d"]
        r["rating"] = "green" if r["issues"] == 0 else "amber" if r["issues"] <= 3 else "red"
        out.append(r)
    out.sort(key=lambda r: -r["issues"])
    return {"week_start": last.isoformat(), "managers": out}
