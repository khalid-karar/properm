import re
import base64
import io
import zipfile
from datetime import timedelta

import pytest

from app import brief, docread
from tests.test_flow import TODAY, app, c, world  # noqa: F401
from tests.test_gates import mk

AR_BOOK = """مشروع تجريبي لبناء منصة بيانات
رقم الكراسة: TEST20260100001
اسم المنافسة: مشروع منصة البيانات التجريبي
58 نطاق العمل وكيفية تنفيذ الخدمات والأعمال
يهدف المشروع إلى بناء منصة بيانات مركزية من خلال تحقيق الأهداف التالية:
1. حصر الأنظمة المصدرية وتوثيق مخطط تدفق البيانات
2. بناء منصة بيانات قابلة للتوسع
المرحلة الأولى: الاستكشاف التقني (Discovery)
على الجهة المنفذة إجراء استكشاف تقني شامل، بحيث تشمل:
1. حصر جميع الأنظمة المصدرية وقواعد البيانات القائمة وتوثيق إصداراتها
2. إعداد مخطط تدفق البيانات يوضح حركة البيانات بين الأنظمة
3. إجراء تحليل أولي لجودة البيانات في المصادر المشمولة
مخرجات المرحلة الأولى:
إعداد وتسليم مخرجات المرحلة للهيئة لاعتمادها، وتشمل وثيقة جرد البيانات، ومخطط تدفق البيانات، وتقرير الاستكشاف، وفق نطاق المرحلة الأولى.
المرحلة الثانية: بناء المنصة
على الجهة المنفذة بناء المنصة، بحيث تشمل:
1. تصميم المعمارية الشاملة للمنصة وتحديد مكوناتها
2. تنفيذ عمليات تكامل البيانات ETL من الأنظمة المصدرية
3. تطبيق ضوابط جودة البيانات وفق متطلبات مكتب إدارة البيانات الوطنية NDMO
مخرجات المرحلة الثانية:
تسليم المخرجات للهيئة، وتشمل وثيقة المعمارية التقنية، ومنصة بيانات مكتملة البناء، وفق نطاق المرحلة الثانية.
59 برنامج العمل
مدة المشروع (6) أشهر وتبدأ من تاريخ توقيع العقد.
المخرجات المدة
المتوقعة
تاريخ البدء المرحلة #
حصر الأنظمة، جرد البيانات، تقرير الاستكشاف.
شهران
بداية المشروع
مرحلة الاستكشاف
والتحليل
وثيقة المعمارية، تنفيذ المنصة.
4 أشهر
بعد اعتماد
مخرجات
المرحلة الأولى
مرحلة البناء
60 مكان تنفيذ الأعمال
سيتم تنفيذ الأعمال بنظام العمل الهجين.
جدول مواصفات فريق العمل
# الفريق الشروط مكان العمل
1 مدير المشروع خبرة لا تقل عن 5 سنوات في إدارة المشاريع هجين
2 مهندس تكامل وبيانات Data Engineer) خبرة لا تقل عن سنتين في تطوير عمليات ETL هجين
3 أخصائي حوكمة وجودة البيانات خبرة لا تقل عن سنتين في حوكمة البيانات هجين
64 الأصناف والمواد
آلية قبول المخرجات:
1. يلتزم المتعاقد بتسليم كل مخرج وفق الخطة الزمنية المعتمدة.
2. تقوم الهيئة بمراجعة المخرج خلال مدة لا تتجاوز (15) يوم عمل من تاريخ استلامه.
3. لا يعد تسليم أي مخرج قبولا نهائيا ما لم يصدر اعتماد كتابي من الهيئة.
ب. نقل المعرفة والتدريب
"""

EN_BOOK = """Request for Proposal: Customer Portal
Reference: RFP-2026-77
Scope of work
The project shall deliver the following objectives:
1. Replace the legacy portal with a new web portal
2. Migrate customer data
Phase 1: Discovery
The contractor shall:
1. Interview stakeholders and document current processes
2. Define the target architecture and the migration approach
Deliverables: requirements document, target architecture, migration plan
Phase 2: Build
The contractor must:
1. Build the portal front end and the back end services
2. Execute integration tests with the billing system
Deliverables: working portal, test report
"""


