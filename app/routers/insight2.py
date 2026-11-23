"""Global search, steering-committee pack, personal calendar, upcoming work, what-if scenarios."""
from datetime import date, timedelta
from html import escape

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_

from .. import rules
from ..alerts import rag_status
from ..config import WEEK_STARTS_ON_SUNDAY
from ..deps import current_user, get_db
from ..evm import compute_evm
from ..models import (ChangeRequest, CommItem, Document, GateReview, Issue, LeaveRequest, Lesson, Milestone, PlannedAllocation, Program,
                      Project, ProjectAction, ProjectDependency, Proposal, Risk, User, WeeklyReport, WeekSubmission)
from ..workcal import effective_capacity
from .dashboards import EXEC, overall_pct
from .projects import can_view, can_view_cost

router = APIRouter(tags=["search and planning"])
ws_of = lambda d: rules.week_start(d, WEEK_STARTS_ON_SUNDAY)


# ---------------- search ----------------
@router.get("/search")
def search(q: str, db=Depends(get_db), user: User = Depends(current_user)):
    q = q.strip()
    if len(q) < 2:
        raise HTTPException(422, "Type at least two characters")
    like = f"%{q}%"
    vis = {p.id: p for p in db.query(Project) if can_view(db, user, p)}
    lab = lambda pid: f"{vis[pid].number} · {vis[pid].name}" if pid in vis else ""
    out = {"projects": [{"id": p.id, "title": f"{p.number} · {p.name}", "sub": p.state, "link": f"#/projects/{p.id}"}
                        for p in vis.values() if any(q.lower() in (x or "").lower() for x in (p.number, p.name, p.client, p.sponsor))][:10],
           "people": [{"id": u.id, "title": u.full_name, "sub": " · ".join(x for x in (u.job_title, u.department, u.role) if x), "link": None}
                      for u in db.query(User).filter(User.active.is_(True), or_(User.full_name.ilike(like), User.staff_id.ilike(like), User.department.ilike(like))).limit(10)]}
    ids = list(vis) or [0]
    out["risks"] = [{"id": r.id, "title": r.title, "sub": lab(r.project_id), "link": f"#/projects/{r.project_id}"}
                    for r in db.query(Risk).filter(Risk.project_id.in_(ids), Risk.title.ilike(like)).limit(10)]
    out["issues"] = [{"id": i.id, "title": i.title, "sub": lab(i.project_id), "link": f"#/projects/{i.project_id}"}
                     for i in db.query(Issue).filter(Issue.project_id.in_(ids), Issue.title.ilike(like)).limit(10)]
    out["documents"] = [{"id": d.id, "title": d.filename, "sub": lab(d.project_id), "link": f"#/projects/{d.project_id}"}
                        for d in db.query(Document).filter(Document.project_id.in_(ids), Document.filename.ilike(like)).limit(10)]
    out["actions"] = [{"id": a.id, "title": a.title, "sub": lab(a.project_id), "link": f"#/projects/{a.project_id}"}
                      for a in db.query(ProjectAction).filter(ProjectAction.project_id.in_(ids), ProjectAction.title.ilike(like)).limit(10)]
    if user.role != "STAFF":
        out["lessons"] = [{"id": x.id, "title": x.recommendation[:120], "sub": lab(x.project_id), "link": "#/lessons"}
                          for x in db.query(Lesson).filter(or_(Lesson.what_happened.ilike(like), Lesson.recommendation.ilike(like))).limit(10)]
        out["programs"] = [{"id": g.id, "title": f"{g.code} · {g.name}", "sub": "", "link": f"#/programs/{g.id}"}
                           for g in db.query(Program).filter(or_(Program.code.ilike(like), Program.name.ilike(like))).limit(10)] if user.role in EXEC else []
    if user.role in EXEC:
        out["proposals"] = [{"id": x.id, "title": f"{x.number} · {x.name}", "sub": x.status, "link": "#/proposals"}
                            for x in db.query(Proposal).filter(or_(Proposal.number.ilike(like), Proposal.name.ilike(like))).limit(10)]
    out["total"] = sum(len(v) for v in out.values())
    return out


