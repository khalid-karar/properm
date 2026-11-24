"""Project book -> reviewed plan (flow chart 1.2 and 1.3). Analyze a tender book or brief (Arabic or English, text, DOCX, PDF or scan),
review the draft, then apply: requirements, deliverables, milestones, tasks with hours, staff proposals, risks and compliance items."""
import calendar
import contextvars
import copy
import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from math import ceil

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from .. import ai, brief, docread, plandomains, progress, rules
from ..audit import log
from ..config import WEEK_STARTS_ON_SUNDAY
from ..deps import current_user, get_db, get_params, require_roles
from ..models import (Activity, ActivityStaffLimit, AiDraft, Assignment, Assumption, ComplianceRequirement, Deliverable, Document, Milestone, PlannedAllocation,
                      Project, ProjectCharter, ProjectCompliance, QualityItem, CommItem, Requirement, ResourceRequest, Risk, Stakeholder, StakeholderEngagement, User, UserSkill)
from ..workcal import effective_capacity
from .projects import can_manage, get_project, need_manage
from .skills import _like

router = APIRouter(tags=["project book"])
MANAGE = ("PM", "PMO", "ADMIN")
ws_of = lambda d: rules.week_start(d, WEEK_STARTS_ON_SUNDAY)


def add_months(d: date, m: int) -> date:
    y, mo = divmod(d.month - 1 + m, 12)
    y, mo = d.year + y, mo + 1
    return date(y, mo, min(d.day, calendar.monthrange(y, mo)[1]))


def span(start: date, a: dict, ph: dict | None = None) -> tuple[date, date]:
    s = add_months(start, int(a["start_month"]))
    e = add_months(start, int(a["end_month"])) - timedelta(days=1)
    return s, max(s, e)


# ---------------- staffing ----------------
def propose(db, start: date, acts: list[dict], exclude_user_ids=()) -> dict:
    """For each task: a person with the needed skill who has free hours every week of the task, or unassigned with the reason."""
    people = [u for u in db.query(User).filter(User.active.is_(True), User.role.in_(("STAFF", "PM"))) if u.id not in exclude_user_ids]
    skills: dict[int, list] = {}
    for s in db.query(UserSkill):
        skills.setdefault(s.user_id, []).append(s)
    booked: dict[tuple, float] = {}
    for pa in db.query(PlannedAllocation):
        booked[(pa.user_id, pa.week_start)] = booked.get((pa.user_id, pa.week_start), 0.0) + pa.hours
    out = {}
    for a in sorted(acts, key=lambda x: (x["start_month"], -float(x["planned_hours"]))):
        s, e = span(start, a)
        weeks = []
        w = ws_of(s)
        while w <= e:
            weeks.append(w)
            w += timedelta(days=7)
        need = round(float(a["planned_hours"]) / max(1, len(weeks)), 1)
        role = a.get("role") or ""
        cand = []
        for u in people:
            lvl = max([k.level for k in skills.get(u.id, []) if role and _like(role, k.skill)] or [0])
            if not lvl and role and u.job_title and _like(role, u.job_title):
                lvl = 2
            if lvl:
                cand.append((u, lvl))
        if not role:
            out[a["code"]] = {"user_id": None, "reason": "No role could be read for this task"}
            continue
        if not cand:
            out[a["code"]] = {"user_id": None, "reason": f"Nobody has the skill '{role}'", "need_per_week": need}
            continue
        best, best_free = None, -1.0
        for u, lvl in sorted(cand, key=lambda c: -c[1]):
            free = min(effective_capacity(db, u.capacity_hours_week, w, u.id) - booked.get((u.id, w), 0.0) for w in weeks)
            if free >= need - 0.01:
                best = (u, lvl, free)
                break
            best_free = max(best_free, free)
        if best:
            u, lvl, free = best
            for w in weeks:
                booked[(u.id, w)] = booked.get((u.id, w), 0.0) + need
            out[a["code"]] = {"user_id": u.id, "name": u.full_name, "level": lvl, "need_per_week": need, "free_per_week": round(free, 1)}
        else:
            out[a["code"]] = {"user_id": None, "need_per_week": need, "reason": f"People with '{role}' exist but none has {need:g} free hours a week (best: {max(best_free, 0):g})"}
    return out


# ---------------- analyze ----------------
class AnalyzeIn(BaseModel):
    document_id: int | None = None
    text: str | None = Field(None, max_length=1_000_000)
    lang: str = "auto"


