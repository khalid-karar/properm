"""Scheduled jobs. Each daily job runs once per calendar day (JobRun is unique per name and date), so it is safe to call as often as you like.
Triggered by the background loop in main.py (PROPERM_SCHEDULER=1), by an admin pressing Run now, or by an external cron calling POST /admin/jobs/run."""
from datetime import date, datetime, timezone
from types import SimpleNamespace

from .audit import log
from .models import JobRun

SYSTEM = SimpleNamespace(id=None, role="ADMIN", full_name="System")


def _alerts(db, today):
    from .routers.alerts import evaluate_all
    return evaluate_all(as_of=today, db=db, user=SYSTEM)


def _reports(db, today):
    from .routers.notifications import run_due
    return run_due(today=today, db=db, user=SYSTEM)


def _reminders(db, today):
    from .routers.weekly import send_reminders
    if today.weekday() != 6:                      # Sunday: the first working day of the Saudi week
        return {"skipped": "not Sunday"}
    return send_reminders(week_of=None, db=db, user=SYSTEM)


def _overdue(db, today):
    """Nudge owners of risks, issues and actions that are past due (once a day, as a notification)."""
    from .models import ProjectAction, Project
    from .notify import notify
    n = 0
    for a in db.query(ProjectAction).filter(ProjectAction.status.in_(("open", "in_progress")), ProjectAction.due_date.isnot(None), ProjectAction.due_date < today):
        if a.owner_id and notify(db, a.owner_id, "action.overdue", f"Overdue: {a.title}"[:300], f"Due {a.due_date}", f"#/projects/{a.project_id}"):
            n += 1
    db.commit()
    return {"nudged": n}


JOBS = {"alerts": _alerts, "reports": _reports, "timesheet_reminders": _reminders, "overdue_actions": _overdue}


def run_due(db, today: date | None = None, force: bool = False) -> dict:
    today = today or date.today()
    out = {}
    for name, fn in JOBS.items():
        done = db.query(JobRun).filter_by(name=name, run_date=today).first()
        if done and not force:
            out[name] = "already ran today"
            continue
        try:
            res = fn(db, today)
            status = "ok"
        except Exception as e:      # one failing job never stops the others
            db.rollback()
            res, status = {"error": f"{type(e).__name__}: {e}"[:300]}, "failed"
        row = done or JobRun(name=name, run_date=today)
        row.status, row.detail, row.started_at = status, res if isinstance(res, dict) else {"result": str(res)}, datetime.now(timezone.utc)
        db.add(row)
        db.commit()
        out[name] = {"status": status, **(res if isinstance(res, dict) else {})}
    from .notify import retry_emails
    out["email_retry"] = retry_emails(db)
    log(db, None, "jobs.run", "system", None, {"date": today.isoformat(), "forced": force})
    db.commit()
    return out
