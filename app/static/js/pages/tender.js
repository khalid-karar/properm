// Project "Tender" tab: the bid stage. Go / no-go, estimate, capacity gap, compliance and risk review, submission checklist, result.
import { api } from "../api.js";
import { t } from "../i18n.js";
import { badge, errorBox, field, guarded, h, mount, num, stat, table, toast } from "../ui.js";

const CRIT = ["strategic_fit", "capability", "capacity", "margin", "client", "competition", "delivery_risk"];
const CHK = ["read_book", "clarifications", "technical", "financial", "guarantee", "forms", "pmo_review", "signed"];

export async function tenderTab(body, p, { pid, me, canManage, render }) {
  const x = await api("GET", `/projects/${pid}/tender`);
  const canDecide = ["PMO", "ADMIN", "DECISION_MAKER"].includes(me.role);
  const locked = !!x.submitted_at;
  const err = h("div", { id: "tn-err" });
  const save = async (patch) => { mount(err); try { await api("PATCH", `/projects/${pid}/tender`, patch); await render(); } catch (e) { mount(err, errorBox(e)); } };
  const act = (path, payload, msg) => guarded(null, async () => { mount(err); try { await api("POST", `/projects/${pid}/tender/${path}`, typeof payload === "function" ? payload() : payload); if (msg) toast(msg); await render(); } catch (e) { mount(err, errorBox(e)); } });

  // header
  const dl = h("input", { type: "date", id: "tn-deadline", value: x.deadline ? String(x.deadline).slice(0, 10) : "", disabled: !canManage || locked });
  dl.addEventListener("change", () => save({ deadline: dl.value || null }));
  const dtxt = x.days_to_deadline == null ? "—" : x.days_to_deadline < 0 ? `${-x.days_to_deadline} ${t("days_late")}` : `${x.days_to_deadline} ${t("days_left")}`;
  const head = h("div", { class: "grid", style: "margin-bottom:16px" }, stat(t("tn_deadline"), h("span", {}, dl, " ", h("small", { class: x.days_to_deadline != null && x.days_to_deadline < 3 ? "neg" : "muted" }, dtxt))),
    stat(t("tn_score"), x.scorecard.pct == null ? "—" : `${x.scorecard.pct}%`), stat(t("tn_decision"), t(`tn_d_${x.decision}`)), stat(t("tn_checklist"), `${x.checklist_done} / ${x.checklist_total}`));

  // scorecard
  const sel = (k, cur) => { const s = h("select", { id: `tn-sc-${k}`, "aria-label": t(`tn_c_${k}`), disabled: !canManage || locked }, h("option", { value: "" }, "—"), [1, 2, 3, 4, 5].map(n => h("option", { value: n, selected: cur === n }, n))); s.addEventListener("change", () => save({ scores: { [k]: { score: s.value ? Number(s.value) : null, note: (x.scorecard.criteria.find(c => c.key === k) || {}).note } } })); return s; };
  const note = (k, cur) => { const a = h("textarea", { rows: 1, dir: "auto", class: "ta", "aria-label": t(`tn_c_${k}`), disabled: !canManage || locked, style: "width:100%" }); a.value = cur || ""; a.addEventListener("change", () => save({ scores: { [k]: { score: (x.scorecard.criteria.find(c => c.key === k) || {}).score, note: a.value } } })); return a; };
  const dnote = h("textarea", { id: "tn-dnote", rows: 2, dir: "auto", class: "ta", style: "width:100%", placeholder: t("tn_dnote_ph") });
  const rec = x.scorecard.recommendation;
  const score = h("div", { class: "card", id: "tn-score" }, h("h2", {}, t("tn_gonogo")), h("p", { class: "muted small" }, t("tn_gonogo_note")),
    table([t("tn_criterion"), t("tn_weight"), t("tn_rating"), t("note")], x.scorecard.criteria.map(c => [t(`tn_c_${c.key}`), `${c.weight}`, sel(c.key, c.score), note(c.key, c.note)])),
    h("p", {}, rec ? [h("strong", {}, `${x.scorecard.pct}% `), badge(t(`tn_r_${rec}`), rec === "go" ? "GREEN" : rec === "review" ? "AMBER" : "RED"), h("span", { class: "muted small" }, ` ${t("tn_rule")}`)] : h("span", { class: "muted small" }, t("tn_incomplete"))),
    x.decision !== "open" ? h("p", {}, badge(t(`tn_d_${x.decision}`), x.decision === "go" ? "GREEN" : "RED"), ` ${x.decided_by || ""} ${x.decision_note || ""}`) : null,
    canDecide && !locked ? h("div", {}, dnote, h("div", { class: "row", style: "margin-top:8px" },
      h("button", { class: "btn", type: "button", id: "tn-go", onClick: act("decision", () => ({ decision: "go", note: dnote.value })) }, t("tn_decide_go")),
      h("button", { class: "btn secondary", type: "button", id: "tn-nogo", onClick: act("decision", () => ({ decision: "no_go", note: dnote.value })) }, t("tn_decide_nogo")))) : h("p", { class: "muted small" }, t("tn_who_decides")));

  // estimate
  const e = x.estimate;
  const margin = h("input", { type: "number", min: 0, max: 300, id: "tn-margin", value: e.margin_pct ?? 20, style: "width:90px", disabled: !canManage || locked });
  margin.addEventListener("change", () => save({ margin_pct: Number(margin.value) }));
  const est = h("div", { class: "card", id: "tn-estimate" }, h("h2", {}, t("tn_estimate")),
    e.available ? h("div", {}, h("div", { class: "grid" }, stat(t("planned_hours"), num(e.hours, 0)), stat(t("tn_rate"), e.blended_rate == null ? "—" : `${num(e.blended_rate, 0)} ${e.currency}`), stat(t("tn_cost"), e.cost == null ? "—" : `${num(e.cost, 0)} ${e.currency}`), stat(t("tn_price"), e.price == null ? "—" : `${num(e.price, 0)} ${e.currency}`)),
      e.rate_missing ? h("p", { class: "warn" }, t("tn_no_rates")) : null,
      h("div", { class: "row", style: "margin-top:8px" }, field(t("tn_margin"), margin)),
      table([t("role"), t("planned_hours")], e.by_role.map(r => [r.role, num(r.hours, 0)])), h("p", { class: "muted small" }, t("tn_est_note"))) : h("p", { class: "muted" }, e.reason));

  // capacity
  const cp = x.capacity;
  const cap = h("div", { class: "card", id: "tn-capacity" }, h("h2", {}, t("tn_capacity")),
    cp.available ? (cp.gaps.length ? h("div", {}, h("p", { class: "warn" }, `${cp.gaps.length} ${t("tn_gaps")} · ${num(cp.unassigned_hours, 0)} h ${t("brief_unassigned")}`), table([t("role"), t("brief_tasks"), t("planned_hours"), t("reason")], cp.gaps.map(g => [g.role, g.tasks, num(g.hours, 0), g.reason])))
      : h("p", {}, badge(t("tn_covered"), "GREEN"))) : h("p", { class: "muted" }, t("tn_need_draft")));

  // review
  const rv = x.review;
  const rev = h("div", { class: "card", id: "tn-review" }, h("h2", {}, t("tn_review")),
    rv.available ? h("div", {}, h("h3", {}, `${t("compliance")} · ${rv.compliance.length}`), rv.compliance.length ? h("ul", { class: "dashlist" }, rv.compliance.map(c => h("li", {}, h("span", {}, c.title), h("span", { class: "muted small" }, c.framework || "")))) : h("p", { class: "muted small" }, t("none")),
      h("h3", {}, t("top_risks")), rv.risks.length ? h("ul", { class: "dashlist" }, rv.risks.map(r => h("li", {}, h("span", {}, r.title), badge(r.score, r.score >= 20 ? "critical" : r.score >= 15 ? "warning" : "info")))) : h("p", { class: "muted small" }, t("none")),
      h("h3", {}, t("tn_terms")), rv.terms.length ? h("ul", { class: "dashlist" }, rv.terms.map(r => h("li", {}, h("span", {}, r.text), h("span", { class: "muted small" }, r.kind)))) : h("p", { class: "muted small" }, t("none"))) : h("p", { class: "muted" }, t("tn_need_draft")));

  // checklist
  const chk = h("div", { class: "card", id: "tn-checklist" }, h("h2", {}, t("tn_submission")),
    h("ul", { class: "checks" }, x.checklist.map(i => { const cb = h("input", { type: "checkbox", id: `tn-ck-${i.key}`, checked: i.done, disabled: !canManage || locked }); cb.addEventListener("change", () => save({ checklist: { [i.key]: { done: cb.checked, note: i.note } } })); return h("li", { class: i.done ? "ok" : "" }, h("label", {}, cb, ` ${t(`tn_k_${i.key}`)}`)); })),
    x.submitted_at ? h("p", {}, badge(t("tn_submitted"), "GREEN"), ` ${String(x.submitted_at).slice(0, 16).replace("T", " ")}`) : canManage ? h("button", { class: "btn", type: "button", id: "tn-submit", onClick: act("submit", null, t("tn_submitted")) }, t("tn_submit")) : null);

  // outcome
  const onote = h("textarea", { id: "tn-onote", rows: 2, dir: "auto", class: "ta", style: "width:100%", placeholder: t("tn_onote_ph") });
  const outc = canManage ? h("div", { class: "card", id: "tn-outcome" }, h("h2", {}, t("tn_outcome")), h("p", { class: "muted small" }, t("tn_outcome_note")), onote,
    h("div", { class: "row", style: "margin-top:8px" }, h("button", { class: "btn gold", type: "button", id: "tn-won", onClick: act("outcome", () => ({ outcome: "won", note: onote.value })) }, t("tn_won")),
      h("button", { class: "btn secondary", type: "button", id: "tn-lost", onClick: act("outcome", () => ({ outcome: "lost", note: onote.value })) }, t("tn_lost")))) : null;
  mount(body, head, err, score, est, cap, rev, chk, outc);
}
