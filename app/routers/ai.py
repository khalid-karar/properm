"""AI endpoints: draft-only, human-in-the-loop, permission-inheriting. See app/ai.py for the rules."""
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import ai
from ..audit import log
from ..deps import current_user, get_db, get_params, require_roles
from ..models import Activity, AiDraft, Alert, Project, User
from .alerts import _visible
from .exports import project_summary
from .projects import ActivityIn, add_activity, can_manage, can_view_cost, get_project, need_manage

router = APIRouter(prefix="/ai", tags=["ai"])
MANAGE = ("PM", "PMO", "ADMIN")


def d_out(d: AiDraft) -> dict:
    return {"id": d.id, "kind": d.kind, "project_id": d.project_id, "alert_id": d.alert_id, "status": d.status, "output": d.output,
            "model": d.model, "mode": d.mode, "created_by": d.created_by, "created_at": d.created_at, "reviewed_by": d.reviewed_by}


def _run(db, user: User, task: str, payload: dict, kind: str, project_id=None, alert_id=None, input_text=None) -> AiDraft:
    params = get_params(db)
    if not params["ai_enabled"]:
        raise HTTPException(403, "The AI assistant is switched off by the administrator")
    since = datetime.now(timezone.utc) - timedelta(hours=1)
    if db.query(AiDraft).filter(AiDraft.created_by == user.id, AiDraft.created_at >= since).count() >= int(params["ai_hourly_limit"]):
        raise HTTPException(429, "AI request limit reached for this hour")
    st = ai.status()
    try:
        out = ai.run(task, payload)
    except ai.AiError as e:
        log(db, user.id, "ai.failed", "ai", 0, {"task": task, "reason": e.msg})
        db.commit()
        raise HTTPException(e.status, e.msg)
    d = AiDraft(kind=kind, project_id=project_id, alert_id=alert_id, input_text=input_text, output=out, model=st["model"], mode=st["mode"], created_by=user.id)
    db.add(d)
    db.flush()
    log(db, user.id, "ai.draft", "ai_draft", d.id, {"kind": kind, "project_id": project_id, "mode": st["mode"], "model": st["model"]})
    db.commit()
    return d


@router.get("/status")
def ai_status(db=Depends(get_db), user: User = Depends(current_user)):
    return {**ai.status(), "enabled": bool(get_params(db)["ai_enabled"])}


class PlanIn(BaseModel):
    project_id: int
    brief: str = Field(min_length=10, max_length=ai.MAX_INPUT_CHARS)
    lang: str = "en"


@router.post("/plans", status_code=201)
def draft_plan(body: PlanIn, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p = get_project(db, body.project_id)
    need_manage(db, user, p)
    if p.state != "planning":
        raise HTTPException(409, "AI plan drafts are for projects in the planning state")
    return d_out(_run(db, user, "plan", {"brief": body.brief, "lang": body.lang}, "plan", p.id, input_text=body.brief))


class NarrativeIn(BaseModel):
    project_id: int
    lang: str = "en"


@router.post("/narrative", status_code=201)
def draft_narrative(body: NarrativeIn, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p = get_project(db, body.project_id)
    need_manage(db, user, p)
    summary = project_summary(db, p, date.today(), with_cost=can_view_cost(db, user, p))   # context = what this user may see
    return d_out(_run(db, user, "narrative", {"summary": summary, "lang": body.lang}, "narrative", p.id))


class AlertIn(BaseModel):
    lang: str = "en"


@router.post("/alerts/{aid}/suggest", status_code=201)
def suggest_alert(aid: int, body: AlertIn, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    a = db.get(Alert, aid)
    if not a or not _visible(db, user, a):
        raise HTTPException(404, "Alert not found")
    p = db.get(Project, a.project_id)
    summary = project_summary(db, p, date.today(), with_cost=can_view_cost(db, user, p))
    return d_out(_run(db, user, "alert", {"rule": a.rule, "cause": a.cause, "summary": summary, "lang": body.lang}, "alert_action", p.id, a.id))


@router.get("/drafts")
def list_drafts(project_id: int | None = None, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    q = db.query(AiDraft)
    if project_id:
        q = q.filter(AiDraft.project_id == project_id)
    rows = [d for d in q.order_by(AiDraft.id.desc()).limit(50) if d.project_id is None or can_manage(db, user, db.get(Project, d.project_id))]
    return [d_out(d) for d in rows]


def _draft(db, user, did) -> AiDraft:
    d = db.get(AiDraft, did)
    if not d or (d.project_id and not can_manage(db, user, db.get(Project, d.project_id))):
        raise HTTPException(404, "Draft not found")
    if d.status != "draft":
        raise HTTPException(409, f"Draft already {d.status}")
    return d


class ApplyIn(BaseModel):
    activities: list[ai.PlanActivity] | None = None     # the reviewer's edited version; omit to accept as drafted


@router.post("/drafts/{did}/apply")
def apply_draft(did: int, body: ApplyIn, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    d = _draft(db, user, did)
    if d.kind != "plan":
        raise HTTPException(422, "Only plan drafts can be applied; copy text drafts where you need them")
    p = get_project(db, d.project_id)
    if p.state != "planning":
        raise HTTPException(409, "The project is no longer in planning")
    acts = body.activities if body.activities is not None else [ai.PlanActivity(**a) for a in d.output["activities"]]
    if not acts:
        raise HTTPException(422, "Nothing to apply")
    codes = [a.code for a in acts]
    existing = {a.code for a in db.query(Activity).filter_by(project_id=p.id)}
    if len(set(codes)) != len(codes) or existing & set(codes):
        raise HTTPException(409, "Activity codes must be unique and not already used in this project")
    for a in acts:
        add_activity(p.id, ActivityIn(code=a.code, name=a.name, planned_hours=a.planned_hours), db, user)
    d.status, d.reviewed_by, d.reviewed_at = "applied", user.id, datetime.now(timezone.utc)
    log(db, user.id, "ai.plan_applied", "ai_draft", d.id, {"project_id": p.id, "activities": len(acts), "edited": body.activities is not None})
    db.commit()
    return d_out(d)


@router.post("/drafts/{did}/reject")
def reject_draft(did: int, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    d = _draft(db, user, did)
    d.status, d.reviewed_by, d.reviewed_at = "rejected", user.id, datetime.now(timezone.utc)
    log(db, user.id, "ai.draft_rejected", "ai_draft", d.id, {})
    db.commit()
    return d_out(d)


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    lang: str | None = None
    project_id: int | None = None


@router.post("/ask")
def ask(body: AskIn, db=Depends(get_db), user: User = Depends(current_user)):
    """Floating assistant. Answers only from what this user may already see; rule-based unless the Saudi-hosted model is live."""
    params = get_params(db)
    if not params["ai_enabled"]:
        raise HTTPException(403, "The AI assistant is switched off by the administrator")
    from .. import assistant
    since = datetime.now(timezone.utc) - timedelta(hours=1)
    n = db.query(AiDraft).filter(AiDraft.created_by == user.id, AiDraft.kind == "ask", AiDraft.created_at >= since).count()
    if n >= int(params["ai_hourly_limit"]) * 4:
        raise HTTPException(429, "Assistant limit reached for this hour")
    out = assistant.ask(db, user, body.question, body.lang, body.project_id)
    st = ai.status()
    db.add(AiDraft(kind="ask", project_id=body.project_id, input_text=None, output={"q_len": len(body.question)}, model=st["model"], mode=st["mode"], created_by=user.id))
    log(db, user.id, "ai.ask", "ai", 0, {"mode": st["mode"]})
    db.commit()
    return out