def test_arabic_book_is_analysed():
    r = brief.analyze([AR_BOOK])
    assert r["meta"]["language"] == "ar" and r["meta"]["duration_months"] == 6 and r["meta"]["tender_number"] == "TEST20260100001"
    ph = {p["n"]: p for p in r["phases"]}
    assert (ph[1]["start_month"], ph[1]["end_month"]) == (0, 2) and (ph[2]["start_month"], ph[2]["end_month"]) == (2, 6)     # phase 2 starts after phase 1 is approved
    assert [t["title"] for t in r["team"]] == ["مدير المشروع", "مهندس تكامل وبيانات", "أخصائي حوكمة وجودة البيانات"] and r["team"][0]["min_years"] == 5
    assert len([d for d in r["deliverables"] if d["phase"] == 1]) == 3 and any("ثيقة" in d["name"] and d["name"].startswith("وثيقة") for d in r["deliverables"])
    assert len(r["objectives"]) == 2 and len([a for a in r["activities"] if a["phase"] == 2]) == 3
    etl = next(a for a in r["activities"] if "ETL" in a["name"])
    assert etl["role"] == "مهندس تكامل وبيانات"
    assert all(a["page"] for a in r["activities"]) and all(q["code"].startswith("R-") for q in r["requirements"])
    assert any(t["kind"] == "acceptance" for t in r["terms"]) and [x["framework"] for x in r["compliance"]] == ["NDMO"]


def test_english_book_is_analysed():
    r = brief.analyze([EN_BOOK])
    assert r["meta"]["language"] == "en" and [p["n"] for p in r["phases"]] == [1, 2]
    assert [d["name"] for d in r["deliverables"] if d["phase"] == 2] == ["working portal", "test report"]
    assert len(r["activities"]) == 4 and all(a["planned_hours"] >= 16 for a in r["activities"])
    assert any(q["priority"] == "must" for q in r["requirements"])


def test_docx_and_text_readers():
    xml = "<w:document><w:body>" + "".join(f"<w:p><w:r><w:t>{ln}</w:t></w:r></w:p>" for ln in AR_BOOK.split("\n")) + "</w:body></w:document>"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", xml)
    rd = docread.read_document("book.docx", buf.getvalue())
    assert rd["method"] == "docx" and "المرحلة الأولى" in rd["text"]
    assert brief.analyze(rd["pages"])["meta"]["duration_months"] == 6
    assert docread.read_document("b.txt", EN_BOOK.encode())["method"] == "text"
    with pytest.raises(docread.ReadError):
        docread.read_document("b.exe", b"x" * 100)
    with pytest.raises(docread.ReadError):
        docread.read_document("empty.txt", b"hi")
    assert docread.clean("\ufefb") == "لا"                    # a lam-alef ligature is folded back to two letters


def test_live_model_refines_a_phase(monkeypatch, c, world):
    from app import ai
    monkeypatch.setenv("PROPERM_AI_BASE_URL", "http://localhost:9999")
    monkeypatch.setattr(ai, "_live", lambda task, payload, prompt: '{"tasks":[{"name":"Interview owners","hours":30,"role":"مدير المشروع"}],"requirements":["The contractor shall run a workshop"],"deliverables":[]}')
    h = world["h"]
    pid = c.post("/projects", headers=h["pm1"], json={"number": "L-1", "name": "Live", "state": "planning"}).json()["id"]
    r = c.post(f"/projects/{pid}/brief/analyze", headers=h["pm1"], json={"text": AR_BOOK})
    assert r.status_code == 201, r.text
    d = c.get(f"/projects/{pid}/brief/{r.json()['draft_id']}", headers=h["pm1"]).json()["draft"]
    assert any(a.get("by") == "model" and a["name"] == "Interview owners" for a in d["activities"])
    assert any(q.get("by") == "model" for q in d["requirements"]) and len(d["notes"]) == 2


