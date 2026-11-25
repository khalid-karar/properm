"""Forecast: where a running project is heading, from the progress and earned-value data it already has.

Schedule: earned schedule. The planned value curve tells on which date the plan expected to have earned what the project has
earned so far (the "earned schedule" date). Time spent against that date gives a schedule performance index in time (SPI-t);
the planned duration divided by SPI-t is the forecast duration. A second, recent-pace estimate uses the last 28 days only.
Cost: three standard estimates at completion (EAC). Likely = BAC / CPI (the project keeps its cost performance), low and high
are the lowest and highest of the three.
Everything is a pure function of the stored data, so a forecast can always be explained and repeated."""
from datetime import date, timedelta

from .evm import _share, compute_evm, latest_progress
from .models import Activity, ActivityProgress, Project

RECENT_DAYS = 28
r2 = lambda x: None if x is None else round(x, 2)


def _curves(db, p: Project):
    acts = [a for a in db.query(Activity).filter_by(project_id=p.id, phase="execution", locked=True).all() if a.baseline_cost]
    spans = []
    for a in acts:
        s, e = (a.planned_start, a.planned_end) if a.planned_start and a.planned_end else (p.planned_start, p.planned_end)
        spans.append((a, s, e))
    return spans


def _pv(spans, day: date) -> float:
    return sum(a.baseline_cost * _share(s, e, day) for a, s, e in spans if s and e)


def _ev(db, spans, day: date) -> float:
    total = 0.0
    for a, _, _ in spans:
        lp = latest_progress(db, a.id, day)
        total += a.baseline_cost * (min(100.0, lp.pct_complete) if lp else 0.0) / 100.0
    return total


def _earned_schedule_day(spans, start: date, end: date, ev: float) -> date:
    """Earliest day on which the planned value reaches `ev` (planned value never decreases, so a bisection finds it)."""
    lo, hi = 0, (end - start).days
    if _pv(spans, end) <= ev:
        return end
    while lo < hi:
        mid = (lo + hi) // 2
        if _pv(spans, start + timedelta(days=mid)) >= ev:
            hi = mid
        else:
            lo = mid + 1
    return start + timedelta(days=lo)


def _rag(value: float, warn: float, crit: float) -> str:
    return "RED" if value >= crit else "AMBER" if value >= warn else "GREEN"


def compute_forecast(db, p: Project, as_of: date, params: dict) -> dict:
    base = {"available": False, "as_of": as_of, "project_id": p.id}
    e = compute_evm(db, p, as_of)
    if not e.get("available"):
        return {**base, "reason": e.get("reason", "No baseline cost to forecast from"), "warnings": e.get("warnings", [])}
    spans = _curves(db, p)
    starts = [s for _, s, _ in spans if s]
    ends = [x for _, _, x in spans if x]
    if not starts or not ends:
        return {**base, "reason": "Planned dates are missing, so a finish date cannot be forecast", "warnings": e["warnings"]}
    start, end = min(starts), max(ends)
    bac, ev, ac = e["BAC"], e["EV"], e["AC"]
    pct = round(100 * ev / bac, 1) if bac else 0.0
    out = {**base, "available": True, "currency": p.currency, "percent_complete": pct, "baseline_start": start, "baseline_finish": end, "warnings": list(e["warnings"])}

    # ---- schedule ----
    reasons = []
    duration = (end - start).days
    if ev <= 0:
        out["finish"] = None
        reasons.append("No progress has been recorded yet, so the finish date cannot be forecast.")
    elif ev >= bac:
        out["finish"] = {"likely": as_of, "earliest": as_of, "latest": as_of}
        out["slip_days"] = (as_of - end).days
    else:
        es_day = _earned_schedule_day(spans, start, end, ev)
        es_days = max(0, (es_day - start).days)
        at_days = max(1, (as_of - start).days)
        if es_days == 0:
            out["finish"] = None
            reasons.append("Work earned so far is less than the plan earned on day one; the finish date cannot be forecast.")
        else:
            spi_t = es_days / at_days
            remaining_plan = duration - es_days
            cum = as_of + timedelta(days=round(remaining_plan / spi_t)) if remaining_plan > 0 else as_of
            # recent pace: earned and planned value over the last RECENT_DAYS
            then = as_of - timedelta(days=RECENT_DAYS)
            recent = None
            if then > start:
                dpv, dev = _pv(spans, as_of) - _pv(spans, then), ev - _ev(db, spans, then)
                if dpv > 0 and dev > 0:
                    recent = as_of + timedelta(days=round(remaining_plan / (dev / dpv))) if remaining_plan > 0 else as_of
            cands = [cum] + ([recent] if recent else [])
            out["finish"] = {"likely": cum, "earliest": min(cands), "latest": max(cands), "recent_pace": recent}
            out["spi_t"] = round(spi_t, 3)
            out["slip_days"] = (cum - end).days
    if out.get("finish") is None:
        out["slip_days"] = None

    # ---- cost ----
    cpi, spi = e.get("CPI"), e.get("SPI")
    cost = {"BAC": bac, "AC": ac, "EV": ev}
    if ev <= 0 or ac <= 0:
        cost.update({"EAC": None, "low": None, "high": None, "VAC": None, "overrun_pct": None})
    else:
        typical = ac + (bac - ev)                                   # the rest of the work is done at the budgeted rate
        by_cpi = bac / cpi                                          # cost performance continues
        combined = ac + (bac - ev) / (cpi * spi) if spi else by_cpi  # cost and schedule performance both continue
        vals = [typical, by_cpi, combined]
        cost.update({"EAC": r2(by_cpi), "low": r2(min(vals)), "high": r2(max(vals)), "VAC": r2(bac - by_cpi), "overrun_pct": round((by_cpi - bac) / bac, 4),
                     "methods": {"budgeted_rate": r2(typical), "cpi": r2(by_cpi), "cpi_and_spi": r2(combined)}})
    out["cost"] = cost

    # ---- how much to trust it ----
    last = None
    for a, _, _ in spans:
        lp = latest_progress(db, a.id, as_of)
        if lp and (last is None or lp.week_start > last):
            last = lp.week_start
    stale_days = int(params.get("stale_progress_weeks", 2)) * 7
    if last is not None and (as_of - last).days > stale_days:
        reasons.append(f"The last progress update is from {last}; the forecast may be out of date.")
    if pct < 10:
        reasons.append("Less than 10% is complete; early forecasts move a lot.")
    out["confidence"] = "low" if (pct < 10 or ev <= 0) else "medium" if (reasons or pct < 40) else "high"
    out["reasons"] = reasons

    # ---- status against the baseline ----
    st = ["GREEN"]
    if out.get("slip_days") is not None:
        st.append(_rag(out["slip_days"], params["forecast_slip_warning_days"], params["forecast_slip_critical_days"]))
    if cost.get("overrun_pct") is not None:
        st.append(_rag(cost["overrun_pct"], params["forecast_overrun_warning_pct"], params["forecast_overrun_critical_pct"]))
    out["status"] = "RED" if "RED" in st else "AMBER" if "AMBER" in st else "GREEN"
    out["last_progress"] = last
    return out
