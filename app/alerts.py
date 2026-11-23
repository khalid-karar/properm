"""Rule-based alert engine (3.3). Deterministic: every finding comes from data and a threshold,
none from a model. Findings are synced into deduplicated alerts with a cooldown after dismissal."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from .audit import emit
from .deps import get_params
from .evm import compute_evm, latest_progress
from sqlalchemy import func

from .models import Activity, Alert, Issue, Project, Risk, TimesheetEntry

RANK = {"info": 0, "warning": 1, "critical": 2}
LIVE = ("open", "acknowledged", "assigned", "resolved")


@dataclass
class Finding:
    rule: str
    subject: str
    severity: str
    cause: str
    action: str


def evaluate_project(db, p: Project, as_of: date) -> list[Finding]:
    P = get_params(db)
    out: list[Finding] = []

    e = compute_evm(db, p, as_of)
    if e.get("available"):
        if e["AC"] > e["BAC"]:
            out.append(Finding("cost_exceeds_baseline", "project", "critical",
                               f"Actual cost {e['AC']:g} exceeds the baseline budget {e['BAC']:g} {e['currency']}",
                               "Review cost to complete with the sponsor; raise a change request or recover scope."))
        for idx, key, name, act in (("CPI", "cpi", "Cost performance", "Review spend drivers and the estimate to complete; consider a cost change request."),
                                    ("SPI", "spi", "Schedule performance", "Re-plan remaining work or add capacity; check critical activities.")):
            v = e.get(idx)
            if v is None:
                continue
            if v < P[f"{key}_critical"]:
                sev = "critical"
            elif v < P[f"{key}_warning"]:
                sev = "warning"
            else:
                continue
            thr = P[f"{key}_critical"] if sev == "critical" else P[f"{key}_warning"]
            out.append(Finding(f"{key}_low", "project", sev, f"{name} index {idx} is {v:.2f}, below {thr:g}", act))

    tol = int(P["slip_tolerance_days"])
    for a in db.query(Activity).filter_by(project_id=p.id, phase="execution", locked=True):
        if not a.planned_end or a.planned_end >= as_of:
            continue
        lp = latest_progress(db, a.id, as_of)
        if lp and lp.pct_complete >= 100:
            continue
        late = (as_of - a.planned_end).days
        if late > tol:
            out.append(Finding("activity_overdue", a.code, "critical" if late >= 3 * tol else "warning",
                               f"Activity {a.code} is {late} days past its planned end and not complete",
                               "Confirm a recovery date with the activity owner; update the baseline through change control if it moves."))

    for r in db.query(Risk).filter(Risk.project_id == p.id, Risk.status.in_(("open", "mitigating"))):
        if r.score >= P["risk_score_critical"]:
            sev = "critical"
        elif r.score >= P["risk_score_warning"]:
            sev = "warning"
        else:
            continue
        out.append(Finding("risk_score_high", f"risk:{r.id}", sev, f"Risk '{r.title}' has score {r.score}", "Review the response plan and owner; confirm mitigation is under way."))

    for i in db.query(Issue).filter(Issue.project_id == p.id, Issue.status.in_(("open", "in_progress"))):
        overdue = i.due_date is not None and i.due_date < as_of
        if i.severity == "critical":
            out.append(Finding("issue_critical", f"issue:{i.id}", "critical", f"Critical issue open: {i.title}", "Escalate to the sponsor and agree an owner and date."))
        elif overdue and i.severity == "high":
            out.append(Finding("issue_overdue", f"issue:{i.id}", "warning", f"High-severity issue overdue: {i.title}", "Agree a new resolution date or escalate."))

    if p.state == "execution":
        spent = dict(db.query(TimesheetEntry.activity_id, func.sum(TimesheetEntry.hours)).filter(
            TimesheetEntry.project_id == p.id, TimesheetEntry.status.in_(("submitted", "approved"))).group_by(TimesheetEntry.activity_id).all())
        for a in db.query(Activity).filter_by(project_id=p.id, phase="execution", locked=True):
            if not a.planned_hours:
                continue
            used = float(spent.get(a.id) or 0.0)
            ratio = used / a.planned_hours
            lp = latest_progress(db, a.id, as_of)
            done = (lp.pct_complete if lp else 0.0) / 100.0
            if done >= 1.0:
                continue
            if ratio >= 1.0:
                out.append(Finding("activity_hours_exceeded", a.code, "critical", f"Activity {a.code} has used {used:g} of {a.planned_hours:g} planned hours ({ratio:.0%}) and is {done:.0%} complete",
                                   "Re-estimate the remaining work, then raise a change request or move the work; do not let hours run on silently."))
            elif ratio >= float(P["burn_warning_pct"]) and ratio - done >= float(P["burn_gap_pct"]):
                out.append(Finding("activity_burn_high", a.code, "warning", f"Activity {a.code} has used {ratio:.0%} of its hours but is only {done:.0%} complete",
                                   "Check the estimate to complete with the owner before the hours run out."))

    stale_weeks = int(P["stale_progress_weeks"])
    stale = []
    for a in db.query(Activity).filter_by(project_id=p.id, phase="execution", locked=True):
        lp = latest_progress(db, a.id, as_of)
        if lp is None or (as_of - lp.week_start).days > 7 * stale_weeks + 6:
            stale.append(a.code)
    if stale and p.state == "execution":
        out.append(Finding("progress_stale", "project", "info", f"No recent progress update for: {', '.join(stale)}", "Submit the weekly progress update."))
    return out


def sync_alerts(db, p: Project, findings: list[Finding]) -> dict:
    """Create / refresh alerts; mark alerts whose condition no longer holds as inactive."""
    P = get_params(db)
    now = datetime.now(timezone.utc)
    live = {a.dedupe_key: a for a in db.query(Alert).filter(Alert.project_id == p.id, Alert.status.in_(LIVE))}
    current, created, updated = set(), 0, 0
    for f in findings:
        key = f"{p.id}:{f.rule}:{f.subject}"
        current.add(key)
        a = live.get(key)
        if a:
            a.last_seen, a.active, a.cause, a.suggested_action = now, True, f.cause, f.action
            if RANK[f.severity] > RANK[a.severity]:
                a.severity = f.severity
            updated += 1
            continue
        cutoff = now - timedelta(days=int(P["alert_cooldown_days"]))
        muted = db.query(Alert).filter(Alert.dedupe_key == key, Alert.status == "dismissed", Alert.last_seen >= cutoff).first()
        if muted:
            continue
        a = Alert(project_id=p.id, rule=f.rule, dedupe_key=key, severity=f.severity, cause=f.cause, suggested_action=f.action)
        db.add(a)
        db.flush()
        emit(db, "alert.raised", {"project_id": p.id, "alert_id": a.id, "severity": a.severity})
        created += 1
    cleared = 0
    for key, a in live.items():
        if key not in current and a.active:
            a.active = False
            cleared += 1
    return {"created": created, "updated": updated, "cleared": cleared}


def rag_status(db, p: Project) -> str:
    """Red: an active critical alert. Amber: an active warning. Green otherwise. Grey: not in delivery."""
    if p.state not in ("execution", "closing"):
        return "GREY"
    rows = db.query(Alert).filter(Alert.project_id == p.id, Alert.status.in_(LIVE), Alert.active.is_(True)).all()
    if any(a.severity == "critical" for a in rows):
        return "RED"
    if any(a.severity == "warning" for a in rows):
        return "AMBER"
    return "GREEN"
