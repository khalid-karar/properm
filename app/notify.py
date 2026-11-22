"""Outbox dispatcher: turns domain events into in-app notifications (and optional e-mail).

Runs after every successful write request (see main.py) and on demand. Pure SQLAlchemy plus the standard
library, so it also runs inside the browser (Pyodide) build, where e-mail is skipped (no sockets)."""
import os
import smtplib
import sys
from email.message import EmailMessage

from .models import Outbox, Project, TimesheetEntry, User, Notification, Alert


def _pm(db, pid):
    p = db.get(Project, pid) if pid else None
    return [p.pm_id] if p else []


def _role(db, *roles):
    return [u.id for u in db.query(User).filter(User.role.in_(roles), User.active.is_(True))]


def _label(db, pid):
    p = db.get(Project, pid) if pid else None
    return f"{p.number} {p.name}" if p else "project"


def targets(db, event: str, d: dict):
    """-> list of (user_id, title, body, link). Events not listed here produce no notification."""
    pid = d.get("project_id")
    L = f"#/projects/{pid}" if pid else None
    if event == "timesheet.submitted":
        e = db.get(TimesheetEntry, d["entry_id"])
        if e and e.project_id:
            return [(u, "Timesheet awaiting approval", f"{_label(db, e.project_id)}: {e.hours} h on {e.entry_date}", "#/approvals") for u in _pm(db, e.project_id)]
    elif event in ("timesheet.approved", "timesheet.rejected"):
        word = event.split(".")[1]
        return [(d["user_id"], f"Timesheet {word}", f"Your entry (id {d['entry_id']}) was {word}", "#/timesheet")]
    elif event == "alert.raised" and d.get("severity") in ("critical", "warning"):
        a = db.get(Alert, d["alert_id"])
        who = set(_pm(db, pid)) | (set(_role(db, "PMO")) if d["severity"] == "critical" else set())
        return [(u, f"{d['severity'].title()} alert: {_label(db, pid)}", a.cause if a else None, "#/alerts") for u in who]
    elif event == "action.assigned":
        return [(d["assignee_id"], "Alert action assigned to you", f"Due {d.get('due_date')}", "#/alerts")]
    elif event == "change.requested":
        return [(u.id, "Change request needs a decision", _label(db, pid), L) for u in db.query(User).filter_by(is_ccb=True, active=True)]
    elif event in ("change.approved", "change.rejected"):
        return [(u, f"Change request {event.split('.')[1]}", _label(db, pid), L) for u in _pm(db, pid)]
    elif event == "project.state_changed":
        return [(u, "Project state changed", f"{_label(db, pid)}: {d['from']} → {d['to']}", L) for u in _pm(db, pid)]
    elif event == "cost.posted" and d.get("approval") == "pending":
        return [(u, "Cost awaiting approval", _label(db, pid), L) for u in _role(db, "PMO", "ADMIN")]
    elif event == "anomaly.flag":
        return [(u, "Timesheet anomaly flagged", f"User {d.get('user_id')} had {d.get('blocks_7d')} flagged blocks in 7 days", "#/approvals") for u in _role(db, "PMO")]
    return []


def send_email(user: User, title: str, body: str | None) -> bool:
    host = os.environ.get("PROPERM_SMTP_HOST")
    if not host or not user.email or sys.platform == "emscripten":
        return False
    try:
        m = EmailMessage()
        m["From"] = os.environ.get("PROPERM_SMTP_FROM", "properm@localhost")
        m["To"], m["Subject"] = user.email, title
        m.set_content(body or title)
        with smtplib.SMTP(host, int(os.environ.get("PROPERM_SMTP_PORT", "587")), timeout=10) as s:
            s.starttls()
            if os.environ.get("PROPERM_SMTP_USER"):
                s.login(os.environ["PROPERM_SMTP_USER"], os.environ.get("PROPERM_SMTP_PASSWORD", ""))
            s.send_message(m)
        return True
    except Exception:
        return False   # delivery is best effort; the in-app notification still exists


def notify(db, user_id: int, kind: str, title: str, body: str | None = None, link: str | None = None) -> Notification | None:
    u = db.get(User, user_id)
    if not u or not u.active:
        return None
    n = Notification(user_id=user_id, kind=kind, title=title[:300], body=body, link=link)
    db.add(n)
    n.emailed = send_email(u, title, body)
    return n


def dispatch(db, limit: int = 200) -> int:
    rows = db.query(Outbox).filter_by(dispatched=False).order_by(Outbox.id).limit(limit).all()
    made = 0
    for r in rows:
        seen = set()
        for uid, title, body, link in targets(db, r.event, r.payload or {}):
            if (uid, title) in seen:
                continue
            seen.add((uid, title))
            if notify(db, uid, r.event, title, body, link):
                made += 1
        r.dispatched = True
    db.commit()
    return made
