"""Tendering stage: go / no-go scorecard, estimate (hours, cost, price) from the project book, capacity and skills gap,
compliance and risk review, submission checklist with deadline, and the win / lose result that moves the project on."""
from collections import defaultdict
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..audit import log
from ..deps import current_user, get_db, require_roles
from ..models import AiDraft, RateCard, Tender, User
from .brief import propose
from .projects import TransitionIn, can_view, get_project, need_manage, transition

router = APIRouter(tags=["tendering"])
MANAGE = ("PM", "PMO", "ADMIN")
DECIDE = ("PMO", "ADMIN", "DECISION_MAKER")

CRITERIA = (("strategic_fit", 20), ("capability", 20), ("capacity", 15), ("margin", 15), ("client", 10), ("competition", 10), ("delivery_risk", 10))
CHECKLIST = ("read_book", "clarifications", "technical", "financial", "guarantee", "forms", "pmo_review", "signed")


class TenderPatch(BaseModel):
    deadline: date | None = None
    margin_pct: float | None = Field(None, ge=0, le=300)
    scores: dict[str, dict] | None = None
    checklist: dict[str, dict] | None = None


class DecisionIn(BaseModel):
    decision: str = Field(pattern="^(go|no_go)$")
    note: str | None = Field(None, max_length=2000)


class OutcomeIn(BaseModel):
    outcome: str = Field(pattern="^(won|lost)$")
    note: str | None = Field(None, max_length=2000)


def _row(db, p) -> Tender:
    t = db.query(Tender).filter_by(project_id=p.id).first()
    if not t:
        t = Tender(project_id=p.id, scores={}, checklist={})
        db.add(t)
        db.flush()
    return t


def _latest_draft(db, pid):
    return db.query(AiDraft).filter_by(project_id=pid, kind="brief").order_by(AiDraft.id.desc()).first()


def _blended_rate(db, ccy: str):
    latest: dict[str, RateCard] = {}
    for r in db.query(RateCard).filter(RateCard.effective_from <= date.today()).order_by(RateCard.effective_from):
        latest[r.grade] = r
    rates = [r.hourly_rate for r in latest.values() if r.currency == ccy]
    return (sum(rates) / len(rates)) if rates else None


def _score(t: Tender) -> dict:
    tot, got, filled = 0, 0.0, 0
    rows = []
    for key, w in CRITERIA:
        sc = (t.scores or {}).get(key) or {}
        s = sc.get("score")
        rows.append({"key": key, "weight": w, "score": s, "note": sc.get("note") or ""})
        tot += w
        if isinstance(s, (int, float)) and 1 <= s <= 5:
            got += w * s / 5
            filled += 1
    pct = round(100 * got / tot, 1) if filled == len(CRITERIA) else None
    rec = None if pct is None else ("go" if pct >= 70 else "review" if pct >= 50 else "no_go")
    return {"criteria": rows, "pct": pct, "recommendation": rec, "complete": filled == len(CRITERIA)}


def _estimate(db, p, t: Tender, draft) -> dict:
    if not draft:
        return {"available": False, "reason": "No draft plan yet. Create the project from the book, or analyse the book in the Plan draft tab."}
    acts = draft.output.get("activities", [])
    by_role: dict[str, float] = defaultdict(float)
    for a in acts:
        by_role[(a.get("role") or "—")] += float(a.get("planned_hours") or 0)
    hours = sum(by_role.values())
    rate = _blended_rate(db, p.currency)
    cost = round(hours * rate, 0) if rate is not None else None
    price = round(cost * (1 + t.margin_pct / 100), 0) if cost is not None else None
    return {"available": True, "hours": round(hours, 1), "by_role": [{"role": k, "hours": round(v, 1)} for k, v in sorted(by_role.items(), key=lambda x: -x[1])],
            "blended_rate": None if rate is None else round(rate, 2), "currency": p.currency, "cost": cost, "margin_pct": t.margin_pct, "price": price,
            "note": "Hours are rule-of-thumb estimates from the book; cost uses the average of the current rate card; price adds your margin.",
            "rate_missing": rate is None}


