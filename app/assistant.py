"""In-app assistant. It answers only from data the asking user may already see (flow chart 4.1), in Arabic or English.
Rules answer the common questions without any model; when the Saudi-hosted model is live it phrases the answer from the same safe facts."""
import re
from datetime import date

from . import ai
from .models import Activity, Alert, Project, Risk, TimesheetEntry
from .routers.alerts import _visible
from .routers.projects import can_manage, can_view, can_view_cost

HOW = {
    "project": ("How to create a project", "كيف أنشئ مشروعاً", "Projects → New project. Fill the number and name, choose tendering or planning, then open the project.", "المشاريع ← مشروع جديد. أدخل الرقم والاسم واختر الطرح أو التخطيط ثم افتح المشروع.", "#/projects", ("PM", "PMO", "ADMIN")),
    "book": ("Upload the project book", "رفع كراسة المشروع", "Open the project → Project book. Choose or upload the file (PDF, Word, text or scan), press Analyse, review the draft, then Apply.", "افتح المشروع ← كراسة المشروع. اختر الملف أو ارفعه ثم اضغط تحليل وراجع المسودة ثم اعتمد.", "#/projects", ("PM", "PMO", "ADMIN")),
    "baseline": ("Lock the baseline", "اعتماد خط الأساس", "Open the project → Plan → Lock baseline. After this, staff can log hours on the activities.", "افتح المشروع ← الخطة ← اعتماد خط الأساس. بعدها يستطيع الموظفون تسجيل الساعات.", "#/projects", ("PM", "PMO", "ADMIN")),
    "hours": ("Log my hours", "تسجيل ساعاتي", "Timesheet → pick the day, project and activity, enter the hours, Save. At the end of the week press Submit week.", "سجل الساعات ← اختر اليوم والمشروع والنشاط وأدخل الساعات ثم احفظ. في نهاية الأسبوع اضغط إرسال الأسبوع.", "#/timesheet", ("STAFF", "PM", "PMO", "ADMIN")),
    "leave": ("Request leave", "طلب إجازة", "Leave → New request. Your line manager decides.", "الإجازات ← طلب جديد. يقرر مديرك المباشر.", "#/leave", None),
    "approve": ("Approve timesheets", "اعتماد الساعات", "Approvals → select entries → Approve, Reject (reason needed) or Adjust hours (reason needed).", "الاعتمادات ← حدد القيود ← اعتماد أو رفض أو تعديل الساعات (السبب مطلوب).", "#/approvals", ("PM", "PMO", "ADMIN", "STAFF")),
    "change": ("Raise a change request", "رفع طلب تغيير", "Project → Control → Change request. State the impact in hours, cost or days. A different person decides.", "المشروع ← التحكم ← طلب تغيير. اذكر الأثر بالساعات أو التكلفة أو الأيام. يقرر شخص آخر.", "#/projects", ("PM", "PMO", "ADMIN")),
    "close": ("Close a project", "إغلاق مشروع", "Project → Overview → move to closing, complete the closure checklist, then archive.", "المشروع ← نظرة عامة ← الانتقال للإغلاق وإكمال قائمة الإغلاق ثم الأرشفة.", "#/projects", ("PM", "PMO", "ADMIN")),
    "password": ("Change my password", "تغيير كلمة المرور", "Profile (top right) → Change password.", "الملف الشخصي (أعلى اليمين) ← تغيير كلمة المرور.", "#/profile", None),
}
KEYS = {
    "project": r"new project|create (a )?project|مشروع جديد|إنشاء مشروع|انشاء مشروع",
    "book": r"book|tender|rfp|upload|كراس|منافس",
    "baseline": r"baseline|lock|خط الأساس|خط الاساس|اعتماد الخطة",
    "hours": r"how (do|can|to).*(log|enter|record|fill).*(hours|time|timesheet)|كيف.*(أسجل|اسجل|تسجيل).*ساعات",
    "leave": r"leave|vacation|holiday|إجازة|اجازة",
    "approve": r"approv|اعتماد|الموافقة",
    "change": r"change request|طلب تغيير|تغيير",
    "close": r"clos(e|ing)|archive|إغلاق|اغلاق|أرشف",
    "password": r"password|كلمة المرور|كلمة السر",
}


