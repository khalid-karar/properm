from datetime import timedelta

from tests.test_flow import TODAY, app, c, world  # noqa: F401


def test_skills_matching_and_team_norms(c, world):
    w, h, pid = world, world["h"], world["pid"]
    pm, pmo, s1, s2, ad = h["pm1"], h["pmo1"], h["s1"], h["s2"], h["admin"]
    assert c.post("/me/skills", headers=s1, json={"skill": "Data engineering", "level": 5}).status_code == 422
    r = c.post("/me/skills", headers=s1, json={"skill": "Data engineering", "level": 3, "target_level": 4, "years": 5}).json()
    assert r["skills"][0]["gap"] is True and r["skills"][0]["level_name"] == "advanced"
    assert len(c.post("/me/skills", headers=s1, json={"skill": "Data engineering", "level": 4}).json()["skills"]) == 1      # updates in place
    c.post("/me/skills", headers=s2, json={"skill": "Data engineering", "level": 2})
    assert c.post("/me/certs", headers=s1, json={"name": "AWS Data Analytics", "issued_on": "2025-01-01", "expires_on": "2024-01-01"}).status_code == 422
    cert = c.post("/me/certs", headers=s1, json={"name": "PMP", "expires_on": str(TODAY + timedelta(days=30))}).json()["certs"][0]
    assert cert["expires_soon"] is True
    assert c.get("/people/skills", headers=s1).status_code == 403
    d = c.get("/people/skills", headers=pm, params={"skill": "pmp"}).json()
    assert [x["name"] for x in d] == [c.get("/me", headers=s1).json()["full_name"]]
    # admin-maintained skill list restricts entries
    assert c.put("/admin/lists/skill/DATA", json={"label": "Data engineering"}, headers=ad).status_code == 200
    assert c.post("/me/skills", headers=s1, json={"skill": "Cobol"}).status_code == 422
    assert c.get("/skills/list", headers=s1).json() == ["Data engineering"]
    c.put("/people/%d/skills" % w["ids"]["s1"], headers=pmo, json={"skill": "Data engineering", "level": 4})       # wrong verb, 405
    assert c.post(f"/people/{w['ids']['s2']}/skills", headers=pmo, json={"skill": "Data engineering", "level": 3}).status_code == 201
    # matching: s1 is expert, s2 advanced; load s1 up so s2 is the one who fits
    rr = c.post(f"/projects/{pid}/resource-requests", headers=pm, json={"skill": "data engineer", "hours_per_week": 20, "start": str(TODAY), "end": str(TODAY + timedelta(days=14))}).json()
    assert c.get(f"/resource-requests/{rr['id']}/matches", headers=pm).status_code == 403
    m = c.get(f"/resource-requests/{rr['id']}/matches", headers=pmo).json()["candidates"]
    assert {x["id"] for x in m} == {w["ids"]["s1"], w["ids"]["s2"]} and m[0]["level"] >= m[-1]["level"]
    assert all(x["min_free_hours"] > 0 for x in m)
    g = c.get("/people/development-gaps", headers=pmo).json()
    assert g["certs_expiring"][0]["name"] == "PMP"
    # team norms
    n = c.post(f"/projects/{pid}/team-norms", headers=pm, json={"category": "meetings", "text": "Stand-up at 9:30, 15 minutes"}).json()
    assert c.post(f"/projects/{pid}/team-norms", headers=pm, json={"category": "mood", "text": "x"}).status_code == 422
    assert c.get(f"/projects/{pid}/team-norms", headers=s1).status_code == 200
    assert c.delete(f"/projects/{pid}/team-norms/{n['id']}", headers=pm).status_code == 204
