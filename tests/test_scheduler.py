from datetime import timedelta

from tests.test_flow import TODAY, app, c, world  # noqa: F401


def test_jobs_run_once_a_day_and_can_be_forced(c, world):
    h = world["h"]
    r1 = c.post("/admin/jobs/run", headers=h["pmo1"]).json()
    assert r1["alerts"]["status"] == "ok" and r1["reports"]["status"] == "ok" and "email_retry" in r1
    r2 = c.post("/admin/jobs/run", headers=h["pmo1"]).json()
    assert r2["alerts"] == "already ran today"
    r3 = c.post("/admin/jobs/run?force=true", headers=h["pmo1"]).json()
    assert r3["alerts"]["status"] == "ok"
    runs = c.get("/admin/jobs", headers=h["admin"]).json()
    assert {x["name"] for x in runs["runs"]} >= {"alerts", "reports", "timesheet_reminders", "overdue_actions"}
    assert c.get("/admin/jobs", headers=h["s1"]).status_code == 403
    assert c.post("/admin/jobs/run", headers=h["s1"]).status_code == 403


def test_sunday_reminders_and_alert_job_creates_alerts(c, world, app):
    from datetime import date
    from app import scheduler
    sunday = date(2026, 11, 22)
    assert sunday.weekday() == 6
    with app.state.Session() as db:
        out = scheduler.run_due(db, today=sunday, force=True)
        assert out["timesheet_reminders"]["status"] == "ok" and "sent" in out["timesheet_reminders"]
        monday = scheduler.run_due(db, today=date(2026, 11, 23), force=True)
        assert monday["timesheet_reminders"].get("skipped") == "not Sunday"


def test_failed_email_is_retried_then_given_up(c, world, app, monkeypatch):
    from app import notify
    from app.models import Notification, User
    calls = {"n": 0}
    def flaky(cfg, to, title, body):
        calls["n"] += 1
        return "SMTP down" if calls["n"] < 3 else None
    monkeypatch.setattr(notify, "deliver", flaky)
    monkeypatch.setattr(notify, "mail_settings", lambda db=None: {"host": "x", "port": 25, "enabled": True, "from": "a@b"})
    with app.state.Session() as db:
        u = db.query(User).filter_by(staff_id="s1").first()
        u.email = "s1@example.com"
        n = notify.notify(db, u.id, "test", "Hello", "body")
        db.commit()
        assert n.emailed is False and n.email_attempts == 1 and n.email_error == "SMTP down"
        r = notify.retry_emails(db)
        assert r["failed"] == 1
        r = notify.retry_emails(db)
        assert r["sent"] == 1
        n = db.query(Notification).filter_by(kind="test").first()
        assert n.emailed is True and n.email_attempts == 3
        assert notify.retry_emails(db)["retried"] == 0            # nothing left to retry