def _refine(db, result: dict, lang: str, tick=None) -> list[str]:
    """When the Saudi-hosted model is live, let it re-read each phase. Rules stay as the fallback for any phase it fails on."""
    notes = []
    if ai.status()["mode"] != "live":
        return notes
    total = len(result["phases"])
    for idx, ph in enumerate(result["phases"]):
        if tick:
            tick(idx, total)
        text = ph.get("text")
        if not text:
            continue
        try:
            raw = ai._live("brief", {}, brief.refine_prompt(ph["name"], text, lang))
            data = ai.extract_json(raw)
            tasks = [t for t in data.get("tasks", []) if isinstance(t, dict) and t.get("name")][:15]
            if tasks:
                result["activities"] = [a for a in result["activities"] if a["phase"] != ph["n"]]
                for j, t in enumerate(tasks, 1):
                    result["activities"].append({"code": f"P{ph['n']}-{j:02d}", "name": str(t["name"])[:200], "description": str(t["name"]), "phase": ph["n"],
                                                 "planned_hours": float(max(4, min(float(t.get("hours") or 40), 2000))), "start_month": ph["start_month"], "end_month": ph["end_month"],
                                                 "role": t.get("role") or None, "page": ph.get("source_page"), "estimate": True, "by": "model"})
            have = {re.sub(r"\W+", "", brief._norm_ar(r["text"]))[:60] for r in result["requirements"]}
            for q in data.get("requirements", [])[:20]:
                k = re.sub(r"\W+", "", brief._norm_ar(str(q)))[:60]
                if k and k not in have:
                    have.add(k)
                    result["requirements"].append({"code": "", "title": brief._short(str(q)), "text": str(q), "page": ph.get("source_page"), "priority": "must", "phase": ph["n"], "section": "model", "by": "model"})
            notes.append(f"Phase {ph['n']} refined by the model")
        except Exception as e:                    # any failure: keep the rule-based result for this phase
            notes.append(f"Phase {ph['n']}: model not used ({getattr(e, 'msg', type(e).__name__)})")
    for i, r in enumerate(result["requirements"], 1):
        r["code"] = f"R-{i:03d}"
    return notes


@router.post("/projects/{pid}/brief/analyze", status_code=201)
def analyze_endpoint(pid: int, body: AnalyzeIn, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE)), progress_id: str | None = Header(None, alias="X-Progress-Id")):
    return analyze(pid, body, db, user, progress_id)


@router.get("/project-intake/progress/{key}")
def analyze_progress(key: str, user: User = Depends(require_roles(*MANAGE))):
    """What the running analysis is doing: {pct, step, info, seconds}. 404 until the job reports its first step."""
    j = progress.get(user.id, key)
    if not j:
        raise HTTPException(404, "No progress yet")
    return j


