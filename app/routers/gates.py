"""Governance: project intake (proposals with a business case and score), stage gates, and the decision log.

Every decision uses the same outcomes: approve, approve with conditions, reject, defer, request more information.
A rationale is required for everything except a plain approval; conditions are required for a conditional approval."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func

from ..audit import emit, log
from ..deps import current_user, get_db, get_params, require_roles
from ..models import (Activity, ChangeRequest, DecisionRecord, GateReview, Issue, Milestone, Project, Proposal, Risk,
                      Stakeholder, User)
from .dashboards import EXEC, overall_pct
from .projects import MANAGE, can_view, get_project, need_manage, new_project, p_out

router = APIRouter(tags=["governance gates"])

OUTCOMES = ("approve", "approve_conditions", "reject", "defer", "request_info")
STATUS_FOR = {"approve": "approved", "approve_conditions": "approved_conditions", "reject": "rejected",
              "defer": "deferred", "request_info": "info_requested"}
DECIDERS = ("DECISION_MAKER", "PMO", "ADMIN")


class DecideIn(BaseModel):
    outcome: str
    rationale: str | None = Field(None, max_length=5000)
    conditions: str | None = Field(None, max_length=5000)


def check_decision(outcome: str, rationale: str | None, conditions: str | None) -> None:
    if outcome not in OUTCOMES:
        raise HTTPException(422, f"outcome must be one of {', '.join(OUTCOMES)}")
    if outcome != "approve" and not (rationale or "").strip():
        raise HTTPException(422, "A rationale is required for this decision")
    if outcome == "approve_conditions" and not (conditions or "").strip():
        raise HTTPException(422, "State the conditions of the approval")


def record_decision(db, entity, eid, pid, title, outcome, rationale, conditions, user) -> DecisionRecord:
    r = DecisionRecord(entity=entity, entity_id=eid, project_id=pid, title=title[:300], outcome=outcome,
                       rationale=(rationale or "").strip() or None, conditions=(conditions or "").strip() or None, decided_by=user.id)
    db.add(r)
    return r


def _names(db):
    return {u.id: u.full_name for u in db.query(User)}


def rec_out(r: DecisionRecord, names) -> dict:
    return {"id": r.id, "entity": r.entity, "entity_id": r.entity_id, "project_id": r.project_id, "title": r.title,
            "outcome": r.outcome, "rationale": r.rationale, "conditions": r.conditions,
            "decided_by": names.get(r.decided_by), "decided_at": r.decided_at.isoformat() if r.decided_at else None}


# ---------------- proposals (project intake) ----------------
class ProposalIn(BaseModel):
    number: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=300)
    business_case: str = Field(min_length=10, max_length=20000)
    expected_benefits: str | None = Field(None, max_length=10000)
    client: str | None = Field(None, max_length=200)
    sponsor: str | None = Field(None, max_length=200)
    est_cost: float | None = Field(None, ge=0)
    currency: str = Field("SAR", min_length=3, max_length=3)
    est_start: date | None = None
    est_end: date | None = None
    strategic_fit: int = Field(3, ge=1, le=5)
    value: int = Field(3, ge=1, le=5)
    urgency: int = Field(3, ge=1, le=5)
    risk_level: int = Field(3, ge=1, le=5)


class ProposalPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=300)
    business_case: str | None = Field(None, min_length=10, max_length=20000)
    expected_benefits: str | None = None
    client: str | None = None
    sponsor: str | None = None
    est_cost: float | None = Field(None, ge=0)
    est_start: date | None = None
    est_end: date | None = None
    strategic_fit: int | None = Field(None, ge=1, le=5)
    value: int | None = Field(None, ge=1, le=5)
    urgency: int | None = Field(None, ge=1, le=5)
    risk_level: int | None = Field(None, ge=1, le=5)
    response: str | None = Field(None, max_length=5000)    # answer to "request more information"


def score(x: Proposal) -> int:
    """0-100. Strategic fit and value weigh most; lower risk scores higher."""
    raw = 0.35 * x.strategic_fit + 0.35 * x.value + 0.15 * x.urgency + 0.15 * (6 - x.risk_level)   # 1..5
    return round((raw - 1) / 4 * 100)


def prop_out(db, x: Proposal, names) -> dict:
    recs = db.query(DecisionRecord).filter_by(entity="proposal", entity_id=x.id).order_by(DecisionRecord.id).all()
    return {"id": x.id, "number": x.number, "name": x.name, "business_case": x.business_case, "expected_benefits": x.expected_benefits,
            "client": x.client, "sponsor": x.sponsor, "est_cost": x.est_cost, "currency": x.currency,
            "est_start": x.est_start, "est_end": x.est_end, "strategic_fit": x.strategic_fit, "value": x.value,
            "urgency": x.urgency, "risk_level": x.risk_level, "score": score(x), "status": x.status,
            "submitted_by": x.submitted_by, "submitted_by_name": names.get(x.submitted_by), "project_id": x.project_id,
            "created_at": x.created_at.isoformat() if x.created_at else None, "decisions": [rec_out(r, names) for r in recs]}


def _number_free(db, number, exclude_id=None):
    if db.query(Project).filter_by(number=number).first():
        return False
    q = db.query(Proposal).filter(Proposal.number == number, Proposal.status.notin_(("rejected",)))
    if exclude_id:
        q = q.filter(Proposal.id != exclude_id)
    return q.first() is None


@router.post("/proposals", status_code=201)
def submit_proposal(body: ProposalIn, db=Depends(get_db), user: User = Depends(require_roles("PM", "PMO", "ADMIN", "PROGRAM_MANAGER"))):
    if body.est_start and body.est_end and body.est_end < body.est_start:
        raise HTTPException(422, "est_end before est_start")
    if not _number_free(db, body.number):
        raise HTTPException(409, "That project number is already used")
    x = Proposal(**body.model_dump(), submitted_by=user.id, status="submitted")
    db.add(x)
    db.flush()
    log(db, user.id, "proposal.submitted", "proposal", x.id, {"number": x.number})
    emit(db, "proposal.submitted", {"proposal_id": x.id, "title": f"{x.number} {x.name}"})
    db.commit()
    return prop_out(db, x, _names(db))


@router.get("/proposals")
def list_proposals(status: str | None = None, db=Depends(get_db), user: User = Depends(current_user)):
    q = db.query(Proposal)
    if user.role not in EXEC:
        q = q.filter(Proposal.submitted_by == user.id)
    if status:
        q = q.filter(Proposal.status == status)
    names = _names(db)
    rows = [prop_out(db, x, names) for x in q.all()]
    open_ = ("submitted", "deferred", "info_requested")
    rows.sort(key=lambda r: (r["status"] not in open_, -r["score"], r["id"]))
    for i, r in enumerate([r for r in rows if r["status"] in ("submitted", "deferred")], start=1):
        r["rank"] = i
    return rows


def _get_prop(db, xid):
    x = db.get(Proposal, xid)
    if not x:
        raise HTTPException(404, "Proposal not found")
    return x


@router.patch("/proposals/{xid}")
def edit_proposal(xid: int, body: ProposalPatch, db=Depends(get_db), user: User = Depends(current_user)):
    x = _get_prop(db, xid)
    if x.submitted_by != user.id and user.role != "ADMIN":
        raise HTTPException(403, "Only the person who submitted it can change a proposal")
    if x.status not in ("submitted", "info_requested", "deferred"):
        raise HTTPException(409, f"Proposal is {x.status} and can no longer be changed")
    ch = body.model_dump(exclude_unset=True)
    resp = ch.pop("response", None)
    for k, v in ch.items():
        setattr(x, k, v)
    if resp:
        x.business_case = f"{x.business_case}\n\nResponse ({date.today()}): {resp}"
    was = x.status
    x.status = "submitted"
    log(db, user.id, "proposal.updated", "proposal", x.id, {"fields": sorted(ch) + (["response"] if resp else [])})
    if was != "submitted":
        emit(db, "proposal.submitted", {"proposal_id": x.id, "title": f"{x.number} {x.name}"})
    db.commit()
    return prop_out(db, x, _names(db))


@router.post("/proposals/{xid}/decision")
def decide_proposal(xid: int, body: DecideIn, db=Depends(get_db), user: User = Depends(require_roles(*DECIDERS))):
    x = _get_prop(db, xid)
    if x.submitted_by == user.id and user.role != "ADMIN":
        raise HTTPException(403, "You cannot decide your own proposal")
    if x.status not in ("submitted", "deferred"):
        raise HTTPException(409, f"Proposal is {x.status}")
    check_decision(body.outcome, body.rationale, body.conditions)
    x.status = STATUS_FOR[body.outcome]
    if body.outcome in ("approve", "approve_conditions"):
        if not _number_free(db, x.number, exclude_id=x.id):
            raise HTTPException(409, "The project number is already used; ask the submitter to change it")
        sub = db.get(User, x.submitted_by)
        pm_id = sub.id if sub and sub.role in MANAGE else user.id
        scope = x.business_case + (f"\n\nExpected benefits: {x.expected_benefits}" if x.expected_benefits else "")
        if body.conditions:
            scope += f"\n\nApproval conditions: {body.conditions}"
        p = new_project(db, {"number": x.number, "name": x.name, "state": "planning", "planned_start": x.est_start,
                             "planned_end": x.est_end, "budget_ceiling": x.est_cost, "currency": x.currency,
                             "client": x.client, "sponsor": x.sponsor, "scope_statement": scope[:10000]}, pm_id, user.id)
        x.project_id = p.id
        from ..models import ProjectScore
        db.add(ProjectScore(project_id=p.id, strategic_fit=x.strategic_fit, value=x.value, urgency=x.urgency, risk_level=x.risk_level, updated_by=user.id))
    record_decision(db, "proposal", x.id, x.project_id, f"Proposal {x.number} {x.name}", body.outcome, body.rationale, body.conditions, user)
    log(db, user.id, "proposal.decided", "proposal", x.id, {"outcome": body.outcome, "project_id": x.project_id})
    emit(db, "proposal.decided", {"proposal_id": x.id, "user_id": x.submitted_by, "outcome": body.outcome,
                                  "title": f"{x.number} {x.name}", "project_id": x.project_id})
    db.commit()
    return prop_out(db, x, _names(db))


# ---------------- stage gates ----------------
GATES = {"planning_execution": ("planning", "execution"), "execution_closing": ("execution", "closing")}
NEXT_GATE = {"planning": "planning_execution", "execution": "execution_closing"}


def gate_checks(db, p: Project, gate: str) -> list[dict]:
    c = lambda key, ok, detail="": {"key": key, "ok": bool(ok), "detail": detail}
    if gate == "planning_execution":
        acts = db.query(Activity).filter_by(project_id=p.id, phase="execution").all()
        incomplete = [a.code for a in acts if not (a.planned_hours and a.planned_start and a.planned_end)]
        n = lambda M: db.query(func.count(M.id)).filter(M.project_id == p.id).scalar()
        return [c("dates_set", p.planned_start and p.planned_end),
                c("budget_set", p.budget_ceiling),
                c("sponsor_named", p.sponsor),
                c("activities_planned", acts and not incomplete, ", ".join(incomplete[:5]) if incomplete else f"{len(acts)}"),
                c("milestones_set", n(Milestone), str(n(Milestone))),
                c("risks_identified", n(Risk), str(n(Risk))),
                c("stakeholders_listed", n(Stakeholder), str(n(Stakeholder)))]
    pct = overall_pct(db, p, date.today()) or 0
    open_ms = db.query(func.count(Milestone.id)).filter(Milestone.project_id == p.id, Milestone.achieved_on.is_(None)).scalar()
    crit = db.query(func.count(Issue.id)).filter(Issue.project_id == p.id, Issue.severity == "critical", Issue.status.in_(("open", "in_progress"))).scalar()
    pend = db.query(func.count(ChangeRequest.id)).filter(ChangeRequest.project_id == p.id, ChangeRequest.status.in_(("requested", "deferred", "info_requested"))).scalar()
    return [c("work_complete", pct >= 95, f"{round(pct)}%"), c("milestones_closed", open_ms == 0, str(open_ms)),
            c("no_critical_issues", crit == 0, str(crit)), c("no_pending_changes", pend == 0, str(pend))]


def gate_passed(db, pid: int, gate: str) -> bool:
    return db.query(GateReview).filter(GateReview.project_id == pid, GateReview.gate == gate,
                                       GateReview.status.in_(("approved", "approved_conditions"))).first() is not None


def require_gate(db, p: Project, gate: str) -> None:
    if get_params(db).get("stage_gates") and not gate_passed(db, p.id, gate):
        raise HTTPException(409, "This move needs an approved stage gate review first (Overview tab → Stage gate)")


def gate_out(db, g: GateReview, names) -> dict:
    recs = db.query(DecisionRecord).filter_by(entity="gate", entity_id=g.id).order_by(DecisionRecord.id).all()
    return {"id": g.id, "project_id": g.project_id, "gate": g.gate, "checks": g.checks, "note": g.note, "status": g.status,
            "requested_by": names.get(g.requested_by), "requested_by_id": g.requested_by,
            "created_at": g.created_at.isoformat() if g.created_at else None, "decisions": [rec_out(r, names) for r in recs]}


@router.get("/projects/{pid}/gates")
def project_gates(pid: int, db=Depends(get_db), user: User = Depends(current_user)):
    p = get_project(db, pid)
    if not can_view(db, user, p):
        raise HTTPException(403, "No access to this project")
    nxt = NEXT_GATE.get(p.state)
    names = _names(db)
    rows = db.query(GateReview).filter_by(project_id=pid).order_by(GateReview.id.desc()).all()
    return {"required": bool(get_params(db).get("stage_gates")), "next_gate": nxt,
            "next_passed": gate_passed(db, pid, nxt) if nxt else None,
            "preview": gate_checks(db, p, nxt) if nxt else [], "reviews": [gate_out(db, g, names) for g in rows]}


class GateIn(BaseModel):
    note: str | None = Field(None, max_length=5000)


@router.post("/projects/{pid}/gates", status_code=201)
def request_gate(pid: int, body: GateIn, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p = get_project(db, pid)
    need_manage(db, user, p)
    gate = NEXT_GATE.get(p.state)
    if not gate:
        raise HTTPException(409, f"No stage gate applies to a project in {p.state}")
    if gate_passed(db, pid, gate):
        raise HTTPException(409, "This gate is already approved")
    if db.query(GateReview).filter(GateReview.project_id == pid, GateReview.gate == gate, GateReview.status.in_(("pending", "deferred"))).first():
        raise HTTPException(409, "A review for this gate is already waiting for a decision")
    g = GateReview(project_id=pid, gate=gate, checks=gate_checks(db, p, gate), note=body.note, requested_by=user.id, status="pending")
    db.add(g)
    db.flush()
    log(db, user.id, "gate.requested", "gate_review", g.id, {"project_id": pid, "gate": gate})
    emit(db, "gate.requested", {"project_id": pid, "gate_id": g.id, "gate": gate})
    db.commit()
    return gate_out(db, g, _names(db))


@router.post("/projects/{pid}/gates/{gid}/decision")
def decide_gate(pid: int, gid: int, body: DecideIn, db=Depends(get_db), user: User = Depends(require_roles(*DECIDERS))):
    p = get_project(db, pid)
    g = db.get(GateReview, gid)
    if not g or g.project_id != pid:
        raise HTTPException(404, "Gate review not found")
    if g.requested_by == user.id and user.role != "ADMIN":
        raise HTTPException(403, "You cannot decide a gate you requested")
    if g.status not in ("pending", "deferred"):
        raise HTTPException(409, f"Gate review is {g.status}")
    if p.state != GATES[g.gate][0]:
        raise HTTPException(409, "The project has moved on since this review was requested")
    check_decision(body.outcome, body.rationale, body.conditions)
    g.checks = gate_checks(db, p, g.gate)
    failing = [c["key"] for c in g.checks if not c["ok"]]
    if body.outcome == "approve" and failing:
        raise HTTPException(422, f"Checks not met ({', '.join(failing)}): reject, or approve with conditions")
    g.status = STATUS_FOR[body.outcome] if body.outcome != "request_info" else "info_requested"
    record_decision(db, "gate", g.id, pid, f"Gate {g.gate.replace('_', ' → ')} · {p.number}", body.outcome, body.rationale, body.conditions, user)
    log(db, user.id, "gate.decided", "gate_review", g.id, {"project_id": pid, "outcome": body.outcome})
    emit(db, "gate.decided", {"project_id": pid, "gate_id": g.id, "outcome": body.outcome})
    db.commit()
    return gate_out(db, g, _names(db))


# ---------------- decision log ----------------
@router.get("/decision-log")
def decision_log(project_id: int | None = None, entity: str | None = None, limit: int = 200, db=Depends(get_db), user: User = Depends(current_user)):
    q = db.query(DecisionRecord)
    if project_id:
        q = q.filter(DecisionRecord.project_id == project_id)
    if entity:
        q = q.filter(DecisionRecord.entity == entity)
    names = _names(db)
    out = []
    for r in q.order_by(DecisionRecord.id.desc()).limit(min(limit, 500)):
        if user.role not in EXEC:
            p = db.get(Project, r.project_id) if r.project_id else None
            if not (p and can_view(db, user, p)) and r.decided_by != user.id:
                continue
        out.append(rec_out(r, names))
    return out


@router.get("/config/governance")
def governance_flags(db=Depends(get_db), _: User = Depends(current_user)):
    prm = get_params(db)
    return {"intake_required": bool(prm.get("intake_required")), "stage_gates": bool(prm.get("stage_gates"))}
