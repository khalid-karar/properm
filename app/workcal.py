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


def leave_days(db, user_id: int, start: date, end: date) -> set:
    """Working days in [start, end] covered by the person's approved leave."""
    from .models import LeaveRequest
    hol = holiday_map(db, start, end)
    out = set()
    for lv in db.query(LeaveRequest).filter(LeaveRequest.user_id == user_id, LeaveRequest.status == "approved",
                                            LeaveRequest.start <= end, LeaveRequest.end >= start):
        d = max(lv.start, start)
        while d <= min(lv.end, end):
            if not is_weekend(d) and d not in hol:
                out.add(d)
            d += timedelta(days=1)
    return out


def effective_capacity(db, capacity: float, week_start: date, user_id: int | None = None) -> float:
    """Weekly capacity after holidays and, when user_id is given, approved leave (used for planning, not for overtime rules)."""
    info = week_info(db, week_start)
    working = info["working_days"]
    if user_id is not None:
        working -= len(leave_days(db, user_id, week_start, week_start + timedelta(days=6)))
    return round(capacity * (max(working, 0) / info["base_days"] if info["base_days"] else 1.0), 2)