def analyze(pid: int, body: AnalyzeIn, db, user: User, progress_id: str | None = None):
    say = lambda pct, step, **info: progress.update(user.id, progress_id, pct, step, **info)
    p = get_project(db, pid)
    need_manage(db, user, p)
    if p.state not in ("tendering", "planning"):
        raise HTTPException(409, "A project book can be analysed while the project is in tendering or planning")
    prm = get_params(db)
    if not prm["ai_enabled"]:
        raise HTTPException(403, "The AI assistant is switched off by the administrator")
    since = datetime.now(timezone.utc) - timedelta(hours=1)
    if db.query(AiDraft).filter(AiDraft.created_by == user.id, AiDraft.created_at >= since).count() >= int(prm["ai_hourly_limit"]):
        raise HTTPException(429, "AI request limit reached for this hour")
    warnings, source = [], None
    say(3, "read")
    if body.document_id:
        doc = db.get(Document, body.document_id)
        if not doc or doc.project_id != pid:
            raise HTTPException(404, "Document not found in this project")
        try:
            rd = docread.read_document(doc.filename, doc.content)
        except docread.ReadError as e:
            raise HTTPException(422, str(e))
        pages, warnings, source = rd["pages"], rd["warnings"], {"document_id": doc.id, "filename": doc.filename, "method": rd["method"]}
    elif body.text and len(body.text.strip()) >= 40:
        pages, source = [docread.clean(body.text)], {"method": "pasted"}
    else:
        raise HTTPException(422, "Give a document_id of an uploaded file, or paste at least a few lines of text")
    say(10, "rules")
    result = brief.analyze(pages, body.lang)
    result["meta"]["source"] = source
    result["domains"] = plandomains.generate(result)
    say(15, "phases", n=0, total=len(result["phases"]))
    notes = _refine(db, result, result["meta"]["language"], tick=lambda i, n: say(15 + 40 * i / max(1, n), "phase", n=i + 1, total=n))
    if ai.status()["mode"] == "live":
        cfg = ai.resolve()                              # resolved here: the worker threads have no request/tenant context
        done = []
        say(55, "sections", n=0, total=len(plandomains.DOMAINS))
        result["domains"], dnotes = plandomains.generate_live(result, lambda prompt: ai._live("brief", {}, prompt, cfg),
                                                              on_done=lambda name: (done.append(name), say(55 + 40 * len(done) / len(plandomains.DOMAINS), "sections", n=len(done), total=len(plandomains.DOMAINS))))
        notes += dnotes
    say(96, "save")
    for ph in result["phases"]:
        ph.pop("text", None)
    if not result["activities"]:
        warnings.append("No tasks could be found. Check that the text is the scope of work, or paste the scope section.")
    st = ai.status()
    d = AiDraft(kind="brief", project_id=pid, input_text=None, output={**result, "notes": notes, "warnings": warnings}, model=st["model"], mode=st["mode"], created_by=user.id)
    db.add(d)
    db.flush()
    log(db, user.id, "brief.analyzed", "project", pid, {"draft_id": d.id, "pages": len(pages), "requirements": len(result["requirements"]), "tasks": len(result["activities"]), "mode": st["mode"], "offsite_demo": st["offsite_demo"]})
    db.commit()
    say(100, "done")
    return {"draft_id": d.id, "mode": st["mode"], "warnings": warnings, "counts": _counts(result)}


def _counts(r: dict) -> dict:
    return {k: len(r[k]) for k in ("phases", "requirements", "deliverables", "activities", "team", "risks", "compliance", "terms")}


def _draft(db, user, pid, did) -> tuple[Project, AiDraft]:
    p = get_project(db, pid)
    need_manage(db, user, p)
    d = db.get(AiDraft, did)
    if not d or d.kind != "brief" or d.project_id != pid:
        raise HTTPException(404, "Draft not found")
    return p, d


def _start(p: Project, given: date | None) -> date:
    return given or p.planned_start or date.today()


