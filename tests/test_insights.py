from tests.test_flow import app, c, world  # noqa: F401


def test_insights(c, world):
    h, pid = world["h"], world["pid"]
    pm, pmo, s1, ccb = h["pm1"], h["pmo1"], h["s1"], h["ccb1"]
    t = c.get(f"/dashboards/project/{pid}/trend", headers=pm)
    assert t.status_code == 200 and len(t.json()) >= 1 and "rag" in t.json()[0]
    assert len(c.get(f"/dashboards/project/{pid}/trend", headers=pm).json()) == len(t.json())   # same-day snapshot is upserted, not duplicated
    assert c.get(f"/dashboards/project/{pid}/trend", headers=s1).status_code == 403
    sc = c.get(f"/dashboards/project/{pid}/scurve", headers=pm)
    assert sc.status_code == 200
    body = sc.json()
    if body["available"]:
        assert body["points"] and all("PV" in x for x in body["points"])
    assert c.get(f"/dashboards/project/{pid}/scurve", headers=s1).status_code == 403
    assert "cells" in c.get(f"/dashboards/project/{pid}/risk-matrix", headers=pm).json()
    hv = c.get(f"/dashboards/project/{pid}/hours-vs-plan", headers=pm).json()
    assert hv and {"code", "planned", "approved"} <= set(hv[0])
    ex = c.get("/dashboards/executive", headers=pmo).json()
    assert ex["projects"] >= 1 and set(ex["rag_counts"]) == {"RED", "AMBER", "GREEN", "GREY"} and "pending_decisions" in ex
    assert c.get("/dashboards/executive", headers=pm).status_code == 403
    assert c.post("/dashboards/snapshots", headers=pm).status_code == 403
    assert c.post("/dashboards/snapshots", headers=pmo).json()["snapshots"] >= 1
    d = c.get("/dashboards/decisions", headers=pmo).json()
    assert {"changes", "costs", "alerts", "total"} <= set(d)
    assert c.get("/dashboards/decisions", headers=s1).json()["total"] == 0
