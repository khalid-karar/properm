"""Earned value calculation (3.1). Definitions follow the V1 flow chart:
PV = sum over activities of baseline cost x share elapsed between the activity's own planned_start and planned_end
(an activity without dates falls back to the project window and is reported in warnings);
EV = sum(activity percent complete x activity baseline cost);
AC = labor (approved hours x the grade rate in effect on each entry date, so past cost is never repriced) + non-labor ledger entries that are approved and invoiced/paid;
CPI = EV/AC; SPI = EV/PV; EAC = BAC/CPI."""
from datetime import date

from .models import Activity, ActivityProgress, CostEntry, Project, RateCard, TimesheetEntry, User


def latest_progress(db, activity_id: int, as_of: date):
    return (db.query(ActivityProgress)
            .filter(ActivityProgress.activity_id == activity_id, ActivityProgress.week_start <= as_of)
            .order_by(ActivityProgress.week_start.desc(), ActivityProgress.id.desc()).first())


def rate_on(db, grade: str, day: date):
    """Rate card row in force for a grade on a date (latest effective_from <= day)."""
    return (db.query(RateCard).filter(RateCard.grade == grade, RateCard.effective_from <= day)
            .order_by(RateCard.effective_from.desc()).first())


def _share(start: date, end: date, as_of: date) -> float:
    if as_of < start:
        return 0.0
    if end <= start or as_of >= end:
        return 1.0
    return (as_of - start).days / (end - start).days


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

    pv, fallback, unphased = 0.0, [], []
    for a in priced:
        if a.planned_start and a.planned_end:
            pv += a.baseline_cost * _share(a.planned_start, a.planned_end, as_of)
        elif p.planned_start and p.planned_end:
            pv += a.baseline_cost * _share(p.planned_start, p.planned_end, as_of)
            fallback.append(a.code)
        else:
            unphased.append(a.code)
    if fallback:
        warnings.append(f"PV for {', '.join(fallback)} uses the project window (no activity dates)")
    if unphased:
        pv = None
        warnings.append(f"No dates for {', '.join(unphased)} and no project window: PV and SPI unavailable")

    labor, no_grade, no_rate, wrong_ccy = 0.0, set(), set(), set()
    rows = (db.query(TimesheetEntry, User).join(User, User.id == TimesheetEntry.user_id)
            .filter(TimesheetEntry.project_id == p.id, TimesheetEntry.status == "approved",
                    TimesheetEntry.entry_date <= as_of).all())
    for e_, u in rows:
        if not u.rate_grade:
            no_grade.add(u.staff_id)
            continue
        rate = rate_on(db, u.rate_grade, e_.entry_date)
        if rate is None:
            no_rate.add(f"{u.rate_grade} on {e_.entry_date}")
        elif rate.currency != p.currency:
            wrong_ccy.add(f"{u.rate_grade} ({rate.currency})")
        else:
            labor += e_.hours * rate.hourly_rate
    if no_grade:
        warnings.append(f"Staff without a rate grade (labor cost counted as 0): {', '.join(sorted(no_grade))}")
    if no_rate:
        warnings.append(f"No rate in effect (labor cost counted as 0): {', '.join(sorted(no_rate))}")
    if wrong_ccy:
        warnings.append(f"Rate currency differs from project currency {p.currency}, excluded: {', '.join(sorted(wrong_ccy))}")

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
