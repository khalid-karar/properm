import base64

from tests.test_flow import TODAY, app, c, world  # noqa: F401


def b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def _xer(rows_task, rows_pred, rows_rsrc=(), extra_project=False):
    L = ["ERMHDR\t8.4\t2026-11-01\tProject\tadmin\tadmin\tdb\tProject Management\tSAR",
         "%T\tPROJECT", "%F\tproj_id\tproj_short_name", "%R\t1\tTOWER"]
    if extra_project:
        L.append("%R\t2\tOTHER")
    L += ["%E", "%T\tTASK", "%F\ttask_id\tproj_id\ttask_code\ttask_name\ttask_type\ttarget_drtn_hr_cnt\ttarget_start_date\ttarget_end_date"]
    L += ["%R\t" + "\t".join(r) for r in rows_task] + ["%E", "%T\tTASKPRED", "%F\ttask_id\tpred_task_id\tproj_id\tpred_type\tlag_hr_cnt"]
    L += ["%R\t" + "\t".join(r) for r in rows_pred] + ["%E", "%T\tTASKRSRC", "%F\ttask_id\ttarget_qty"]
    L += ["%R\t" + "\t".join(r) for r in rows_rsrc] + ["%E", "%E"]
    return "\r\n".join(L).encode("cp1252")


TASKS = [("10", "1", "WBS", "Tower", "TT_WBS", "0", "2027-01-03 08:00", "2027-03-30 17:00"),
         ("11", "1", "A100", "Excavation", "TT_Task", "80", "2027-01-03 08:00", "2027-01-20 17:00"),
         ("12", "1", "A200", "Foundations", "TT_Task", "160", "2027-01-21 08:00", "2027-02-20 17:00"),
         ("13", "1", "A300", "Structure", "TT_Task", "240", "2027-02-21 08:00", "2027-03-25 17:00"),
         ("14", "1", "M1", "Foundations complete", "TT_Mile", "0", "2027-02-20 17:00", "2027-02-20 17:00"),
         ("15", "1", "LOE1", "Project management", "TT_LOE", "800", "2027-01-03 08:00", "2027-03-30 17:00"),
         ("16", "2", "X1", "Other project task", "TT_Task", "8", "2027-01-03 08:00", "2027-01-04 17:00")]
PREDS = [("12", "11", "1", "PR_FS", "0"), ("13", "12", "1", "PR_FS", "0"), ("13", "11", "1", "PR_SS", "8"),
         ("14", "12", "1", "PR_FS", "0"), ("11", "13", "1", "PR_FS", "0")]          # last one would close a loop
RSRC = [("11", "100"), ("11", "20")]                                                  # A100 has 120 h of resource work


def _planning(c, h, num):
    return c.post("/projects", headers=h["pm1"], json={"number": num, "name": "Sched", "state": "planning", "planned_start": "2027-01-03", "planned_end": "2027-06-30"}).json()["id"]


def test_xer_preview_commit_and_rerun(c, world):
    h = world["h"]
    pid = _planning(c, h, "SCH-1")
    url = f"/projects/{pid}/import/schedule"
    data = _xer(TASKS, PREDS, RSRC, extra_project=True)
    body = {"filename": "plan.xer", "content_b64": b64(data)}
    assert c.post(url, headers=h["s1"], json=body).status_code == 403
    pv = c.post(url, headers=h["pm1"], json=body).json()
    assert pv["file_project"] == "TOWER" and pv["file_projects"] == ["TOWER", "OTHER"]
    assert pv["counts"] == {"activities": 3, "milestones": 1, "links": 2}                  # FS A100>A200, A200>A300; SS, milestone link and loop left out
    text = " ".join(pv["notes"])
    assert "WBS summary" in text and "level-of-effort" in text and "other types" in text and "circular" in text and "milestone" in text
    assert not pv["committed"]
    done = c.post(url, headers=h["pm1"], json={**body, "commit": True}).json()
    assert done["committed"] and done["saved"] == 4 and done["counts"]["links"] == 2
    detail = c.get(f"/projects/{pid}", headers=h["pm1"]).json()
    acts = {a["code"]: a for a in detail["activities"]}
    assert acts["A100"]["planned_hours"] == 120 and acts["A200"]["planned_hours"] == 160 and str(acts["A200"]["planned_start"]) == "2027-01-21"
    deps = c.get(f"/projects/{pid}/dependencies", headers=h["pm1"]).json()
    assert {(d["predecessor_code"], d["activity_code"]) for d in deps} == {("A100", "A200"), ("A200", "A300")}
    again = c.post(url, headers=h["pm1"], json={**body, "commit": True}).json()
    assert again["saved"] == 0 and again["duplicates"] == 4 and not again["errors"]
    other = c.post(url + "?project=OTHER", headers=h["pm1"], json=body).json()
    assert other["counts"]["activities"] == 1
    assert c.post(url + "?project=NOPE", headers=h["pm1"], json=body).status_code == 422


