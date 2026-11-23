"""Tender book / brief analysis (flow chart 1.2). Turns the text of a project book, Arabic or English, into a DRAFT:
requirements, deliverables, phases with dates, tasks with hour estimates, team roles, risks, compliance items and contract terms.
Everything carries its source page. Nothing here writes to the project: a person reviews the draft first (1.3).
Two engines: deterministic rules (always available, works offline) and the Saudi-hosted model (refines each phase when AI is live)."""
import re
from bisect import bisect_right
from math import ceil

ORD_AR = {"الاولى": 1, "الأولى": 1, "الثانية": 2, "الثالثة": 3, "الرابعة": 4, "الخامسة": 5, "السادسة": 6, "السابعة": 7, "الثامنة": 8, "التاسعة": 9, "العاشرة": 10}
ORD_AR_MONTH = {"الاول": 1, "الأول": 1, "الثاني": 2, "الثالث": 3, "الرابع": 4, "الخامس": 5, "السادس": 6, "السابع": 7, "الثامن": 8, "التاسع": 9, "العاشر": 10, "الحادي عشر": 11, "الثاني عشر": 12}
ORD_EN = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
FTE_DEFAULT = 2.0          # assumed average full-time people working a phase, used only for the hour estimate
WEEK_H = 40.0

MUST = re.compile(r"يجب|يلتزم|على الجهة المنفذة|على المتعاقد|على المورد|ضمان|\bshall\b|\bmust\b|\brequired\b|\bis required\b", re.I)
AR = re.compile("[؀-ۿ]")


class Doc:
    """Text with page tracking."""
    def __init__(self, pages: list[str]):
        self.pages = pages
        self.starts, pos, parts = [], 0, []
        for p in pages:
            self.starts.append(pos)
            parts.append(p)
            pos += len(p) + 1
        self.text = "\n".join(parts)

    def page(self, pos: int) -> int:
        return bisect_right(self.starts, pos)


def _norm_ar(s: str) -> str:
    return s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ى", "ي").replace("ة", "ه")


def _short(s: str, n: int = 110) -> str:
    s = re.sub(r"\s+", " ", s).strip(" .:؛;-")
    s = re.sub(r"^\d+[\.\-\)]\s*", "", s)
    for sep in ("، ", ", ", " بحيث", " بما يشمل", " بما في ذلك", " ، ", ": "):
        i = s.find(sep, 22)
        if 0 < i <= n:
            return s[:i].strip(" .:؛;-")
    if len(s) <= n:
        return s
    cut = s[:n].rsplit(" ", 1)[0]
    return cut + "…"