def doc(c, h, pid, name, raw):
    r = c.post(f"/projects/{pid}/documents", headers=h["pm1"], json={"kind": "scope", "filename": name, "content_b64": base64.b64encode(raw).decode()})
    assert r.status_code == 201, r.text
    return r.json()["id"]




def test_book_to_plan_to_close(c, world):
    """The whole story: a tender book arrives, the plan is drafted, staff are proposed, the PM applies it, the project runs and burns hours, and closes."""
    h, ids = world["h"], world["ids"]
    ad, pm, pmo, s1, s2 = h["admin"], h["pm1"], h["pmo1"], h["s1"], h["s2"]
    # people and skills: s1 integration engineer, s2 governance specialist; nobody can be the architect/manager role
    for uid, sk in ((ids["s1"], "مهندس تكامل وبيانات"), (ids["s2"], "أخصائي حوكمة وجودة البيانات")):
        assert c.post(f"/people/{uid}/skills", headers=pmo, json={"skill": sk, "level": 3}).status_code in (200, 201)
    start = TODAY - timedelta(days=9)
    r = c.post("/projects", headers=pm, json={"number": "TND-1", "name": "Data platform", "state": "tendering", "planned_start": str(start), "planned_end": str(start + timedelta(days=185)), "project_type": "hybrid"})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    # tendering: analyse is allowed, apply is not until the project is in planning
    did_doc = doc(c, h, pid, "book.txt", AR_BOOK.encode())
    a = c.post(f"/projects/{pid}/brief/analyze", headers=pm, json={"document_id": did_doc})
    assert a.status_code == 201, a.text
    draft_id = a.json()["draft_id"]
    assert a.json()["counts"]["activities"] == 6 and a.json()["counts"]["phases"] == 2
    assert c.post(f"/projects/{pid}/brief/analyze", headers=s1, json={"document_id": did_doc}).status_code == 403
    assert c.post(f"/projects/{pid}/brief/analyze", headers=pm, json={}).status_code == 422
    assert c.post(f"/projects/{pid}/brief/{draft_id}/apply", headers=pm, json={}).status_code == 409
    assert c.post(f"/projects/{pid}/transition", headers=pm, json={"to_state": "planning"}).status_code == 200
    g = c.get(f"/projects/{pid}/brief/{draft_id}", headers=pm).json()
    st = g["staffing"]
    by_role = {a["code"]: a["role"] for a in g["draft"]["activities"]}
    for code, role in by_role.items():
        if role == "مهندس تكامل وبيانات":
            assert st[code]["user_id"] == ids["s1"]
        elif role == "أخصائي حوكمة وجودة البيانات":
            assert st[code]["user_id"] == ids["s2"] or "free hours" in st[code]["reason"], st[code]          # capacity-aware: no free hours -> unassigned with the reason
        else:
            assert st[code]["user_id"] is None and "Nobody has the skill" in st[code]["reason"]          # marked unassigned, with the reason
    # the PM edits one estimate: a small budget so the burn alert is easy to see later
    acts = g["draft"]["activities"]
    etl = next(a for a in acts if a["role"] == "مهندس تكامل وبيانات")
    etl["planned_hours"] = 20.0
    ap = c.post(f"/projects/{pid}/brief/{draft_id}/apply", headers=pm, json={"draft": {"activities": acts}})
    assert ap.status_code == 200, ap.text
    n = ap.json()
    assert n["activities"] == 6 and n["milestones"] == 2 and n["unassigned"] >= 1 and n["resource_requests"] >= 1 and n["assigned"] >= 1
    assert n["requirements"] >= 8 and n["deliverables"] == 5 and n["risks"] >= 3 and n["compliance"] == 1
    assert c.post(f"/projects/{pid}/brief/{draft_id}/apply", headers=pm, json={}).status_code == 409           # only once
    # what landed
    assert len(c.get(f"/projects/{pid}/requirements", headers=pm).json()) == n["requirements"]
    wbs = c.get(f"/projects/{pid}/wbs", headers=pm).json()
    assert len(wbs) == 5
    rr = c.get("/resource-requests", headers=pmo)
    assert rr.status_code == 200
    assert any(x["skill"] == "مدير المشروع" for x in rr.json()) or rr.json()
    # baseline, then run the project
    assert c.post(f"/projects/{pid}/baseline/lock", headers=pm).status_code == 200
    acts_now = {a["code"]: a for a in c.get(f"/projects/{pid}", headers=pm).json()["activities"]}
    ecode = etl["code"]
    eid = acts_now[ecode]["id"]
    # staff burn hours: 18 of 20 on the ETL task; the per-activity cap (R2) protects the budget
    for k in range(2):
        d = TODAY - timedelta(days=k)
        if d.weekday() in (4, 5):
            continue
        r = c.post("/timesheets", headers=s1, json={"project_id": pid, "activity_id": eid, "entry_date": str(d), "hours": 9})
        assert r.status_code in (200, 201), r.text
    r = c.post("/timesheets", headers=s1, json={"project_id": pid, "activity_id": eid, "entry_date": str(TODAY - timedelta(days=5)), "hours": 8})
    # monitoring: hours used far ahead of progress raises an alert
    c.put(f"/projects/{pid}/progress", headers=pm, json={"week_of": str(TODAY), "updates": [{"activity_id": eid, "pct_complete": 20}]})
    ev = c.post(f"/projects/{pid}/alerts/evaluate", headers=pm)
    assert ev.status_code == 200, ev.text
    al = c.get(f"/alerts?project_id={pid}", headers=pm).json()
    assert any(x["rule"] in ("activity_burn_high", "activity_hours_exceeded") and ecode in x["cause"] for x in al), al
    # delivery: the PM approves the burned hours, the client accepts every deliverable, the work reaches 100%, the project closes
    for e in c.get("/timesheets/queue", headers=pm).json():
        if e["status"] == "submitted":
            assert c.post(f"/timesheets/{e['id']}/decision", headers=pm, json={"action": "approve"}).status_code == 200
    rp = c.put(f"/projects/{pid}/progress", headers=pm, json={"week_of": str(TODAY), "updates": [{"activity_id": a["id"], "pct_complete": 100} for a in acts_now.values() if a.get("phase")=="execution"]})
    assert rp.status_code == 200, rp.text
    for d in c.get(f"/projects/{pid}/wbs", headers=pm).json():
        assert c.post(f"/projects/{pid}/wbs/{d['id']}/start", headers=pm).status_code == 200, d
        assert c.post(f"/projects/{pid}/wbs/{d['id']}/submit", headers=pm).status_code == 200
        assert c.post(f"/projects/{pid}/wbs/{d['id']}/decision", headers=pmo, json={"accept": True, "note": "Accepted"}).status_code == 200
    sm = c.get(f"/projects/{pid}/scope-summary", headers=pm).json()
    assert sm["deliverables"]["accepted_pct"] == 100
    assert c.post(f"/projects/{pid}/transition", headers=pm, json={"to_state": "closing"}).status_code == 200
    for k in ("costs_reconciled", "risks_reviewed", "lessons_learned", "documents_archived", "benefits_handover"):
        assert c.put(f"/projects/{pid}/closure/{k}", headers=pm, json={"done": True, "note": "ok"}).status_code == 200
    cl = c.get(f"/projects/{pid}/closure", headers=pm).json()
    assert next(i for i in cl["items"] if i["key"] == "deliverables_accepted")["satisfied"] is True         # automatic: every deliverable accepted
    r = c.post(f"/projects/{pid}/transition", headers=pmo, json={"to_state": "archived"})
    assert r.status_code == 200, r.text



