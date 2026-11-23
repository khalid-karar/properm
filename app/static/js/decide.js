// One decision dialog for every governance decision (proposals, stage gates, change requests).
import { t } from "./i18n.js";
import { errorBox, field, h, modal, mount } from "./ui.js";

export const OUTCOMES = ["approve", "approve_conditions", "reject", "defer", "request_info"];

/** submit({outcome, rationale, conditions}) must return a promise; errors are shown in the dialog. */
export function decide(title, submit, { context } = {}) {
  const out = h("select", {}, OUTCOMES.map(o => h("option", { value: o }, t(`oc_${o}`))));
  const why = h("textarea", { rows: 3 }), cond = h("textarea", { rows: 2 }), err = h("div");
  const condWrap = field(t("conditions"), cond);
  const sync = () => { condWrap.style.display = out.value === "approve_conditions" ? "" : "none"; };
  out.addEventListener("change", sync); sync();
  modal({ title, body: h("div", {}, context || null, err, field(t("outcome"), out), field(t("rationale"), why), condWrap, h("p", { class: "muted small" }, t("decision_note"))),
    actions: [{ label: t("cancel"), class: "secondary", onClick: (c) => c() }, { label: t("record_decision"), onClick: async (c) => {
      mount(err);
      try { await submit({ outcome: out.value, rationale: why.value.trim() || null, conditions: cond.value.trim() || null }); c(); }
      catch (e) { mount(err, errorBox(e)); }
    } }] });
}

export const outcomeBadge = (status) => {
  const cls = { approved: "GREEN", approved_conditions: "GREEN", rejected: "RED", deferred: "AMBER", info_requested: "AMBER", submitted: "GREY", pending: "GREY", requested: "GREY" }[status] || "GREY";
  return h("span", { class: `badge ${cls}` }, t(`ps_${status}`));
};

export const decisionList = (recs) => recs.length ? h("ul", { class: "declog" }, recs.map(r => h("li", {},
  h("strong", {}, t(`oc_${r.outcome}`)), ` · ${r.decided_by || ""} · ${(r.decided_at || "").slice(0, 10)}`,
  r.rationale ? h("div", {}, r.rationale) : null, r.conditions ? h("div", { class: "muted" }, `${t("conditions")}: ${r.conditions}`) : null))) : null;
