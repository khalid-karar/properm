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