def _clean_item(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _num(s: str) -> int | None:
    s = _norm_ar(s.strip())
    if s in ("شهران", "شهرين"):
        return 2
    m = re.search(r"\d+", s)
    return int(m.group()) if m else (1 if s.startswith("شهر") else None)


# ---------------- sections ----------------
PH_HEAD = re.compile(r"^(?:المرحلة\s+(الاولى|الأولى|الثانية|الثالثة|الرابعة|الخامسة|السادسة|السابعة|الثامنة)\s*[:：]|(?:Phase|Stage)\s+(\d+|One|Two|Three|Four|Five|Six|Seven|Eight)\s*[:\-–.]\s*)(.*)$", re.M | re.I)
NUM_ITEM = re.compile(r"^\s*(\d{1,2})\s*[\.\-\)]\s+(?=\S)", re.M)


def _phase_sections(d: Doc):
    heads = [(m.start(), m.end(), m) for m in PH_HEAD.finditer(d.text)]
    out = []
    for i, (s, e, m) in enumerate(heads):
        end = heads[i + 1][0] if i + 1 < len(heads) else None
        # a phase section ends at the next phase heading or at a numbered article heading like "59 برنامج العمل"
        body = d.text[e: end if end else len(d.text)]
        stop = re.search(r"^\s*\d{1,3}\s+(?:برنامج العمل|مكان تنفيذ|Work program|Schedule)\b", body, re.M)
        if stop:
            body = body[:stop.start()]
        un = re.search(r"^[^\n\d•][^\n]{5,100}\n[^\n]*(?:المجالات التالية|following areas)", body, re.M)
        if un:
            body = body[:un.start()]
        n = ORD_AR.get(m.group(1) or "") or (int(m.group(2)) if (m.group(2) or "").isdigit() else ORD_EN.get((m.group(2) or "").lower()))
        out.append({"n": n or i + 1, "title": _clean_item(m.group(3)) if m.group(3) else "", "start": s, "body": body, "body_start": e})
    # the heading line itself carries the title: drop "(Technical Discovery)" noise duplicates
    return out


def _items(body: str, base: int):
    """Numbered items inside a section: [(text, offset)]. Item text runs until the next number."""
    ms = list(NUM_ITEM.finditer(body))
    res = []
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(body)
        txt = body[m.end():end]
        txt = re.split(r"\n\s*(?:مخرجات المرحلة|المخرجات المطلوبة|Deliverables)", txt)[0]
        txt = _clean_item(txt)
        if len(txt) > 12:
            res.append((txt, base + m.start(), int(m.group(1))))
    # keep only the first 1..n run (a section may contain later unrelated lists)
    seq, keep = 0, []
    for t, off, k in res:
        if k == seq + 1 or (seq == 0 and k == 1):
            seq = k
            keep.append((t, off, k))
    return keep


def _deliverables_text(body: str) -> str | None:
    m = re.search(r"(?:مخرجات المرحلة[^\n:]*[:：]?|المخرجات المطلوبة[:：]?|Deliverables[:：]?)\s*(.+?)(?:\n\s*\n|\Z)", body, re.S | re.I)
    if not m:
        return None
    t = _clean_item(m.group(1))
    t = re.sub(r"^.*?(?:وتشمل|تشمل|including|include|includes)\s+", "", t, count=1) if re.search(r"وتشمل|تشمل|includ", t) else t
    t = re.split(r"،?\s*وفق (?:نطاق|المتطلبات)|\s+per the scope", t)[0]
    return t.strip(" .")


NOT_CONJ = ("وثيق", "وصف", "وظيف", "وحد", "وكال", "ورق", "وسائ", "وقت", "وضع", "وجود", "واجه", "وصول", "وثائق")


def _split_list(t: str) -> list[str]:
    parts = re.split(r"[،;؛]|\s*,\s+(?![^()]*\))", t)
    out = []
    for p in parts:
        p = p.strip()
        if p.startswith("و") and not p.startswith(NOT_CONJ) and out:
            p = p[1:]
        p = re.sub(r"^and\s+", "", p).strip(" .")
        if len(p) >= 4 and not re.match(r"^(?:بما |إضافة|بالإضافة|المجالات|ومتطلباتها)", p):
            out.append(re.split(r"\s+بما (?:يشمل|في ذلك)", p)[0].strip())
    return out


# ---------------- work program table ----------------
DUR = re.compile(r"(شهران|شهرين|\d+\s*أشهر|\d+\s*اشهر|\d+\s*شهر(?:ا|اً)?|\d+\s*months?)", re.I)


def _start_offset(txt: str, ends: dict[int, int]) -> int:
    t = _norm_ar(txt)
    m = re.search(r"بعد اعتماد.*?المرحله\s+(\w+)", t, re.S)
    if m:
        n = ORD_AR.get(m.group(1)) or ORD_AR.get(m.group(1).replace("ا", "أ", 1))
        if not n:
            for k, v in ORD_AR.items():
                if _norm_ar(k) == m.group(1):
                    n = v
        if n and n in ends:
            return ends[n]
    m = re.search(r"الشهر\s+(الحادي عشر|الثاني عشر|\w+)", t)
    if m:
        for k, v in ORD_AR_MONTH.items():
            if _norm_ar(k) == m.group(1):
                return v - 1
    return 0


def parse_program(d: Doc):
    """Work-program table: duration, start rule, phase name. Returns (total_months, [rows]) or (None, [])."""
    total = None
    m = re.search(r"مدة المشروع\s*\(?\s*(\d+)\s*\)?\s*(?:أشهر|اشهر|شهر)", d.text) or re.search(r"(?:project )?duration[^\d]{0,30}(\d+)\s*months?", d.text, re.I)
    if m:
        total = int(m.group(1))
    m = re.search(r"المرحلة\s*#\s*\n(.*?)(?=\n\s*\d{1,3}\s+(?:مكان تنفيذ|Place of|Location)|\Z)", d.text, re.S)
    if not m:
        return total, []
    lines = [ln.strip() for ln in m.group(1).split("\n") if ln.strip() and not re.fullmatch(r"\d{1,2}", ln.strip())]
    rows, deliv, start, name, state, prev = [], [], [], [], "deliv", ""
    i = 0
    while i < len(lines):
        ln = lines[i]
        if state == "deliv":
            dm = DUR.search(ln)
            if dm:
                before = ln[:dm.start()].strip()
                if before:
                    deliv.append(before)
                dur = _num(dm.group(1))
                state, start = "start", []
                rest = ln[dm.end():].strip()
                if rest:
                    start.append(rest)
            else:
                deliv.append(ln)
        else:
            if ln.startswith("مرحلة") and not prev.endswith("مع"):
                name = [ln]
                j = i + 1
                while j < len(lines) and len(name) < 3 and len(lines[j]) <= 22 and not DUR.search(lines[j]) and "،" not in lines[j] and not lines[j].startswith("مرحلة") and not lines[j].endswith("."):
                    name.append(lines[j])
                    j += 1
                rows.append({"name": " ".join(name), "deliverables_text": " ".join(deliv), "months": dur, "start_text": " ".join(start)})
                deliv, state, i = [], "deliv", j - 1
            else:
                start.append(ln)
        prev = ln
        i += 1
    ends, offs = {}, []
    for k, r in enumerate(rows, 1):
        r["n"] = k
        r["start_month"] = _start_offset(r["start_text"], ends)
        r["end_month"] = r["start_month"] + (r["months"] or 1)
        ends[k] = r["end_month"]
    return total, rows


# ---------------- team, terms, risks, compliance ----------------
def parse_team(d: Doc):
    m = re.search(r"الفريق\s+الشروط\s+مكان العمل(.*?)(?=\n\s*\d{1,3}\s+(?:الاصناف|الأصناف|المواد)|\Z)", d.text, re.S) or \
        re.search(r"(?:Role|Team member|Position)\s+(?:Requirements|Qualifications)[^\n]*\n(.*?)(?:\n\n|\Z)", d.text, re.S | re.I)
    if not m:
        return []
    t = re.sub(r"\s+", " ", m.group(1))
    roles = []
    for seg in re.split(r"(?<=هجين)|(?<=حضوري)|(?<=عن بعد)|(?<=hybrid)|(?<=onsite)|(?<=remote)", t):
        r = re.search(r"^\s*(?:\d\s+)?(.{3,90}?)\s+(?:خبرة لا تقل\s*عن|at least|minimum)\s*(سنتين|سنتان|\d+)", seg, re.I)
        if not r:
            continue
        years = 2 if r.group(2) in ("سنتين", "سنتان") else int(r.group(2))
        title = re.sub(r"\s*[\(\)]\s*", " ", r.group(1)).strip()
        eng = re.findall(r"[A-Za-z][A-Za-z /&]+", title)
        roles.append({"title": re.sub(r"\s*[A-Za-z][A-Za-z /&]+\s*$", "", title).strip() or title, "english": eng[0].strip() if eng else None, "min_years": years})
    return roles


RISK_RULES = [
    (r"اعتماد مخرجات|مراجعة المخرج|deliverable review", "Client approvals delay phase hand-over", "schedule", 3, 4, "Agree review dates in the kick-off; chase approvals weekly; escalate to the sponsor after 5 working days"),
    (r"بالتوازي|in parallel", "Parallel phases compete for the same people", "resource", 3, 4, "Confirm named staff for overlapping phases before baseline; watch load in the capacity plan"),
    (r"جودة البيانات|data quality", "Poor source data quality slows integration", "technical", 4, 3, "Do the early data-quality analysis; agree remediation owners with the client"),
    (r"البيانات الشخصية|personal data|sensitive", "Personal or sensitive data handled in non-production environments", "compliance", 3, 5, "Use masking or test data; apply the client's classification controls"),
    (r"المنصة الجاهزة|pre-?built|ready-made", "Ready-made platform does not fit the client environment", "technical", 3, 4, "Run the fit and gap assessment in phase 1; record gaps as change items"),
    (r"التراخيص|licen[cs]e", "Licences or dependencies not available when needed", "procurement", 3, 3, "List licences and responsibilities in phase 1; order early"),
    (r"الأنظمة المصدرية|source systems", "Source system owners are slow to give access or documentation", "dependency", 4, 3, "Name a client contact per system; request access at kick-off"),
    (r"نقل المعرفة|training|knowledge transfer", "Client team not available for training and knowledge transfer", "resource", 2, 3, "Fix the training calendar in the plan; get named attendees"),
    (r"غرامة تأخير|غرامات التأخير|delay penalt|liquidated damages", "Contract penalties for missing deadlines", "contract", 2, 4, "Track delivery dates against the contract; raise change requests early"),
    (r"ضمان نهائي|الضمان النهائي|performance guarantee|final guarantee", "Final guarantee and payment timing affect cash flow", "financial", 2, 3, "Plan guarantee issue before contract signature; match invoices to accepted deliverables"),
]
FRAMEWORKS = [(r"NDMO|مكتب إدارة البيانات الوطنية", "NDMO", "Comply with the National Data Management Office controls that apply to the project"),
              (r"PDPL|نظام حماية البيانات الشخصية", "PDPL", "Comply with the Personal Data Protection Law"),
              (r"الهيئة الوطنية للأمن السيبراني|\bNCA\b|\bECC\b", "NCA", "Comply with the National Cybersecurity Authority controls that apply to the project"),
              (r"المحتوى المحلي|local content", "Local content", "Meet the local content and SME preference requirements")]


def _sentences_with(d: Doc, pat: str, limit=6):
    out = []
    for m in re.finditer(pat, d.text):
        a = max(d.text.rfind(".", 0, m.start()), d.text.rfind("\n", 0, m.start())) + 1
        b = d.text.find(".", m.end())
        b = len(d.text) if b < 0 else b + 1
        s = _clean_item(d.text[a:b])
        if 20 < len(s) < 420 and s not in [x["text"] for x in out]:
            out.append({"text": s, "page": d.page(m.start())})
        if len(out) >= limit:
            break
    return out


def parse_terms(d: Doc):
    terms = []
    m = re.search(r"آلية قبول المخرجات[:：]?(.*?)(?=\n\s*ب\s*[\.\-]\s|نقل المعرفة|\Z)", d.text, re.S)
    if m:
        for it, off, k in _items(m.group(1), m.start(1)):
            terms.append({"kind": "acceptance", "text": it, "page": d.page(off)})
    for kind, pat in (("penalty", r"غرامة التأخير|غرامات التأخير|غرامة مالية|delay penalt|liquidated"), ("payment", r"جدول الدفعات|payment schedule"), ("guarantee", r"الضمان النهائي|performance guarantee")):
        for s in _sentences_with(d, pat, 6):
            if kind == "penalty" and re.search(r"العرض|المتنافس|الانسحاب|bid|tender", s["text"]):
                continue
            if len([t for t in terms if t["kind"] == kind]) < 3:
                terms.append({"kind": kind, **s})
    vat = re.search(r"(\d+)\s*%\s*(?:\()?\s*ضريبة القيمة المضافة|ضريبة القيمة المضافة\s*(\d+)\s*%|VAT\s*(?:of\s*)?(\d+)\s*%", d.text)
    if vat:
        terms.append({"kind": "tax", "text": f"VAT {next(g for g in vat.groups() if g)}%", "page": d.page(vat.start())})
    return terms


# ---------------- roles for tasks ----------------
ROLE_KEYS = [
    (r"ETL|ELT|API|تكامل|معالجة|ضخ|pipeline|integration|ingest", ("integration", "تكامل", "engineer", "مهندس")),
    (r"جودة|حوكمة|NDMO|امتثال|تصنيف|وصفية|حماية|governance|quality|compliance|catalog|metadata", ("حوكمة", "جودة", "governance", "quality")),
    (r"معمار|تصميم|نمذجة|مخطط|هيكلة|طبقة|architect|design|schema|model|layer", ("architect", "معمار")),
    (r"إدارة المشروع|خطة|اختبار|قبول|تسليم|تدريب|نقل المعرفة|test|accept|handover|training|plan", ("مدير", "manager")),
]


def role_for(text: str, roles: list[dict]) -> str | None:
    if not roles:
        return None
    for pat, keys in ROLE_KEYS:
        if re.search(pat, text, re.I):
            for k in keys:
                for r in roles:
                    if _norm_ar(k) in _norm_ar((r["title"] + " " + (r.get("english") or "")).lower()):
                        return r["title"]
    return roles[0]["title"]


# ---------------- main ----------------
def analyze(pages: list[str], lang: str = "auto") -> dict:
    d = Doc(pages)
    arabic = len(AR.findall(d.text)) > 0.3 * max(1, len(re.findall(r"\w", d.text)))
    total, prog = parse_program(d)
    secs = _phase_sections(d)
    roles = parse_team(d)
    meta = {"language": "ar" if arabic else "en", "pages": len(pages), "duration_months": total}
    m = re.search(r"رقم الكراسة\s*[:：]?\s*([A-Z0-9\-]{6,})|(?:tender|RFP|reference)\s*(?:no\.?|number)?\s*[:#]?\s*([A-Z0-9\-]{6,})", d.text, re.I)
    if m:
        meta["tender_number"] = next(g for g in m.groups() if g)
    m = re.search(r"اسم المنافسة\s*[:：]\s*(.+)", d.text)
    if m:
        meta["name"] = _clean_item(m.group(1))
    # phases: the work program is the schedule authority, headed sections give the detail
    phases = []
    names = {r["n"]: r for r in prog}
    ns = sorted({s["n"] for s in secs} | set(names))
    if not ns:
        ns = [1]
    cur = 0
    for n in ns:
        r, s = names.get(n), next((x for x in secs if x["n"] == n), None)
        name = (r["name"] if r else None) or (s["title"] if s else "") or f"Phase {n}"
        name = re.sub(r"\s*\(.*?\)\s*$", "", name).strip() or name
        months = (r or {}).get("months")
        if r:
            sm, em = r["start_month"], r["end_month"]
        else:
            sm = cur
            em = sm + (months or max(1, round((total or 6) / max(len(ns), 1))))
        cur = em
        phases.append({"n": n, "name": name, "start_month": sm, "end_month": em, "months": em - sm, "source_page": d.page(s["start"]) if s else None, "_sec": s, "_row": r})
    if phases and not total:
        meta["duration_months"] = max(p["end_month"] for p in phases)
    reqs, delivs, acts = [], [], []
    # global objectives (numbered list before the first phase heading, under the scope article)
    pre = None
    mm = re.search(r"(?:الأهداف التالية|الاهداف التالية|following objectives|objectives:?)\s*[:：]?(.*?)(?=^المرحلة|^(?:Phase|Stage)\s+\d|\Z)", d.text, re.S | re.M | re.I)
    objectives = []
    if mm:
        for it, off, k in _items(mm.group(1), mm.start(1)):
            objectives.append(it)
            reqs.append({"title": _short(it), "text": it, "page": d.page(off), "priority": "must", "phase": None, "section": "Objectives"})
    for ph in phases:
        s, r = ph["_sec"], ph["_row"]
        items = _items(s["body"], s["body_start"]) if s else []
        for it, off, k in items:
            reqs.append({"title": _short(it), "text": it, "page": d.page(off), "priority": "must" if MUST.search(it) else "should", "phase": ph["n"], "section": f"Phase {ph['n']} item {k}"})
        dt = _deliverables_text(s["body"]) if s else None
        names_ = _split_list(dt) if dt else []
        if r and len(_split_list(r["deliverables_text"])) > len(names_):
            names_ = _split_list(r["deliverables_text"])
        for j, nm in enumerate(names_, 1):
            delivs.append({"code": f"D{ph['n']}.{j}", "name": _short(nm, 120), "description": nm, "phase": ph["n"], "page": ph["source_page"]})
        tasks = [(_short(it), it, off) for it, off, k in items if not re.search(r"^\s*(?:إعداد وتنفيذ وتسليم مخرجات المرحلة|لا يترتب)", it)]
        if not tasks and r:
            tasks = [(_short(x, 110), x, None) for x in _split_list(r["deliverables_text"])] or [(ph["name"], ph["name"], None)]
        ph["_tasks"] = tasks
    # a bullet-grouped scope without its own phase heading (for example a compliance section) joins the phase it names
    for m in re.finditer(r"((?:^|\n)\s*[•·▪]\s*[^\n:]{3,60}[:：]\s*\n(?:\s*\d+\s*[\.\-]\s*[^\n]+\n?)+)", d.text):
        pass
    blocks = list(re.finditer(r"^\s*[•·▪]\s*([^\n:：]{3,60})[:：]\s*\n((?:\s*\d+\s*[\.\-]\s*[^\n]+(?:\n(?!\s*\d+\s*[\.\-]|\s*[•·▪]|\s*المخرجات)[^\n]+)*\n?)+)", d.text, re.M))
    if blocks:
        target = next((p for p in phases if re.search(r"امتثال|compliance", p["name"], re.I)), None)
        if target:
            target["_tasks"] = []
            for b in blocks:
                its = [_clean_item(x) for x in re.split(r"\n\s*\d+\s*[\.\-]\s*", "\n" + b.group(2)) if _clean_item(x)]
                target["_tasks"].append((_short(b.group(1).strip() + ": " + (its[0] if its else "")), b.group(1).strip() + ": " + " / ".join(its), b.start()))
                for it in its:
                    reqs.append({"title": _short(it), "text": it, "page": d.page(b.start()), "priority": "must" if MUST.search(it) else "should", "phase": target["n"], "section": b.group(1).strip()})
    # technical platform spec items "1- يجب ..."
    m = re.search(r"المواصفات الفنية للمنصة\s*[:：](.*?)(?=\n\s*\d{1,3}\s+برنامج العمل|\Z)", d.text, re.S)
    if m:
        for it, off, k in _items(re.sub(r"(?m)^(\s*\d+)\s*-\s", r"\1. ", m.group(1)), m.start(1)):
            reqs.append({"title": _short(it), "text": it, "page": d.page(off), "priority": "must" if MUST.search(it) else "should", "phase": None, "section": "Platform specification"})
    # knowledge transfer and training clauses
    m = re.search(r"نقل المعرفة والتدريب\s*(.*?)(?=\n\s*\w+\s*[\.\-]\s*[^\n]{0,30}\n|\Z)", d.text, re.S)
    if m:
        for it, off, k in _items(m.group(1), m.start(1)):
            reqs.append({"title": _short(it), "text": it, "page": d.page(off), "priority": "must" if MUST.search(it) else "should", "phase": phases[-1]["n"] if phases else None, "section": "Knowledge transfer"})
    # tasks with hours, dates and the role they need
    for ph in phases:
        tasks = ph.pop("_tasks", None) or [(ph["name"], ph["name"], None)]
        weeks = max(1.0, ph["months"] * 4.33)
        pool = weeks * WEEK_H * FTE_DEFAULT
        each = max(16, int(round(pool / max(1, len(tasks)) / 4.0) * 4))
        for j, (nm, full, off) in enumerate(tasks, 1):
            acts.append({"code": f"P{ph['n']}-{j:02d}", "name": nm, "description": full, "phase": ph["n"], "planned_hours": float(each),
                         "start_month": ph["start_month"], "end_month": ph["end_month"], "role": role_for(full, roles),
                         "page": d.page(off) if off is not None else (ph["source_page"] or (acts[-1]["page"] if acts else None)), "estimate": True})
        ph["text"] = ph["_sec"]["body"][:6000] if ph.get("_sec") else (ph["_row"]["deliverables_text"] if ph.get("_row") else "")
        ph.pop("_sec", None)
        ph.pop("_row", None)
    risks = [{"title": t, "category": c, "probability": p, "impact": i, "response": rsp} for pat, t, c, p, i, rsp in RISK_RULES if re.search(pat, d.text, re.I)]
    comp = []
    for pat, fw, title in FRAMEWORKS:
        mm_ = re.search(pat, d.text)
        if mm_:
            comp.append({"framework": fw, "title": title, "page": d.page(mm_.start())})
    terms = parse_terms(d)
    for r_ in roles:
        r_["location"] = "hybrid" if re.search(r"هجين|hybrid", d.text) else None
    assumptions = [f"Hour estimates are a starting point: {FTE_DEFAULT:g} full-time people per phase spread over its tasks. Replace with real estimates before the baseline.",
                   "Dates are counted from contract signature; phases follow the work program in the book." if prog else "No work program table was found; phases are spread evenly over the project duration."]
    acc = [t for t in terms if t["kind"] == "acceptance"]
    if acc:
        assumptions.append("Client review and acceptance rules from the book apply to every deliverable (see terms).")
    return {"meta": meta, "objectives": objectives, "phases": phases, "requirements": _number(reqs), "deliverables": delivs, "activities": acts,
            "team": roles, "risks": risks, "compliance": comp, "terms": terms, "assumptions": assumptions}


def _number(reqs):
    seen, out = set(), []
    for r in reqs:
        key = re.sub(r"\W+", "", _norm_ar(r["text"]))[:80]
        if key in seen:
            continue
        seen.add(key)
        r["code"] = f"R-{len(out) + 1:03d}"
        out.append(r)
    return out


# ---------------- live model refinement (per phase) ----------------
def refine_prompt(phase_name: str, text: str, lang: str) -> str:
    L = "Arabic" if lang == "ar" else "English"
    return (f"You read one phase of a project book and plan its work. Reply in {L} with JSON only: "
            '{"tasks":[{"name":"...","hours":40,"role":"..."}],"requirements":["..."],"deliverables":["..."]}. '
            "Tasks are concrete work items (at most 15) with realistic hours; requirements are the obligations stated in the text, one sentence each; "
            f"deliverables are the documents or systems to hand over. Use only what the text says.\nPhase: {phase_name}\n<data>\n{text[:6000]}\n</data>")
