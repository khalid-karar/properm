"""Arabic versions of the fixed template wording the plan generator writes.
Used when the source book is Arabic, so the whole plan reads in one language.
Pure Python, no model. Unknown strings pass through unchanged."""
import re

FIXED = {
    "Sponsor": "الراعي", "Day-to-day contact": "جهة التواصل اليومي", "Regulator": "جهة تنظيمية", "Team": "الفريق",
    "Approve deliverables, resolve escalations": "اعتماد المخرجات وحل التصعيدات",
    "Weekly review, deliverable acceptance": "مراجعة أسبوعية وقبول المخرجات",
    "Keep informed of compliance status; meet on request": "إبلاغها بحالة الامتثال والاجتماع عند الطلب",
    "Weekly planning": "التخطيط الأسبوعي", "Delivery team": "فريق التنفيذ", "Client project team": "فريق مشروع الجهة", "Client": "الجهة",
    "Sponsor / steering": "الراعي / اللجنة التوجيهية", "Status, risks, decisions needed": "الحالة والمخاطر والقرارات المطلوبة",
    "Report + meeting": "تقرير واجتماع", "Meeting": "اجتماع", "Progress, issues, next two weeks": "التقدم والمشكلات والأسبوعان القادمان",
    "Plan, priorities, timesheet reminders": "الخطة والأولويات وتذكير سجل الساعات", "Stand-up": "اجتماع قصير يومي",
    "Phase deliverables for acceptance": "مخرجات المرحلة للقبول", "Formal submission": "تسليم رسمي",
    "Follow the book's acceptance rule": "اتباع آلية القبول الواردة في الكراسة",
    "Check against the requirements list before the client sees it": "المطابقة مع قائمة المتطلبات قبل عرضها على الجهة",
    "Client written acceptance": "قبول كتابي من الجهة",
    "Estimated labour hours; price them with the rate card": "ساعات العمل المقدرة؛ تُسعَّر وفق جدول الأسعار",
    "Contingency reserve": "احتياطي الطوارئ", "10% of labour hours held back for unknowns": "10٪ من ساعات العمل محتجزة لما لا يمكن توقعه",
    "No payment schedule found in the book. Tie each payment to client acceptance of a phase deliverable.": "لم يرد جدول دفعات في الكراسة. اربط كل دفعة بقبول الجهة لمخرج مرحلة.",
    "Any change to scope, time or cost is raised as a change request, assessed for impact, and approved by the sponsor before work starts.": "أي تغيير في النطاق أو الوقت أو التكلفة يُرفع كطلب تغيير، ويُقيَّم أثره، ويعتمده الراعي قبل بدء العمل.",
    "Requirements from the book are the scope baseline; additions are tracked against it.": "متطلبات الكراسة هي خط أساس النطاق، وتُتابع أي إضافات مقابلها.",
    "Client approvals delay phase hand-over": "تأخر اعتماد الجهة يؤخر تسليم المراحل",
    "Agree review dates in the kick-off; chase approvals weekly; escalate to the sponsor after one missed review": "الاتفاق على مواعيد المراجعة في الاجتماع الافتتاحي، ومتابعة الاعتمادات أسبوعيًا، والتصعيد إلى الراعي بعد تفويت مراجعة واحدة",
    "Parallel phases compete for the same people": "المراحل المتوازية تتنافس على الأشخاص أنفسهم",
    "Confirm named staff for overlapping phases before baseline; watch load in the capacity plan": "تأكيد أسماء الموظفين للمراحل المتداخلة قبل خط الأساس، ومراقبة الحمل في خطة الطاقة",
    "Poor source data quality slows integration": "ضعف جودة البيانات المصدرية يبطئ التكامل",
    "Do the early data-quality analysis; agree remediation owners with the client": "إجراء تحليل مبكر لجودة البيانات والاتفاق مع الجهة على مسؤولي المعالجة",
    "Personal or sensitive data handled in non-production environments": "التعامل مع بيانات شخصية أو حساسة في بيئات غير الإنتاج",
    "Use masking or test data; apply the client's classification controls": "استخدام الإخفاء أو بيانات اختبار وتطبيق ضوابط التصنيف لدى الجهة",
    "Ready-made platform does not fit the client environment": "المنصة الجاهزة لا تناسب بيئة الجهة",
    "Run the fit and gap assessment in phase 1; record gaps as change items": "إجراء تقييم الملاءمة والفجوات في المرحلة الأولى وتسجيل الفجوات كطلبات تغيير",
    "Licences or dependencies not available when needed": "عدم توفر التراخيص أو الاعتمادات عند الحاجة",
    "List licences and responsibilities in phase 1; order early": "حصر التراخيص والمسؤوليات في المرحلة الأولى والطلب مبكرًا",
    "Source system owners are slow to give access or documentation": "تأخر ملاك الأنظمة المصدرية في منح الوصول أو التوثيق",
    "Name a client contact per system; request access at kick-off": "تسمية مسؤول لدى الجهة لكل نظام وطلب الوصول عند الانطلاق",
    "Client team not available for training and knowledge transfer": "عدم توفر فريق الجهة للتدريب ونقل المعرفة",
    "Fix the training calendar in the plan; get named attendees": "تثبيت جدول التدريب في الخطة والحصول على أسماء الحاضرين",
    "Contract penalties for missing deadlines": "غرامات العقد عند تفويت المواعيد",
    "Track delivery dates against the contract; raise change requests early": "متابعة مواعيد التسليم مقابل العقد ورفع طلبات التغيير مبكرًا",
    "Final guarantee and payment timing affect cash flow": "الضمان النهائي وتوقيت الدفعات يؤثران على التدفق النقدي",
    "Comply with the National Data Management Office controls that apply to the project": "الالتزام بضوابط مكتب إدارة البيانات الوطنية المنطبقة على المشروع",
    "Comply with the Personal Data Protection Law": "الالتزام بنظام حماية البيانات الشخصية",
    "Comply with the National Cybersecurity Authority controls that apply to the project": "الالتزام بضوابط الهيئة الوطنية للأمن السيبراني المنطبقة على المشروع",
    "Meet the local content and SME preference requirements": "تحقيق متطلبات المحتوى المحلي وأفضلية المنشآت الصغيرة والمتوسطة",
}
FIXED.update({
    "Agree review dates in the kick-off; chase approvals weekly; escalate to the sponsor after 5 working days": "الاتفاق على مواعيد المراجعة في الاجتماع الافتتاحي، ومتابعة الاعتمادات أسبوعيًا، والتصعيد إلى الراعي بعد 5 أيام عمل",
    "Plan guarantee issue before contract signature; match invoices to accepted deliverables": "التخطيط لإصدار الضمان قبل توقيع العقد، ومطابقة الفواتير مع المخرجات المقبولة",
    "Dates are counted from contract signature; phases follow the work program in the book.": "تُحسب التواريخ من توقيع العقد، وتتبع المراحل برنامج العمل الوارد في الكراسة.",
    "No work program table was found; phases are spread evenly over the project duration.": "لم يُعثر على جدول برنامج عمل؛ تُوزَّع المراحل بالتساوي على مدة المشروع.",
    "Client review and acceptance rules from the book apply to every deliverable (see terms).": "تنطبق قواعد المراجعة والقبول الواردة في الكراسة على كل مخرج (انظر الشروط).",
})
PATTERNS = [
    (r"^Hour estimates are a starting point: (\S+) full-time people per phase spread over its tasks\. Replace with real estimates before the baseline\.$", lambda m: f"تقديرات الساعات نقطة بداية: {m.group(1)} أشخاص بدوام كامل لكل مرحلة موزعين على مهامها. استبدلها بتقديرات حقيقية قبل خط الأساس."),
    (r"^(.+) authority$", lambda m: f"جهة {m.group(1)}"),
    (r"^Acceptance review: (.+)$", lambda m: f"مراجعة القبول: {m.group(1)}"),
    (r"^Internal quality audit before submitting: (.+)$", lambda m: f"تدقيق جودة داخلي قبل تسليم: {m.group(1)}"),
    (r"^Accepted in writing by the client \(book p\.(.+)\)$", lambda m: f"قبول كتابي من الجهة (الكراسة ص {m.group(1)})"),
    (r"^(.*) \(book p\.(.+)\)$", lambda m: f"{m.group(1)} (الكراسة ص {m.group(2)})"),
]


def ar(s):
    if not isinstance(s, str):
        return s
    if s in FIXED:
        return FIXED[s]
    for pat, fn in PATTERNS:
        m = re.match(pat, s)
        if m:
            return fn(m)
    return s


def ar_items(items, skip=("kind", "frequency")):
    return [{k: (v if k in skip else ar(v)) for k, v in it.items()} for it in items]
