import base64
from datetime import timedelta

from app import tabular, xlsx
from tests.test_flow import TODAY, app, c, world  # noqa: F401


def b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def xl(header, rows):
    return b64(xlsx.build_xlsx([("S", header, rows)]))


MSP = b"""<?xml version="1.0"?><Project xmlns="http://schemas.microsoft.com/project"><Tasks>
<Task><UID>0</UID><ID>0</ID><Name>Root</Name><OutlineNumber>0</OutlineNumber></Task>
<Task><UID>1</UID><ID>1</ID><Name>Phase A</Name><WBS>1</WBS><OutlineNumber>1</OutlineNumber><Summary>1</Summary></Task>
<Task><UID>2</UID><ID>2</ID><Name>Design</Name><WBS>1.1</WBS><OutlineNumber>1.1</OutlineNumber><Work>PT80H0M0S</Work><Start>2027-01-03T08:00:00</Start><Finish>2027-01-20T17:00:00</Finish></Task>
<Task><UID>3</UID><ID>3</ID><Name>Build</Name><WBS>1.2</WBS><OutlineNumber>1.2</OutlineNumber><Work>PT120H0M0S</Work><Start>2027-01-21T08:00:00</Start><Finish>2027-02-20T17:00:00</Finish></Task></Tasks></Project>"""


def test_readers():
    h, r = tabular.read_msproject(MSP)
    assert h[0] == "code" and [x[1] for x in r] == ["Design", "Build"] and r[0][2] == 80
    h, r = tabular.read_csv("Staff ID;Name\nA1;علي\n".encode("utf-8-sig"))
    assert h == ["staff_id", "name"] and r[0][1] == "علي"


def test_staff_import_preview_and_commit(c, world):
    h = world["h"]
    f = xl(["staff_id", "full_name", "role", "email"], [["N1", "New One", "STAFF", "n1@x.sa"], ["N2", "Bad Role", "KING", None], ["s1", "Dup", "STAFF", None]])
    body = {"filename": "staff.xlsx", "content_b64": f}
    assert c.post("/import/staff", headers=h["pm1"], json=body).status_code == 403
    pv = c.post("/import/staff", headers=h["admin"], json=body).json()
    assert pv["ok"] == 1 and pv["errors"] == 2 and not pv["committed"]
    blocked = c.post("/import/staff", headers=h["admin"], json={**body, "commit": True}).json()
    assert blocked["blocked"] and not blocked["committed"]                         # one bad row stops everything
    done = c.post("/import/staff", headers=h["admin"], json={**body, "commit": True, "skip_errors": True}).json()
    assert done["saved"] == 1 and done["generated_passwords"]["N1"]
    assert c.post("/import/staff", headers=h["admin"], json={"filename": "x.xlsx", "content_b64": xl(["a"], [[1]])}).status_code == 422   # missing columns
    assert c.post("/import/staff", headers=h["admin"], json={"filename": "x.pdf", "content_b64": b64(b"x")}).status_code == 422


def test_timesheet_import(c, world):
    h = world["h"]
    r = c.post("/projects", headers=h["pm1"], json={"number": "IMP-1", "name": "Imp", "state": "planning", "planned_start": str(TODAY), "planned_end": str(TODAY + timedelta(days=90))})
    assert r.status_code == 201
    d = TODAY - timedelta(days=400)
    rows = [["s1", str(d), 8, "IMP-1", None, None, "load"], ["s1", str(d), 8, "IMP-1", None, None, "dup in file"], ["s2", str(d), 30, "IMP-1", None, None, None],
            ["zzz", str(d), 4, "IMP-1", None, None, None], ["s2", str(d), 4, None, None, "TRAIN", "training"], ["s2", "not a date", 4, "IMP-1", None, None, None]]
    f = xl(["staff_id", "date", "hours", "project", "activity", "nonproject_code", "description"], rows)
    body = {"filename": "ts.xlsx", "content_b64": f}
    assert c.post("/import/timesheets", headers=h["s1"], json=body).status_code == 403
    pv = c.post("/import/timesheets", headers=h["pmo1"], json=body).json()
    assert pv["ok"] == 2 and pv["duplicates"] == 1 and pv["errors"] == 3
    done = c.post("/import/timesheets", headers=h["pmo1"], json={**body, "commit": True, "skip_errors": True}).json()
    assert done["saved"] == 2
    again = c.post("/import/timesheets", headers=h["pmo1"], json={**body, "commit": True, "skip_errors": True}).json()
    assert again["saved"] == 0 and again["duplicates"] == 3                          # re-running the same file adds nothing
    x = c.get("/export/timesheets.xlsx", headers=h["pmo1"])
    assert x.status_code == 200 and x.content[:2] == b"PK"
    head, rows_ = tabular.read_xlsx(x.content)
    assert head[0] == "date" and any(float(r[3]) == 8 for r in rows_)


def test_plan_import_and_export_roundtrip(c, world):
    h = world["h"]
    pid = c.post("/projects", headers=h["pm1"], json={"number": "IMP-2", "name": "Plan imp", "state": "planning", "planned_start": "2027-01-03", "planned_end": "2027-06-30"}).json()["id"]
    url = f"/projects/{pid}/import/plan"
    assert c.post(url, headers=h["s1"], json={"filename": "p.xml", "content_b64": b64(MSP)}).status_code == 403
    pv = c.post(url, headers=h["pm1"], json={"filename": "p.xml", "content_b64": b64(MSP)}).json()
    assert pv["ok"] == 2 and pv["errors"] == 0
    assert c.post(url, headers=h["pm1"], json={"filename": "p.xml", "content_b64": b64(MSP), "commit": True}).json()["saved"] == 2
    assert c.post(url, headers=h["pm1"], json={"filename": "p.xml", "content_b64": b64(MSP), "commit": True}).json()["errors"] == 2      # codes now exist
    x = c.get(f"/projects/{pid}/export/plan.xlsx", headers=h["pm1"])
    head, rows = tabular.read_xlsx(x.content)
    assert head[:3] == ["code", "name", "planned_hours"] and {"1.1", "1.2"} <= {r[0] for r in rows}
    bad = xl(["code", "name", "planned_hours"], [["Z1", "Zero hours", 0]])
    assert c.post(url, headers=h["pm1"], json={"filename": "b.xlsx", "content_b64": bad}).json()["errors"] == 1
    assert c.get("/export/portfolio.xlsx", headers=h["pmo1"]).status_code == 200
    assert c.get("/export/portfolio.xlsx", headers=h["s1"]).status_code == 403
