"""Outbox dispatcher: turns domain events into in-app notifications (and optional e-mail).

Runs after every successful write request (see main.py) and on demand. Pure SQLAlchemy plus the standard
library, so it also runs inside the browser (Pyodide) build, where e-mail is skipped (no sockets)."""
import os
import smtplib
import sys
from email.message import EmailMessage

from .models import Outbox, Project, TimesheetEntry, User, Notification, Alert, UserPref


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
    elif event == "project.manager_changed":
        return [(d["user_id"], "You are now the project manager", _label(db, pid), L)]
    elif event == "project.state_changed":
        return [(u, "Project state changed", f"{_label(db, pid)}: {d['from']} → {d['to']}", L) for u in _pm(db, pid)]
    elif event == "cost.posted" and d.get("approval") == "pending":
        return [(u, "Cost awaiting approval", _label(db, pid), L) for u in _role(db, "PMO", "ADMIN")]
    elif event == "proposal.submitted":
        return [(u, "Project proposal needs a decision", d.get("title"), "#/proposals") for u in _role(db, "DECISION_MAKER", "PMO")]
    elif event == "proposal.decided":
        word = {"approve": "approved", "approve_conditions": "approved with conditions", "reject": "rejected", "defer": "deferred", "request_info": "returned for more information"}.get(d.get("outcome"), "decided")
        return [(d["user_id"], f"Your proposal was {word}", d.get("title"), f"#/projects/{d['project_id']}" if d.get("project_id") else "#/proposals")]
    elif event == "gate.requested":
        return [(u, "Stage gate review needs a decision", _label(db, pid), "#/decisions") for u in _role(db, "DECISION_MAKER", "PMO")]
    elif event == "gate.decided":
        return [(u, f"Stage gate decision: {d.get('outcome', '').replace('_', ' ')}", _label(db, pid), L) for u in _pm(db, pid)]
    elif event == "change.returned":
        return [(d["user_id"], f"Change request {'deferred' if d.get('outcome') == 'defer' else 'needs more information'}", _label(db, pid), L)]
    elif event == "leave.requested":
        u = db.get(User, d["user_id"])
        who = [u.line_manager_id] if u and u.line_manager_id else _role(db, "PMO")
        if u and u.line_manager_id:
            lm = db.get(User, u.line_manager_id)
            if lm and lm.delegate_id:
                who.append(lm.delegate_id)
        return [(x, "Leave request needs a decision", f"{d.get('name')}: {d['start']} – {d['end']}", "#/leave") for x in who]
    elif event == "leave.decided":
        return [(d["user_id"], f"Your leave was {d['status']}", f"{d['start']} – {d['end']}", "#/leave")]
    elif event == "resource.requested":
        return [(u, "Resource request needs a decision", f"{_label(db, pid)}: {d.get('skill')}", "#/load") for u in _role(db, "PMO")]
    elif event == "resource.decided":
        out = [(d["user_id"], f"Resource request {d['status']}", f"{_label(db, pid)}: {d.get('skill')}", L)]
        if d.get("assigned_id"):
            out.append((d["assigned_id"], "You have been assigned to a project", _label(db, pid), L))
        return out
    elif event == "anomaly.flag":
        return [(u, "Timesheet anomaly flagged", f"User {d.get('user_id')} had {d.get('blocks_7d')} flagged blocks in 7 days", "#/approvals") for u in _role(db, "PMO")]
    return []


def mail_settings(db) -> dict:
    """Administrator settings first (Configuration page), then environment variables."""
    from .models import MailConfig
    m = db.query(MailConfig).first() if db is not None else None
    if m and m.host:
        return {"host": m.host, "port": m.port or 587, "user": m.username, "password": m.password, "from": m.from_addr or "properm@localhost",
                "starttls": m.starttls, "enabled": m.enabled}
    return {"host": os.environ.get("PROPERM_SMTP_HOST"), "port": int(os.environ.get("PROPERM_SMTP_PORT", "587")),
            "user": os.environ.get("PROPERM_SMTP_USER"), "password": os.environ.get("PROPERM_SMTP_PASSWORD", ""),
            "from": os.environ.get("PROPERM_SMTP_FROM", "properm@localhost"), "starttls": True, "enabled": True}


def deliver(cfg: dict, to: str, title: str, body: str | None) -> str | None:
    """Send one message. Returns None on success or a short error text."""
    if sys.platform == "emscripten":
        return "E-mail cannot be sent from the browser demo"
    if not cfg.get("host") or not cfg.get("enabled"):
        return "No mail server is set up"
    try:
        m = EmailMessage()
        m["From"], m["To"], m["Subject"] = cfg["from"], to, title
        m.set_content(body or title)
        with smtplib.SMTP(cfg["host"], int(cfg["port"]), timeout=10) as s:
            if cfg.get("starttls", True):
                s.starttls()
            if cfg.get("user"):
                s.login(cfg["user"], cfg.get("password") or "")
            s.send_message(m)
        return None
    except Exception as e:      # delivery is best effort; the in-app notification still exists
        return f"{type(e).__name__}: {e}"[:300]


def send_email(user: User, title: str, body: str | None, db=None) -> bool:
    return try_email(user, title, body, db)[0]


def try_email(user: User, title: str, body: str | None, db=None) -> tuple[bool, bool, str | None]:
    """-> (sent, attempted, error). Not attempted when there is no address or no mail server."""
    if not user.email:
        return False, False, None
    cfg = mail_settings(db)
    if not cfg.get("host"):
        return False, False, None
    err = deliver(cfg, user.email, title, body)
    return err is None, True, err


def notify(db, user_id: int, kind: str, title: str, body: str | None = None, link: str | None = None) -> Notification | None:
    u = db.get(User, user_id)
    if not u or not u.active:
        return None
    pref = db.get(UserPref, user_id)
    if pref and kind in (pref.muted_kinds or []):
        return None
    n = Notification(user_id=user_id, kind=kind, title=title[:300], body=body, link=link)
    db.add(n)
    if not pref or pref.email_enabled:
        n.emailed, tried, err = try_email(u, title, body, db)
        n.email_attempts, n.email_error = (1 if tried else 0), err
    else:
        n.emailed = False
    return n


def retry_emails(db, max_attempts: int = 5, limit: int = 100) -> dict:
    """Second chance for e-mails that failed (mail server down, wrong password). Gives up after max_attempts or 3 days."""
    from datetime import datetime, timedelta, timezone
    since = datetime.now(timezone.utc) - timedelta(days=3)
    sent = failed = 0
    rows = db.query(Notification).filter(Notification.emailed.is_(False), Notification.email_attempts > 0, Notification.email_attempts < max_attempts,
                                         Notification.created_at >= since).order_by(Notification.id).limit(limit).all()
    for n in rows:
        u = db.get(User, n.user_id)
        if not u or not u.active:
            n.email_attempts = max_attempts
            continue
        ok, tried, err = try_email(u, n.title, n.body, db)
        if tried:
            n.email_attempts += 1
            n.email_error = err
            n.emailed = ok
            sent, failed = sent + ok, failed + (not ok)
    db.commit()
    return {"retried": len(rows), "sent": sent, "failed": failed}


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
