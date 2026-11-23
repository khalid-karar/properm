"""Depth items: risk response plans and opportunities, contingency / management reserve, quality log,
document versions, stakeholder engagement."""
import base64
import binascii
import os
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..audit import log
from ..deps import current_user, get_db, require_roles
from ..models import (Deliverable, Document, DocumentVersion, Opportunity, ProjectReserve, QualityItem, ReserveDrawdown, Risk,
                      RiskResponse, Stakeholder, StakeholderEngagement, User)
from ..notify import notify
from ..regkit import project_register
from .intake import DOC_EXT, MAX_DOC_BYTES
from .projects import MANAGE, can_manage, can_view, can_view_cost, get_project, need_manage

router = APIRouter(tags=["project depth"])
EXECS = ("PMO", "ADMIN", "DECISION_MAKER")


def _view(db, user, pid):
    p = get_project(db, pid)
    if not can_view(db, user, p):
        raise HTTPException(403, "No access to this project")
    return p


# ---------------- risk responses ----------------
STRATEGIES = ("avoid", "mitigate", "transfer", "accept", "escalate")


class ResponseIn(BaseModel):
    strategy: str
    trigger: str | None = Field(None, max_length=500)
    plan: str | None = Field(None, max_length=4000)
    contingency_amount: float | None = Field(None, ge=0)
    residual_probability: int | None = Field(None, ge=1, le=5)
    residual_impact: int | None = Field(None, ge=1, le=5)
    owner_id: int | None = None


def _resp_row(db, r, resp, names):
    d = {"risk_id": r.id, "title": r.title, "category": r.category, "probability": r.probability, "impact": r.impact, "score": r.score, "status": r.status,
         "strategy": None, "trigger": None, "plan": None, "contingency_amount": None, "residual_probability": None, "residual_impact": None, "residual_score": None,
         "owner_id": None, "owner": None}
    if resp:
        d.update({"strategy": resp.strategy, "trigger": resp.trigger, "plan": resp.plan, "contingency_amount": resp.contingency_amount,
                  "residual_probability": resp.residual_probability, "residual_impact": resp.residual_impact, "owner_id": resp.owner_id, "owner": names.get(resp.owner_id),
                  "residual_score": resp.residual_probability * resp.residual_impact if resp.residual_probability and resp.residual_impact else None})
    d["needs_response"] = bool(not resp and r.score >= 15 and r.status in ("open", "mitigating"))
    return d


@router.get("/projects/{pid}/risk-responses")
def risk_responses(pid: int, db=Depends(get_db), user: User = Depends(current_user)):
    p = _view(db, user, pid)
    names = {u.id: u.full_name for u in db.query(User)}
    resp = {x.risk_id: x for x in db.query(RiskResponse).filter_by(project_id=pid)}
    rows = [_resp_row(db, r, resp.get(r.id), names) for r in db.query(Risk).filter_by(project_id=pid).order_by(Risk.id)]
    rows.sort(key=lambda x: -x["score"])
    show_cost = can_view_cost(db, user, p)
    if not show_cost:
        for x in rows:
            x["contingency_amount"] = None
    return {"risks": rows, "without_response": [x["risk_id"] for x in rows if x["needs_response"]],
            "exposure": sum(x["score"] for x in rows if x["status"] in ("open", "mitigating")),
            "residual_exposure": sum((x["residual_score"] or x["score"]) for x in rows if x["status"] in ("open", "mitigating"))}


