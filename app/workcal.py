"""Work calendar: Sunday-Thursday week plus public holidays."""
from datetime import date, timedelta

from .config import WEEKEND_DAYS
from .models import Holiday


def is_weekend(d: date) -> bool:
    return d.weekday() in WEEKEND_DAYS


def holiday_map(db, start: date, end: date) -> dict:
    return {h.day: h.name for h in db.query(Holiday).filter(Holiday.day >= start, Holiday.day <= end)}


def non_working_reason(db, d: date) -> str | None:
    h = holiday_map(db, d, d).get(d)
    if h:
        return h
    return "weekend" if is_weekend(d) else None


def week_info(db, week_start: date) -> dict:
    days = [week_start + timedelta(days=i) for i in range(7)]
    hol = holiday_map(db, days[0], days[-1])
    working = [d for d in days if not is_weekend(d) and d not in hol]
    base = [d for d in days if not is_weekend(d)]
    return {"week_start": week_start, "working_days": len(working), "base_days": len(base), "holidays": {str(k): v for k, v in hol.items()},
            "factor": (len(working) / len(base)) if base else 1.0}


def effective_capacity(db, capacity: float, week_start: date) -> float:
    return round(capacity * week_info(db, week_start)["factor"], 2)