def _ar(q: str) -> bool:
    return bool(re.search(r"[؀-ۿ]", q))


def visible_projects(db, user):
    return [p for p in db.query(Project).order_by(Project.id) if can_view(db, user, p)]


def _match_project(db, user, q: str):
    ql = q.lower()
    for p in visible_projects(db, user):
        if p.number.lower() in ql or (p.name and p.name.lower() in ql):
            return p
    return None


def ask(db, user, question: str, lang: str | None = None, project_id: int | None = None) -> dict:
    from .routers.timesheets import utilization
    from .routers.workflow import todo
    q = (question or "").strip()
    ar = (lang == "ar") or (lang is None and _ar(q))
    L = lambda en, a: a if ar else en
    out = {"answer": "", "links": [], "suggestions": [], "mode": ai.status()["mode"], "facts": {}}
    ql = q.lower()
    proj = _match_project(db, user, q)
    if not proj and project_id:
        p0 = db.get(Project, project_id)
        proj = p0 if p0 and can_view(db, user, p0) else None

    def link(label_en, label_ar, href):
        out["links"].append({"label": L(label_en, label_ar), "href": href})

    # how-to
    for key, rx in KEYS.items():
        if re.search(rx, ql) and re.search(r"how|كيف|where|أين|اين|steps|خطوات|can i|هل|ماذا أفعل|what do i", ql + " " + q):
            t_en, t_ar, b_en, b_ar, href, roles = HOW[key]
            if roles and user.role not in roles:
                out["answer"] = L(f"{t_en}: this is done by {', '.join(roles)}. Your role is {user.role}.", f"{t_ar}: يقوم بها {', '.join(roles)}. دورك هو {user.role}.")
            else:
                out["answer"] = L(f"{t_en}. {b_en}", f"{t_ar}. {b_ar}")
                link(t_en, t_ar, href)
            return _finish(out, user, L, ar)

    # project status (only projects the user may see)
    if proj and re.search(r"status|health|progress|how is|حالة|وضع|تقدم|كيف", ql + q):
        from .routers.dashboards import overall_pct, rag_status
        pct = overall_pct(db, proj, date.today())
        risks = db.query(Risk).filter(Risk.project_id == proj.id, Risk.status.in_(("open", "mitigating"))).count()
        al = [a for a in db.query(Alert).filter_by(project_id=proj.id, active=True) if _visible(db, user, a) and a.status not in ("closed", "dismissed")]
        crit = sum(1 for a in al if a.severity == "critical")
        rag = rag_status(db, proj) if (can_manage(db, user, proj) or user.role in ("PMO", "ADMIN", "DECISION_MAKER", "PROGRAM_MANAGER")) else None
        out["facts"] = {"project": proj.number, "state": proj.state, "progress_pct": pct, "open_risks": risks, "alerts": len(al), "critical_alerts": crit, "rag": rag}
        out["answer"] = L(f"{proj.number} {proj.name}: state {proj.state}, progress {pct:.0f}%, {risks} open risks, {len(al)} active alerts ({crit} critical)" + (f", health {rag}." if rag else "."),
                          f"{proj.number} {proj.name}: الحالة {proj.state}، التقدم {pct:.0f}%، {risks} مخاطر مفتوحة، {len(al)} تنبيهات نشطة ({crit} حرجة)" + (f"، الصحة {rag}." if rag else "."))
        link(f"Open {proj.number}", f"افتح {proj.number}", f"#/projects/{proj.id}")
        return _finish(out, user, L, ar)
    if not proj and re.search(r"project|مشروع|مشاريع", ql + q) and re.search(r"status|health|progress|حالة|تقدم", ql + q):
        pv = visible_projects(db, user)
        out["answer"] = L(f"You can see {len(pv)} project(s). Say which one by its number, for example: status of {pv[0].number}." if pv else "No project is visible to you yet.",
                          f"يمكنك رؤية {len(pv)} مشروع. اذكر رقم المشروع، مثال: حالة {pv[0].number}." if pv else "لا توجد مشاريع ظاهرة لك بعد.")
        out["suggestions"] = [L(f"Status of {p.number}", f"حالة {p.number}") for p in pv[:4]]
        return _finish(out, user, L, ar)

    # my hours
    if re.search(r"hours|timesheet|utili[sz]ation|capacity|ساعة|ساعات|ساعاتي|الدوام|سعة", ql + q) and not re.search(r"burn|حرق", ql):
        u = utilization(None, db=db, user=user)
        live = u["submitted"] + u["approved"]
        out["facts"] = {"week_hours": live, "capacity": u["capacity"], "remaining": u["remaining_capacity"], "pending": u["submitted"], "rejected": u["rejected"]}
        out["answer"] = L(f"This week you have {live:g} of {u['capacity']:g} hours ({u['utilization_pct']:g}%): {u['approved']:g} approved, {u['submitted']:g} waiting for approval, {u['rejected']:g} rejected. {u['remaining_capacity']:g} hours of capacity are left.",
                          f"هذا الأسبوع لديك {live:g} من {u['capacity']:g} ساعة ({u['utilization_pct']:g}%): {u['approved']:g} معتمدة و{u['submitted']:g} بانتظار الاعتماد و{u['rejected']:g} مرفوضة. المتبقي {u['remaining_capacity']:g} ساعة.")
        link("Open timesheet", "افتح سجل الساعات", "#/timesheet")
        return _finish(out, user, L, ar)

    # alerts
    if re.search(r"alert|warning|تنبيه|تنبيهات|تحذير", ql + q):
        al = [a for a in db.query(Alert).filter(Alert.active.is_(True)) if _visible(db, user, a) and a.status not in ("closed", "dismissed")]
        al.sort(key=lambda a: {"critical": 0, "warning": 1, "info": 2}[a.severity])
        out["facts"] = {"alerts": len(al), "critical": sum(1 for a in al if a.severity == "critical")}
        top = "; ".join(a.cause[:90] for a in al[:3])
        out["answer"] = L(f"{len(al)} active alert(s), {out['facts']['critical']} critical." + (f" Most urgent: {top}" if top else " Nothing needs attention."),
                          f"{len(al)} تنبيه نشط، {out['facts']['critical']} حرج." + (f" الأهم: {top}" if top else " لا شيء يحتاج انتباهاً."))
        link("Open alerts", "افتح التنبيهات", "#/alerts")
        return _finish(out, user, L, ar)

    # risks
    if re.search(r"risk|مخاطر|خطر", ql + q):
        rs = [r for r in db.query(Risk).filter(Risk.status.in_(("open", "mitigating"))) if (p := db.get(Project, r.project_id)) and can_view(db, user, p) and (user.role != "STAFF")]
        rs.sort(key=lambda r: -r.score)
        out["answer"] = L(f"{len(rs)} open risk(s)." + (" Highest: " + "; ".join(f"{r.title} (score {r.score})" for r in rs[:3]) if rs else ""),
                          f"{len(rs)} مخاطر مفتوحة." + (" الأعلى: " + "; ".join(f"{r.title} (الدرجة {r.score})" for r in rs[:3]) if rs else ""))
        link("Open dashboard", "افتح لوحة المعلومات", "#/dashboard")
        return _finish(out, user, L, ar)

    # activity burn (managers)
    if re.search(r"burn|over ?budget|hours used|حرق|استهلاك", ql + q) and user.role != "STAFF":
        rows = []
        for p in visible_projects(db, user):
            if not can_manage(db, user, p) and user.role not in ("PMO", "ADMIN"):
                continue
            for a in db.query(Activity).filter_by(project_id=p.id, phase="execution", locked=True):
                if not a.planned_hours:
                    continue
                used = sum(e.hours for e in db.query(TimesheetEntry).filter(TimesheetEntry.activity_id == a.id, TimesheetEntry.status.in_(("submitted", "approved"))))
                if used / a.planned_hours >= 0.8:
                    rows.append((used / a.planned_hours, p.number, a.code, used, a.planned_hours))
        rows.sort(reverse=True)
        out["answer"] = L(f"{len(rows)} task(s) have used 80% or more of their hours." + (" " + "; ".join(f"{r[1]} {r[2]} {r[3]:g}/{r[4]:g}h" for r in rows[:4]) if rows else ""),
                          f"{len(rows)} مهمة استهلكت 80% أو أكثر من ساعاتها." + (" " + "; ".join(f"{r[1]} {r[2]} {r[3]:g}/{r[4]:g}س" for r in rows[:4]) if rows else ""))
        return _finish(out, user, L, ar)

    # default: today
    t = todo(db=db, user=user)
    bits_en, bits_ar = [], []
    if t["rejected_entries"]:
        bits_en.append(f"{len(t['rejected_entries'])} rejected timesheet entr(ies) to fix"); bits_ar.append(f"{len(t['rejected_entries'])} قيد مرفوض يحتاج تصحيحاً")
    if t["approvals_waiting"]:
        bits_en.append(f"{t['approvals_waiting']} entr(ies) waiting for your approval"); bits_ar.append(f"{t['approvals_waiting']} قيد بانتظار اعتمادك")
    if t["week_due"]:
        bits_en.append(f"last week's timesheet is not submitted ({t['week_due']['missing_days']} day(s) missing)"); bits_ar.append(f"لم يُرسل سجل الأسبوع الماضي (ينقص {t['week_due']['missing_days']} يوم)")
    for k, en, a_ in (("alerts", "alert(s) assigned to you", "تنبيه مسند إليك"), ("risks", "risk(s) you own", "خطر تملكه"), ("issues", "issue(s) you own", "مشكلة تملكها"), ("actions", "action(s) due", "إجراء مطلوب")):
        if t[k]:
            bits_en.append(f"{len(t[k])} {en}"); bits_ar.append(f"{len(t[k])} {a_}")
    if t["leave_waiting"]:
        bits_en.append(f"{t['leave_waiting']} leave request(s) to decide"); bits_ar.append(f"{t['leave_waiting']} طلب إجازة للبت فيه")
    out["facts"] = {"todo_total": t["total"]}
    if bits_en:
        out["answer"] = L("Today: " + "; ".join(bits_en) + ".", "اليوم: " + "؛ ".join(bits_ar) + ".")
        link("Open my to-do", "افتح مهامي", "#/todo")
    else:
        out["answer"] = L("You are up to date. Nothing needs your attention right now.", "كل شيء محدث. لا يوجد ما يحتاج انتباهك الآن.")
    if not re.search(r"today|do|todo|to-do|اليوم|مهام|ماذا|what|أفعل", ql + q) and q:
        out["answer"] = L("I can help with your hours, approvals, alerts, risks, project status and how-to steps. ", "أستطيع مساعدتك في ساعاتك والاعتمادات والتنبيهات والمخاطر وحالة المشاريع وخطوات العمل. ") + out["answer"]
    return _finish(out, user, L, ar)