@router.put("/projects/{pid}/risks/{rid}/response")
def put_response(pid: int, rid: int, body: ResponseIn, db=Depends(get_db), user: User = Depends(current_user)):
    p = _view(db, user, pid)
    need_manage(db, user, p)
    r = db.get(Risk, rid)
    if not r or r.project_id != pid:
        raise HTTPException(404, "Risk not found")
    if body.strategy not in STRATEGIES:
        raise HTTPException(422, f"strategy must be one of: {', '.join(STRATEGIES)}")
    if body.strategy in ("avoid", "mitigate", "transfer", "escalate") and not (body.plan or "").strip():
        raise HTTPException(422, "Describe the response plan")
    if body.owner_id and not db.get(User, body.owner_id):
        raise HTTPException(422, "Unknown owner")
    if (body.residual_probability is None) != (body.residual_impact is None):
        raise HTTPException(422, "Give both residual probability and residual impact, or neither")
    row = db.query(RiskResponse).filter_by(risk_id=rid).first()
    if not row:
        row = RiskResponse(risk_id=rid, project_id=pid, strategy=body.strategy)
        db.add(row)
    for k, v in body.model_dump().items():
        setattr(row, k, v)
    if body.plan:
        r.response = body.plan
    if body.strategy == "escalate":
        for u in db.query(User).filter(User.role.in_(EXECS), User.active.is_(True)):
            notify(db, u.id, "risk", f"Risk escalated: {p.number} {r.title}", body.plan, f"#/projects/{pid}")
    log(db, user.id, "risk.response", "risk", rid, {"strategy": body.strategy})
    db.commit()
    return _resp_row(db, r, row, {u.id: u.full_name for u in db.query(User)})


@router.delete("/projects/{pid}/risks/{rid}/response", status_code=204)
def del_response(pid: int, rid: int, db=Depends(get_db), user: User = Depends(current_user)):
    p = _view(db, user, pid)
    need_manage(db, user, p)
    row = db.query(RiskResponse).filter_by(risk_id=rid, project_id=pid).first()
    if not row:
        raise HTTPException(404, "No response plan")
    db.delete(row)
    db.commit()


def _opp_enrich(db, p, rows, ds):
    names = {u.id: u.full_name for u in db.query(User)}
    for d in ds:
        d["score"] = d["probability"] * d["impact"]
        d["owner"] = names.get(d["owner_id"])


def _score_ok(db, p, data, row):
    for k in ("probability", "impact"):
        if k in data and not (1 <= (data[k] or 0) <= 5):
            raise HTTPException(422, f"{k} must be 1 to 5")


project_register(router, "opportunities", Opportunity, {"title": str, "probability": int, "impact": int, "strategy": str, "status": str, "owner_id": int, "note": str},
                 choices={"strategy": ("exploit", "enhance", "share", "accept"), "status": ("open", "pursuing", "realized", "closed")}, required=("title",),
                 defaults={"probability": 3, "impact": 3, "strategy": "enhance", "status": "open"}, validate=_score_ok, enrich=_opp_enrich, order=[Opportunity.id])


# ---------------- reserves ----------------
def _reserve_out(db, p, user):
    r = db.query(ProjectReserve).filter_by(project_id=p.id).first()
    dd = db.query(ReserveDrawdown).filter_by(project_id=p.id).order_by(ReserveDrawdown.id.desc()).all()
    names = {u.id: u.full_name for u in db.query(User)}
    risks = {x.id: x.title for x in db.query(Risk).filter_by(project_id=p.id)}
    out = {"currency": p.currency, "contingency": r.contingency if r else 0.0, "management": r.management if r else 0.0}
    for kind in ("contingency", "management"):
        drawn = sum(x.amount for x in dd if x.kind == kind and x.status == "approved")
        pend = sum(x.amount for x in dd if x.kind == kind and x.status == "requested")
        out[f"{kind}_drawn"], out[f"{kind}_pending"] = drawn, pend
        out[f"{kind}_remaining"] = out[kind] - drawn
    out["drawdowns"] = [{"id": x.id, "kind": x.kind, "amount": x.amount, "reason": x.reason, "risk": risks.get(x.risk_id), "status": x.status, "requested_by": names.get(x.requested_by),
                         "decided_by": names.get(x.decided_by), "created_on": x.created_on.isoformat(), "decided_on": x.decided_on.isoformat() if x.decided_on else None} for x in dd]
    out["budget_with_reserves"] = (p.budget_ceiling or 0) + out["contingency"] + out["management"] if p.budget_ceiling else None
    return out


def _cost(db, user, pid):
    p = get_project(db, pid)
    if not can_view_cost(db, user, p):
        raise HTTPException(403, "cost_view permission required")
    return p


