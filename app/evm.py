"""Earned value calculation (3.1). Definitions follow the V1 flow chart:
PV = baseline cost phased linearly over the planned window up to the status date (MVP simplification);
EV = sum(activity percent complete x activity baseline cost);
AC = labor (approved hours x staff cost rate) + non-labor ledger entries that are approved and invoiced/paid;
CPI = EV/AC; SPI = EV/PV; EAC = BAC/CPI."""
from datetime import date

from .models import Activity, ActivityProgress, CostEntry, Project, TimesheetEntry, User


def latest_progress(db, activity_id: int, as_of: date):
    return (db.query(ActivityProgress)
            .filter(ActivityProgress.activity_id == activity_id, ActivityProgress.week_start <= as_of)
            .order_by(ActivityProgress.week_start.desc(), ActivityProgress.id.desc()).first())


def compute_evm(db, p: Project, as_of: date) -> dict:
    warnings: list[str] = []
    acts = db.query(Activity).filter_by(project_id=p.id, phase="execution", locked=True).all()
    priced = [a for a in acts if a.baseline_cost is not None]
    missing = [a.code for a in acts if a.baseline_cost is None]
    if missing:
        warnings.append(f"Activities without baseline_cost excluded from EVM: {', '.join(missing)}")
    bac = sum(a.baseline_cost for a in priced)
    if bac <= 0:
        return {"available": False, "reason": "No baseline cost set on any baselined activity", "warnings": warnings}

    ev = 0.0
    for a in priced:
        lp = latest_progress(db, a.id, as_of)
        ev += a.baseline_cost * (lp.pct_complete if lp else 0.0) / 100.0

    if p.planned_start and p.planned_end and p.planned_end > p.planned_start:
        frac = (as_of - p.planned_start).days / (p.planned_end - p.planned_start).days
        pv = bac * min(1.0, max(0.0, frac))
    else:
        pv = None
        warnings.append("planned_start/planned_end missing: PV and SPI unavailable")

    labor, no_rate = 0.0, set()
    rows = (db.query(TimesheetEntry, User).join(User, User.id == TimesheetEntry.user_id)
            .filter(TimesheetEntry.project_id == p.id, TimesheetEntry.status == "approved",
                    TimesheetEntry.entry_date <= as_of).all())
    for e, u in rows:
        if u.cost_rate_hour is None:
            no_rate.add(u.staff_id)
        else:
            labor += e.hours * u.cost_rate_hour
    if no_rate:
        warnings.append(f"Staff without cost rate (labor cost counted as 0): {', '.join(sorted(no_rate))}")

    nonlabor = 0.0
    for c in db.query(CostEntry).filter(CostEntry.project_id == p.id, CostEntry.approval == "approved",
                                        CostEntry.cost_status.in_(("invoiced", "paid")), CostEntry.entry_date <= as_of):
        if c.currency != p.currency:
            warnings.append(f"Cost entry {c.id} is in {c.currency}, project currency is {p.currency}: excluded")
            continue
        nonlabor += c.amount
    ac = labor + nonlabor

    cpi = ev / ac if ac > 0 else None
    spi = ev / pv if pv and pv > 0 else None
    eac = bac / cpi if cpi else None
    r = lambda x: None if x is None else round(x, 2)
    return {"available": True, "as_of": as_of, "currency": p.currency, "BAC": r(bac), "PV": r(pv), "EV": r(ev),
            "AC": r(ac), "AC_labor": r(labor), "AC_nonlabor": r(nonlabor),
            "CPI": None if cpi is None else round(cpi, 3), "SPI": None if spi is None else round(spi, 3),
            "EAC": r(eac), "ETC": r(eac - ac) if eac is not None else None, "VAC": r(bac - eac) if eac is not None else None,
            "warnings": warnings}
