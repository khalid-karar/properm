"""Import a schedule from Primavera P6 (.xer) or MS Project (.xml): activities with dates and hours, milestones, and finish-to-start links.
Preview first (commit=false). The project must be in planning. Other link types and lags are not stored, and the preview says how many were left out."""
import base64
import binascii
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException

from ..audit import log
from ..deps import get_db, require_roles
from ..models import Activity, ActivityDependency, Milestone, User
from ..schedule import ScheduleError, read_schedule
from .imports import MAX_FILE, ImportIn, _verdict
from .projects import MANAGE, get_project, need_manage

router = APIRouter(tags=["imports"])


def _has_path(adj, start, goal) -> bool:
    seen, stack = set(), [start]
    while stack:
        cur = stack.pop()
        if cur == goal:
            return True
        if cur in seen:
            continue
        seen.add(cur)
        stack += adj.get(cur, ())
    return False


@router.post("/projects/{pid}/import/schedule")
def import_schedule(pid: int, body: ImportIn, project: str | None = None, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p = get_project(db, pid)
    need_manage(db, user, p)
    if p.state != "planning":
        raise HTTPException(409, "A schedule can be imported while the project is in planning")
    try:
        data = base64.b64decode(body.content_b64, validate=False)
    except (binascii.Error, ValueError):
        raise HTTPException(422, "The file could not be read")
    if len(data) > MAX_FILE:
        raise HTTPException(413, "The file is larger than 10 MB. Split it and import in parts.")
    try:
        sched = read_schedule(body.filename, data, project)
    except ScheduleError as e:
        raise HTTPException(422, str(e))

    have = {a.code: a.id for a in db.query(Activity).filter_by(project_id=pid)}
    have_ms = {(m.name, m.due_date) for m in db.query(Milestone).filter_by(project_id=pid)}
    seen, out, est = set(), [], 0
    for n, t in enumerate(sched["tasks"], start=1):
        code, name = t["code"][:60], t["name"][:300]
        e = None
        if not code or not name:
            e = "code and name are required"
        elif t["start"] and t["end"] and t["end"] < t["start"]:
            e = "end is before start"
        elif t["milestone"] and not (t["start"] or t["end"]):
            e = "milestone has no date"
        elif not t["milestone"] and t["hours"] <= 0:
            e = "no work hours or duration"
        elif not t["milestone"] and (t["start"] is None) != (t["end"] is None):
            e = "give both start and end, or neither"
        elif code in seen:
            e = "code appears twice in the file"
        if e:
            out.append({"line": n, "key": code, "status": "error", "message": e})
            continue
        seen.add(code)
        if t["milestone"]:
            due = t["start"] or t["end"]
            if (name, due) in have_ms:
                out.append({"line": n, "key": code, "status": "duplicate", "message": "milestone already in this project, skipped"})
                continue
            out.append({"line": n, "key": code, "status": "ok", "message": f"milestone · {name} · {due}", "_obj": ("m", code, name, due)})
        else:
            if code in have:
                out.append({"line": n, "key": code, "status": "duplicate", "message": "activity code already in this project, skipped"})
                continue
            est += t["hours_from_duration"]
            out.append({"line": n, "key": code, "status": "ok", "message": f"{name} · {t['hours']:g} h" + (" (from duration)" if t["hours_from_duration"] else ""),
                        "_obj": ("a", code, name, t["hours"], t["start"], t["end"])})

    # links: only finish-to-start between activities (milestones are not activities here); refuse any that would make a loop
    existing = {(a, b) for a, b in db.query(ActivityDependency.activity_id, ActivityDependency.predecessor_id)}
    idc = {v: k for k, v in have.items()}
    adj = defaultdict(list)                                      # predecessor code -> successor codes
    for a, b in existing:
        if a in idc and b in idc:
            adj[idc[b]].append(idc[a])
    ok_act = {r["key"] for r in out if r["status"] == "ok" and r["_obj"][0] == "a"}
    known = ok_act | set(have)
    miss = defaultdict(int)
    new_links = []
    for pred, succ, typ in sched["links"]:
        pred, succ = pred[:60], succ[:60]
        if typ != "FS":
            miss["non_fs"] += 1
        elif pred == succ:
            miss["self"] += 1
        elif pred not in known or succ not in known:
            miss["skipped_end"] += 1
        elif (pred, succ) in {(a, b) for a, b in new_links} or (have.get(succ), have.get(pred)) in existing:
            miss["duplicate"] += 1
        elif _has_path(adj, succ, pred):
            miss["loop"] += 1
        else:
            new_links.append((pred, succ))
            adj[pred].append(succ)
    notes = list(sched["warnings"])
    if est:
        notes.append(f"{est} activities had no resource work hours, so their planned hours come from the task duration. Review them.")
    if miss["non_fs"]:
        notes.append(f"{miss['non_fs']} links of other types (start-to-start, finish-to-finish, start-to-finish) were not imported. Only finish-to-start is stored; lags are ignored.")
    if miss["skipped_end"]:
        notes.append(f"{miss['skipped_end']} links were not imported because one end is a milestone or a skipped row.")
    if miss["loop"]:
        notes.append(f"{miss['loop']} links were not imported because they would create a circular dependency.")
    notes.append("Dates and hours are read as the planned (target) values. Progress and actuals in the file are not imported.")

    def save(objs):
        acts = [o for o in objs if o[0] == "a"]
        for o in acts:
            db.add(Activity(project_id=pid, code=o[1], name=o[2], phase="execution", planned_hours=o[3], planned_start=o[4], planned_end=o[5]))
        for o in objs:
            if o[0] == "m":
                db.add(Milestone(project_id=pid, name=o[2], due_date=o[3]))
        db.flush()
        ids = {a.code: a.id for a in db.query(Activity).filter_by(project_id=pid)}
        saved_codes = {o[1] for o in acts}
        n_links = 0
        for pred, succ in new_links:
            if (pred in saved_codes or pred in have) and (succ in saved_codes or succ in have):
                db.add(ActivityDependency(activity_id=ids[succ], predecessor_id=ids[pred]))
                n_links += 1
        log(db, user.id, "import.schedule", "project", pid, {"activities": len(acts), "milestones": len(objs) - len(acts), "links": n_links, "file": body.filename[:100], "source": sched["source"]})
        db.commit()
        save.links = n_links
        return len(objs)
    save.links = 0
    res = _verdict(out, body, save)
    ms = sum(1 for r in out if r["status"] == "ok" and r["message"].startswith("milestone"))
    res.update({"source": sched["source"], "file_project": sched["project"], "file_projects": sched["projects"], "notes": notes,
                "counts": {"activities": res["ok"] - ms, "milestones": ms, "links": len(new_links) if not res["committed"] else save.links}})
    return res
