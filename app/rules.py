"""Timesheet rule engine (Section 2.3). Pure functions: no database access, so every
rule is unit-testable. The caller builds a Ctx from the database and evaluates it."""
from dataclasses import dataclass, field
from datetime import date, timedelta

BLOCK, WARN, FLAG = "BLOCK", "WARN", "FLAG"

# Project states in which time may be booked, mapped to the activity phase allowed there.
STATE_PHASE = {"tendering": "tendering", "planning": "planning", "execution": "execution", "closing": "closing"}


@dataclass
class Violation:
    rule: str
    severity: str
    message: str


@dataclass
class Ctx:
    today: date
    entry_date: date
    hours: float
    severities: dict
    params: dict
    # target
    is_nonproject: bool = False
    code_valid: bool = True
    project_state: str | None = None
    project_start: date | None = None
    project_end: date | None = None
    assigned: bool = True
    activity_found: bool = True
    activity_phase: str | None = None
    activity_locked: bool = True
    activity_cap: float | None = None        # per-staff cap for this activity
    user_activity_hours: float = 0.0         # existing hours of this user on the activity (excl. this entry)
    # capacity
    week_hours: float = 0.0                  # existing hours this week, all projects (excl. this entry)
    capacity: float = 40.0
    # integrity
    locked_through: date | None = None
    exact_duplicate: bool = False
    is_leave: bool = False


def week_start(d: date, sunday: bool = True) -> date:
    """Start of the work week containing d (Sunday-based by default)."""
    back = (d.weekday() + 1) % 7 if sunday else d.weekday()
    return d - timedelta(days=back)


def evaluate(c: Ctx) -> list[Violation]:
    v: list[Violation] = []
    sev = lambda rule: c.severities.get(rule, BLOCK)

    # R8 period lock
    if c.locked_through and c.entry_date <= c.locked_through:
        v.append(Violation("R8", sev("R8"), f"Period locked through {c.locked_through}"))
    # R9 future date (leave may be booked ahead)
    if c.entry_date > c.today and not c.is_leave:
        v.append(Violation("R9", sev("R9"), "Future date not allowed"))

    if c.is_nonproject:
        if not c.code_valid:
            v.append(Violation("R6", sev("R6"), "Unknown non-project code"))
    else:
        # R3 assignment
        if not c.assigned:
            v.append(Violation("R3", sev("R3"), "Not assigned to this project"))
        # R4 project state / activity phase
        if c.project_state not in STATE_PHASE:
            v.append(Violation("R4", sev("R4"), f"Project is {c.project_state}: time entry not allowed"))
        elif c.activity_found and c.activity_phase != STATE_PHASE[c.project_state]:
            v.append(Violation("R4", sev("R4"), "Activity not valid in current project status"))
        # R6 activity existence in approved baseline
        if not c.activity_found:
            v.append(Violation("R6", sev("R6"), "Activity not in baseline"))
        elif c.activity_phase == "execution" and not c.activity_locked:
            v.append(Violation("R6", sev("R6"), "Activity not in baseline"))
        # R5 date window
        if c.project_start and c.project_end:
            tol = int(c.params["date_tolerance_days"])
            if c.entry_date < c.project_start or c.entry_date > c.project_end:
                gap = (c.project_start - c.entry_date).days if c.entry_date < c.project_start else (c.entry_date - c.project_end).days
                if gap > tol:
                    v.append(Violation("R5", BLOCK, f"Entry date {gap} days outside project window (tolerance {tol})"))
                else:
                    v.append(Violation("R5", sev("R5"), f"Entry date outside project window ({gap} days)"))
        # R2 per-activity cap (soft tier inside tolerance, hard tier beyond)
        if c.activity_cap is not None and c.activity_found:
            total = c.user_activity_hours + c.hours
            if total > c.activity_cap:
                hard = c.activity_cap * (1 + c.params["activity_cap_tolerance"])
                s = BLOCK if total > hard else sev("R2")
                v.append(Violation("R2", s, f"Activity cap exceeded ({total:g}/{c.activity_cap:g} hrs)"))

    # R1 weekly capacity (all projects and non-project time)
    total_week = c.week_hours + c.hours
    if total_week > c.capacity:
        ceiling = c.capacity * c.params["overtime_ceiling_pct"]
        s = BLOCK if total_week > ceiling else sev("R1")
        v.append(Violation("R1", s, f"Weekly capacity exceeded ({total_week:g}/{c.capacity:g} hrs)"))

    # R7 exact duplicate
    if c.exact_duplicate:
        v.append(Violation("R7", sev("R7"), "Entry already exists"))
    return v


def blocking(vs): return [x for x in vs if x.severity == BLOCK]
def warnings(vs): return [x for x in vs if x.severity == WARN]
def flags(vs): return [x for x in vs if x.severity == FLAG]
