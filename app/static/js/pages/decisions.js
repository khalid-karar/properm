// Decision queue: everything waiting on this person, in one list.
import { api } from "../api.js";
import { t } from "../i18n.js";
import { decide, outcomeBadge } from "../decide.js";
import { badge, guarded, h, mount, num, table, toast } from "../ui.js";

export default async function (root, { me }) {
  const render = async () => {
  const d = await api("GET", "/dashboards/decisions");
  const link = (pid, text) => h("a", { href: `#/projects/${pid}` }, text);
  const btn = (label, fn) => h("button", { class: "btn small", type: "button", onClick: guarded(null, fn) }, label);
  const done = async () => { toast(t("saved")); await render(); };
  const checks = (g) => h("ul", { class: "checks" }, g.checks.map(c => h("li", { class: c.ok ? "ok" : "bad" }, `${c.ok ? "✓" : "✗"} ${t(`gc_${c.key}`)}${c.detail ? ` (${c.detail})` : ""}`)));
  mount(root, h("h1", {}, `${t("nav_decisions")} `, d.total ? badge(d.total, "critical") : null),
    (d.proposals || []).length ? h("div", { class: "card", id: "dq-proposals" }, h("h2", {}, t("nav_proposals")),
      table([t("name"), t("score"), t("est_cost"), t("status"), ""], d.proposals.map(x => [x.title, x.score, x.est_cost == null ? "—" : `${num(x.est_cost, 0)} ${x.currency}`, outcomeBadge(x.status),
        h("span", { class: "row", style: "gap:6px" }, h("a", { class: "btn small secondary", href: "#/proposals" }, t("open")), btn(t("decide"), () => decide(x.title, async (v) => { await api("POST", `/proposals/${x.id}/decision`, v); await done(); })))]))) : null,
    (d.gates || []).length ? h("div", { class: "card", id: "dq-gates" }, h("h2", {}, t("stage_gates")),
      table([t("project"), t("gate"), t("checks"), t("note"), ""], d.gates.map(g => [h("a", { href: `#/projects/${g.project_id}` }, g.project), t(`gate_${g.gate}`), checks(g), g.note || "",
        btn(t("decide"), () => decide(`${g.project} · ${t(`gate_${g.gate}`)}`, async (v) => { await api("POST", `/projects/${g.project_id}/gates/${g.id}/decision`, v); await done(); }, { context: checks(g) }))]))) : null,
    d.total ? null : h("div", { class: "card" }, h("p", { class: "muted" }, t("nothing_pending"))),
    d.changes.length ? h("div", { class: "card" }, h("h2", {}, t("changes")),
      table([t("project"), t("change_type"), t("description"), t("cost_delta"), t("schedule_days"), ""], d.changes.map(c => [c.project, t(`ct_${c.type}`), c.title, num(c.cost_delta, 0), num(c.schedule_days, 0), h("span", { class: "row", style: "gap:6px" }, link(c.project_id, t("open")),
        btn(t("decide"), () => decide(c.title, async (v) => { await api("POST", `/projects/${c.project_id}/changes/${c.id}/decision`, { outcome: v.outcome, reason: v.rationale, conditions: v.conditions }); await done(); })))]))) : null,
    d.costs.length ? h("div", { class: "card" }, h("h2", {}, t("cost_approvals")),
      table([t("project"), t("category"), t("amount"), ""], d.costs.map(c => [c.project, c.title, `${num(c.amount, 0)} ${c.currency}`, link(c.project_id, t("open"))]))) : null,
    d.alerts.length ? h("div", { class: "card" }, h("h2", {}, t("critical_alerts")),
      table([t("project"), t("cause"), ""], d.alerts.map(a => [a.project, a.title, h("a", { href: "#/alerts" }, t("open"))]))) : null);
  };
  await render();
}