def _finish(out, user, L, ar):
    sug = [L("What should I do today?", "ماذا أفعل اليوم؟"), L("How many hours have I logged this week?", "كم ساعة سجلت هذا الأسبوع؟"), L("Any alerts?", "هل توجد تنبيهات؟")]
    if user.role in ("PM", "PMO", "ADMIN"):
        sug += [L("Which tasks are burning hours?", "أي المهام تستهلك الساعات؟"), L("How do I upload the project book?", "كيف أرفع كراسة المشروع؟")]
    elif user.role == "STAFF":
        sug += [L("How do I request leave?", "كيف أطلب إجازة؟")]
    else:
        sug += [L("Top risks", "أهم المخاطر")]
    out["suggestions"] = out["suggestions"] or sug[:4]
    # the model only rephrases the already-permitted answer; it never receives anything else
    if out["mode"] == "live":
        try:
            raw = ai._live("ask", {}, "Rewrite this answer for a busy project professional in {} in at most 3 short sentences, keeping every number. Reply JSON only {{\"text\":\"...\"}}.\n<data>\n{}\n</data>".format("Arabic" if ar else "English", out["answer"]))
            txt = ai.extract_json(raw).get("text")
            if isinstance(txt, str) and txt.strip():
                out["answer"] = txt.strip()
        except Exception:  # noqa: BLE001  the rule-based answer stands
            pass
    return out