def _capacity(db, p, draft) -> dict:
    if not draft:
        return {"available": False}
    acts = [a for a in draft.output.get("activities", []) if a.get("planned_hours")]
    if not acts:
        return {"available": True, "tasks": 0, "gaps": [], "unassigned_hours": 0.0}
    st = propose(db, p.planned_start or date.today(), acts)
    gaps: dict[str, dict] = {}
    for a in acts:
        s = st.get(a["code"]) or {}
        if not s.get("user_id"):
            g = gaps.setdefault(a.get("role") or "—", {"role": a.get("role") or "—", "tasks": 0, "hours": 0.0, "reason": s.get("reason") or ""})
            g["tasks"] += 1
            g["hours"] = round(g["hours"] + float(a["planned_hours"]), 1)
    return {"available": True, "tasks": len(acts), "gaps": sorted(gaps.values(), key=lambda g: -g["hours"]), "unassigned_hours": round(sum(g["hours"] for g in gaps.values()), 1)}


def _review(draft) -> dict:
    if not draft:
        return {"available": False}
    o = draft.output
    risks = sorted(o.get("risks", []), key=lambda r: -(int(r.get("probability") or 0) * int(r.get("impact") or 0)))[:5]
    return {"available": True, "compliance": [{"framework": c.get("framework"), "title": c.get("title")} for c in o.get("compliance", [])],
            "risks": [{"title": r.get("title"), "score": int(r.get("probability") or 0) * int(r.get("impact") or 0)} for r in risks],
            "terms": [{"kind": x.get("kind"), "text": x.get("text")} for x in o.get("terms", []) if x.get("kind") in ("penalty", "guarantee", "payment", "acceptance")]}


def _out(db, p, t: Tender) -> dict:
    draft = _latest_draft(db, p.id)
    done = {k: bool(((t.checklist or {}).get(k) or {}).get("done")) for k in CHECKLIST}
    days = (t.deadline - date.today()).days if t.deadline else None
    names = {u.id: u.full_name for u in db.query(User).filter(User.id == (t.decided_by or 0))}
    return {"state": p.state, "deadline": t.deadline, "days_to_deadline": days, "decision": t.decision, "decision_note": t.decision_note, "decided_by": names.get(t.decided_by),
            "scorecard": _score(t), "estimate": _estimate(db, p, t, draft), "capacity": _capacity(db, p, draft), "review": _review(draft),
            "checklist": [{"key": k, "done": done[k], "note": ((t.checklist or {}).get(k) or {}).get("note") or ""} for k in CHECKLIST], "checklist_done": sum(done.values()), "checklist_total": len(CHECKLIST),
            "submitted_at": t.submitted_at, "outcome": t.outcome, "outcome_note": t.outcome_note, "has_draft": draft is not None}


@router.get("/projects/{pid}/tender")
def get_tender(pid: int, db=Depends(get_db), user: User = Depends(current_user)):
    p = get_project(db, pid)
    if not can_view(db, user, p):
        raise HTTPException(403, "No access to this project")
    t = db.query(Tender).filter_by(project_id=pid).first()
    if not t:
        if p.state != "tendering":
            raise HTTPException(404, "This project has no tender record")
        t = _row(db, p)
        db.commit()
    return _out(db, p, t)