# ---------------- steering-committee pack ----------------
@router.get("/reports/board-pack.html", response_class=HTMLResponse)
def board_pack(program_id: int | None = None, db=Depends(get_db), user: User = Depends(current_user)):
    """One printable page per project plus a portfolio cover page, for the steering committee."""
    if user.role not in EXEC:
        raise HTTPException(403, "The steering-committee pack is for PMO, ADMIN, DECISION_MAKER and PROGRAM_MANAGER")
    today = date.today()
    q = db.query(Project).filter(Project.state.in_(("planning", "execution", "closing", "on_hold")))
    if program_id:
        q = q.filter(Project.program_id == program_id)
    projects = q.order_by(Project.number).all()
    colour = {"RED": "#c0392b", "AMBER": "#d68910", "GREEN": "#1e8449", "GREY": "#7f8c8d"}
    pill = lambda r: f"<span class='pill' style='background:{colour.get(r, '#777')}'>{escape(r)}</span>"
    rows, pages = [], []
    for p in projects:
        r = rag_status(db, p)
        e = compute_evm(db, p, today) if p.state in ("execution", "closing") else {}
        pct = overall_pct(db, p, today) if p.state in ("execution", "closing") else None
        rows.append(f"<tr><td>{escape(p.number)}</td><td>{escape(p.name)}</td><td>{escape(p.state)}</td><td>{pill(r)}</td><td>{'' if pct is None else f'{pct:.0f}%'}</td>"
                    f"<td>{e.get('CPI') or ''}</td><td>{e.get('SPI') or ''}</td></tr>")
        risks = db.query(Risk).filter(Risk.project_id == p.id, Risk.status.in_(("open", "mitigating"))).all()
        risks.sort(key=lambda x: -x.score)
        ms = db.query(Milestone).filter(Milestone.project_id == p.id, Milestone.achieved_on.is_(None)).order_by(Milestone.due_date).limit(4).all()
        asks = [f"Change request: {escape(c.description[:120])}" for c in db.query(ChangeRequest).filter(ChangeRequest.project_id == p.id, ChangeRequest.status.in_(("requested", "deferred")))]
        asks += [f"Stage gate review: {escape(g.gate.replace('_', ' → '))}" for g in db.query(GateReview).filter(GateReview.project_id == p.id, GateReview.status.in_(("pending", "deferred")))]
        rep = db.query(WeeklyReport).filter_by(project_id=p.id).order_by(WeeklyReport.week_start.desc()).first()
        narrative = (rep.narrative or {}) if rep else {}
        money = ""
        if e.get("available") and can_view_cost(db, user, p):
            money = f"<p><b>Budget</b> {e['BAC']:,.0f} {escape(e['currency'])} · <b>Spent</b> {e['AC']:,.0f} · <b>Forecast</b> {(e.get('EAC') or 0):,.0f}</p>"
        pages.append(
            f"<section class='page'><h2>{escape(p.number)} · {escape(p.name)} {pill(r)}</h2>"
            f"<p>State: {escape(p.state)} · Sponsor: {escape(p.sponsor or '—')} · Plan {p.planned_start or '—'} → {p.planned_end or '—'}"
            f"{'' if pct is None else f' · Progress {pct:.0f}%'}{'' if not e.get('CPI') else f' · CPI {e['CPI']} · SPI {e['SPI']}'}</p>{money}"
            f"<h3>Since last report</h3><p>{escape(str(narrative.get('accomplishments') or '—'))}</p>"
            f"<h3>Next period</h3><p>{escape(str(narrative.get('next_steps') or '—'))}</p>"
            f"<h3>Top risks</h3><ul>{''.join(f'<li>{escape(x.title)} (score {x.score})</li>' for x in risks[:3]) or '<li>None open</li>'}</ul>"
            f"<h3>Next milestones</h3><ul>{''.join(f'<li>{escape(m.name)} — {m.due_date}{' (late)' if m.due_date < today else ''}</li>' for m in ms) or '<li>None</li>'}</ul>"
            f"<h3>Decisions needed from the committee</h3><ul>{''.join(f'<li>{a}</li>' for a in asks) or '<li>None</li>'}</ul></section>")
    title = "Steering committee pack" + (f" · {escape(db.get(Program, program_id).name)}" if program_id and db.get(Program, program_id) else "")
    cover = (f"<section class='page'><h1>{title}</h1><p>As of {today} · {len(projects)} projects</p>"
             f"<table><thead><tr><th>No.</th><th>Project</th><th>State</th><th>Status</th><th>Progress</th><th>CPI</th><th>SPI</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"
             f"<p class='muted'>Proposals waiting for a decision: {db.query(Proposal).filter(Proposal.status.in_(('submitted', 'deferred'))).count()}</p></section>")
    css = ("body{font:13px/1.45 system-ui,sans-serif;color:#111;margin:0}.page{max-width:900px;margin:24px auto;padding:0 18px;page-break-after:always}"
           "h1,h2{color:#0b2545}h2{border-bottom:2px solid #c9a227;padding-bottom:3px}h3{margin:12px 0 2px;font-size:13px;color:#0b2545}"
           ".pill{color:#fff;border-radius:10px;padding:1px 8px;font-size:11px;vertical-align:middle}table{border-collapse:collapse;width:100%}"
           "th,td{border:1px solid #ccc;padding:4px 8px;text-align:start}th{background:#0b2545;color:#fff}.muted{color:#666}@media print{.page{margin:0 auto}}")
    return HTMLResponse(f"<!doctype html><html><head><meta charset='utf-8'><title>{title}</title><style>{css}</style></head><body>{cover}{''.join(pages)}</body></html>")


