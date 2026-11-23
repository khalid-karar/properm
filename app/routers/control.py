"""PM control: baseline vs forecast per activity, the project action log, and lessons learned."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_

from ..audit import log
from ..deps import current_user, get_db, require_roles
from ..evm import latest_progress
from ..models import Activity, ActivityForecast, Lesson, Project, ProjectAction, TimesheetEntry, User
from .dashboards import EXEC
from .projects import MANAGE, can_manage, can_view, can_view_cost, get_project, need_manage

router = APIRouter(tags=["project control"])

LESSON_CATEGORIES = ("scope", "schedule", "cost", "quality", "resources", "stakeholders", "procurement", "risk", "technical", "other")


def _view(db, user, pid):
    p = get_project(db, pid)
    if not can_view(db, user, p):
        raise HTTPException(403, "No access to this project")
    return p


# ---------------- variance ----------------
@router.get("/projects/{pid}/variance")
def variance(pid: int, db=Depends(get_db), user: User = Depends(current_user)):
    p = _view(db, user, pid)
    cost_ok = can_view_cost(db, user, p)
    today, rows = date.today(), []
    for a in db.query(Activity).filter_by(project_id=pid, phase="execution").order_by(Activity.code):
        actual = float(db.query(func.coalesce(func.sum(TimesheetEntry.hours), 0.0)).filter(
            TimesheetEntry.activity_id == a.id, TimesheetEntry.status.in_(("submitted", "approved"))).scalar())
        lp = latest_progress(db, a.id, today)
        pct = lp.pct_complete if lp else 0.0
        if lp and lp.etc_hours is not None:
            etc, etc_source = lp.etc_hours, "pm"
        elif pct >= 100:
            etc, etc_source = 0.0, "done"
        elif pct > 0:
            etc, etc_source = round(actual / pct * 100 - actual, 1), "trend"
        else:
            etc, etc_source = max(0.0, (a.planned_hours or 0) - actual), "plan"
        eac = round(actual + etc, 1)
        fc = db.get(ActivityForecast, a.id)
        b_end = a.planned_end or p.planned_end            # activity end, else the project end
        f_end = fc.forecast_end if fc and fc.forecast_end else b_end
        slip = (f_end - b_end).days if f_end and b_end else None
        if b_end and b_end < today and pct < 100 and not (fc and fc.forecast_end):
            slip = (today - b_end).days                    # running late with no new forecast
        hv = round((a.planned_hours or 0) - eac, 1)
        r = {"activity_id": a.id, "code": a.code, "name": a.name, "baseline_hours": a.planned_hours, "actual_hours": round(actual, 1),
             "pct_complete": pct, "etc_hours": etc, "etc_source": etc_source, "eac_hours": eac, "hours_variance": hv,
             "baseline_end": b_end, "forecast_end": f_end, "forecast_note": fc.note if fc else None, "slip_days": slip,
             "status": "red" if (a.planned_hours and hv < -0.1 * a.planned_hours) or (slip or 0) > 14 else
                       "amber" if hv < 0 or (slip or 0) > 0 else "green"}
        if cost_ok and a.baseline_cost is not None and a.planned_hours:
            r["baseline_cost"] = a.baseline_cost
            r["eac_cost"] = round(a.baseline_cost * eac / a.planned_hours, 0)
            r["cost_variance"] = round(a.baseline_cost - r["eac_cost"], 0)
        rows.append(r)
    tot = {k: round(sum((x.get(k) or 0) for x in rows), 1) for k in ("baseline_hours", "actual_hours", "etc_hours", "eac_hours", "hours_variance")}
    if cost_ok and any("baseline_cost" in x for x in rows):
        tot.update({k: round(sum(x.get(k, 0) for x in rows), 0) for k in ("baseline_cost", "eac_cost", "cost_variance")})
    return {"rows": rows, "totals": tot, "currency": p.currency if cost_ok else None}


class ForecastIn(BaseModel):
    forecast_end: date | None = None
    note: str | None = Field(None, max_length=2000)


@router.put("/projects/{pid}/activities/{aid}/forecast")
def set_forecast(pid: int, aid: int, body: ForecastIn, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p = get_project(db, pid)
    need_manage(db, user, p)
    a = db.get(Activity, aid)
    if not a or a.project_id != pid:
        raise HTTPException(404, "Activity not found")
    f = db.get(ActivityForecast, aid) or ActivityForecast(activity_id=aid, updated_by=user.id)
    f.forecast_end, f.note, f.updated_by = body.forecast_end, body.note, user.id
    db.add(f)
    log(db, user.id, "forecast.updated", "activity", aid, {"forecast_end": str(body.forecast_end) if body.forecast_end else None})
    db.commit()
    return {"activity_id": aid, "forecast_end": f.forecast_end, "note": f.note}


# ---------------- action log ----------------
class ActionIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    owner_id: int | None = None
    due_date: date | None = None
    source: str | None = Field(None, max_length=100)


class ActionPatch(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=300)
    owner_id: int | None = None
    due_date: date | None = None
    status: str | None = None


def act_out(x: ProjectAction, names) -> dict:
    return {"id": x.id, "project_id": x.project_id, "title": x.title, "owner_id": x.owner_id, "owner": names.get(x.owner_id),
            "due_date": x.due_date, "source": x.source, "status": x.status, "done_on": x.done_on,
            "overdue": x.status == "open" and x.due_date is not None and x.due_date < date.today()}


def _names(db):
    return {u.id: u.full_name for u in db.query(User)}


@router.get("/projects/{pid}/actions")
def list_actions(pid: int, db=Depends(get_db), user: User = Depends(current_user)):
    _view(db, user, pid)
    names = _names(db)
    rows = db.query(ProjectAction).filter_by(project_id=pid).all()
    rows.sort(key=lambda x: (x.status != "open", x.due_date or date.max, x.id))
    return [act_out(x, names) for x in rows]


@router.post("/projects/{pid}/actions", status_code=201)
def add_action(pid: int, body: ActionIn, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p = get_project(db, pid)
    need_manage(db, user, p)
    if body.owner_id is not None and not db.get(User, body.owner_id):
        raise HTTPException(422, "owner_id must be an existing user")
    x = ProjectAction(project_id=pid, created_by=user.id, **body.model_dump())
    db.add(x)
    db.flush()
    log(db, user.id, "action.created", "project_action", x.id, {"project_id": pid})
    db.commit()
    return act_out(x, _names(db))


@router.patch("/projects/{pid}/actions/{xid}")
def patch_action(pid: int, xid: int, body: ActionPatch, db=Depends(get_db), user: User = Depends(current_user)):
    p = get_project(db, pid)
    x = db.get(ProjectAction, xid)
    if not x or x.project_id != pid:
        raise HTTPException(404, "Action not found")
    ch = body.model_dump(exclude_unset=True)
    owner_only = x.owner_id == user.id and set(ch) <= {"status"}
    if not (can_manage(db, user, p) or owner_only):
        raise HTTPException(403, "Only the project manager, or the owner marking it done, can change an action")
    if "status" in ch and ch["status"] not in ("open", "done", "cancelled"):
        raise HTTPException(422, "status must be open, done or cancelled")
    if ch.get("owner_id") is not None and not db.get(User, ch["owner_id"]):
        raise HTTPException(422, "owner_id must be an existing user")
    for k, v in ch.items():
        setattr(x, k, v)
    if "status" in ch:
        x.done_on = date.today() if ch["status"] == "done" else None
    log(db, user.id, "action.updated", "project_action", x.id, ch | ({"due_date": str(ch["due_date"])} if ch.get("due_date") else {}))
    db.commit()
    return act_out(x, _names(db))


@router.delete("/projects/{pid}/actions/{xid}", status_code=204)
def delete_action(pid: int, xid: int, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p = get_project(db, pid)
    need_manage(db, user, p)
    x = db.get(ProjectAction, xid)
    if not x or x.project_id != pid:
        raise HTTPException(404, "Action not found")
    db.delete(x)
    log(db, user.id, "action.deleted", "project_action", xid, {"project_id": pid})
    db.commit()


# ---------------- lessons learned ----------------
class LessonIn(BaseModel):
    category: str
    impact: str = "negative"
    what_happened: str = Field(min_length=5, max_length=5000)
    recommendation: str = Field(min_length=5, max_length=5000)


def les_out(x: Lesson, names, projects) -> dict:
    p = projects.get(x.project_id)
    return {"id": x.id, "project_id": x.project_id, "project": f"{p.number} · {p.name}" if p else None, "category": x.category,
            "impact": x.impact, "what_happened": x.what_happened, "recommendation": x.recommendation,
            "created_by": names.get(x.created_by), "created_at": x.created_at.isoformat() if x.created_at else None}


@router.get("/projects/{pid}/lessons")
def project_lessons(pid: int, db=Depends(get_db), user: User = Depends(current_user)):
    _view(db, user, pid)
    projects = {p.id: p for p in db.query(Project).filter_by(id=pid)}
    return [les_out(x, _names(db), projects) for x in db.query(Lesson).filter_by(project_id=pid).order_by(Lesson.id.desc())]


@router.post("/projects/{pid}/lessons", status_code=201)
def add_lesson(pid: int, body: LessonIn, db=Depends(get_db), user: User = Depends(current_user)):
    p = _view(db, user, pid)          # anyone on the project can record a lesson
    if body.category not in LESSON_CATEGORIES:
        raise HTTPException(422, f"category must be one of {', '.join(LESSON_CATEGORIES)}")
    if body.impact not in ("positive", "negative"):
        raise HTTPException(422, "impact must be positive or negative")
    x = Lesson(project_id=pid, created_by=user.id, **body.model_dump())
    db.add(x)
    db.flush()
    log(db, user.id, "lesson.recorded", "lesson", x.id, {"project_id": pid})
    db.commit()
    return les_out(x, _names(db), {p.id: p})


@router.delete("/projects/{pid}/lessons/{lid}", status_code=204)
def delete_lesson(pid: int, lid: int, db=Depends(get_db), user: User = Depends(current_user)):
    p = get_project(db, pid)
    x = db.get(Lesson, lid)
    if not x or x.project_id != pid:
        raise HTTPException(404, "Lesson not found")
    if not (x.created_by == user.id or can_manage(db, user, p)):
        raise HTTPException(403, "Only the author or the project manager can remove a lesson")
    db.delete(x)
    log(db, user.id, "lesson.deleted", "lesson", lid, {"project_id": pid})
    db.commit()


@router.get("/lessons")
def lessons_library(q: str | None = None, category: str | None = None, impact: str | None = None, db=Depends(get_db),
                    user: User = Depends(require_roles("PM", "PMO", "ADMIN", *EXEC))):
    """Lessons from every project, so a new project can learn from earlier ones."""
    qq = db.query(Lesson)
    if category:
        qq = qq.filter(Lesson.category == category)
    if impact:
        qq = qq.filter(Lesson.impact == impact)
    if q:
        like = f"%{q.strip()}%"
        qq = qq.filter(or_(Lesson.what_happened.ilike(like), Lesson.recommendation.ilike(like)))
    projects = {p.id: p for p in db.query(Project)}
    return {"categories": list(LESSON_CATEGORIES), "lessons": [les_out(x, _names(db), projects) for x in qq.order_by(Lesson.id.desc()).limit(300)]}