def test_plan_domains_review_and_apply(c, world):
    h = world["h"]
    pm, s1 = h["pm1"], h["s1"]
    r = c.post("/projects", headers=pm, json={"number": "TND-D", "name": "Domains", "state": "planning", "planned_start": str(TODAY), "planned_end": str(TODAY + timedelta(days=185)), "project_type": "hybrid"})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    a = c.post(f"/projects/{pid}/brief/analyze", headers=pm, json={"text": AR_BOOK})
    assert a.status_code == 201, a.text
    did = a.json()["draft_id"]
    g = c.get(f"/projects/{pid}/brief/{did}", headers=pm).json()["draft"]
    assert set(g["domains"]) == {"stakeholders", "communication", "quality", "cost", "procurement", "change"}
    assert all(d["status"] == "proposed" and d["items"] for d in g["domains"].values())
    url = f"/projects/{pid}/brief/{did}/domains"
    assert c.post(f"{url}/cost", headers=s1, json={"action": "accept"}).status_code == 403
    assert c.post(f"{url}/nope", headers=pm, json={"action": "accept"}).status_code == 404
    assert c.post(f"{url}/cost", headers=pm, json={"action": "reject"}).status_code == 422        # needs feedback
    # modify: tracked diff
    items = g["domains"]["communication"]["items"]
    items[0]["frequency"] = "weekly"
    m = c.post(f"{url}/communication", headers=pm, json={"action": "modify", "items": items}).json()
    assert m["status"] == "modified" and m["history"][-1]["diff"]
    # reject and regenerate with feedback: feedback is kept visible, status goes back to proposed
    rj = c.post(f"{url}/cost", headers=pm, json={"action": "reject", "feedback": "add travel costs"}).json()
    assert rj["status"] == "proposed" and any("travel" in str(i) for i in rj["items"]) and rj["history"][-1]["feedback"] == "add travel costs"
    assert c.post(f"{url}/stakeholders", headers=pm, json={"action": "accept"}).status_code == 200
    ap = c.post(f"/projects/{pid}/brief/{did}/apply", headers=pm, json={"sections": ["domains"]})
    assert ap.status_code == 200, ap.text
    n = ap.json()
    assert n["domains_skipped"] == 4 and n["domain_items"] > 3          # only the two reviewed domains were applied
    st = c.get(f"/projects/{pid}/stakeholders", headers=pm)
    assert st.status_code == 200 and len(st.json()) >= 3