@router.get("/projects/{pid}/brief")
def list_drafts(pid: int, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p = get_project(db, pid)
    need_manage(db, user, p)
    return [{"id": d.id, "status": d.status, "created_at": d.created_at, "counts": _counts(d.output), "meta": d.output.get("meta")}
            for d in db.query(AiDraft).filter_by(project_id=pid, kind="brief").order_by(AiDraft.id.desc()).limit(20)]


@router.get("/projects/{pid}/brief/{did}")
def get_draft(pid: int, did: int, start: date | None = None, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p, d = _draft(db, user, pid, did)
    s = _start(p, start)
    if "domains" not in d.output:
        d.output = {**d.output, "domains": plandomains.generate(d.output)}
        db.commit()
    return {"id": d.id, "status": d.status, "start": s, "draft": d.output, "staffing": propose(db, s, d.output["activities"])}


class StaffingIn(BaseModel):
    activities: list[dict]
    start: date | None = None


@router.post("/projects/{pid}/brief/{did}/staffing")
def staffing(pid: int, did: int, body: StaffingIn, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p, d = _draft(db, user, pid, did)
    for a in body.activities:
        if not {"code", "planned_hours", "start_month", "end_month"} <= set(a):
            raise HTTPException(422, "Each activity needs code, planned_hours, start_month and end_month")
    return propose(db, _start(p, body.start), body.activities)


class DomainIn(BaseModel):
    action: str = Field(pattern="^(accept|modify|reject)$")
    items: list[dict] | None = None
    feedback: str | None = Field(default=None, max_length=1000)


def _domain_model(lang):
    if ai.status()["mode"] != "live":
        return None

    def run(name, before, feedback):
        prompt = (f"Rewrite this {name} plan list for a project. Return JSON {{\"items\": [...]}} with the same fields per item. "
                  f"Reviewer feedback to apply: {feedback}\nCurrent list: {json.dumps(before, ensure_ascii=False)[:6000]}\nLanguage: {lang}")
        return ai.extract_json(ai._live("brief", {}, prompt)).get("items", [])
    return run


@router.post("/projects/{pid}/brief/{did}/domains/{name}")
def review_domain(pid: int, did: int, name: str, body: DomainIn, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p, d = _draft(db, user, pid, did)
    if d.status != "draft":
        raise HTTPException(409, f"Draft already {d.status}")
    if name not in plandomains.DOMAINS:
        raise HTTPException(404, "Unknown plan domain")
    out = copy.deepcopy(d.output)
    doms = out.get("domains") or plandomains.generate(out)
    dom = doms[name]
    if body.action == "accept":
        plandomains.accept(dom, user.id)
    elif body.action == "modify":
        if body.items is None:
            raise HTTPException(422, "Send the edited items")
        plandomains.modify(name, dom, body.items, user.id)
    else:
        if not (body.feedback or "").strip():
            raise HTTPException(422, "Tell the assistant what was wrong so the new version is better")
        plandomains.reject(name, dom, out, body.feedback.strip(), user.id, _domain_model(out.get("meta", {}).get("language")))
    out["domains"] = doms
    d.output = out
    log(db, user.id, f"brief.domain.{body.action}", "project", pid, {"draft_id": d.id, "domain": name})
    db.commit()
    return {"domain": name, **dom}


# ---------------- apply ----------------
class ApplyIn(BaseModel):
    draft: dict | None = None                # the reviewer's edited version; omit to accept as drafted
    start: date | None = None
    assignments: dict[str, int | None] | None = None      # task code -> user id; null = unassigned. Omit to accept the proposals
    sections: list[str] = ["requirements", "deliverables", "activities", "milestones", "risks", "compliance", "charter", "assumptions", "domains"]


@router.post("/projects/{pid}/brief/{did}/apply")
def apply(pid: int, did: int, body: ApplyIn, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p, d = _draft(db, user, pid, did)
    if d.status != "draft":
        raise HTTPException(409, f"Draft already {d.status}")
    if p.state != "planning":
        raise HTTPException(409, "Move the project to planning before applying a plan to it")
    out = {**d.output, **(body.draft or {})}
    start = _start(p, body.start)
    secs = set(body.sections)
    acts = out["activities"] if "activities" in secs else []
    codes = [a["code"] for a in acts]
    if len(set(codes)) != len(codes):
        raise HTTPException(422, "Task codes must be unique")
    if {a.code for a in db.query(Activity).filter_by(project_id=pid)} & set(codes):
        raise HTTPException(409, "Some task codes already exist in this project")
    pnums = {ph.get("n") for ph in out.get("phases", [])}
    for a in acts:
        try:
            hrs = float(a.get("planned_hours") or 0)
        except (TypeError, ValueError):
            hrs = 0
        if hrs <= 0:
            raise HTTPException(422, f"Task {a.get('code')} needs hours above zero")
        if not str(a.get("code") or "").strip() or not str(a.get("name") or "").strip():
            raise HTTPException(422, "Every task needs a code and a name")
        if a.get("phase") not in pnums:
            raise HTTPException(422, f"Task {a['code']} points to a phase that does not exist")
        if float(a.get("end_month") or 0) < float(a.get("start_month") or 0):
            raise HTTPException(422, f"Task {a['code']} ends before it starts")
    for key, label in (("requirements", "title"), ("deliverables", "name"), ("risks", "title"), ("compliance", "title")):
        if key in secs:
            for it in out.get(key, []):
                if not str(it.get(label) or "").strip():
                    raise HTTPException(422, f"A {key[:-1] if key != 'compliance' else 'compliance item'} has no {label}; fill it in or delete it")
                if key == "deliverables" and it.get("phase") not in pnums:
                    raise HTTPException(422, f"Deliverable {it.get('code')} points to a phase that does not exist")
    for ph in out.get("phases", []):
        if not str(ph.get("name") or "").strip():
            raise HTTPException(422, "A phase has no name; fill it in or delete it")
    prop = propose(db, start, acts) if acts else {}
    pick = body.assignments if body.assignments is not None else {c: v.get("user_id") for c, v in prop.items()}
    n = {"requirements": 0, "deliverables": 0, "activities": 0, "milestones": 0, "assigned": 0, "unassigned": 0, "risks": 0, "compliance": 0, "assumptions": 0, "resource_requests": 0}
    amap, last_in_phase, owner_of = {}, {}, {}
    phases = {ph["n"]: ph for ph in out.get("phases", [])}
    for a in sorted(acts, key=lambda x: (x["phase"], x["code"])):
        s, e = span(start, a)
        row = Activity(project_id=pid, code=a["code"], name=a["name"][:300], phase="execution", planned_hours=float(a["planned_hours"]), planned_start=s, planned_end=e)
        db.add(row)
        db.flush()
        amap[a["code"]] = row
        last_in_phase[a["phase"]] = row
        n["activities"] += 1
    unassigned: dict[str, list] = {}
    existing = {x.user_id for x in db.query(Assignment).filter_by(project_id=pid)}
    for a in acts:
        row, uid = amap[a["code"]], pick.get(a["code"])
        s, e = span(start, a)
        if uid:
            u = db.get(User, uid)
            if not u or not u.active:
                raise HTTPException(422, f"Task {a['code']}: that person is not active")
            if uid not in existing:
                db.add(Assignment(project_id=pid, user_id=uid))
                existing.add(uid)
            db.add(ActivityStaffLimit(activity_id=row.id, user_id=uid, max_hours=float(a["planned_hours"])))
            weeks, w = [], ws_of(s)
            while w <= e:
                weeks.append(w)
                w += timedelta(days=7)
            per = round(float(a["planned_hours"]) / max(1, len(weeks)), 2)
            for w in weeks:
                pa = db.query(PlannedAllocation).filter_by(project_id=pid, user_id=uid, week_start=w).first()
                if pa:
                    pa.hours += per
                else:
                    db.add(PlannedAllocation(project_id=pid, user_id=uid, week_start=w, hours=per))
            owner_of[a["code"]] = uid
            n["assigned"] += 1
        else:
            n["unassigned"] += 1
            unassigned.setdefault(a.get("role") or "Unspecified role", []).append((a, s, e))
    for role, items in unassigned.items():                # one resource request per missing role, for the PMO to fill
        s0, e0 = min(i[1] for i in items), max(i[2] for i in items)
        wk = max(1, ceil((e0 - s0).days / 7))
        hrs = round(sum(float(i[0]["planned_hours"]) for i in items) / wk, 1)
        db.add(ResourceRequest(project_id=pid, requested_by=user.id, skill=role[:200], hours_per_week=hrs, start=s0, end=e0,
                               note="From the project book. Tasks: " + ", ".join(i[0]["code"] for i in items)[:400]))
        n["resource_requests"] += 1
    reqs = {}
    delivs_by_phase: dict[int, list] = {}
    if "deliverables" in secs:
        for dv in out.get("deliverables", []):
            ph = phases.get(dv["phase"])
            _, due = span(start, {"start_month": ph["start_month"], "end_month": ph["end_month"]}) if ph else (None, None)
            lastact = last_in_phase.get(dv["phase"])
            row = Deliverable(project_id=pid, code=dv["code"][:40], name=dv["name"][:300], kind="deliverable", description=dv.get("description"),
                              acceptance_criteria="Accepted in writing by the client after review (see the project terms).", due_date=due,
                              activity_id=lastact.id if lastact else None, owner_id=None)
            db.add(row)
            db.flush()
            delivs_by_phase.setdefault(dv["phase"], []).append(row)
            n["deliverables"] += 1
    if "requirements" in secs:
        for r in out.get("requirements", []):
            ds = delivs_by_phase.get(r.get("phase")) or []
            db.add(Requirement(project_id=pid, code=r["code"][:40], title=r["title"][:300], description=r["text"],
                               source=f"Book p.{r['page']} · {r.get('section') or ''}"[:200], priority="must" if r.get("priority") == "must" else "should",
                               status="proposed", deliverable_id=ds[0].id if len(ds) == 1 else None))
            n["requirements"] += 1
    if "milestones" in secs:
        for ph in phases.values():
            _, due = span(start, {"start_month": ph["start_month"], "end_month": ph["end_month"]})
            lastact = last_in_phase.get(ph["n"])
            db.add(Milestone(project_id=pid, name=(f"اكتمال {ph['name']}" if d.output.get("meta", {}).get("language") == "ar" else f"{ph['name']} complete")[:300], due_date=due, activity_id=lastact.id if lastact else None))
            n["milestones"] += 1
    if "risks" in secs:
        for r in out.get("risks", []):
            db.add(Risk(project_id=pid, title=r["title"][:300], category=r.get("category"), probability=int(r["probability"]), impact=int(r["impact"]), response=r.get("response")))
            n["risks"] += 1
    if "compliance" in secs:
        have = {x.project_id for x in db.query(ProjectCompliance).filter_by(project_id=pid)}
        for c in out.get("compliance", []):
            lib = db.query(ComplianceRequirement).filter_by(framework=c["framework"], title=c["title"][:300]).first()
            if not lib:
                k = db.query(ComplianceRequirement).count() + 1
                code = f"BK-{c['framework'][:8].upper()}-{k}"
                while db.query(ComplianceRequirement).filter_by(code=code).first():
                    k += 1
                    code = f"BK-{c['framework'][:8].upper()}-{k}"
                lib = ComplianceRequirement(code=code, framework=c["framework"][:60], title=c["title"][:300], description="Read from the project book", active=True)
                db.add(lib)
                db.flush()
            if not db.query(ProjectCompliance).filter_by(project_id=pid, requirement_id=lib.id).first():
                db.add(ProjectCompliance(project_id=pid, requirement_id=lib.id, status="not_started"))
                n["compliance"] += 1
    if "charter" in secs and not db.query(ProjectCharter).filter_by(project_id=pid).first():
        meta = out.get("meta", {})
        db.add(ProjectCharter(project_id=pid, purpose=meta.get("name"), objectives="\n".join(f"{i}. {o}" for i, o in enumerate(out.get("objectives", []), 1)) or None,
                              in_scope="\n".join(f"{ph['n']}. {ph['name']}" for ph in phases.values()) or None, status="draft"))
    if "assumptions" in secs:
        for t in out.get("assumptions", []):
            db.add(Assumption(project_id=pid, kind="assumption", text=t[:600]))
            n["assumptions"] += 1
        for t in out.get("terms", []):
            if t["kind"] in ("acceptance", "penalty"):
                db.add(Assumption(project_id=pid, kind="constraint", text=f"{t['text']} (book p.{t['page']})"[:600]))
                n["assumptions"] += 1
    n["domain_items"], n["domains_skipped"] = 0, 0
    if "domains" in secs:
        for dn, dom in (out.get("domains") or {}).items():
            if dom["status"] not in ("accepted", "modified"):
                n["domains_skipped"] += 1
                continue
            for it in dom["items"]:
                if dn == "stakeholders":
                    st = Stakeholder(project_id=pid, name=it["name"][:200], organisation=it.get("organisation"), role=it.get("role"), power=it.get("power") or 3, interest=it.get("interest") or 3, engagement=it.get("engagement"))
                    db.add(st)
                    db.flush()
                    db.add(StakeholderEngagement(stakeholder_id=st.id, project_id=pid, plan=it.get("engagement")))
                elif dn == "communication":
                    db.add(CommItem(project_id=pid, audience=it["audience"][:200], information=(it.get("information") or "")[:300], method=(it.get("method") or "")[:100], frequency=it.get("frequency") or "monthly"))
                elif dn == "quality":
                    db.add(QualityItem(project_id=pid, kind=it.get("kind") or "inspection", title=it["title"][:300], severity="low", status="open", note=it.get("note")))
                else:
                    label = {"cost": "Cost plan", "procurement": "Procurement and payment", "change": "Change control"}[dn]
                    body_t = (f"{it['name']}: {it.get('hours', 0)} h. {it.get('note') or ''}" if dn == "cost" else f"{it.get('kind', '')}: {it['text']}" if dn == "procurement" else it["text"])
                    db.add(Assumption(project_id=pid, kind="constraint", text=f"[{label}] {body_t}"[:600]))
                n["domain_items"] += 1
    d.output = {**out}
    d.status, d.reviewed_by, d.reviewed_at = "applied", user.id, datetime.now(timezone.utc)
    log(db, user.id, "brief.applied", "project", pid, {"draft_id": d.id, **n, "edited": body.draft is not None})
    db.commit()
    return {"applied": True, **n}


@router.post("/projects/{pid}/brief/{did}/reject")
def reject(pid: int, did: int, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p, d = _draft(db, user, pid, did)
    if d.status != "draft":
        raise HTTPException(409, f"Draft already {d.status}")
    d.status, d.reviewed_by, d.reviewed_at = "rejected", user.id, datetime.now(timezone.utc)
    log(db, user.id, "brief.rejected", "project", pid, {"draft_id": d.id})
    db.commit()
    return {"status": "rejected"}


# ---------------- start a project from the book ----------------

class BookIn(BaseModel):
    filename: str | None = Field(None, max_length=200)
    content_b64: str | None = None
    text: str | None = None
    lang: str | None = None


class BookConfirm(BookIn):
    number: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=300)
    planned_start: date
    planned_end: date
    client: str | None = Field(None, max_length=200)
    state: str = "planning"


def _book_pages(body: BookIn):
    import base64
    import binascii
    import os
    from .intake import DOC_EXT, MAX_DOC_BYTES
    if body.content_b64:
        name = os.path.basename((body.filename or "book.txt").replace("\\", "/"))
        if os.path.splitext(name)[1].lower() not in DOC_EXT:
            raise HTTPException(422, "File type not allowed (pdf, docx, doc, txt, md, png, jpg, xlsx)")
        try:
            raw = base64.b64decode(body.content_b64, validate=True)
        except (binascii.Error, ValueError):
            raise HTTPException(422, "content_b64 is not valid base64")
        if not raw or len(raw) > MAX_DOC_BYTES:
            raise HTTPException(422, f"File must be between 1 byte and {MAX_DOC_BYTES // 1024 // 1024} MB")
        try:
            rd = docread.read_document(name, raw)
        except docread.ReadError as e:
            raise HTTPException(422, str(e))
        return name, raw, rd["pages"], rd["warnings"]
    if body.text and len(body.text.strip()) >= 40:
        return None, None, [docread.clean(body.text)], []
    raise HTTPException(422, "Upload the book, or paste at least a few lines of its text")


def _suggest_number(db, tender: str | None) -> str:
    if tender and not db.query(Project).filter_by(number=tender).first():
        return tender
    n = db.query(Project).count() + 1
    while db.query(Project).filter_by(number=f"PRJ-{date.today().year}-{n:03d}").first():
        n += 1
    return f"PRJ-{date.today().year}-{n:03d}"


@router.post("/project-intake/book/preview")
def book_preview(body: BookIn, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    """Read the book and propose the project number, name, dates and phases. Nothing is created."""
    _, _, pages, warnings = _book_pages(body)
    r = brief.analyze(pages, body.lang or "auto")
    meta = r["meta"]
    start = date.today()
    months = int(meta.get("duration_months") or sum(max(1, ph.get("months", 1)) for ph in r["phases"]) or 6)
    tender = meta.get("tender_number")
    return {"number": _suggest_number(db, tender), "tender_number": tender, "number_from_book": bool(tender) and not db.query(Project).filter_by(number=tender).first(),
            "name": meta.get("name") or "", "language": meta.get("language"), "pages": meta.get("pages"), "planned_start": start, "planned_end": add_months(start, months) - timedelta(days=1),
            "duration_months": months, "phases": [{"n": ph["n"], "name": ph["name"], "start_month": ph["start_month"], "end_month": ph["end_month"]} for ph in r["phases"]],
            "counts": _counts(r), "warnings": warnings}


@router.post("/project-intake/book/confirm", status_code=201)
def book_confirm(body: BookConfirm, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE)), progress_id: str | None = Header(None, alias="X-Progress-Id")):
    """The user confirmed (and maybe corrected) the proposal: create the project, keep the book as a document, and leave a draft plan ready to review."""
    from .projects import new_project
    if body.state not in ("tendering", "planning"):
        raise HTTPException(422, "Initial state must be tendering or planning")
    if body.planned_end < body.planned_start:
        raise HTTPException(422, "planned_end before planned_start")
    if db.query(Project).filter_by(number=body.number).first():
        raise HTTPException(409, "project_number already exists")
    if user.role == "PM" and get_params(db).get("intake_required"):
        raise HTTPException(403, "New projects start as a proposal that a decision maker approves (Proposals page)")
    name, raw, pages, _ = _book_pages(body)
    p = new_project(db, {"number": body.number.strip(), "name": body.name.strip(), "state": body.state, "planned_start": body.planned_start, "planned_end": body.planned_end,
                         "client": body.client}, user.id, user.id)
    doc_id = None
    if raw is not None:
        d = Document(project_id=p.id, kind="tender_book", filename=name, size=len(raw), content=raw, uploaded_by=user.id, description="Project book the plan was drafted from")
        db.add(d)
        db.flush()
        doc_id = d.id
    db.commit()
    try:
        out = analyze(p.id, AnalyzeIn(document_id=doc_id, text=None if doc_id else body.text, lang=body.lang or "auto"), db, user, progress_id)
    except HTTPException as e:                  # the project exists even if the reader is switched off or rate limited
        return {"project_id": p.id, "draft_id": None, "counts": {}, "warnings": [str(e.detail)]}
    return {"project_id": p.id, "draft_id": out["draft_id"], "counts": out["counts"], "warnings": out["warnings"]}


# ---------------- translation of what was extracted ----------------
TRANSLATABLE = {"phases": ("name",), "activities": ("name", "description"), "requirements": ("title", "text"), "deliverables": ("name", "description"),
                "risks": ("title", "response"), "team": ("title",), "compliance": ("title",)}


class TranslateIn(BaseModel):
    target: str = Field(pattern="^(en|ar)$")


@router.post("/projects/{pid}/brief/{did}/translate")
def translate_draft(pid: int, did: int, body: TranslateIn, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE)), progress_id: str | None = Header(None, alias="X-Progress-Id")):
    """Translate the extracted text with the Saudi-hosted model. Without a live model nothing is translated and the original stays as the only text."""
    p, d = _draft(db, user, pid, did)
    st = ai.status()
    if st["mode"] != "live" or st["blocked"]:
        return {"status": "unavailable", "reason": "No Saudi-hosted language model is connected, so the extracted text is shown in the language of the book."}
    out = copy.deepcopy(d.output)
    items: list[tuple[str, str]] = []
    for i, o in enumerate(out.get("objectives", [])):
        if str(o).strip():
            items.append((f"objectives.{i}", str(o)))
    for sec, fields in TRANSLATABLE.items():
        for i, row in enumerate(out.get(sec, [])):
            for f in fields:
                if str(row.get(f) or "").strip():
                    items.append((f"{sec}.{i}.{f}", str(row[f])))
    tr = out.setdefault("translations", {}).setdefault(body.target, {})
    name = "English" if body.target == "en" else "Arabic"
    # small chunks, run together: the time is about that of the slowest chunk, not the sum of all of them
    size = 15
    parts = [items[k:k + size] for k in range(0, len(items), size)]
    chunks = max(1, len(parts))
    progress.update(user.id, progress_id, 3, "translate", n=0, total=chunks)
    cfg = ai.resolve()                                        # read on the request thread; workers then only make the model call
    done = {"n": 0}
    lock = threading.Lock()

    def one(chunk):
        prompt = (f"Translate each string into {name}. Keep numbers, codes and names. Return only JSON: {{\"items\": [\"...\"]}} with exactly {len(chunk)} strings in the same order.\n"
                  + json.dumps([v for _, v in chunk], ensure_ascii=False))
        data = ai.extract_json(ai._live("translate", {}, prompt, cfg))
        res = data.get("items") if isinstance(data, dict) else None
        if not isinstance(res, list) or len(res) != len(chunk):
            raise ai.AiError(502, "The model returned a translation that does not match the text")
        with lock:
            done["n"] += 1
            progress.update(user.id, progress_id, 3 + 92 * done["n"] / chunks, "translate", n=done["n"], total=chunks)
        return res

    try:
        ctxs = [contextvars.copy_context() for _ in parts]    # one copy per worker, taken here: each carries this request's tenant and user for the usage record
        with ThreadPoolExecutor(max_workers=min(6, chunks)) as ex:
            replies = list(ex.map(lambda cp: cp[0].run(one, cp[1]), zip(ctxs, parts)))
        for chunk, res in zip(parts, replies):
            for (key, src), t_ in zip(chunk, res):
                tr[key] = {"src": src, "t": str(t_)}
    except ai.AiError as e:
        raise HTTPException(502, getattr(e, "msg", None) or "Translation failed")
    progress.update(user.id, progress_id, 97, "save")
    d.output = out
    log(db, user.id, "brief.translated", "project", pid, {"draft_id": did, "target": body.target, "strings": len(items)})
    db.commit()
    progress.update(user.id, progress_id, 100, "done")
    return {"status": "ok", "translated": len(items), "translations": out["translations"]}