MSP = b"""<?xml version="1.0"?><Project xmlns="http://schemas.microsoft.com/project"><Name>Fitout</Name><Tasks>
<Task><UID>0</UID><ID>0</ID><Name>Root</Name><OutlineNumber>0</OutlineNumber></Task>
<Task><UID>1</UID><Name>Phase</Name><WBS>1</WBS><OutlineNumber>1</OutlineNumber><Summary>1</Summary></Task>
<Task><UID>2</UID><Name>Design</Name><WBS>1.1</WBS><OutlineNumber>1.1</OutlineNumber><Work>PT80H0M0S</Work><Start>2027-01-03T08:00:00</Start><Finish>2027-01-20T17:00:00</Finish></Task>
<Task><UID>3</UID><Name>Build</Name><WBS>1.2</WBS><OutlineNumber>1.2</OutlineNumber><Work>PT120H0M0S</Work><Start>2027-01-21T08:00:00</Start><Finish>2027-02-20T17:00:00</Finish>
<PredecessorLink><PredecessorUID>2</PredecessorUID><Type>1</Type></PredecessorLink></Task>
<Task><UID>4</UID><Name>Handover</Name><WBS>1.3</WBS><OutlineNumber>1.3</OutlineNumber><Milestone>1</Milestone><Start>2027-02-21T08:00:00</Start><Finish>2027-02-21T08:00:00</Finish>
<PredecessorLink><PredecessorUID>3</PredecessorUID><Type>1</Type></PredecessorLink></Task></Tasks></Project>"""


def test_msproject_xml_with_links_and_milestone(c, world):
    h = world["h"]
    pid = _planning(c, h, "SCH-2")
    url = f"/projects/{pid}/import/schedule"
    r = c.post(url, headers=h["pm1"], json={"filename": "p.xml", "content_b64": b64(MSP), "commit": True}).json()
    assert r["saved"] == 3 and r["counts"] == {"activities": 2, "milestones": 1, "links": 1}
    deps = c.get(f"/projects/{pid}/dependencies", headers=h["pm1"]).json()
    assert [(d["predecessor_code"], d["activity_code"]) for d in deps] == [("1.1", "1.2")]


def test_refusals_and_bad_files(c, world):
    h = world["h"]
    pid = _planning(c, h, "SCH-3")
    url = f"/projects/{pid}/import/schedule"
    post = lambda name, data: c.post(url, headers=h["pm1"], json={"filename": name, "content_b64": b64(data)})
    assert post("a.mpp", b"\xd0\xcf\x11").status_code == 422
    assert post("a.xer", b"not an xer").status_code == 422
    assert post("a.csv", b"x").status_code == 422
    bomb = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><Project><Tasks><Task><UID>1</UID><Name>&a;</Name></Task></Tasks></Project>'
    assert "entity" in post("a.xml", bomb).json()["detail"].lower()
    active = c.post("/projects", headers=h["pm1"], json={"number": "SCH-4", "name": "Not planning", "state": "execution"})
    if active.status_code == 201:
        assert c.post(f"/projects/{active.json()['id']}/import/schedule", headers=h["pm1"], json={"filename": "p.xml", "content_b64": b64(MSP)}).status_code == 409
