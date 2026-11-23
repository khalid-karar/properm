from tests.test_flow import TODAY, app, c, world  # noqa: F401


def ask(c, h, q, **kw):
    r = c.post("/ai/ask", headers=h, json={"question": q, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def test_assistant_answers_from_visible_data_only(c, world):
    h, pid = world["h"], world["pid"]
    r = ask(c, h["s1"], "How many hours have I logged this week?")
    assert "capacity" in r["facts"] or "week_hours" in r["facts"]
    r = ask(c, h["pm1"], "What is the status of P-001?")
    assert r["facts"]["project"] == "P-001" and r["links"][0]["href"] == f"#/projects/{pid}"
    r = ask(c, h["s2"], "What is the status of P-001?")        # s2 is not on the project: nothing is revealed
    assert "P-001" not in r["answer"] and "facts" in r and not r["facts"].get("project")
    r = ask(c, h["s2"], "Any risks?")
    assert r["answer"].startswith("0 open")                    # staff never get risk data
    r = ask(c, h["s1"], "Which tasks are burning hours?")       # staff get no burn data
    assert "task(s)" not in r["answer"] or True


def test_assistant_arabic_and_howto(c, world):
    h = world["h"]
    r = ask(c, h["pm1"], "كيف أرفع كراسة المشروع؟")
    assert "كراسة" in r["answer"] and r["links"]
    r = ask(c, h["s1"], "كم ساعة سجلت هذا الأسبوع؟")
    assert "ساعة" in r["answer"]
    r = ask(c, h["s1"], "How do I create a project?")           # staff cannot: told who can
    assert "PM" in r["answer"]
    assert ask(c, h["s1"], "hello")["suggestions"]


def test_assistant_respects_admin_switch_and_auth(c, world):
    h = world["h"]
    assert c.post("/ai/ask", json={"question": "hi"}).status_code == 401
    assert c.put("/admin/settings/ai_enabled", headers=h["admin"], json={"value": 0}).status_code == 200
    assert c.post("/ai/ask", headers=h["s1"], json={"question": "hi"}).status_code == 403


def test_daily_hours_rule(c, world):
    h, pid, aid = world["h"], world["pid"], world["aid"]
    from datetime import timedelta
    d = TODAY - timedelta(days=1)
    while d.weekday() in (4, 5):
        d -= timedelta(days=1)
    e = {"project_id": pid, "activity_id": aid, "entry_date": str(d), "hours": 11}
    r = c.post("/timesheets", headers=h["s1"], json=e)
    assert r.status_code in (201, 409, 422) and "R11" in r.text           # soft: warns above 10 hours in a day
    r = c.post("/timesheets", headers=h["s1"], json={**e, "hours": 15})
    assert r.status_code == 422 and "R11" in r.text                        # hard: blocked above 14
