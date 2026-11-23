// Project intake: submit a business case; decision makers rank, decide, and approved proposals become projects.
import { api } from "../api.js";
import { decide, decisionList, outcomeBadge } from "../decide.js";
import { t } from "../i18n.js";
import { objectivePicker } from "../register.js";
import { bar, errorBox, field, guarded, h, modal, mount, num, table, toast } from "../ui.js";

const DECIDERS = ["DECISION_MAKER", "PMO", "ADMIN"];
const CAN_SUBMIT = ["PM", "PMO", "ADMIN", "PROGRAM_MANAGER"];

export default async function (root, { me }) {
  const canDecide = DECIDERS.includes(me.role);
  const scoreSel = (v = 3) => h("select", {}, [1, 2, 3, 4, 5].map(n => h("option", { value: n, selected: n === v }, String(n))));

  function open(x, render) {
    const mine = x.submitted_by === me.id;
    const editable = mine && ["submitted", "info_requested", "deferred"].includes(x.status);
    const resp = h("textarea", { rows: 3 }), err = h("div");
    const actions = [{ label: t("close"), class: "secondary", onClick: (c) => c() }];
    if (canDecide && !mine && ["submitted", "deferred"].includes(x.status))
      actions.push({ label: t("decide"), onClick: (c) => { c(); decide(`${x.number} · ${x.name}`, async (d) => { await api("POST", `/proposals/${x.id}/decision`, d); toast(t("saved")); await render(); }); } });
    if (editable && x.status !== "submitted")
      actions.push({ label: t("resubmit"), onClick: async (c) => { mount(err); try { await api("PATCH", `/proposals/${x.id}`, { response: resp.value.trim() || null }); toast(t("saved")); c(); await render(); } catch (e) { mount(err, errorBox(e)); } } });
    modal({ title: `${x.number} · ${x.name}`, body: h("div", { class: "prop" },
      h("p", {}, outcomeBadge(x.status), " ", `${t("score")}: ${x.score}/100 · ${t("submitted_by")}: ${x.submitted_by_name || ""}`),
      h("p", { class: "muted small" }, [x.sponsor && `${t("sponsor")}: ${x.sponsor}`, x.client && `${t("client")}: ${x.client}`, x.est_cost != null && `${t("est_cost")}: ${num(x.est_cost, 0)} ${x.currency}`, x.est_start && `${x.est_start} → ${x.est_end || "?"}`].filter(Boolean).join(" · ")),
      h("h3", {}, t("business_case")), h("p", { style: "white-space:pre-wrap" }, x.business_case),
      x.expected_benefits ? [h("h3", {}, t("expected_benefits")), h("p", { style: "white-space:pre-wrap" }, x.expected_benefits)] : null,
      h("p", { class: "small" }, `${t("strategic_fit")} ${x.strategic_fit} · ${t("value_score")} ${x.value} · ${t("urgency")} ${x.urgency} · ${t("risk_level")} ${x.risk_level}`),
      x.decisions.length ? [h("h3", {}, t("decision_history")), decisionList(x.decisions)] : null,
      x.project_id ? h("p", {}, h("a", { href: `#/projects/${x.project_id}` }, t("open_project"))) : null,
      editable && x.status !== "submitted" ? [h("h3", {}, t("your_response")), resp] : null, err),
      actions });
  }

  async function render() {
    const rows = await api("GET", "/proposals");
    const f = { num: h("input", { style: "width:120px" }), name: h("input", { style: "min-width:220px" }), bc: h("textarea", { rows: 4 }), ben: h("textarea", { rows: 2 }),
      sponsor: h("input"), client: h("input"), cost: h("input", { type: "number", min: "0", style: "width:130px" }), ccy: h("input", { value: "SAR", maxlength: "3", style: "width:70px" }),
      s: h("input", { type: "date" }), e: h("input", { type: "date" }), fit: scoreSel(), val: scoreSel(), urg: scoreSel(), risk: scoreSel() };
    const objs = (await api("GET", "/objectives")).filter(o => o.active).map(o => ({ id: o.id, code: o.code, name: o.name })), pick = objectivePicker(objs);
    const err = h("div"), btn = h("button", { class: "btn", type: "button" }, t("submit_proposal"));
    btn.addEventListener("click", guarded(btn, async () => {
      mount(err);
      try {
        const created = await api("POST", "/proposals", { number: f.num.value.trim(), name: f.name.value.trim(), business_case: f.bc.value.trim(), expected_benefits: f.ben.value.trim() || null,
          sponsor: f.sponsor.value.trim() || null, client: f.client.value.trim() || null, est_cost: f.cost.value ? Number(f.cost.value) : null, currency: f.ccy.value.toUpperCase(),
          est_start: f.s.value || null, est_end: f.e.value || null, strategic_fit: Number(f.fit.value), value: Number(f.val.value), urgency: Number(f.urg.value), risk_level: Number(f.risk.value) });
        if (pick.ids().length) await api("PUT", `/proposals/${created.id}/objectives`, { objective_ids: pick.ids() });
        toast(t("saved")); await render();
      } catch (e) { mount(err, errorBox(e)); }
    }));
    mount(root, h("h1", {}, t("nav_proposals")), h("p", { class: "muted" }, t("proposals_note")),
      h("div", { class: "card" }, h("h2", {}, canDecide ? t("ranked_proposals") : t("my_proposals")),
        table(["#", t("number"), t("name"), t("score"), t("est_cost"), t("submitted_by"), t("status"), ""],
          rows.map(x => [x.rank || "", x.number, x.name, h("div", { style: "min-width:90px" }, `${x.score}`, bar(x.score)), x.est_cost == null ? "—" : `${num(x.est_cost, 0)} ${x.currency}`,
            x.submitted_by_name || "", outcomeBadge(x.status), h("button", { class: "btn small secondary", type: "button", onClick: () => open(x, render) }, t("open"))]), t("none"))),
      CAN_SUBMIT.includes(me.role) ? h("div", { class: "card", id: "new-proposal" }, h("h2", {}, t("new_proposal")),
        h("div", { class: "row" }, field(t("number"), f.num), field(t("name"), f.name), field(t("sponsor"), f.sponsor), field(t("client"), f.client), field(t("est_cost"), f.cost), field(t("currency"), f.ccy), field(t("planned_start"), f.s), field(t("planned_end"), f.e)),
        field(t("business_case"), f.bc), field(t("expected_benefits"), f.ben),
        h("h3", {}, t("nav_strategy")), pick.node,
        h("p", { class: "muted small" }, t("scoring_note")),
        h("div", { class: "row" }, field(t("strategic_fit"), f.fit), field(t("value_score"), f.val), field(t("urgency"), f.urg), field(t("risk_level"), f.risk), btn), err) : null);
  }
  await render();
}