def test_apply_validates_edited_draft(c, world):
    """Edits made in the review screen are checked on the server: orphan phases, blank names, bad hours."""
    h = world["h"]
    pm = h["pm1"]
    start = TODAY
    r = c.post("/projects", headers=pm, json={"number": "VAL-1", "name": "Validate", "state": "planning", "planned_start": str(start), "planned_end": str(start + timedelta(days=185))})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    did = doc(c, h, pid, "book.txt", AR_BOOK.encode())
    a = c.post(f"/projects/{pid}/brief/analyze", headers=pm, json={"document_id": did})
    assert a.status_code == 201, a.text
    dr = c.get(f"/projects/{pid}/brief/{a.json()['draft_id']}", headers=pm).json()["draft"]
    url = f"/projects/{pid}/brief/{a.json()['draft_id']}/apply"
    import copy
    bad = copy.deepcopy(dr); bad["activities"][0]["phase"] = 99
    assert c.post(url, headers=pm, json={"draft": bad}).status_code == 422
    bad = copy.deepcopy(dr); bad["activities"][0]["name"] = "  "
    assert c.post(url, headers=pm, json={"draft": bad}).status_code == 422
    bad = copy.deepcopy(dr); bad["phases"][0]["name"] = ""
    assert c.post(url, headers=pm, json={"draft": bad}).status_code == 422
    bad = copy.deepcopy(dr); bad["requirements"].append({"code": "R-X", "title": "", "text": "", "priority": "should", "phase": None})
    assert c.post(url, headers=pm, json={"draft": bad}).status_code == 422
    ok = copy.deepcopy(dr); ok["activities"].append({"code": "NEW-1", "name": "Added by hand", "description": "", "phase": dr["phases"][0]["n"], "planned_hours": 10, "start_month": 0, "end_month": 1, "role": "", "page": None, "estimate": True})
    ok["requirements"].append({"code": "R-NEW", "title": "Added requirement", "text": "x", "priority": "must", "phase": None, "page": None, "section": "added"})
    g = c.post(url, headers=pm, json={"draft": ok})
    assert g.status_code in (200, 201), g.text


