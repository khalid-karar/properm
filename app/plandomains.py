"""Plan domains built from the project book: stakeholders, communication, quality, cost, procurement and payment terms, change control.
Rules-based (works offline). Each domain is a small list of items a reviewer can accept, edit or reject-and-regenerate with feedback."""
import difflib
import json
import re
from datetime import datetime, timezone

DOMAINS = ("stakeholders", "communication", "quality", "cost", "procurement", "change")
FIELDS = {
    "stakeholders": ("name", "organisation", "role", "power", "interest", "engagement"),
    "communication": ("audience", "information", "method", "frequency"),
    "quality": ("title", "kind", "note"),
    "cost": ("name", "hours", "note"),
    "procurement": ("kind", "text"),
    "change": ("text",),
}
FREQ = ("weekly", "biweekly", "monthly", "quarterly", "milestone", "ad_hoc")


def _ar(meta) -> bool:
    return (meta or {}).get("language") == "ar"


def _stakeholders(r, ar):
    client = "الجهة المتعاقدة" if ar else "Client"
    items = [{"name": client + (" – " if ar else " – ") + ("الراعي" if ar else "sponsor"), "organisation": client, "role": "Sponsor", "power": 5, "interest": 5, "engagement": "Approve deliverables, resolve escalations"},
             {"name": "Client project team" if not ar else "فريق مشروع الجهة", "organisation": client, "role": "Day-to-day contact", "power": 3, "interest": 5, "engagement": "Weekly review, deliverable acceptance"}]
    for fw in sorted({c["framework"] for c in r.get("compliance", [])}):
        items.append({"name": f"{fw} authority", "organisation": fw, "role": "Regulator", "power": 4, "interest": 2, "engagement": "Keep informed of compliance status; meet on request"})
    for t in r.get("team", [])[:6]:
        items.append({"name": t.get("title", "Team role"), "organisation": "Delivery team", "role": "Team", "power": 2, "interest": 5, "engagement": "Weekly planning"})
    return items


def _communication(r, ar):
    return [{"audience": "Sponsor / steering", "information": "Status, risks, decisions needed", "method": "Report + meeting", "frequency": "monthly"},
            {"audience": "Client project team", "information": "Progress, issues, next two weeks", "method": "Meeting", "frequency": "weekly"},
            {"audience": "Delivery team", "information": "Plan, priorities, timesheet reminders", "method": "Stand-up", "frequency": "weekly"},
            {"audience": "Client", "information": "Phase deliverables for acceptance", "method": "Formal submission", "frequency": "milestone"}]


def _quality(r, ar):
    items = [{"title": f"Acceptance review: {d['name'][:120]}", "kind": "inspection", "note": f"Accepted in writing by the client (book p.{d.get('page', '?')})" if d.get("page") else "Client written acceptance"} for d in r.get("deliverables", [])[:30]]
    for ph in r.get("phases", []):
        items.append({"title": f"Internal quality audit before submitting: {ph['name'][:120]}", "kind": "audit", "note": "Check against the requirements list before the client sees it"})
    for q in r.get("terms", []):
        if q.get("kind") == "acceptance":
            items.append({"title": "Follow the book's acceptance rule", "kind": "audit", "note": q["text"][:300]})
    return items


def _cost(r, ar):
    items, per_phase = [], {}
    for a in r.get("activities", []):
        per_phase[a["phase"]] = per_phase.get(a["phase"], 0) + float(a["planned_hours"])
    names = {p["n"]: p["name"] for p in r.get("phases", [])}
    for n, hrs in sorted(per_phase.items()):
        items.append({"name": names.get(n, f"Phase {n}"), "hours": round(hrs, 1), "note": "Estimated labour hours; price them with the rate card"})
    items.append({"name": "Contingency reserve", "hours": round(sum(per_phase.values()) * 0.1, 1), "note": "10% of labour hours held back for unknowns"})
    return items


