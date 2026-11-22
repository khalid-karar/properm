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
}

DEFAULT_PARAMS = {
    "overtime_ceiling_pct": 1.25,   # hard ceiling as a multiple of weekly capacity
    "activity_cap_tolerance": 0.10, # tolerance above the activity cap before BLOCK
    "date_tolerance_days": 14,      # tolerance outside project window before BLOCK
    "anomaly_block_count": 3,       # BLOCK violations within 7 days that raise anomaly.flag
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
