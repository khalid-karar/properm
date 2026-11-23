"""Audit-log viewer, period-lock status and rate-card maintenance (read-mostly oversight for PMO/ADMIN)."""
from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func

from ..audit import log
from ..deps import get_db, require_roles
from ..models import AuditLog, PeriodLock, RateCard, TimesheetEntry, User

router = APIRouter(tags=["oversight"])


@router.get("/admin/audit")
def audit_log(actor_id: int | None = None, action: str | None = None, entity: str | None = None, entity_id: int | None = None,
              date_from: date | None = None, date_to: date | None = None, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
              db=Depends(get_db), _: User = Depends(require_roles("PMO", "ADMIN"))):
    q = db.query(AuditLog)
    if actor_id is not None:
        q = q.filter(AuditLog.actor_id == actor_id)
    if action:
        q = q.filter(AuditLog.action.like(f"{action.strip()}%"))
    if entity:
        q = q.filter(AuditLog.entity == entity)
    if entity_id is not None:
        q = q.filter(AuditLog.entity_id == entity_id)
    if date_from:
        q = q.filter(AuditLog.ts >= datetime.combine(date_from, time.min, tzinfo=timezone.utc))
    if date_to:
        q = q.filter(AuditLog.ts <= datetime.combine(date_to, time.max, tzinfo=timezone.utc))
    total = q.count()
    rows = q.order_by(AuditLog.id.desc()).offset(offset).limit(limit).all()
    names = {u.id: u.full_name for u in db.query(User).filter(User.id.in_({r.actor_id for r in rows if r.actor_id} or {0}))}
    return {"total": total, "items": [{"id": r.id, "ts": r.ts.isoformat() if r.ts else None, "actor_id": r.actor_id, "actor": names.get(r.actor_id),
                                       "action": r.action, "entity": r.entity, "entity_id": r.entity_id, "detail": r.detail} for r in rows]}


@router.get("/admin/audit/facets")
def audit_facets(db=Depends(get_db), _: User = Depends(require_roles("PMO", "ADMIN"))):
    return {"actions": [a for (a,) in db.query(AuditLog.action).distinct().order_by(AuditLog.action)],
            "entities": [e for (e,) in db.query(AuditLog.entity).distinct().order_by(AuditLog.entity)]}


@router.get("/timesheets/periods")
def periods(db=Depends(get_db), _: User = Depends(require_roles("PMO", "ADMIN"))):
    locks = db.query(PeriodLock).order_by(PeriodLock.id.desc()).limit(20).all()
    names = {u.id: u.full_name for u in db.query(User).filter(User.id.in_({l.locked_by for l in locks} or {0}))}
    cur = locks[0].locked_through if locks else None
    pending = db.query(TimesheetEntry.entry_date, func.count(TimesheetEntry.id)).filter(TimesheetEntry.status == "submitted").group_by(TimesheetEntry.entry_date).all()
    return {"locked_through": cur.isoformat() if cur else None,
            "history": [{"locked_through": l.locked_through.isoformat(), "locked_by": names.get(l.locked_by), "at": l.created_at.isoformat() if l.created_at else None} for l in locks],
            "pending_by_date": {d.isoformat(): n for d, n in sorted(pending)}}


@router.delete("/admin/rates/{rid}", status_code=204)
def delete_future_rate(rid: int, db=Depends(get_db), user: User = Depends(require_roles("ADMIN", "PMO"))):
    """Only a rate that has not taken effect yet may be removed (so past cost is never repriced)."""
    r = db.get(RateCard, rid)
    if not r:
        raise HTTPException(404, "Rate not found")
    if r.effective_from <= date.today():
        raise HTTPException(409, "This rate is already in effect; add a new rate with a later effective date instead")
    log(db, user.id, "rate.deleted", "rate_card", rid, {"grade": r.grade, "effective_from": r.effective_from.isoformat()})
    db.delete(r)
    db.commit()