def _procurement(r, ar):
    items = [{"kind": t["kind"], "text": f"{t['text']} (book p.{t.get('page', '?')})"} for t in r.get("terms", []) if t["kind"] in ("payment", "penalty", "guarantee", "tax")]
    if not any(i["kind"] == "payment" for i in items):
        items.append({"kind": "payment", "text": "No payment schedule found in the book. Tie each payment to client acceptance of a phase deliverable."})
    return items


def _change(r, ar):
    return [{"text": "Any change to scope, time or cost is raised as a change request, assessed for impact, and approved by the sponsor before work starts."},
            {"text": "Requirements from the book are the scope baseline; additions are tracked against it."}]


GEN = {"stakeholders": _stakeholders, "communication": _communication, "quality": _quality, "cost": _cost, "procurement": _procurement, "change": _change}


def _fresh(name, r):
    return {"status": "proposed", "items": GEN[name](r, _ar(r.get("meta"))), "history": []}


def generate(result: dict) -> dict:
    return {n: _fresh(n, result) for n in DOMAINS}


def _clean(name, items):
    out = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        row = {k: it.get(k) for k in FIELDS[name]}
        if not any(str(v or "").strip() for v in row.values()):
            continue
        for k in ("power", "interest"):
            if k in row:
                row[k] = max(1, min(5, int(row[k] or 3)))
        if "hours" in row:
            row["hours"] = max(0.0, float(row["hours"] or 0))
        if "frequency" in row and row["frequency"] not in FREQ:
            row["frequency"] = "monthly"
        if "kind" in row and name == "quality" and row["kind"] not in ("inspection", "audit", "test"):
            row["kind"] = "inspection"
        out.append({k: (v.strip()[:300] if isinstance(v, str) else v) for k, v in row.items()})
    return out


def diff(old, new) -> list[str]:
    a, b = json.dumps(old, ensure_ascii=False, indent=1).splitlines(), json.dumps(new, ensure_ascii=False, indent=1).splitlines()
    return [x for x in difflib.unified_diff(a, b, "before", "after", lineterm="", n=0) if not x.startswith(("---", "+++"))][:200]


def _stamp(dom, user_id, action, feedback=None, d=None):
    dom["history"].append({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "by": user_id, "action": action, "feedback": feedback, "diff": d or []})


def accept(dom, user_id):
    dom["status"] = "accepted" if dom["status"] != "modified" else "modified"
    _stamp(dom, user_id, "accept")


def modify(name, dom, items, user_id):
    new = _clean(name, items)
    d = diff(dom["items"], new)
    dom["items"], dom["status"] = new, "modified"
    _stamp(dom, user_id, "modify", None, d)


def reject(name, dom, result, feedback, user_id, model=None):
    """Regenerate. Rules produce the baseline; the reviewer's feedback is applied by the live model when there is one, otherwise kept as a visible note."""
    before = dom["items"]
    new = GEN[name](result, _ar(result.get("meta")))
    how = "rules"
    if model:
        try:
            got = model(name, before, feedback)
            cleaned = _clean(name, got)
            if cleaned:
                new, how = cleaned, "model"
        except Exception:
            pass
    if how == "rules" and feedback:
        f = {"stakeholders": "engagement", "communication": "information", "quality": "note", "cost": "note", "procurement": "text", "change": "text"}[name]
        key = {"stakeholders": "name", "communication": "audience", "quality": "title", "cost": "name", "procurement": "kind", "change": "text"}[name]
        note = {k: None for k in FIELDS[name]}
        note[key] = "Reviewer note" if name != "change" else f"Reviewer note: {feedback}"
        note[f] = feedback
        if name == "procurement":
            note["kind"] = "note"
        new = new + [_clean(name, [note])[0]] if _clean(name, [note]) else new
    d = diff(before, new)
    dom["items"], dom["status"] = new, "proposed"
    _stamp(dom, user_id, f"reject_regenerate:{how}", feedback, d)
    return how
