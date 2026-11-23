"""Project Overview dashboard data: readable by anyone who can see the project; cost only for those allowed to see cost."""
from tests.test_flow import TODAY, app, c, entry, login, mkuser, world   # noqa: F401


def test_project_summary_shape_and_access(c, world):
    h, pid = world["h"], world["pid"]
    r = c.get(f"/dashboards/project/{pid}/summary", headers=h["pm1"])
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("rag", "progress_pct", "hours", "milestones", "risks", "risks_open", "issues_open", "actions", "actions_open", "overdue_activities"):
        assert k in d
    assert d["hours"]["planned"] >= 0
    st = c.get(f"/dashboards/project/{pid}/summary", headers=h["s1"])
    assert st.status_code in (200, 403)                      # staff see it only when assigned
    if st.status_code == 200:
        assert "cost" not in st.json()
    assert c.get("/dashboards/project/99999/summary", headers=h["pm1"]).status_code == 404
