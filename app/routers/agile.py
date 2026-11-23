"""Agile / hybrid delivery: product backlog, sprints, a task board that team members can move, velocity and burndown."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..audit import log
from ..deps import current_user, get_db
from ..models import Assignment, BacklogItem, Deliverable, Sprint, User
from ..regkit import project_register
from .projects import can_manage, can_view, get_project, need_manage

router = APIRouter(tags=["agile"])
STATUSES = ("backlog", "ready", "in_progress", "review", "done")


def _check_type(db, p, data, row):
    if p.project_type == "predictive":
        raise HTTPException(409, "Backlog and sprints are for hybrid or adaptive projects. Change the project type in Details first")


def _item_validate(db, p, data, row):
    _check_type(db, p, data, row)
    if data.get("sprint_id"):
        s = db.get(Sprint, data["sprint_id"])
        if not s or s.project_id != p.id:
            raise HTTPException(422, "Sprint not found in this project")
        if s.status == "closed":
            raise HTTPException(409, "That sprint is closed")
    if data.get("assignee_id") and not db.get(User, data["assignee_id"]):
        raise HTTPException(422, "Unknown user")
    if data.get("deliverable_id"):
        d = db.get(Deliverable, data["deliverable_id"])
        if not d or d.project_id != p.id:
            raise HTTPException(422, "Deliverable not found in this project")
    if data.get("points") is not None and data["points"] < 0:
        raise HTTPException(422, "Points cannot be negative")
    if "status" in data:
        _set_done(data, row)


def _set_done(data, row):
    if data.get("status") == "done" and not (row and row.done_on):
        data["done_on"] = date.today()
    elif data.get("status") and data["status"] != "done":
        data["done_on"] = None


def _item_enrich(db, p, rows, ds):
    names = {u.id: u.full_name for u in db.query(User)}
    sp = {s.id: s.name for s in db.query(Sprint).filter_by(project_id=p.id)}
    for d in ds:
        d["assignee"] = names.get(d["assignee_id"])
        d["sprint"] = sp.get(d["sprint_id"])


ITEM = project_register(router, "backlog", BacklogItem,
                        {"title": str, "description": str, "acceptance_criteria": str, "kind": str, "points": float, "rank": int,
                         "status": str, "sprint_id": int, "assignee_id": int, "deliverable_id": int},
                        choices={"kind": ("story", "bug", "task", "epic"), "status": STATUSES}, required=("title",),
                        defaults={"kind": "story", "rank": 100, "status": "backlog"}, validate=_item_validate, enrich=_item_enrich,
                        order=[BacklogItem.rank, BacklogItem.id])


class MoveIn(BaseModel):
    status: str


@router.post("/projects/{pid}/backlog/{iid}/move")
def move_item(pid: int, iid: int, body: MoveIn, db=Depends(get_db), user: User = Depends(current_user)):
    """Board move. The project manager, or the person the card is assigned to (or any assigned team member for an unassigned card)."""
    p = get_project(db, pid)
    if not can_view(db, user, p):
        raise HTTPException(403, "No access to this project")
    it = ITEM["one"](db, p, iid)
    if body.status not in STATUSES:
        raise HTTPException(422, "Unknown status")
    member = db.query(Assignment).filter_by(project_id=pid, user_id=user.id).first() is not None
    if not (can_manage(db, user, p) or (member and it.assignee_id in (None, user.id))):
        raise HTTPException(403, "Only the project manager or the person this card is assigned to can move it")
    if body.status in ("in_progress", "review", "done") and not it.sprint_id:
        raise HTTPException(409, "Put the item into a sprint before working on it")
    data = {"status": body.status}
    _set_done(data, it)
    it.status, it.done_on = body.status, data.get("done_on", it.done_on)
    if body.status == "in_progress" and it.assignee_id is None and member and not can_manage(db, user, p):
        it.assignee_id = user.id
    log(db, user.id, "backlog.moved", "backlog_items", iid, {"to": body.status})
    db.commit()
    return ITEM["out"](db, p, [it])[0]


# ---------------- sprints ----------------
def _sprint_validate(db, p, data, row):
    _check_type(db, p, data, row)
    s, e = data.get("start_date") or (row and row.start_date), data.get("end_date") or (row and row.end_date)
    if s and e and e < s:
        raise HTTPException(422, "Sprint end is before its start")
    if row and row.status == "closed":
        raise HTTPException(409, "Closed sprints are read-only")


def _sprint_enrich(db, p, rows, ds):
    for r, d in zip(rows, ds):
        items = db.query(BacklogItem).filter_by(sprint_id=r.id).all()
        d["items"] = len(items)
        d["points"] = sum(i.points or 0 for i in items)
        d["done_points"] = sum(i.points or 0 for i in items if i.status == "done")


SPR = project_register(router, "sprints", Sprint, {"name": str, "goal": str, "start_date": date, "end_date": date, "review_note": str, "retro_note": str},
                       required=("name", "start_date", "end_date"), validate=_sprint_validate, enrich=_sprint_enrich, order=[Sprint.start_date])


@router.post("/projects/{pid}/sprints/{sid}/start")
def start_sprint(pid: int, sid: int, db=Depends(get_db), user: User = Depends(current_user)):
    p = get_project(db, pid)
    need_manage(db, user, p)
    s = SPR["one"](db, p, sid)
    if s.status != "planned":
        raise HTTPException(409, "Only a planned sprint can be started")
    if db.query(Sprint).filter_by(project_id=pid, status="active").first():
        raise HTTPException(409, "Close the active sprint first")
    s.status = "active"
    s.committed_points = sum(i.points or 0 for i in db.query(BacklogItem).filter_by(sprint_id=sid))
    log(db, user.id, "sprint.started", "sprints", sid, {"committed": s.committed_points})
    db.commit()
    return SPR["out"](db, p, [s])[0]


class CloseIn(BaseModel):
    move_to: int | None = None       # next sprint for unfinished items; none = back to the backlog
    review_note: str | None = Field(None, max_length=3000)
    retro_note: str | None = Field(None, max_length=3000)


@router.post("/projects/{pid}/sprints/{sid}/close")
def close_sprint(pid: int, sid: int, body: CloseIn, db=Depends(get_db), user: User = Depends(current_user)):
    p = get_project(db, pid)
    need_manage(db, user, p)
    s = SPR["one"](db, p, sid)
    if s.status != "active":
        raise HTTPException(409, "Only the active sprint can be closed")
    nxt = None
    if body.move_to:
        nxt = db.get(Sprint, body.move_to)
        if not nxt or nxt.project_id != pid or nxt.status != "planned":
            raise HTTPException(422, "Choose a planned sprint of this project")
    moved = 0
    for i in db.query(BacklogItem).filter_by(sprint_id=sid):
        if i.status != "done":
            moved += 1
            i.sprint_id = nxt.id if nxt else None
            if not nxt:
                i.status = "backlog"
    s.status = "closed"
    if body.review_note is not None:
        s.review_note = body.review_note
    if body.retro_note is not None:
        s.retro_note = body.retro_note
    log(db, user.id, "sprint.closed", "sprints", sid, {"moved": moved})
    db.commit()
    return {**SPR["out"](db, p, [s])[0], "moved": moved}


# ---------------- velocity and burndown ----------------
@router.get("/projects/{pid}/agile-summary")
def agile_summary(pid: int, db=Depends(get_db), user: User = Depends(current_user)):
    p = get_project(db, pid)
    if not can_view(db, user, p):
        raise HTTPException(403, "No access to this project")
    items = db.query(BacklogItem).filter_by(project_id=pid).all()
    sprints = db.query(Sprint).filter_by(project_id=pid).order_by(Sprint.start_date).all()
    vel = []
    for s in sprints:
        if s.status == "closed":
            vel.append({"sprint": s.name, "committed": s.committed_points or 0,
                        "done": sum(i.points or 0 for i in items if i.sprint_id == s.id and i.status == "done")})
    # closed sprints keep their done items, so velocity above is stable; unfinished items were moved out
    avg = round(sum(v["done"] for v in vel[-3:]) / len(vel[-3:]), 1) if vel else None
    remaining = sum(i.points or 0 for i in items if i.status != "done" and i.kind != "epic")
    act = next((s for s in sprints if s.status == "active"), None)
    burn = None
    if act:
        its = [i for i in items if i.sprint_id == act.id]
        total = act.committed_points if act.committed_points is not None else sum(i.points or 0 for i in its)
        days = (act.end_date - act.start_date).days + 1
        today = date.today()
        pts = []
        for n in range(days):
            day = act.start_date + timedelta(days=n)
            done = sum(i.points or 0 for i in its if i.done_on and i.done_on <= day)
            pts.append({"date": day.isoformat(), "ideal": round(total * (1 - n / max(1, days - 1)), 1),
                        "remaining": round(total - done, 1) if day <= today else None})
        burn = {"sprint": act.name, "total": total, "points": pts, "done": sum(i.points or 0 for i in its if i.status == "done")}
    return {"project_type": p.project_type, "velocity": vel, "average_velocity": avg, "remaining_points": remaining,
            "sprints_to_go": round(remaining / avg, 1) if avg else None, "unestimated": sum(1 for i in items if i.points is None and i.status != "done" and i.kind != "epic"),
            "burndown": burn, "counts": {s: sum(1 for i in items if i.status == s) for s in STATUSES}}
