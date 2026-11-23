"""Configuration defaults. Severities and numeric params are overridable at runtime
via the admin endpoints (stored in rule_config / setting tables)."""

ROLES = ("PM", "STAFF", "PMO", "PROGRAM_MANAGER", "DECISION_MAKER", "ADMIN")

# Default severity of the soft tier of each rule. BLOCK = reject, WARN = allow with
# acknowledgment, FLAG = allow and mark for the approver. Hard tiers are always BLOCK.
DEFAULT_SEVERITIES = {
    "R1": "WARN",   # weekly capacity exceeded, up to the overtime ceiling
    "R2": "FLAG",   # activity cap exceeded within tolerance
    "R3": "BLOCK",  # not assigned to project
    "R4": "BLOCK",  # activity not valid in current project state
    "R5": "WARN",   # date outside project window, within tolerance
    "R6": "BLOCK",  # activity / code does not exist in baseline
    "R7": "BLOCK",  # exact duplicate entry
    "R8": "BLOCK",  # period locked
    "R9": "BLOCK",  # future date
    "R10": "FLAG",  # entry on a weekend or public holiday
}

DEFAULT_PARAMS = {
    "overtime_ceiling_pct": 1.25,   # hard ceiling as a multiple of weekly capacity
    "activity_cap_tolerance": 0.10, # tolerance above the activity cap before BLOCK
    "date_tolerance_days": 14,      # tolerance outside project window before BLOCK
    "anomaly_block_count": 3,       # BLOCK violations within 7 days that raise anomaly.flag
    "cost_approval_threshold": 50000.0,  # non-labor costs above this need PMO/ADMIN approval (Finance stand-in)
    "stale_progress_weeks": 2,      # weeks without a progress update before an activity is flagged
    # rule-based alerts (3.3); every threshold is editable via PUT /admin/settings/{key}
    "cpi_warning": 0.9, "cpi_critical": 0.8,
    "spi_warning": 0.9, "spi_critical": 0.8,
    "slip_tolerance_days": 7,       # overdue activity: warning beyond this, critical beyond 3x
    "risk_score_warning": 15, "risk_score_critical": 20,
    "ai_enabled": 1.0,              # 1 = AI assistant on, 0 = off for everyone
    "ai_hourly_limit": 30.0,        # AI requests per person per hour
    "burn_warning_pct": 0.8,         # hours used as a share of an activity budget before the burn warning can fire
    "burn_gap_pct": 0.25,            # ... and hours used must run this far ahead of the percent complete
    "alert_cooldown_days": 7,
    "intake_required": 0.0,         # 1 = project managers submit a proposal; a decision maker approves it into a project
    "stage_gates": 0.0,
    "password_min_length": 8.0,     # passwords also need at least one letter and one digit
    "lockout_attempts": 5.0,        # failed sign-ins in a row before the account is locked
    "lockout_minutes": 15.0,        # how long a locked account stays locked (an admin can unlock earlier)
    "session_hours": 8.0,           # sign-in lifetime
    "require_2fa_privileged": 0.0,  # 1 = ADMIN, PMO and DECISION_MAKER must turn on two-factor sign-in before using the system
    "force_password_change": 0.0,   # 1 = new users and admin-set passwords must be changed at next sign-in             # 1 = planning->execution and execution->closing need an approved gate review       # a dismissed alert is not re-raised within this many days
}

# Non-project time codes valid for any user in any state (4.5 configuration, minimal).
NON_PROJECT_CODES = {"LEAVE": "Leave", "ADMIN": "Administration", "TRAINING": "Training", "PRESALES": "Presales"}

# Phase activities created automatically with every project so time can be logged
# before a baseline exists (1.0 state machine).
PHASE_ACTIVITIES = {
    "tendering": ("PRE-BID", "Bid preparation"),
    "planning": ("PLAN-GEN", "Planning and baseline preparation"),
    "closing": ("CLOSE-GEN", "Closure activities"),
}

# Work week starts on Sunday (Saudi deployments). Change here until the work calendar
# service (4.6) exists.
WEEK_STARTS_ON_SUNDAY = True

# Saudi work week: Sunday to Thursday. Python weekday numbers: Friday=4, Saturday=5.
WEEKEND_DAYS = (4, 5)
CLOSURE_ITEMS = [
    ("deliverables_accepted", False), ("costs_reconciled", False), ("timesheets_approved", True), ("issues_closed", True),
    ("risks_reviewed", False), ("lessons_learned", False), ("documents_archived", False), ("benefits_handover", False),
]   # (key, checked by the system)
