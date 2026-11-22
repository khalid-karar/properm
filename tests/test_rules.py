from datetime import date, timedelta
from app import rules
from app.config import DEFAULT_PARAMS, DEFAULT_SEVERITIES

TODAY = date(2026, 11, 18)  # Wednesday


def ctx(**kw):
    base = dict(today=TODAY, entry_date=TODAY, hours=8, severities=dict(DEFAULT_SEVERITIES),
                params=dict(DEFAULT_PARAMS), project_state="execution", activity_phase="execution",
                activity_cap=100, project_start=TODAY - timedelta(days=30), project_end=TODAY + timedelta(days=30))
    base.update(kw)
    return rules.Ctx(**base)


def ids(vs, sev=None):
    return {v.rule for v in vs if sev is None or v.severity == sev}


def test_clean_entry_passes():
    assert rules.evaluate(ctx()) == []


def test_week_start_is_sunday():
    assert rules.week_start(date(2026, 11, 18)) == date(2026, 11, 15)   # Wed -> Sun
    assert rules.week_start(date(2026, 11, 15)) == date(2026, 11, 15)   # Sun -> Sun
    assert rules.week_start(date(2026, 11, 21)) == date(2026, 11, 15)   # Sat -> Sun


def test_r1_capacity_tiers():
    assert ids(rules.evaluate(ctx(week_hours=32, hours=8))) == set()                   # 40/40 ok
    v = rules.evaluate(ctx(week_hours=36, hours=8))                                      # 44/40 -> WARN
    assert ids(v, "WARN") == {"R1"}
    v = rules.evaluate(ctx(week_hours=45, hours=8))                                      # 53 > 50 ceiling -> BLOCK
    assert ids(v, "BLOCK") == {"R1"}


def test_r1_severity_is_configurable():
    sev = dict(DEFAULT_SEVERITIES, R1="FLAG")
    v = rules.evaluate(ctx(week_hours=36, hours=8, severities=sev))
    assert ids(v, "FLAG") == {"R1"} and not rules.blocking(v)


def test_r2_activity_cap_tiers():
    assert ids(rules.evaluate(ctx(activity_cap=20, user_activity_hours=10, hours=8))) == set()
    v = rules.evaluate(ctx(activity_cap=20, user_activity_hours=15, hours=6))            # 21/20 -> within 10% -> FLAG
    assert ids(v, "FLAG") == {"R2"}
    v = rules.evaluate(ctx(activity_cap=20, user_activity_hours=15, hours=8))            # 23/20 -> BLOCK
    assert ids(v, "BLOCK") == {"R2"}


def test_r3_not_assigned():
    assert ids(rules.evaluate(ctx(assigned=False)), "BLOCK") == {"R3"}


def test_r4_state_and_phase():
    assert ids(rules.evaluate(ctx(project_state="archived")), "BLOCK") == {"R4"}
    assert ids(rules.evaluate(ctx(project_state="planning", activity_phase="execution")), "BLOCK") == {"R4"}
    assert rules.evaluate(ctx(project_state="tendering", activity_phase="tendering", project_start=None, project_end=None)) == []


def test_r5_date_window():
    v = rules.evaluate(ctx(entry_date=TODAY - timedelta(days=40), project_start=TODAY - timedelta(days=30)))
    assert ids(v, "WARN") == {"R5"}                                                      # 10 days outside
    v = rules.evaluate(ctx(entry_date=TODAY - timedelta(days=60), project_start=TODAY - timedelta(days=30)))
    assert ids(v, "BLOCK") == {"R5"}                                                     # 30 days outside


def test_r6_activity_existence():
    assert ids(rules.evaluate(ctx(activity_found=False)), "BLOCK") == {"R6"}
    assert ids(rules.evaluate(ctx(activity_locked=False)), "BLOCK") == {"R6"}
    assert ids(rules.evaluate(ctx(is_nonproject=True, code_valid=False)), "BLOCK") == {"R6"}


def test_r7_duplicate():
    assert ids(rules.evaluate(ctx(exact_duplicate=True)), "BLOCK") == {"R7"}


def test_r8_period_lock():
    assert ids(rules.evaluate(ctx(locked_through=TODAY)), "BLOCK") == {"R8"}
    assert rules.evaluate(ctx(locked_through=TODAY - timedelta(days=1))) == []


def test_r9_future_date_but_leave_allowed():
    assert ids(rules.evaluate(ctx(entry_date=TODAY + timedelta(days=1))), "BLOCK") >= {"R9"}
    assert rules.evaluate(ctx(entry_date=TODAY + timedelta(days=1), is_nonproject=True, is_leave=True)) == []
