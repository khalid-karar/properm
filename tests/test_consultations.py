from tests.test_flow import app, c, login   # noqa: F401

from app.models import ConsultationRequest, Notification
from app.routers import consultations

OK = {"name": "Sara Alharbi", "organization": "Acme Co", "email": "sara@acme.sa", "interest": "demo"}


def test_public_request_is_saved_and_owner_notified(c, app):
    consultations._HITS.clear()
    assert c.post("/public/consultation", json={**OK, "team_size": "11-50", "message": "Hello", "lang": "ar"}).status_code == 201
    with app.state.Session() as db:
        r = db.query(ConsultationRequest).one()
        assert r.organization == "Acme Co" and r.team_size == "11-50" and r.lang == "ar" and r.status == "new"
        assert db.query(Notification).filter(Notification.kind == "consultation").count() == 1


def test_validation_and_honeypot(c, app):
    consultations._HITS.clear()
    assert c.post("/public/consultation", json={**OK, "email": "nope"}).status_code == 422
    assert c.post("/public/consultation", json={**OK, "name": " "}).status_code == 422
    assert c.post("/public/consultation", json={**OK, "website": "http://spam"}).status_code == 201     # looks fine to the bot
    with app.state.Session() as db:
        assert db.query(ConsultationRequest).count() == 0


def test_rate_limit(c):
    consultations._HITS.clear()
    for _ in range(consultations.MAX_PER_WINDOW):
        assert c.post("/public/consultation", json=OK).status_code == 201
    assert c.post("/public/consultation", json=OK).status_code == 429
    consultations._HITS.clear()


def test_only_platform_owner_reads_and_updates(c):
    consultations._HITS.clear()
    c.post("/public/consultation", json=OK)
    assert c.get("/consultations").status_code in (401, 403)
    admin = login(c, "admin")
    rows = c.get("/consultations", headers=admin).json()
    assert len(rows) == 1 and rows[0]["email"] == "sara@acme.sa"
    assert c.patch(f"/consultations/{rows[0]['id']}", headers=admin, json={"status": "contacted"}).json()["status"] == "contacted"
    assert c.patch(f"/consultations/{rows[0]['id']}", headers=admin, json={"status": "bogus"}).status_code == 422
    assert len(c.get("/consultations?status=new", headers=admin).json()) == 0


def test_request_is_emailed_to_sales_inbox(c, monkeypatch):
    consultations._HITS.clear()
    sent = []
    from app import notify
    monkeypatch.setattr(notify, "mail_settings", lambda db: {"host": "smtp.test", "enabled": True})
    monkeypatch.setattr(notify, "deliver", lambda cfg, to, title, body: sent.append((to, title, body)) or None)
    assert c.post("/public/consultation", json=OK).status_code == 201
    assert sent and sent[0][0] == "info@elevantec.sa" and "Acme Co" in sent[0][1] and "sara@acme.sa" in sent[0][2]