@router.get("/projects/{pid}/reserves")
def reserves(pid: int, db=Depends(get_db), user: User = Depends(current_user)):
    return _reserve_out(db, _cost(db, user, pid), user)


class ReserveIn(BaseModel):
    contingency: float | None = Field(None, ge=0)
    management: float | None = Field(None, ge=0)


@router.put("/projects/{pid}/reserves")
def set_reserves(pid: int, body: ReserveIn, db=Depends(get_db), user: User = Depends(current_user)):
    p = _cost(db, user, pid)
    r = db.query(ProjectReserve).filter_by(project_id=pid).first() or ProjectReserve(project_id=pid)
    db.add(r)
    if body.contingency is not None:
        if not (can_manage(db, user, p) and p.baseline_version == 0) and user.role not in ("PMO", "ADMIN"):
            raise HTTPException(403, "The project manager sets the contingency before the baseline; after that only the PMO can change it")
        r.contingency = body.contingency
    if body.management is not None:
        if user.role not in EXECS:
            raise HTTPException(403, "Management reserve is set by the PMO or a decision maker")
        r.management = body.management
    log(db, user.id, "reserve.set", "project", pid, body.model_dump(exclude_none=True))
    db.commit()
    return _reserve_out(db, p, user)


class DrawIn(BaseModel):
    kind: str = Field(pattern="^(contingency|management)$")
    amount: float = Field(gt=0)
    reason: str = Field(min_length=1, max_length=600)
    risk_id: int | None = None


@router.post("/projects/{pid}/reserves/drawdowns", status_code=201)
def draw(pid: int, body: DrawIn, db=Depends(get_db), user: User = Depends(current_user)):
    p = _cost(db, user, pid)
    need_manage(db, user, p)
    if p.state not in ("execution", "closing"):
        raise HTTPException(409, "Reserves are drawn down during execution")
    cur = _reserve_out(db, p, user)
    if body.amount > cur[f"{body.kind}_remaining"] - cur[f"{body.kind}_pending"] + 1e-6:
        raise HTTPException(409, f"Only {cur[f'{body.kind}_remaining'] - cur[f'{body.kind}_pending']:,.0f} of the {body.kind} reserve is left")
    if body.risk_id:
        rk = db.get(Risk, body.risk_id)
        if not rk or rk.project_id != pid:
            raise HTTPException(422, "Risk not found in this project")
    auto = body.kind == "contingency"          # contingency is the project manager's; management reserve needs approval above the project
    d = ReserveDrawdown(project_id=pid, kind=body.kind, amount=body.amount, reason=body.reason, risk_id=body.risk_id, requested_by=user.id,
                        status="approved" if auto else "requested", decided_by=user.id if auto else None, decided_on=date.today() if auto else None)
    db.add(d)
    db.flush()
    log(db, user.id, f"reserve.{'drawn' if auto else 'requested'}", "project", pid, {"kind": body.kind, "amount": body.amount})
    if not auto:
        for u in db.query(User).filter(User.role.in_(EXECS), User.active.is_(True)):
            notify(db, u.id, "reserve", f"Management reserve requested: {p.number}", f"{body.amount:,.0f} {p.currency}: {body.reason}", f"#/projects/{pid}")
    db.commit()
    return _reserve_out(db, p, user)


class DrawDecision(BaseModel):
    approve: bool
    note: str | None = None


@router.post("/projects/{pid}/reserves/drawdowns/{did}/decision")
def decide_draw(pid: int, did: int, body: DrawDecision, db=Depends(get_db), user: User = Depends(require_roles(*EXECS))):
    p = get_project(db, pid)
    d = db.get(ReserveDrawdown, did)
    if not d or d.project_id != pid:
        raise HTTPException(404, "Not found")
    if d.status != "requested":
        raise HTTPException(409, "Already decided")
    if body.approve:
        cur = _reserve_out(db, p, user)
        if d.amount > cur[f"{d.kind}_remaining"] + 1e-6:
            raise HTTPException(409, "Not enough reserve left")
    d.status, d.decided_by, d.decided_on = ("approved" if body.approve else "rejected"), user.id, date.today()
    log(db, user.id, f"reserve.{d.status}", "project", pid, {"drawdown": did})
    notify(db, d.requested_by, "reserve", f"Reserve request {d.status}: {p.number}", body.note, f"#/projects/{pid}")
    db.commit()
    return _reserve_out(db, p, user)