@router.patch("/projects/{pid}/tender")
def patch_tender(pid: int, body: TenderPatch, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p = get_project(db, pid)
    need_manage(db, user, p)
    if p.state != "tendering":
        raise HTTPException(409, "The tender can be edited while the project is in tendering")
    t = _row(db, p)
    if t.submitted_at and body.checklist is not None:
        raise HTTPException(409, "The bid was already submitted")
    d = body.model_dump(exclude_unset=True)
    if "deadline" in d:
        t.deadline = d["deadline"]
    if d.get("margin_pct") is not None:
        t.margin_pct = float(d["margin_pct"])
    if body.scores is not None:
        sc = dict(t.scores or {})
        for k, v in body.scores.items():
            if k not in dict(CRITERIA):
                raise HTTPException(422, f"Unknown criterion {k}")
            s = v.get("score")
            if s is not None and (not isinstance(s, (int, float)) or not 1 <= s <= 5):
                raise HTTPException(422, "A score is between 1 and 5")
            sc[k] = {"score": s, "note": str(v.get("note") or "")[:500]}
        t.scores = sc
    if body.checklist is not None:
        ck = dict(t.checklist or {})
        for k, v in body.checklist.items():
            if k not in CHECKLIST:
                raise HTTPException(422, f"Unknown checklist item {k}")
            ck[k] = {"done": bool(v.get("done")), "note": str(v.get("note") or "")[:500]}
        t.checklist = ck
    log(db, user.id, "tender.updated", "project", pid, {"deadline": str(t.deadline) if t.deadline else None, "margin_pct": t.margin_pct})
    db.commit()
    return _out(db, p, t)


@router.post("/projects/{pid}/tender/decision")
def tender_decision(pid: int, body: DecisionIn, db=Depends(get_db), user: User = Depends(require_roles(*DECIDE))):
    p = get_project(db, pid)
    if p.state != "tendering":
        raise HTTPException(409, "Go / no-go is decided while the project is in tendering")
    t = _row(db, p)
    sc = _score(t)
    if not sc["complete"]:
        raise HTTPException(422, "Score every criterion before deciding")
    if body.decision == "no_go" and not (body.note or "").strip():
        raise HTTPException(422, "Say why the decision is no-go")
    if body.decision == "go" and sc["recommendation"] == "no_go" and not (body.note or "").strip():
        raise HTTPException(422, "The scorecard recommends no-go; write why you go ahead anyway")
    t.decision, t.decision_note, t.decided_by = body.decision, (body.note or "").strip() or None, user.id
    log(db, user.id, "tender.decision", "project", pid, {"decision": body.decision, "score": sc["pct"]})
    db.commit()
    return _out(db, p, t)


@router.post("/projects/{pid}/tender/submit")
def tender_submit(pid: int, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p = get_project(db, pid)
    need_manage(db, user, p)
    t = _row(db, p)
    if p.state != "tendering":
        raise HTTPException(409, "Not in tendering")
    if t.decision != "go":
        raise HTTPException(409, "The bid needs a go decision before it is submitted")
    missing = [k for k in CHECKLIST if not ((t.checklist or {}).get(k) or {}).get("done")]
    if missing:
        raise HTTPException(409, f"Finish the submission checklist first: {', '.join(missing)}")
    t.submitted_at = datetime.now(timezone.utc)
    log(db, user.id, "tender.submitted", "project", pid, {"late": bool(t.deadline and date.today() > t.deadline)})
    db.commit()
    return _out(db, p, t)


@router.post("/projects/{pid}/tender/outcome")
def tender_outcome(pid: int, body: OutcomeIn, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    """Won: the project moves to planning. Lost: it is archived with the reason kept."""
    p = get_project(db, pid)
    need_manage(db, user, p)
    t = _row(db, p)
    if p.state != "tendering":
        raise HTTPException(409, "Not in tendering")
    if body.outcome == "won" and not t.submitted_at:
        raise HTTPException(409, "Submit the bid before recording a win")
    if body.outcome == "lost" and not (body.note or "").strip():
        raise HTTPException(422, "Record why the bid was lost (price, score, competitor); it feeds the next bid")
    transition(pid, TransitionIn(to_state="planning" if body.outcome == "won" else "archived"), db, user)
    t = _row(db, get_project(db, pid))
    t.outcome, t.outcome_note, t.outcome_at = body.outcome, (body.note or "").strip() or None, datetime.now(timezone.utc)
    log(db, user.id, "tender.outcome", "project", pid, {"outcome": body.outcome})
    db.commit()
    return _out(db, get_project(db, pid), t)
