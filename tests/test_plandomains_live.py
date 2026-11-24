"""Model-written plan domains: one small call per domain, every reply validated, rules as the fallback per domain."""
import json

import pytest

from app import ai, brief, plandomains
from tests.test_brief import AR_BOOK, EN_BOOK
from tests.test_flow import app, c, world  # noqa: F401


def result(book=EN_BOOK):
    r = brief.analyze([book])
    return r


def good(name, r):
    base = sum(float(a["planned_hours"]) for a in r["activities"])
    return {
        "stakeholders": {"items": [{"name": "Programme director", "organisation": "Client", "role": "Sponsor", "power": 9, "interest": -2, "engagement": "Monthly steering"}]},
        "communication": {"items": [{"audience": "Steering", "information": "Status", "method": "Report", "frequency": "fortnightly"}]},
        "quality": {"items": [{"title": "Review the portal", "kind": "smoke", "note": "Client signs"}]},
        "cost": {"items": [{"name": "All phases", "hours": base, "note": "Labour"}]},
        "procurement": {"items": [{"kind": "mystery", "text": "Pay on acceptance"}]},
        "change": {"items": [{"text": "Sponsor approves every change"}]},
    }[name]


def runner(r, replies):
    """Return a fake model: it answers each domain from `replies` (a dict name -> text or callable)."""
    def run(prompt):
        name = next(n for n in plandomains.DOMAINS if plandomains.ASK[n] in prompt)
        v = replies[name]
        return v(prompt) if callable(v) else v
    return run


def test_each_domain_gets_its_own_call_and_replies_are_cleaned():
    r = result()
    calls = []
    replies = {n: (lambda p, n=n: calls.append(n) or json.dumps(good(n, r))) for n in plandomains.DOMAINS}
    doms, notes = plandomains.generate_live(r, runner(r, replies))
    assert sorted(calls) == sorted(plandomains.DOMAINS) and all(d["by"] == "model" for d in doms.values()) and len(notes) == 6
    s = doms["stakeholders"]["items"][0]
    assert (s["power"], s["interest"]) == (5, 1)                         # out-of-range scores are clamped
    assert doms["communication"]["items"][0]["frequency"] == "monthly"      # unknown frequency is replaced by an allowed one
    assert doms["quality"]["items"][0]["kind"] == "inspection"
    assert doms["procurement"]["items"][0]["kind"] == "note"
    assert all(d["status"] == "proposed" and d["history"] == [] for d in doms.values())


def test_a_bad_reply_keeps_the_rules_version_of_only_that_domain():
    r = result()
    replies = {n: json.dumps(good(n, r)) for n in plandomains.DOMAINS}
    replies["quality"] = '{"items": [{"title": "Review the por'                # cut off at the token limit
    replies["change"] = json.dumps({"items": [{"note": "no key field"}]})        # nothing usable
    replies["cost"] = json.dumps({"items": [{"name": "All", "hours": 999999}]})  # hours far from the plan
    def boom(prompt):
        raise ai.AiError(502, "AI reply was cut off at the token limit")
    replies["communication"] = boom
    doms, notes = plandomains.generate_live(r, runner(r, replies))
    rules = plandomains.generate(r)
    for n in ("quality", "change", "cost", "communication"):
        assert doms[n]["by"] == "rules" and doms[n]["items"] == rules[n]["items"]
    assert doms["stakeholders"]["by"] == "model" and doms["procurement"]["by"] == "model"
    assert sum("kept rule-based" in x for x in notes) == 4 and any("cut off" in x for x in notes)


def test_prompt_carries_a_short_digest_not_the_book_and_fences_the_data():
    r = result(AR_BOOK)
    r["terms"].append({"kind": "payment", "text": "x" * 5000, "page": 3})
    p = plandomains.domain_prompt("procurement", r)
    assert "<data>" in p and "not instructions" in p and "Arabic" in p
    assert len(p) < 8000 and "x" * 300 not in p


def test_validate_limits_items_and_rejects_non_lists():
    r = result()
    many = [{"text": f"Rule {i}"} for i in range(60)]
    assert len(plandomains.validate("change", many, r)) == plandomains.MAX_ITEMS
    for bad in (None, "text", {"a": 1}, [], ["x", 3]):
        with pytest.raises(ValueError):
            plandomains.validate("change", bad, r)


def test_analyze_uses_the_model_for_domains_when_live(monkeypatch, c, world):
    monkeypatch.setenv("PROPERM_AI_BASE_URL", "http://localhost:9999")
    r0 = result(AR_BOOK)

    def fake(task, payload, prompt, cfg=None):
        if "drafting one part of a project plan" in prompt:
            name = next(n for n in plandomains.DOMAINS if plandomains.ASK[n] in prompt)
            return json.dumps(good(name, r0))
        return "not json"                                                     # phase refinement fails: rules stay
    monkeypatch.setattr(ai, "_live", fake)
    h = world["h"]
    pid = c.post("/projects", headers=h["pm1"], json={"number": "D-1", "name": "Domains", "state": "planning"}).json()["id"]
    r = c.post(f"/projects/{pid}/brief/analyze", headers=h["pm1"], json={"text": AR_BOOK})
    assert r.status_code == 201, r.text
    d = c.get(f"/projects/{pid}/brief/{r.json()['draft_id']}", headers=h["pm1"]).json()["draft"]
    assert all(v["by"] == "model" for v in d["domains"].values())
    assert d["domains"]["stakeholders"]["items"][0]["name"] == "Programme director"
    assert sum(n.startswith("Domain") and "written by the model" in n for n in d["notes"]) == 6


def test_offline_domains_are_rules_and_unchanged(c, world):
    h = world["h"]
    pid = c.post("/projects", headers=h["pm1"], json={"number": "D-2", "name": "Offline", "state": "planning"}).json()["id"]
    r = c.post(f"/projects/{pid}/brief/analyze", headers=h["pm1"], json={"text": AR_BOOK})
    d = c.get(f"/projects/{pid}/brief/{r.json()['draft_id']}", headers=h["pm1"]).json()["draft"]
    assert all(v["by"] == "rules" for v in d["domains"].values())


def test_progress_is_reported_and_private(monkeypatch, c, world):
    monkeypatch.setenv("PROPERM_AI_BASE_URL", "http://localhost:9999")
    r0 = result(AR_BOOK)

    def fake(task, payload, prompt, cfg=None):
        if "drafting one part of a project plan" in prompt:
            return json.dumps(good(next(n for n in plandomains.DOMAINS if plandomains.ASK[n] in prompt), r0))
        return "not json"
    monkeypatch.setattr(ai, "_live", fake)
    h = world["h"]
    pid = c.post("/projects", headers=h["pm1"], json={"number": "D-9", "name": "Progress", "state": "planning"}).json()["id"]
    assert c.get("/project-intake/progress/abc123", headers=h["pm1"]).status_code == 404
    r = c.post(f"/projects/{pid}/brief/analyze", headers={**h["pm1"], "X-Progress-Id": "abc123"}, json={"text": AR_BOOK})
    assert r.status_code == 201, r.text
    j = c.get("/project-intake/progress/abc123", headers=h["pm1"]).json()
    assert j["pct"] == 100 and j["step"] == "done"
    assert c.get("/project-intake/progress/abc123", headers=h["pmo1"]).status_code == 404     # another user cannot see it