# ---------------- quality log ----------------
def _q_validate(db, p, data, row):
    if data.get("deliverable_id"):
        d = db.get(Deliverable, data["deliverable_id"])
        if not d or d.project_id != p.id:
            raise HTTPException(422, "Deliverable not found in this project")
    st = data.get("status") or (row.status if row else "open")
    if st == "closed" and "closed_on" not in data:
        data["closed_on"] = date.today()
    elif st in ("open", "fixed", "verified") and "status" in data:
        data["closed_on"] = None
    if row and row.status == "open" and st == "verified":
        raise HTTPException(409, "Mark it fixed before verified")


def _q_enrich(db, p, rows, ds):
    dl = {d.id: f"{d.code} · {d.name}" for d in db.query(Deliverable).filter_by(project_id=p.id)}
    names = {u.id: u.full_name for u in db.query(User)}
    for d in ds:
        d["deliverable"] = dl.get(d["deliverable_id"])
        d["owner"] = names.get(d["owner_id"])


Q = project_register(router, "quality", QualityItem,
                     {"kind": str, "title": str, "severity": str, "status": str, "deliverable_id": int, "found_on": date, "owner_id": int, "note": str},
                     choices={"kind": ("defect", "inspection", "audit", "test"), "severity": ("low", "medium", "high", "critical"), "status": ("open", "fixed", "verified", "closed")},
                     required=("title",), defaults={"kind": "defect", "severity": "medium", "status": "open"}, validate=_q_validate, enrich=_q_enrich, order=[QualityItem.id.desc()])


@router.get("/projects/{pid}/quality-summary")
def quality_summary(pid: int, db=Depends(get_db), user: User = Depends(current_user)):
    _view(db, user, pid)
    items = db.query(QualityItem).filter_by(project_id=pid).all()
    defects = [i for i in items if i.kind == "defect"]
    op = [i for i in defects if i.status in ("open", "fixed")]
    return {"defects": len(defects), "open_defects": len(op), "open_by_severity": {s: sum(1 for i in op if i.severity == s) for s in ("critical", "high", "medium", "low")},
            "closure_rate_pct": round(100 * (len(defects) - len(op)) / len(defects)) if defects else None, "inspections": sum(1 for i in items if i.kind != "defect")}


# ---------------- document versions ----------------
class VersionIn(BaseModel):
    filename: str = Field(min_length=1, max_length=200)
    content_b64: str
    note: str | None = Field(None, max_length=300)


def _doc(db, pid, did):
    d = db.get(Document, did)
    if not d or d.project_id != pid:
        raise HTTPException(404, "Document not found")
    return d


