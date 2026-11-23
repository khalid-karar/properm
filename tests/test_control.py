from datetime import timedelta

from tests.test_flow import TODAY, app, c, entry, world  # noqa: F401


def test_variance_actions_lessons(c, world):
    w, h = world, world["h"]
    pm, s1, pid, aid = h["pm1"], h["s1"], w["pid"], w["aid"]
    c.post("/timesheets", headers=s1, json=entry(w, entry_date=str(TODAY - timedelta(days=1)), hours=6))
    v = c.get(f"/projects/{pid}/variance", headers=pm).json()
    row = next(r for r in v["rows"] if r["activity_id"] == aid)
    assert row["actual_hours"] >= 6 and row["etc_source"] in ("plan", "trend", "pm", "done") and "eac_hours" in row
    assert "baseline_cost" not in next(r for r in c.get(f"/projects/{pid}/variance", headers=s1).json()["rows"] if r["activity_id"] == aid)
    late = str((TODAY + timedelta(days=400)))
    assert c.put(f"/projects/{pid}/activities/{aid}/forecast", headers=s1, json={"forecast_end": late}).status_code == 403
    assert c.put(f"/projects/{pid}/activities/{aid}/forecast", headers=pm, json={"forecast_end": late, "note": "Vendor late"}).status_code == 200
    row = next(r for r in c.get(f"/projects/{pid}/variance", headers=pm).json()["rows"] if r["activity_id"] == aid)
    assert row["slip_days"] > 0 and row["status"] in ("amber", "red") and row["forecast_note"] == "Vendor late"
    # actions
    x = c.post(f"/projects/{pid}/actions", headers=pm, json={"title": "Send minutes", "owner_id": w["ids"]["s1"], "due_date": str(TODAY - timedelta(days=1))}).json()
    assert x["overdue"]
    todo = c.get("/me/todo", headers=s1).json()
    assert any(a["id"] == x["id"] for a in todo["actions"])
    assert c.patch(f"/projects/{pid}/actions/{x['id']}", headers=s1, json={"title": "hack"}).status_code == 403
    assert c.patch(f"/projects/{pid}/actions/{x['id']}", headers=s1, json={"status": "done"}).json()["done_on"]
    assert c.post(f"/projects/{pid}/actions", headers=s1, json={"title": "x"}).status_code == 403
    # lessons
    assert c.post(f"/projects/{pid}/lessons", headers=s1, json={"category": "bogus", "what_happened": "aaaaa", "recommendation": "bbbbb"}).status_code == 422
    les = c.post(f"/projects/{pid}/lessons", headers=s1, json={"category": "schedule", "impact": "negative", "what_happened": "Access to test servers came late", "recommendation": "Request access in week one"})
    assert les.status_code == 201
    lib = c.get("/lessons?q=access", headers=pm).json()
    assert lib["lessons"] and lib["lessons"][0]["project"]
    assert c.get("/lessons", headers=s1).status_code == 403
    assert c.delete(f"/projects/{pid}/lessons/{les.json()['id']}", headers=pm).status_code == 204