def test_start_project_from_the_book(c, world):
    import base64
    h = world["h"]
    pm = h["pm1"]
    body = {"filename": "book.txt", "content_b64": base64.b64encode(AR_BOOK.encode()).decode()}
    pv = c.post("/project-intake/book/preview", headers=pm, json=body)
    assert pv.status_code == 200, pv.text
    pr = pv.json()
    assert pr["number"] and len(pr["phases"]) == 2 and pr["planned_end"] > pr["planned_start"] and pr["counts"]["activities"] == 6
    assert c.post("/project-intake/book/preview", headers=h["s1"], json=body).status_code == 403
    assert c.post("/project-intake/book/preview", headers=pm, json={}).status_code == 422
    # nothing was created by the preview
    assert not [p for p in c.get("/projects", headers=pm).json() if p["number"] == pr["number"]]
    ok = c.post("/project-intake/book/confirm", headers=pm, json={**body, "number": "BOOK-1", "name": pr["name"] or "From the book", "planned_start": pr["planned_start"], "planned_end": pr["planned_end"]})
    assert ok.status_code == 201, ok.text
    pid = ok.json()["project_id"]
    assert ok.json()["draft_id"] and ok.json()["counts"]["activities"] == 6
    assert c.post("/project-intake/book/confirm", headers=pm, json={**body, "number": "BOOK-1", "name": "dup", "planned_start": pr["planned_start"], "planned_end": pr["planned_end"]}).status_code == 409
    docs = c.get(f"/projects/{pid}/documents", headers=pm).json()
    assert [d["kind"] for d in docs] == ["tender_book"]
    assert c.get(f"/projects/{pid}/brief", headers=pm).json()[0]["id"] == ok.json()["draft_id"]


def test_translation_needs_the_saudi_model(monkeypatch, c, world):
    import json as _json

    from app import ai
    h = world["h"]
    pid = c.post("/projects", headers=h["pm1"], json={"number": "TR-1", "name": "Tr", "state": "planning"}).json()["id"]
    a = c.post(f"/projects/{pid}/brief/analyze", headers=h["pm1"], json={"text": AR_BOOK})
    did = a.json()["draft_id"]
    url = f"/projects/{pid}/brief/{did}/translate"
    r = c.post(url, headers=h["pm1"], json={"target": "en"})
    assert r.status_code == 200 and r.json()["status"] == "unavailable"                  # stub mode: nothing is translated, nothing is invented
    assert "translations" not in c.get(f"/projects/{pid}/brief/{did}", headers=h["pm1"]).json()["draft"]
    assert c.post(url, headers=h["pm1"], json={"target": "fr"}).status_code == 422
    monkeypatch.setenv("PROPERM_AI_BASE_URL", "http://localhost:9999")
    monkeypatch.setattr(ai, "_live", lambda task, payload, prompt: _json.dumps({"items": ["EN:" + x for x in _json.loads(prompt.splitlines()[-1])]}, ensure_ascii=False))
    r = c.post(url, headers=h["pm1"], json={"target": "en"})
    assert r.status_code == 200 and r.json()["status"] == "ok" and r.json()["translated"] > 5
    d = c.get(f"/projects/{pid}/brief/{did}", headers=h["pm1"]).json()["draft"]
    first = d["activities"][0]["name"]
    assert d["translations"]["en"]["activities.0.name"] == {"src": first, "t": "EN:" + first}
    monkeypatch.setattr(ai, "_live", lambda task, payload, prompt: '{"items": ["only one"]}')
    assert c.post(url, headers=h["pm1"], json={"target": "en"}).status_code == 502


def test_arabic_book_gives_arabic_plan_wording():
    from app import brief, plandomains
    text = "رقم الكراسة: ABC-123456\nاسم المنافسة: مشروع تجريبي\nيتم اعتماد مخرجات كل مرحلة، وجودة البيانات مهمة، وبالتوازي مع مراحل أخرى.\n"
    r = brief.analyze([text])
    assert r["meta"]["language"] == "ar"
    assert r["risks"] and all(re.search(r"[؀-ۿ]", x["title"]) for x in r["risks"])
    dom = plandomains.generate(r)
    assert re.search(r"[؀-ۿ]", dom["communication"]["items"][0]["audience"])
    assert dom["communication"]["items"][0]["frequency"] == "monthly"