@router.post("/projects/{pid}/documents/{did}/versions", status_code=201)
def new_version(pid: int, did: int, body: VersionIn, db=Depends(get_db), user: User = Depends(require_roles(*MANAGE))):
    p = get_project(db, pid)
    need_manage(db, user, p)
    d = _doc(db, pid, did)
    name = os.path.basename(body.filename.replace("\\", "/"))
    if os.path.splitext(name)[1].lower() not in DOC_EXT:
        raise HTTPException(422, "File type not allowed")
    try:
        raw = base64.b64decode(body.content_b64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(422, "content_b64 is not valid base64")
    if not raw or len(raw) > MAX_DOC_BYTES:
        raise HTTPException(422, f"File must be between 1 byte and {MAX_DOC_BYTES // 1024 // 1024} MB")
    n = db.query(DocumentVersion).filter_by(document_id=did).count()
    db.add(DocumentVersion(document_id=did, version=n + 1, filename=d.filename, size=d.size, content=d.content, note=None, uploaded_by=d.uploaded_by, uploaded_at=d.uploaded_at))
    d.filename, d.size, d.content, d.uploaded_by, d.uploaded_at = name, len(raw), raw, user.id, __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    log(db, user.id, "document.new_version", "project", pid, {"document_id": did, "version": n + 2, "note": body.note})
    db.commit()
    return {"document_id": did, "version": n + 2}


@router.get("/projects/{pid}/documents/{did}/versions")
def versions(pid: int, did: int, db=Depends(get_db), user: User = Depends(current_user)):
    _view(db, user, pid)
    d = _doc(db, pid, did)
    names = {u.id: u.full_name for u in db.query(User)}
    old = db.query(DocumentVersion).filter_by(document_id=did).order_by(DocumentVersion.version.desc()).all()
    cur = {"version": len(old) + 1, "current": True, "filename": d.filename, "size": d.size, "uploaded_by": names.get(d.uploaded_by), "uploaded_at": d.uploaded_at.isoformat(), "id": None}
    return [cur] + [{"id": v.id, "version": v.version, "current": False, "filename": v.filename, "size": v.size, "uploaded_by": names.get(v.uploaded_by), "uploaded_at": v.uploaded_at.isoformat()} for v in old]


@router.get("/projects/{pid}/documents/{did}/versions/{vid}/content")
def version_content(pid: int, did: int, vid: int, db=Depends(get_db), user: User = Depends(current_user)):
    _view(db, user, pid)
    _doc(db, pid, did)
    v = db.get(DocumentVersion, vid)
    if not v or v.document_id != did:
        raise HTTPException(404, "Version not found")
    return {"filename": v.filename, "content_b64": base64.b64encode(v.content).decode()}


# ---------------- stakeholder engagement ----------------
LEVELS = ("unaware", "resistant", "neutral", "supportive", "leading")


class EngIn(BaseModel):
    current: str
    desired: str
    plan: str | None = Field(None, max_length=3000)


@router.get("/projects/{pid}/engagement")
def engagement(pid: int, db=Depends(get_db), user: User = Depends(current_user)):
    _view(db, user, pid)
    eng = {e.stakeholder_id: e for e in db.query(StakeholderEngagement).filter_by(project_id=pid)}
    out = []
    for s in db.query(Stakeholder).filter_by(project_id=pid).order_by(Stakeholder.id):
        e = eng.get(s.id)
        gap = LEVELS.index(e.desired) - LEVELS.index(e.current) if e else None
        out.append({"stakeholder_id": s.id, "name": s.name, "organisation": s.organisation, "role": s.role, "power": s.power, "interest": s.interest,
                    "current": e.current if e else None, "desired": e.desired if e else None, "gap": gap, "plan": e.plan if e else None,
                    "reviewed_on": e.reviewed_on.isoformat() if e and e.reviewed_on else None})
    out.sort(key=lambda x: (-(x["gap"] or 0) * x["power"]))
    return out


@router.put("/projects/{pid}/stakeholders/{sid}/engagement")
def set_engagement(pid: int, sid: int, body: EngIn, db=Depends(get_db), user: User = Depends(current_user)):
    p = _view(db, user, pid)
    need_manage(db, user, p)
    s = db.get(Stakeholder, sid)
    if not s or s.project_id != pid:
        raise HTTPException(404, "Stakeholder not found")
    if body.current not in LEVELS or body.desired not in LEVELS:
        raise HTTPException(422, f"Levels are: {', '.join(LEVELS)}")
    if body.current != body.desired and not (body.plan or "").strip():
        raise HTTPException(422, "Say how you will close the gap between current and desired engagement")
    e = db.query(StakeholderEngagement).filter_by(stakeholder_id=sid).first()
    if not e:
        e = StakeholderEngagement(stakeholder_id=sid, project_id=pid)
        db.add(e)
    e.current, e.desired, e.plan, e.reviewed_on = body.current, body.desired, body.plan, date.today()
    log(db, user.id, "stakeholder.engagement", "project", pid, {"stakeholder": sid})
    db.commit()
    return next(x for x in engagement(pid, db, user) if x["stakeholder_id"] == sid)