# ---------------- my calendar ----------------
@router.get("/me/calendar")
def my_calendar(days: int = 28, db=Depends(get_db), user: User = Depends(current_user)):
    """What is coming up for me in the next weeks: reports, timesheet weeks, communications, milestones, actions, leave."""
    today = date.today()
    end = today + timedelta(days=min(max(days, 7), 90))
    out = []
    add = lambda d, kind, title, link: out.append({"date": d.isoformat(), "kind": kind, "title": title, "link": link}) if today - timedelta(days=7) <= d <= end else None
    mine = db.query(Project).filter(Project.pm_id == user.id, Project.state.in_(("planning", "execution", "closing"))).all()
    ws = ws_of(today)
    while ws <= end:
        thu = ws + timedelta(days=4)
        for p in mine:
            if p.state == "execution" and not db.query(WeeklyReport).filter_by(project_id=p.id, week_start=ws).first():
                add(thu, "weekly_report", f"{p.number}: weekly report", f"#/projects/{p.id}")
        if user.role in ("STAFF", "PM") and not db.query(WeekSubmission).filter_by(user_id=user.id, week_start=ws).first():
            add(thu, "timesheet_week", f"Submit timesheet for week of {ws}", "#/timesheet")
        ws += timedelta(days=7)
    for p in mine:
        for m in db.query(Milestone).filter(Milestone.project_id == p.id, Milestone.achieved_on.is_(None)):
            add(m.due_date, "milestone", f"{p.number}: {m.name}", f"#/projects/{p.id}")
    from .pmtools import c_out
    for c in db.query(CommItem).filter(or_(CommItem.owner_id == user.id, CommItem.project_id.in_([p.id for p in mine] or [0]))):
        due = c_out(c, {})["next_due"]
        if due:
            add(due, "communication", f"{c.audience}: {c.information}", f"#/projects/{c.project_id}")
    for a in db.query(ProjectAction).filter(ProjectAction.owner_id == user.id, ProjectAction.status == "open", ProjectAction.due_date.isnot(None)):
        add(a.due_date, "action", a.title, f"#/projects/{a.project_id}")
    for lv in db.query(LeaveRequest).filter(LeaveRequest.user_id == user.id, LeaveRequest.status == "approved", LeaveRequest.end >= today):
        add(max(lv.start, today), "leave", f"Leave {lv.start} – {lv.end}", "#/leave")
    out.sort(key=lambda x: (x["date"], x["kind"]))
    for x in out:
        x["overdue"] = x["date"] < today.isoformat()
    return out


# ---------------- upcoming work ----------------
@router.get("/me/upcoming")
def my_upcoming(weeks: int = 8, db=Depends(get_db), user: User = Depends(current_user)):
    start = ws_of(date.today())
    wks = [start + timedelta(days=7 * i) for i in range(max(1, min(weeks, 16)))]
    names = {p.id: f"{p.number} · {p.name}" for p in db.query(Project)}
    rows = db.query(PlannedAllocation).filter(PlannedAllocation.user_id == user.id, PlannedAllocation.week_start >= wks[0], PlannedAllocation.week_start <= wks[-1]).all()
    by_proj = {}
    for a in rows:
        by_proj.setdefault(a.project_id, {})[a.week_start.isoformat()] = a.hours
    return {"weeks": [w.isoformat() for w in wks],
            "capacity": [effective_capacity(db, user.capacity_hours_week, w, user.id) for w in wks],
            "projects": [{"project_id": pid, "project": names.get(pid), "hours": [h.get(w.isoformat(), 0) for w in wks]} for pid, h in by_proj.items()],
            "totals": [sum(h.get(w.isoformat(), 0) for h in by_proj.values()) for w in wks]}


# ---------------- what-if ----------------
class Scenario(BaseModel):
    project_id: int
    action: str                      # stop | delay
    weeks: int = Field(4, ge=1, le=52)


class WhatIfIn(BaseModel):
    changes: list[Scenario] = Field(min_length=1, max_length=10)
    horizon_weeks: int = Field(12, ge=4, le=26)


@router.post("/portfolio/what-if")
def what_if(body: WhatIfIn, db=Depends(get_db), user: User = Depends(current_user)):
    """Effect of stopping or delaying projects on capacity (over-allocation) and on dependent projects. Nothing is saved."""
    if user.role not in EXEC:
        raise HTTPException(403, "What-if requires PMO, ADMIN, DECISION_MAKER or PROGRAM_MANAGER")
    start = ws_of(date.today())
    wks = [start + timedelta(days=7 * i) for i in range(body.horizon_weeks)]
    lo, hi = wks[0], wks[-1] + timedelta(days=6 * 7)
    allocs = db.query(PlannedAllocation).filter(PlannedAllocation.week_start >= lo, PlannedAllocation.week_start <= hi).all()
    change = {c.project_id: c for c in body.changes}
    for c in body.changes:
        if c.action not in ("stop", "delay"):
            raise HTTPException(422, "action must be stop or delay")
        if not db.get(Project, c.project_id):
            raise HTTPException(404, f"Project {c.project_id} not found")

    def demand(apply):
        d = {}
        for a in allocs:
            c = change.get(a.project_id) if apply else None
            if c and c.action == "stop":
                continue                                         # stopped: its planned hours are freed
            w = a.week_start + timedelta(days=7 * c.weeks) if c else a.week_start
            d[(a.user_id, w)] = d.get((a.user_id, w), 0.0) + a.hours
        return d
    people = db.query(User).filter(User.active.is_(True), User.role.in_(("STAFF", "PM"))).all()
    caps = {(u.id, w): effective_capacity(db, u.capacity_hours_week, w, u.id) for u in people for w in wks}

    def summary(d):
        over = [(u.full_name, w) for u in people for w in wks if d.get((u.id, w), 0) > caps[(u.id, w)] + 0.01]
        tot = [{"week_start": w.isoformat(), "demand": round(sum(d.get((u.id, w), 0) for u in people), 1),
                "supply": round(sum(caps[(u.id, w)] for u in people), 1)} for w in wks]
        return {"over_allocated_weeks": len(over), "over": [{"user": n, "week_start": w.isoformat()} for n, w in over[:30]], "weeks": tot}
    before, after = summary(demand(False)), summary(demand(True))
    effects = []
    for c in body.changes:
        p = db.get(Project, c.project_id)
        shift = c.weeks * 7 if c.action == "delay" else 10 ** 5
        freed = sum(a.hours for a in allocs if a.project_id == p.id and a.week_start <= wks[-1])
        e = compute_evm(db, p, date.today()) if p.state in ("execution", "closing") and can_view_cost(db, user, p) else {}
        effects.append({"project_id": p.id, "project": f"{p.number} · {p.name}", "action": c.action, "weeks": c.weeks if c.action == "delay" else None,
                        "old_end": p.planned_end, "new_end": (p.planned_end + timedelta(days=shift)) if p.planned_end and c.action == "delay" else None,
                        "hours_freed": round(freed, 1) if c.action == "stop" else 0,
                        "budget_not_spent": round(e["BAC"] - e["AC"], 0) if c.action == "stop" and e.get("available") else None,
                        "currency": e.get("currency")})
        for dep in db.query(ProjectDependency).filter_by(predecessor_id=p.id):
            m = db.get(Milestone, dep.milestone_id) if dep.milestone_id else None
            if m and m.achieved_on:
                continue
            delivers = (m.due_date if m else p.planned_end)
            if delivers and (c.action == "stop" or delivers + timedelta(days=shift) > dep.needed_by):
                w_ = db.get(Project, dep.project_id)
                effects[-1].setdefault("hits", []).append({"project": f"{w_.number} · {w_.name}", "needed_by": dep.needed_by,
                                                           "would_arrive": (delivers + timedelta(days=shift)) if c.action == "delay" else None})
    return {"before": before, "after": after, "effects": effects}
